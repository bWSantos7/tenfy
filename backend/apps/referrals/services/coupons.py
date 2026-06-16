"""
Validação de cupom e cálculo de desconto (Fase 2 — Fluxo B do PRD).

Sem efeitos colaterais: só lê e calcula (RF-006, NFR < 2s). O incremento de uso
e a geração de comissão acontecem após o pagamento confirmado (Fase 3).
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.utils import timezone

from apps.referrals.models import Coupon, CommissionLedger, Partner

_CENTS = Decimal('0.01')


@dataclass
class CouponValidation:
    valid: bool
    reason: str = ''          # código: not_found, draft, inactive, expired, not_started,
                              #         partner_inactive, plan_not_allowed, exhausted, already_used
    message: str = ''         # mensagem amigável (PT) para o cliente
    coupon: Optional[Coupon] = field(default=None, repr=False)
    partner: Optional[Partner] = field(default=None, repr=False)
    original: Decimal = Decimal('0')
    discount: Decimal = Decimal('0')
    final: Decimal = Decimal('0')


def compute_discount(coupon: Coupon, price) -> Decimal:
    """Valor de desconto para o preço informado. Nunca maior que o preço."""
    price = Decimal(price or 0)
    if coupon.discount_type == Coupon.DISCOUNT_PERCENT:
        disc = price * Decimal(coupon.discount_value) / Decimal('100')
    else:
        disc = Decimal(coupon.discount_value)
    disc = min(disc, price)
    if disc < 0:
        disc = Decimal('0')
    return disc.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _invalid(reason: str, message: str, price: Decimal) -> CouponValidation:
    return CouponValidation(valid=False, reason=reason, message=message, original=price)


def validate_coupon(code: str, plan, billing_period: str, user=None) -> CouponValidation:
    """
    Valida um cupom para um plano/período/usuário e devolve original/desconto/final.

    RN-002 (ativo + vigência), RN-003 (plan_scope), §16 (parceiro inativo),
    limites de uso (RF-004) e uso por cliente.
    """
    price = Decimal(plan.price_for_period(billing_period) or 0).quantize(_CENTS)

    norm = (code or '').strip().upper()
    if not norm:
        return _invalid('not_found', 'Informe um cupom válido.', price)

    coupon = (
        Coupon.objects.select_related('partner')
        .filter(code=norm)
        .first()
    )
    if coupon is None:
        return _invalid('not_found', 'Cupom não encontrado.', price)

    partner = coupon.partner
    # §16 — cupom de parceiro inativo não pode ser usado
    if partner is None or not partner.is_active:
        return _invalid('partner_inactive', 'Este cupom não está disponível no momento.', price)

    # RN-002 — precisa estar ativo
    if coupon.status != Coupon.STATUS_ACTIVE:
        reason_map = {
            Coupon.STATUS_DRAFT:     ('draft', 'Cupom indisponível.'),
            Coupon.STATUS_INACTIVE:  ('inactive', 'Cupom indisponível.'),
            Coupon.STATUS_EXPIRED:   ('expired', 'Este cupom expirou.'),
            Coupon.STATUS_EXHAUSTED: ('exhausted', 'Este cupom atingiu o limite de uso.'),
        }
        reason, msg = reason_map.get(coupon.status, ('inactive', 'Cupom indisponível.'))
        return _invalid(reason, msg, price)

    # RN-002 — vigência
    now = timezone.now()
    if coupon.starts_at and now < coupon.starts_at:
        return _invalid('not_started', 'Este cupom ainda não está válido.', price)
    if coupon.expires_at and now > coupon.expires_at:
        return _invalid('expired', 'Este cupom expirou.', price)

    # RN-003 — restrição por plano
    if not coupon.scope_allows_plan(plan.slug):
        return _invalid('plan_not_allowed', 'Este cupom não vale para o plano escolhido.', price)

    # RF-004 — limite total de usos
    if coupon.max_total_uses and coupon.times_used >= coupon.max_total_uses:
        return _invalid('exhausted', 'Este cupom atingiu o limite de uso.', price)

    # Limite por cliente — conta resgates já confirmados (comissão não revertida/cancelada).
    if user is not None and coupon.max_uses_per_customer:
        used_by_customer = (
            CommissionLedger.objects
            .filter(coupon=coupon, subscription__user=user)
            .exclude(status__in=[CommissionLedger.STATUS_REVERSED, CommissionLedger.STATUS_CANCELED])
            .count()
        )
        if used_by_customer >= coupon.max_uses_per_customer:
            return _invalid('already_used', 'Você já utilizou este cupom.', price)

    discount = compute_discount(coupon, price)
    final = (price - discount).quantize(_CENTS)
    return CouponValidation(
        valid=True, coupon=coupon, partner=partner,
        original=price, discount=discount, final=final,
    )
