"""
Painel admin — programa de parceiros, cupons, comissões e repasses (Fase 4).

Acesso restrito ao master (IsSuperUser): dados financeiros sensíveis.
Endpoints sob /api/admin-panel/.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.core.permissions import IsSuperUser
from apps.referrals.models import CommissionLedger, CommissionRule, Coupon, Partner, Payout
from apps.referrals.serializers import (
    CommissionLedgerSerializer, CommissionRuleSerializer,
    CouponSerializer, PartnerSerializer, PayoutSerializer,
)

logger = logging.getLogger('apps.admin_panel')


def _audit(actor, action, entity_type, entity_id, *, diff=None, reason=''):
    try:
        AuditLog.objects.create(
            actor=actor, action=action, entity_type=entity_type,
            entity_id=str(entity_id), diff=diff or {}, reason=reason or '',
        )
    except Exception:  # noqa: BLE001
        logger.exception('Audit write failed (%s %s)', action, entity_type)


def _page_size(request, default=50, cap=200):
    try:
        return min(int(request.query_params.get('page_size', default)), cap)
    except (TypeError, ValueError):
        return default


# ── Parceiros ────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def partners(request):
    if request.method == 'GET':
        qs = Partner.objects.all().order_by('name')
        q = request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(name__icontains=q)
        st = request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        return Response({'count': qs.count(), 'results': PartnerSerializer(qs[:_page_size(request)], many=True).data})

    ser = PartnerSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    partner = ser.save()
    _audit(request.user, AuditLog.ACTION_CREATE, 'partner', partner.id, diff={'name': partner.name})
    return Response(PartnerSerializer(partner).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsSuperUser])
def partner_detail(request, pk):
    partner = Partner.objects.filter(pk=pk).first()
    if partner is None:
        return Response({'detail': 'Parceiro não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(PartnerSerializer(partner).data)
    if request.method == 'DELETE':
        # Protege histórico financeiro: não exclui parceiro com comissões/repasses.
        if CommissionLedger.objects.filter(partner=partner).exists() or Payout.objects.filter(partner=partner).exists():
            return Response(
                {'detail': 'Parceiro possui comissões ou repasses. Desative-o em vez de excluir (ou remova o histórico antes).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pid = partner.id
        partner.delete()  # cascata: cupons e regras do parceiro
        _audit(request.user, AuditLog.ACTION_DELETE, 'partner', pid)
        return Response(status=status.HTTP_204_NO_CONTENT)
    ser = PartnerSerializer(partner, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    _audit(request.user, AuditLog.ACTION_UPDATE, 'partner', partner.id, diff=request.data)
    return Response(PartnerSerializer(partner).data)


# ── Cupons ─────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def coupons(request):
    if request.method == 'GET':
        qs = Coupon.objects.select_related('partner').all().order_by('-created_at')
        partner_id = request.query_params.get('partner')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        st = request.query_params.get('status')
        if st:
            qs = qs.filter(status=st)
        q = request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(code__icontains=q.upper())
        return Response({'count': qs.count(), 'results': CouponSerializer(qs[:_page_size(request)], many=True).data})

    ser = CouponSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    coupon = ser.save()
    _audit(request.user, AuditLog.ACTION_CREATE, 'coupon', coupon.id, diff={'code': coupon.code})
    return Response(CouponSerializer(coupon).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsSuperUser])
def coupon_detail(request, pk):
    coupon = Coupon.objects.select_related('partner').filter(pk=pk).first()
    if coupon is None:
        return Response({'detail': 'Cupom não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(CouponSerializer(coupon).data)
    if request.method == 'DELETE':
        cid = coupon.id
        coupon.delete()  # regras do cupom em cascata; comissões/assinaturas mantêm histórico (FK vira NULL)
        _audit(request.user, AuditLog.ACTION_DELETE, 'coupon', cid)
        return Response(status=status.HTTP_204_NO_CONTENT)
    ser = CouponSerializer(coupon, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    _audit(request.user, AuditLog.ACTION_UPDATE, 'coupon', coupon.id, diff=request.data)
    return Response(CouponSerializer(coupon).data)


# ── Regras de comissão ───────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def commission_rules(request):
    if request.method == 'GET':
        qs = CommissionRule.objects.select_related('partner', 'coupon').all().order_by('-created_at')
        partner_id = request.query_params.get('partner')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        return Response({'count': qs.count(), 'results': CommissionRuleSerializer(qs[:_page_size(request)], many=True).data})

    ser = CommissionRuleSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    rule = ser.save()
    _audit(request.user, AuditLog.ACTION_CREATE, 'commission_rule', rule.id, diff=request.data)
    return Response(CommissionRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsSuperUser])
def commission_rule_detail(request, pk):
    rule = CommissionRule.objects.filter(pk=pk).first()
    if rule is None:
        return Response({'detail': 'Regra não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        rid = rule.id
        rule.delete()  # comissões já geradas mantêm histórico (FK da regra vira NULL)
        _audit(request.user, AuditLog.ACTION_DELETE, 'commission_rule', rid)
        return Response(status=status.HTTP_204_NO_CONTENT)
    ser = CommissionRuleSerializer(rule, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    _audit(request.user, AuditLog.ACTION_UPDATE, 'commission_rule', rule.id, diff=request.data)
    return Response(CommissionRuleSerializer(rule).data)


# ── Comissões (lançamentos) ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsSuperUser])
def commissions(request):
    """Lista comissões (RF-015). Filtros: partner, status."""
    qs = (
        CommissionLedger.objects
        .select_related('partner', 'coupon', 'subscription__user')
        .all().order_by('-created_at')
    )
    partner_id = request.query_params.get('partner')
    if partner_id:
        qs = qs.filter(partner_id=partner_id)
    st = request.query_params.get('status')
    if st:
        qs = qs.filter(status=st)
    return Response({'count': qs.count(), 'results': CommissionLedgerSerializer(qs[:_page_size(request)], many=True).data})


_VALID_COMMISSION_TRANSITIONS = {
    CommissionLedger.STATUS_PENDING:  {CommissionLedger.STATUS_APPROVED, CommissionLedger.STATUS_CANCELED},
    CommissionLedger.STATUS_APPROVED: {CommissionLedger.STATUS_CANCELED},
}


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def commission_detail(request, pk):
    """Aprovar ou cancelar uma comissão (transições controladas)."""
    led = CommissionLedger.objects.filter(pk=pk).first()
    if led is None:
        return Response({'detail': 'Comissão não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
    new_status = request.data.get('status')
    allowed = _VALID_COMMISSION_TRANSITIONS.get(led.status, set())
    if new_status not in allowed:
        return Response(
            {'detail': f'Transição inválida de {led.status} para {new_status}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    led.status = new_status
    led.save(update_fields=['status', 'updated_at'])
    _audit(request.user, AuditLog.ACTION_UPDATE, 'commission', led.id, diff={'status': new_status})
    return Response(CommissionLedgerSerializer(led).data)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def commissions_summary(request):
    """Consolida comissões por parceiro para fechamento (RF-016)."""
    rows = (
        CommissionLedger.objects
        .values('partner_id', 'partner__name')
        .annotate(
            total_count=Count('id'),
            pending_amount=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_PENDING)),
            approved_amount=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_APPROVED)),
            paid_amount=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_PAID)),
            reversed_amount=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_REVERSED)),
        )
        .order_by('partner__name')
    )
    result = []
    for r in rows:
        pending = r['pending_amount'] or Decimal('0')
        approved = r['approved_amount'] or Decimal('0')
        result.append({
            'partner_id':      r['partner_id'],
            'partner_name':    r['partner__name'],
            'total_count':     r['total_count'],
            'pending_amount':  str(pending),
            'approved_amount': str(approved),
            'paid_amount':     str(r['paid_amount'] or Decimal('0')),
            'reversed_amount': str(r['reversed_amount'] or Decimal('0')),
            'payable_amount':  str(pending + approved),  # a repassar
        })
    return Response({'count': len(result), 'results': result})


# ── Repasses (payouts) ───────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def payouts(request):
    if request.method == 'GET':
        qs = Payout.objects.select_related('partner').all().order_by('-created_at')
        partner_id = request.query_params.get('partner')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        return Response({'count': qs.count(), 'results': PayoutSerializer(qs[:_page_size(request)], many=True).data})

    # POST — registra repasse manual e marca as comissões como pagas (RF-017, Fluxo D).
    partner_id = request.data.get('partner')
    partner = Partner.objects.filter(pk=partner_id).first()
    if partner is None:
        return Response({'detail': 'Parceiro não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    commission_ids = request.data.get('commission_ids')
    qs = CommissionLedger.objects.filter(
        partner=partner,
        status__in=[CommissionLedger.STATUS_PENDING, CommissionLedger.STATUS_APPROVED],
    )
    if commission_ids:
        qs = qs.filter(id__in=commission_ids)

    with transaction.atomic():
        ledgers = list(qs.select_for_update())
        if not ledgers:
            return Response(
                {'detail': 'Nenhuma comissão a repassar para este parceiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        total = sum((l.commission_amount for l in ledgers), Decimal('0'))
        payout = Payout.objects.create(
            partner=partner,
            amount=total,
            status=Payout.STATUS_PAID,
            method=request.data.get('method', '') or '',
            reference=request.data.get('reference', '') or '',
            notes=request.data.get('notes', '') or '',
            paid_at=timezone.now(),
        )
        ids = [l.id for l in ledgers]
        CommissionLedger.objects.filter(id__in=ids).update(
            status=CommissionLedger.STATUS_PAID, payout=payout, updated_at=timezone.now(),
        )

    _audit(
        request.user, AuditLog.ACTION_UPDATE, 'payout', payout.id,
        diff={'partner': partner.id, 'amount': str(total), 'commissions': ids},
        reason='repasse manual',
    )
    return Response(PayoutSerializer(payout).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsSuperUser])
def payout_detail(request, pk):
    """Exclui um repasse: devolve as comissões pagas dele para 'aprovada' (a repassar)."""
    payout = Payout.objects.filter(pk=pk).first()
    if payout is None:
        return Response({'detail': 'Repasse não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    with transaction.atomic():
        reverted = CommissionLedger.objects.filter(
            payout=payout, status=CommissionLedger.STATUS_PAID,
        ).update(status=CommissionLedger.STATUS_APPROVED, payout=None, updated_at=timezone.now())
        pid = payout.id
        payout.delete()
    _audit(request.user, AuditLog.ACTION_DELETE, 'payout', pid, diff={'commissions_revertidas': reverted})
    return Response(status=status.HTTP_204_NO_CONTENT)
