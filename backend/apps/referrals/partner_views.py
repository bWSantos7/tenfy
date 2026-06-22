"""
Área exclusiva do parceiro (/api/partner/).

Cada parceiro autentica com uma conta User (role=partner) vinculada ao Partner
e enxerga SOMENTE os seus próprios dados. Todo queryset é filtrado por
``request.user.partner_account`` — nunca por parâmetro do cliente — garantindo o
isolamento entre parceiros e o bloqueio a dados administrativos.

Login reaproveita POST /api/auth/login/ (o token já carrega role).
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsPartnerUser

from .models import CommissionLedger, CommissionRule, Coupon
from .serializers import CommissionLedgerSerializer

# Lançamentos que representam valor real (excluem cancelados/revertidos).
_LIVE = [
    CommissionLedger.STATUS_PENDING,
    CommissionLedger.STATUS_APPROVED,
    CommissionLedger.STATUS_PAID,
]


def _partner(request):
    """Parceiro vinculado à conta autenticada (garantido pela IsPartnerUser)."""
    return request.user.partner_account


def _applicable_rule(partner, coupon):
    """Regra do cupom tem prioridade; senão, regra padrão do parceiro (igual ao service de comissão)."""
    rule = (
        CommissionRule.objects
        .filter(partner=partner, coupon=coupon, status=CommissionRule.STATUS_ACTIVE)
        .first()
    )
    if rule is None:
        rule = (
            CommissionRule.objects
            .filter(partner=partner, coupon__isnull=True, status=CommissionRule.STATUS_ACTIVE)
            .first()
        )
    return rule


def _rule_payload(rule):
    if rule is None:
        return None
    return {
        'commission_type':  rule.commission_type,
        'commission_value': str(rule.commission_value),
        'rule_scope':       rule.rule_scope,
        'base_amount_type': rule.base_amount_type,
    }


@api_view(['GET'])
@permission_classes([IsPartnerUser])
def partner_me(request):
    """Dados básicos do parceiro autenticado."""
    p = _partner(request)
    return Response({
        'id':          p.id,
        'name':        p.name,
        'type':        p.type,
        'status':      p.status,
        'login_email': request.user.email,
    })


@api_view(['GET'])
@permission_classes([IsPartnerUser])
def partner_dashboard(request):
    """KPIs do parceiro: receita gerada, comissões por status, conversões e cupons ativos."""
    p = _partner(request)

    agg = (
        CommissionLedger.objects
        .filter(partner=p)
        .aggregate(
            revenue_generated=Sum('base_amount', filter=Q(status__in=_LIVE)),
            commission_pending=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_PENDING)),
            commission_approved=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_APPROVED)),
            commission_paid=Sum('commission_amount', filter=Q(status=CommissionLedger.STATUS_PAID)),
            total_conversions=Count('id', filter=Q(status__in=_LIVE)),
        )
    )

    def _s(v):
        return str(v or Decimal('0'))

    pending = agg['commission_pending'] or Decimal('0')
    approved = agg['commission_approved'] or Decimal('0')
    return Response({
        'revenue_generated':    _s(agg['revenue_generated']),
        'commission_pending':   _s(pending),
        'commission_approved':  _s(approved),
        'commission_payable':   _s(pending + approved),   # a receber
        'commission_paid':      _s(agg['commission_paid']),
        'total_conversions':    agg['total_conversions'] or 0,
        'active_coupons':       Coupon.objects.filter(partner=p, status=Coupon.STATUS_ACTIVE).count(),
        'total_coupons':        Coupon.objects.filter(partner=p).count(),
    })


@api_view(['GET'])
@permission_classes([IsPartnerUser])
def partner_coupons(request):
    """Cupons do parceiro com regra, desconto, escopo, usos e conversões/receita por cupom."""
    p = _partner(request)
    coupons = Coupon.objects.filter(partner=p).order_by('-created_at')

    # Conversões e receita por cupom (1 query agregada).
    stats = {
        row['coupon_id']: row
        for row in (
            CommissionLedger.objects
            .filter(partner=p, coupon__isnull=False, status__in=_LIVE)
            .values('coupon_id')
            .annotate(conversions=Count('id'), revenue=Sum('base_amount'),
                      commission=Sum('commission_amount'))
        )
    }

    results = []
    for c in coupons:
        st = stats.get(c.id, {})
        results.append({
            'id':              c.id,
            'code':            c.code,
            'status':          c.status,
            'discount_type':   c.discount_type,
            'discount_value':  str(c.discount_value),
            'plan_scope':      c.plan_scope,
            'times_used':      c.times_used,
            'max_total_uses':  c.max_total_uses,
            'max_uses_per_customer': c.max_uses_per_customer,
            'starts_at':       c.starts_at,
            'expires_at':      c.expires_at,
            'rule':            _rule_payload(_applicable_rule(p, c)),
            'conversions':     st.get('conversions', 0),
            'revenue':         str(st.get('revenue') or Decimal('0')),
            'commission':      str(st.get('commission') or Decimal('0')),
        })
    return Response({'count': len(results), 'results': results})


@api_view(['GET'])
@permission_classes([IsPartnerUser])
def partner_usages(request):
    """Histórico de uso dos cupons (quem usou, quando, valor e comissão). Filtro opcional ?coupon=."""
    p = _partner(request)
    qs = (
        CommissionLedger.objects
        .select_related('coupon', 'subscription__user')
        .filter(partner=p)
        .order_by('-created_at')
    )
    coupon_id = request.query_params.get('coupon')
    if coupon_id:
        qs = qs.filter(coupon_id=coupon_id)
    return Response({
        'count': qs.count(),
        'results': CommissionLedgerSerializer(qs[:200], many=True).data,
    })
