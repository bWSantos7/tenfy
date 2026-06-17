"""
Materialização de cadastro pendente → conta real.

A conta em accounts.User só é criada aqui (quando o usuário entra de fato:
grátis/tester ao concluir; pago após pagamento confirmado).
"""
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger('apps.accounts')

CONSENT_VERSION = '1.0.0'


def materialize_pending(pending):
    """Cria (ou retorna, se já existir) o User a partir do PendingRegistration.
    A senha já vem com hash — usamos Manager.create (não re-hashea)."""
    U = get_user_model()
    existing = U.objects.filter(email__iexact=pending.email).first()
    if existing:
        return existing
    user = U.objects.create(
        email=pending.email,
        full_name=pending.full_name,
        phone=pending.phone,
        cpf=pending.cpf,
        role=pending.role or 'player',
        marketing_consent=pending.marketing_consent,
        email_verified=True,
        password=pending.password,  # já é hash
        consent_version=CONSENT_VERSION,
        consented_at=timezone.now(),
    )
    logger.info('Pending %s materialized → user %s', pending.token, user.id)
    return user


def ensure_subscription_for_pending(user, pending):
    """Garante a assinatura (pendente) do usuário com plano/cupom/parceiro do cadastro."""
    from apps.billing.models import Plan, Subscription
    from apps.referrals.models import Coupon

    plan = Plan.objects.filter(slug=pending.plan_slug, is_active=True).first()
    if plan is None:
        return None
    sub, _ = Subscription.objects.get_or_create(
        user=user,
        defaults={
            'plan': plan,
            'billing_period': pending.billing_period or 'monthly',
            'status': Subscription.STATUS_PENDING,
        },
    )
    sub.pending_plan = plan
    sub.pending_billing_period = pending.billing_period or 'monthly'
    if pending.asaas_customer_id and not sub.asaas_customer_id:
        sub.asaas_customer_id = pending.asaas_customer_id
    if pending.coupon_code:
        c = Coupon.objects.select_related('partner').filter(code=pending.coupon_code.strip().upper()).first()
        if c:
            sub.coupon = c
            sub.partner = c.partner
    sub.save()
    return sub


def materialize_full(pending):
    """Materializa usuário + assinatura e marca o pendente como consumido."""
    user = materialize_pending(pending)
    ensure_subscription_for_pending(user, pending)
    if not pending.consumed:
        pending.consumed = True
        pending.save(update_fields=['consumed', 'updated_at'])
    return user
