"""
Geração e reversão de comissão (Fase 3 — Fluxos C e estorno do PRD).

Regras:
  - Só gera comissão se a assinatura tem parceiro + cupom (RN-005).
  - Só no 1º pagamento confirmado (RN-010).
  - Base = valor líquido pago quando a regra pede net (RN-006).
  - 1 comissão por pagamento (RF-013): unique em CommissionLedger.payment +
    guarda explícita por assinatura.
  - Estorno reverte a comissão (RF-014/RN-009).

Deve ser chamado de dentro da transação do webhook (transaction.atomic).
"""
import logging
from decimal import Decimal

from apps.referrals.models import CommissionLedger, CommissionRule, Coupon

logger = logging.getLogger('apps.referrals')


def _applicable_rule(partner, coupon):
    """Regra do cupom tem prioridade; senão, regra padrão do parceiro."""
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


def generate_commission_for_payment(payment, subscription):
    """
    Cria o lançamento de comissão (status pending) para o 1º pagamento confirmado
    de uma assinatura com cupom. Idempotente. Retorna o CommissionLedger ou None.
    """
    if payment is None or subscription is None:
        return None
    # RN-005 — sem cupom/parceiro não há comissão
    if not subscription.partner_id or not subscription.coupon_id:
        return None

    # RF-013 — idempotência: este pagamento já gerou comissão
    if CommissionLedger.objects.filter(payment=payment).exists():
        logger.info('Commission already exists for payment %s — skipping', payment.id)
        return None

    # RN-010 — só no 1º pagamento: assinatura já tem comissão (não cancelada)
    if (
        CommissionLedger.objects
        .filter(subscription=subscription)
        .exclude(status=CommissionLedger.STATUS_CANCELED)
        .exists()
    ):
        logger.info('Subscription %s already has a commission — not first payment, skipping', subscription.id)
        return None

    rule = _applicable_rule(subscription.partner, subscription.coupon)
    if rule is None:
        logger.warning(
            'No active commission rule for partner=%s coupon=%s — commission not generated',
            subscription.partner_id, subscription.coupon_id,
        )
        return None

    # RN-006 — base = valor líquido pago quando a regra pedir net
    if rule.base_amount_type == CommissionRule.BASE_NET and payment.paid_net_amount is not None:
        base = Decimal(payment.paid_net_amount)
    else:
        base = Decimal(payment.amount)

    commission_amount = rule.compute(base)

    ledger = CommissionLedger.objects.create(
        partner=subscription.partner,
        coupon=subscription.coupon,
        subscription=subscription,
        payment=payment,
        commission_rule=rule,
        base_amount=base,
        commission_amount=commission_amount,
        status=CommissionLedger.STATUS_PENDING,
    )

    # Resgate confirmado — incrementa uso do cupom (e marca esgotado se atingiu o limite).
    coupon = subscription.coupon
    coupon.times_used = (coupon.times_used or 0) + 1
    fields = ['times_used', 'updated_at']
    if coupon.max_total_uses and coupon.times_used >= coupon.max_total_uses:
        coupon.status = Coupon.STATUS_EXHAUSTED
        fields.append('status')
    coupon.save(update_fields=fields)

    logger.info(
        'Commission %s generated: partner=%s amount=%s base=%s payment=%s',
        ledger.id, subscription.partner_id, commission_amount, base, payment.id,
    )
    return ledger


def reverse_commission_for_payment(payment):
    """
    Reverte a comissão associada a um pagamento estornado (RF-014/RN-009).
    Retorna o CommissionLedger revertido ou None.
    """
    if payment is None:
        return None
    ledger = (
        CommissionLedger.objects
        .filter(payment=payment)
        .exclude(status__in=[CommissionLedger.STATUS_REVERSED, CommissionLedger.STATUS_CANCELED])
        .first()
    )
    if ledger is None:
        return None

    was_paid = ledger.status == CommissionLedger.STATUS_PAID
    ledger.status = CommissionLedger.STATUS_REVERSED
    ledger.save(update_fields=['status', 'updated_at'])
    if was_paid:
        logger.warning(
            'Commission %s was already PAID but reversed due to refund — financial follow-up needed',
            ledger.id,
        )

    # Desfaz o resgate no cupom.
    if ledger.coupon_id:
        coupon = ledger.coupon
        if coupon.times_used and coupon.times_used > 0:
            coupon.times_used -= 1
            fields = ['times_used', 'updated_at']
            if coupon.status == Coupon.STATUS_EXHAUSTED and (
                not coupon.max_total_uses or coupon.times_used < coupon.max_total_uses
            ):
                coupon.status = Coupon.STATUS_ACTIVE
                fields.append('status')
            coupon.save(update_fields=fields)

    logger.info('Commission %s reversed for refunded payment %s', ledger.id, payment.id)
    return ledger
