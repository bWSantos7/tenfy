"""
Billing API views.

Endpoints:
  GET  /api/billing/plans/                  — list all active plans with features
  GET  /api/billing/subscription/           — current user's subscription
  POST /api/billing/subscription/checkout/  — subscribe / upgrade
  POST /api/billing/subscription/cancel/    — cancel subscription
  POST /api/billing/subscription/reactivate/— re-activate before period ends
  GET  /api/billing/payments/               — payment history
  GET  /api/billing/features/               — check accessible features
  POST /api/billing/webhooks/asaas/         — Asaas webhook receiver
"""
import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

# PCI-DSS: fields that must never be persisted from Asaas payment responses
_SENSITIVE_PAYMENT_FIELDS = frozenset({
    'creditCard', 'card', 'cardNumber', 'holderName', 'expiryMonth',
    'expiryYear', 'ccv', 'cvv', 'creditCardToken',
})

# Valid subscription status transitions (state machine) — uses string values directly
_VALID_TRANSITIONS: dict[str, set] = {
    'pending':  {'active', 'canceled', 'unpaid'},
    'active':   {'unpaid', 'expired', 'canceled'},
    'unpaid':   {'active', 'canceled'},
    'expired':  {'active', 'canceled'},
    'trial':    {'active', 'canceled', 'expired'},
    'canceled': set(),  # terminal — no transitions out
}

from apps.audit.models import AuditLog
from .models import FamilyMembership, Feature, Payment, Plan, Subscription, WebhookEvent
from .serializers import (
    CancelSubscriptionSerializer,
    CheckoutSerializer,
    FamilyMemberAddSerializer,
    FamilyMembershipSerializer,
    PaymentSerializer,
    PlanSerializer,
    SubscriptionSerializer,
)

logger = logging.getLogger('apps.billing')


class WebhookThrottle(AnonRateThrottle):
    """Dedicated rate limit for the Asaas webhook endpoint."""
    scope = 'webhook'


# ── Plans (public) ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def plans_list(request):
    """Return all active plans with their feature matrix."""
    qs = Plan.objects.filter(is_active=True).prefetch_related('plan_features__feature')
    return Response(PlanSerializer(qs, many=True).data)


# ── Current subscription ───────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def subscription_detail(request):
    """Return the authenticated user's subscription. Returns 404 if none exists (no auto-create)."""
    try:
        sub = request.user.subscription
        return Response(SubscriptionSerializer(sub).data)
    except Subscription.DoesNotExist:
        return Response({'has_subscription': False}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def subscription_checkout(request):
    """
    Subscribe to a plan or upgrade/downgrade.

    When ASAAS_API_KEY is configured, this creates a real Asaas subscription.
    Without API key, the subscription is created locally in pending state —
    useful for testing the full flow before payment goes live.
    """
    ser = CheckoutSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data

    try:
        plan = Plan.objects.get(slug=d['plan_slug'], is_active=True)
    except Plan.DoesNotExist:
        return Response({'detail': 'Plano não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    # Programa de parceiros — valida cupom (se informado) antes do gate (Fluxo B).
    coupon_validation = None
    if d.get('coupon_code', '').strip():
        from apps.referrals.services.coupons import validate_coupon
        coupon_validation = validate_coupon(d['coupon_code'], plan, d['billing_period'], request.user)
    has_valid_coupon = bool(coupon_validation and coupon_validation.valid)

    # Planos pagos ficam invisíveis ao público; o checkout pago só é liberado para
    # contas de teste (TESTING) ou quando há um cupom válido (acesso controlado).
    _PAID_PLANS = {'individual', 'familia'}
    if plan.slug in _PAID_PLANS and not getattr(settings, 'TESTING', False) and not has_valid_coupon:
        return Response(
            {'detail': 'Este plano está disponível apenas com um cupom válido no momento.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        is_tester = plan.slug == Plan.SLUG_TESTER

        sub, created = Subscription.objects.get_or_create(
            user=request.user,
            defaults={
                'plan': plan,
                'billing_period': d['billing_period'],
                'status': Subscription.STATUS_ACTIVE if is_tester else Subscription.STATUS_PENDING,
                'start_date': date.today(),
            },
        )

        asaas_result = None
        pix_qr = None

        # Programa de parceiros — vincula cupom/parceiro à assinatura (RN-004).
        discount_amount = coupon_validation.discount if has_valid_coupon else Decimal('0')
        if has_valid_coupon:
            sub.partner = coupon_validation.partner
            sub.coupon = coupon_validation.coupon
            sub.save(update_fields=['partner', 'coupon', 'updated_at'])

        if is_tester:
            # Tester plan: activate immediately — no payment required
            sub.plan = plan
            sub.status = Subscription.STATUS_ACTIVE
            sub.pending_plan = None
            sub.pending_billing_period = ''
            sub.cancel_at_period_end = False
            sub.save(update_fields=['plan', 'status', 'pending_plan', 'pending_billing_period', 'cancel_at_period_end', 'updated_at'])
        else:
            # Track pending plan; activated via PAYMENT_CONFIRMED webhook
            sub.pending_plan = plan
            sub.pending_billing_period = d['billing_period']
            sub.cancel_at_period_end = False
            sub.save(update_fields=['pending_plan', 'pending_billing_period', 'cancel_at_period_end', 'updated_at'])
            try:
                from .services.asaas_service import (
                    create_subscription, create_subscription_with_first_discount,
                    get_subscription_first_pix_qr, get_pix_qr_code, AsaasNotConfiguredError,
                )
                payment_method_map = {
                    'credit_card': 'CREDIT_CARD',
                    'pix': 'PIX',
                    'boleto': 'BOLETO',
                    'debit_card': 'DEBIT_CARD',
                }
                method = payment_method_map[d['payment_method']]
                # PCI-DSS: only card_token accepted — raw card data is tokenized
                # client-side by the mobile app directly with Asaas.
                if discount_amount and discount_amount > 0:
                    # Com cupom: 1ª cobrança avulsa descontada + recorrência cheia.
                    combo = create_subscription_with_first_discount(
                        user=request.user,
                        plan=plan,
                        billing_period=d['billing_period'],
                        payment_method=method,
                        discount_amount=discount_amount,
                        card_token=d.get('card_token', ''),
                    )
                    asaas_result = combo['subscription']
                    first_payment = combo.get('first_payment') or {}
                    sub.asaas_subscription_id = asaas_result.get('id', '')
                    sub.save(update_fields=['asaas_subscription_id', 'updated_at'])
                    logger.info('Asaas subscription %s (cupom) created for user %s', sub.asaas_subscription_id, request.user.id)
                    # Pix: QR vem da cobrança avulsa (1º pagamento descontado)
                    if d['payment_method'] == 'pix' and first_payment.get('id'):
                        pix_qr = get_pix_qr_code(first_payment['id'])
                else:
                    asaas_result = create_subscription(
                        user=request.user,
                        plan=plan,
                        billing_period=d['billing_period'],
                        payment_method=method,
                        card_token=d.get('card_token', ''),
                    )
                    sub.asaas_subscription_id = asaas_result.get('id', '')
                    sub.save(update_fields=['asaas_subscription_id', 'updated_at'])
                    logger.info('Asaas subscription %s created for user %s', sub.asaas_subscription_id, request.user.id)

                    # For Pix: fetch QR code from first pending payment
                    if d['payment_method'] == 'pix' and sub.asaas_subscription_id:
                        pix_qr = get_subscription_first_pix_qr(sub.asaas_subscription_id)

            except Exception as exc:  # AsaasNotConfiguredError or network error
                logger.warning('Asaas not available (%s); subscription created locally.', exc)

        _log_action(request.user, 'billing.checkout', f'Checkout plan={plan.slug} method={d["payment_method"]}')

    resp_data = SubscriptionSerializer(sub).data
    if asaas_result:
        # Only expose safe fields — never raw card data or internal Asaas tokens
        resp_data['asaas'] = {
            k: v for k, v in asaas_result.items()
            if k not in _SENSITIVE_PAYMENT_FIELDS
            and k not in ('creditCardToken', 'token', 'accessToken')
        }
    if pix_qr:
        resp_data['pix'] = {
            'qr_code_image': pix_qr.get('encodedImage', ''),
            'copia_e_cola':  pix_qr.get('payload', ''),
            'expiration':    pix_qr.get('expirationDate', ''),
        }
    if coupon_validation is not None:
        resp_data['coupon'] = {
            'applied':  has_valid_coupon,
            'code':     d['coupon_code'].strip().upper(),
            'original': str(coupon_validation.original),
            'discount': str(coupon_validation.discount),
            'final':    str(coupon_validation.final),
        }
        if not has_valid_coupon:
            resp_data['coupon']['reason'] = coupon_validation.reason
            resp_data['coupon']['detail'] = coupon_validation.message
    return Response(resp_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def checkout_validate_coupon(request):
    """
    Valida um cupom para um plano/período e retorna valor original, desconto e
    valor final (RF-006/RF-007). Sem efeitos colaterais (NFR < 2s).
    POST /api/billing/checkout/validate-coupon/
    Body: {coupon_code, plan_slug, billing_period}
    """
    code = (request.data.get('coupon_code') or request.data.get('code') or '').strip()
    plan_slug = request.data.get('plan_slug')
    billing_period = request.data.get('billing_period', 'monthly')
    if not code:
        return Response({'valid': False, 'detail': 'Informe um cupom.'}, status=status.HTTP_400_BAD_REQUEST)

    plan = Plan.objects.filter(slug=plan_slug, is_active=True).first()
    if plan is None:
        return Response({'detail': 'Plano não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    from apps.referrals.services.coupons import validate_coupon
    result = validate_coupon(code, plan, billing_period, request.user)
    payload = {
        'valid':    result.valid,
        'code':     code.upper(),
        'original': str(result.original),
        'discount': str(result.discount),
        'final':    str(result.final),
    }
    if not result.valid:
        payload['reason'] = result.reason
        payload['detail'] = result.message
    return Response(payload)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def subscription_cancel(request):
    """Cancel the user's subscription."""
    ser = CancelSubscriptionSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    immediate = ser.validated_data['immediate']

    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'detail': 'Nenhuma assinatura ativa.'}, status=status.HTTP_404_NOT_FOUND)

    if sub.status == Subscription.STATUS_CANCELED:
        return Response({'detail': 'Assinatura já cancelada.'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        if immediate:
            if sub.asaas_subscription_id:
                try:
                    from .services.asaas_service import cancel_subscription
                    cancel_subscription(sub.asaas_subscription_id)
                except Exception as exc:
                    logger.warning('Asaas cancel failed: %s', exc)

            sub.status = Subscription.STATUS_CANCELED
            sub.canceled_at = timezone.now()
            sub.save(update_fields=['status', 'canceled_at', 'updated_at'])
        else:
            sub.cancel_at_period_end = True
            sub.save(update_fields=['cancel_at_period_end', 'updated_at'])

    _log_action(request.user, 'billing.cancel', f'immediate={immediate}')
    return Response(SubscriptionSerializer(sub).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def subscription_reactivate(request):
    """Remove cancel_at_period_end flag (keep subscription alive)."""
    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'detail': 'Nenhuma assinatura encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    if sub.status == Subscription.STATUS_CANCELED:
        return Response({'detail': 'Assinatura já cancelada definitivamente. Faça uma nova assinatura.'}, status=status.HTTP_400_BAD_REQUEST)

    sub.cancel_at_period_end = False
    sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
    _log_action(request.user, 'billing.reactivate', '')
    return Response(SubscriptionSerializer(sub).data)


# ── Payment history ────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def payment_history(request):
    """Return the user's payment history (last 50)."""
    qs = Payment.objects.filter(user=request.user).order_by('-created_at')[:50]
    return Response(PaymentSerializer(qs, many=True).data)


# ── Feature access map ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_features(request):
    """
    Return a map of all features with their access status and limit for the current user.
    Cached per user — invalidated on subscription changes.
    """
    from django.core.cache import cache as _cache
    from .permissions import user_has_feature, user_feature_limit, _user_features_cache_key

    cache_key = f'my_features:{request.user.id}'
    cached = _cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    features = Feature.objects.all()
    result = {}
    for f in features:
        result[f.code] = {
            'has_access': user_has_feature(request.user, f.code),
            'limit': user_feature_limit(request.user, f.code),
            'name': f.name,
        }
    _cache.set(cache_key, result, 300)
    return Response(result)


# ── Asaas Webhook ──────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def asaas_webhook_status(request):
    """
    Staff-only diagnostic: confirms whether ASAAS_WEBHOOK_TOKEN is configured.
    Never returns the token value — only presence and length.
    GET /api/billing/webhooks/asaas/status/
    """
    token = getattr(settings, 'ASAAS_WEBHOOK_TOKEN', '').strip()
    return Response({
        'token_configured': bool(token),
        'token_length':     len(token) if token else 0,
        'expected_header':  'asaas-access-token',
        'endpoint':         '/api/billing/webhooks/asaas/',
        'hint': (
            'Token configured. Ensure the Asaas webhook authToken matches exactly.'
            if token else
            'MISSING: set ASAAS_WEBHOOK_TOKEN in Railway backend variables and redeploy.'
        ),
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
@throttle_classes([WebhookThrottle])
def asaas_webhook(request):
    """
    Receive and process Asaas webhook events.
    https://docs.asaas.com/reference/webhook

    Security:
    - authentication_classes=[] bypasses JWT — Asaas does not send Bearer tokens
    - Token validated via hmac.compare_digest against ASAAS_WEBHOOK_TOKEN env var
    - Rate-limited via WebhookThrottle
    - Processed inside transaction.atomic() for consistency
    """
    # Asaas sends the authToken in the 'asaas-access-token' header (primary).
    # Fallback to 'asaas-webhook-token' for backwards compatibility.
    token = (
        request.META.get('HTTP_ASAAS_ACCESS_TOKEN', '').strip()
        or request.META.get('HTTP_ASAAS_WEBHOOK_TOKEN', '').strip()
    )
    from .services.asaas_service import validate_webhook_token
    if not validate_webhook_token(token):
        # validate_webhook_token already logs the specific failure reason
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    payload = request.data
    event_type = payload.get('event', 'UNKNOWN')
    payment_data = payload.get('payment', {})
    asaas_id = payment_data.get('id', '') or payload.get('subscription', {}).get('id', '')
    logger.info('[webhook] Received: event=%s asaas_id=%s', event_type, asaas_id)

    if not asaas_id:
        # Events without an ID cannot be deduplicated — log and accept but don't process
        logger.warning('Webhook received without asaas_id: event_type=%s — accepted but skipped processing', event_type)
        return Response({'received': True})

    # Idempotency: skip already-processed events with the same asaas_id+event_type
    if WebhookEvent.objects.filter(
        asaas_id=asaas_id, event_type=event_type, processed=True
    ).exists():
        logger.info('Duplicate webhook skipped: %s %s', event_type, asaas_id)
        return Response({'received': True})

    event = WebhookEvent.objects.create(
        event_type=event_type,
        asaas_id=asaas_id,
        payload=payload,
    )

    try:
        with transaction.atomic():
            _process_webhook_event(event_type, payload, event)
        event.processed = True
        event.save(update_fields=['processed', 'updated_at'])
    except Exception as exc:
        logger.exception('Error processing webhook event %s', event_type)
        event.error = str(exc)
        event.save(update_fields=['error', 'updated_at'])

    return Response({'received': True})


def _process_webhook_event(event_type: str, payload: dict, event: WebhookEvent):
    """Dispatch webhook event to the appropriate handler."""
    handlers = {
        'PAYMENT_CONFIRMED':           _handle_payment_confirmed,
        'PAYMENT_RECEIVED':            _handle_payment_confirmed,
        'PAYMENT_OVERDUE':             _handle_payment_overdue,
        'PAYMENT_DELETED':             _handle_payment_deleted,
        'PAYMENT_REFUNDED':            _handle_payment_refunded,
        'PAYMENT_CHARGEBACK_DISPUTE':  _handle_payment_chargeback,
        'SUBSCRIPTION_CREATED':        _handle_subscription_created,
        'SUBSCRIPTION_UPDATED':        _handle_subscription_updated,
        'SUBSCRIPTION_INACTIVATED':    _handle_subscription_inactivated,
        'SUBSCRIPTION_DELETED':        _handle_subscription_deleted,
    }
    handler = handlers.get(event_type)
    if handler:
        handler(payload)
    else:
        logger.info('Unhandled Asaas webhook event: %s', event_type)


def _safe_raw_response(data: dict) -> dict:
    """Strip PCI-sensitive fields before persisting payment response."""
    return {k: v for k, v in data.items() if k not in _SENSITIVE_PAYMENT_FIELDS}


def _transition_subscription(sub: Subscription, new_status: str, context: str = '') -> bool:
    """
    Apply a status transition only if it's valid per the state machine.
    Returns True if transition was applied, False if rejected.
    """
    allowed = _VALID_TRANSITIONS.get(sub.status, set())
    if sub.status == new_status:
        return True
    if new_status not in allowed:
        logger.error(
            'Invalid subscription transition %s -> %s (sub_id=%s) context=%s',
            sub.status, new_status, sub.id, context,
        )
        return False
    return True


def _find_subscription_by_asaas(asaas_subscription_id: str):
    return (
        Subscription.objects
        .select_related('user', 'plan')
        .filter(asaas_subscription_id=asaas_subscription_id)
        .first()
    )


def _handle_payment_confirmed(payload: dict):
    p = payload.get('payment', {})
    asaas_sub_id = p.get('subscription', '')
    sub = _find_subscription_by_asaas(asaas_sub_id) if asaas_sub_id else None

    user = sub.user if sub else _user_from_external_ref(p.get('externalReference', ''))
    if user is None:
        logger.error(
            'PAYMENT_CONFIRMED: user not found for asaas_payment_id=%s externalReference=%s — '
            'payment record not created. Check externalReference in Asaas subscription.',
            p.get('id', ''), p.get('externalReference', ''),
        )
        return

    # Programa de parceiros — valor líquido (RN-006) e desconto aplicado (informativo).
    # Calculado antes da ativação, pois ela limpa pending_plan/pending_billing_period.
    _net = p.get('netValue')
    paid_net = Decimal(str(_net)) if _net is not None else Decimal(str(p.get('value', 0) or 0))
    discount = Decimal('0')
    if sub and sub.coupon_id:
        _plan = sub.pending_plan or sub.plan
        _period = sub.pending_billing_period or sub.billing_period
        gross = Decimal(str(_plan.price_for_period(_period)))
        discount = gross - Decimal(str(p.get('value', 0) or 0))
        if discount < 0:
            discount = Decimal('0')

    payment_obj, _created = Payment.objects.update_or_create(
        asaas_payment_id=p.get('id', ''),
        defaults={
            'user': user,
            'subscription': sub,
            'amount': p.get('value', 0),
            'discount_amount': discount,
            'paid_net_amount': paid_net,
            'payment_method': _map_billing_type(p.get('billingType', '')),
            'status': Payment.STATUS_PAID,
            'transaction_id': p.get('id', ''),
            'paid_at': timezone.now(),
            'description': p.get('description', ''),
            'raw_response': _safe_raw_response(p),  # PCI: strip card data
        },
    )
    if sub and _transition_subscription(sub, Subscription.STATUS_ACTIVE, 'payment_confirmed'):
        from datetime import date as date_cls
        if sub.pending_plan_id:
            sub.plan = sub.pending_plan
            if sub.pending_billing_period:
                sub.billing_period = sub.pending_billing_period
            sub.pending_plan = None
            sub.pending_billing_period = ''
        sub.status = Subscription.STATUS_ACTIVE
        sub.start_date = sub.start_date or date_cls.today()
        if sub.billing_period == 'yearly':
            sub.next_due_date = date_cls.today().replace(year=date_cls.today().year + 1)
        else:
            from dateutil.relativedelta import relativedelta
            sub.next_due_date = date_cls.today() + relativedelta(months=1)
        sub.save(update_fields=[
            'plan', 'billing_period', 'pending_plan', 'pending_billing_period',
            'status', 'start_date', 'next_due_date', 'updated_at',
        ])
        logger.info('Subscription %s activated after payment confirmed', sub.id)

    # Comissão de parceiro (Fluxo C) — 1º pagamento confirmado. Idempotente.
    if sub:
        from apps.referrals.services.commission import generate_commission_for_payment
        generate_commission_for_payment(payment_obj, sub)


def _handle_payment_overdue(payload: dict):
    p = payload.get('payment', {})
    asaas_sub_id = p.get('subscription', '')
    sub = _find_subscription_by_asaas(asaas_sub_id) if asaas_sub_id else None
    if sub and sub.pending_plan_id and sub.status == Subscription.STATUS_PENDING:
        # Payment failed for a brand-new pending sub — clear the pending upgrade, do not mark unpaid.
        sub.pending_plan = None
        sub.pending_billing_period = ''
        sub.save(update_fields=['pending_plan', 'pending_billing_period', 'updated_at'])
        Payment.objects.filter(asaas_payment_id=p.get('id', '')).update(status=Payment.STATUS_OVERDUE)
        return
    if sub and _transition_subscription(sub, Subscription.STATUS_UNPAID, 'payment_overdue'):
        sub.status = Subscription.STATUS_UNPAID
        sub.save(update_fields=['status', 'updated_at'])
    Payment.objects.filter(asaas_payment_id=p.get('id', '')).update(status=Payment.STATUS_OVERDUE)


def _handle_payment_deleted(payload: dict):
    p = payload.get('payment', {})
    Payment.objects.filter(asaas_payment_id=p.get('id', '')).update(status=Payment.STATUS_FAILED)


def _handle_payment_refunded(payload: dict):
    p = payload.get('payment', {})
    Payment.objects.filter(asaas_payment_id=p.get('id', '')).update(status=Payment.STATUS_REFUNDED)
    # Estorno reverte a comissão (RF-014/RN-009).
    payment = Payment.objects.filter(asaas_payment_id=p.get('id', '')).first()
    if payment:
        from apps.referrals.services.commission import reverse_commission_for_payment
        reverse_commission_for_payment(payment)


def _handle_payment_chargeback(payload: dict):
    p = payload.get('payment', {})
    asaas_sub_id = p.get('subscription', '')
    sub = _find_subscription_by_asaas(asaas_sub_id) if asaas_sub_id else None
    if sub and _transition_subscription(sub, Subscription.STATUS_UNPAID, 'chargeback'):
        sub.status = Subscription.STATUS_UNPAID
        sub.save(update_fields=['status', 'updated_at'])
    # Chargeback também reverte a comissão (RN-009).
    payment = Payment.objects.filter(asaas_payment_id=p.get('id', '')).first()
    if payment:
        from apps.referrals.services.commission import reverse_commission_for_payment
        reverse_commission_for_payment(payment)
    logger.warning('Chargeback dispute for payment %s', p.get('id'))


def _handle_subscription_created(payload: dict):
    s = payload.get('subscription', {})
    sub = _find_subscription_by_asaas(s.get('id', ''))
    if sub and sub.pending_plan_id:
        logger.info('Subscription %s created at Asaas; waiting for payment confirmation', sub.id)
        return
    # Only activate subscriptions that are explicitly pending (awaiting first confirmation).
    # Never re-activate expired or canceled subscriptions via this event alone — payment
    # confirmation (PAYMENT_CONFIRMED) is the authoritative activation trigger.
    if sub and sub.status == Subscription.STATUS_PENDING:
        if _transition_subscription(sub, Subscription.STATUS_ACTIVE, 'subscription_created'):
            sub.status = Subscription.STATUS_ACTIVE
            sub.save(update_fields=['status', 'updated_at'])


def _handle_subscription_updated(payload: dict):
    s = payload.get('subscription', {})
    sub = _find_subscription_by_asaas(s.get('id', ''))
    if sub and sub.pending_plan_id:
        logger.info('Subscription %s updated at Asaas; waiting for payment confirmation', sub.id)
        return
    if sub and s.get('status') == 'ACTIVE':
        if _transition_subscription(sub, Subscription.STATUS_ACTIVE, 'subscription_updated'):
            sub.status = Subscription.STATUS_ACTIVE
            sub.save(update_fields=['status', 'updated_at'])


def _handle_subscription_inactivated(payload: dict):
    s = payload.get('subscription', {})
    sub = _find_subscription_by_asaas(s.get('id', ''))
    if sub and sub.pending_plan_id:
        sub.pending_plan = None
        sub.pending_billing_period = ''
        sub.save(update_fields=['pending_plan', 'pending_billing_period', 'updated_at'])
        return
    if sub and _transition_subscription(sub, Subscription.STATUS_EXPIRED, 'subscription_inactivated'):
        sub.status = Subscription.STATUS_EXPIRED
        sub.save(update_fields=['status', 'updated_at'])


def _handle_subscription_deleted(payload: dict):
    s = payload.get('subscription', {})
    sub = _find_subscription_by_asaas(s.get('id', ''))
    if sub and sub.pending_plan_id:
        sub.pending_plan = None
        sub.pending_billing_period = ''
        sub.save(update_fields=['pending_plan', 'pending_billing_period', 'updated_at'])
        return
    if sub and _transition_subscription(sub, Subscription.STATUS_CANCELED, 'subscription_deleted'):
        sub.status = Subscription.STATUS_CANCELED
        sub.canceled_at = timezone.now()
        sub.save(update_fields=['status', 'canceled_at', 'updated_at'])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _map_billing_type(billing_type: str) -> str:
    return {
        'CREDIT_CARD': Payment.METHOD_CREDIT_CARD,
        'PIX':         Payment.METHOD_PIX,
        'DEBIT_CARD':  Payment.METHOD_DEBIT_CARD,
        'BOLETO':      Payment.METHOD_BOLETO,
    }.get(billing_type, '')


def _user_from_external_ref(ref: str):
    User = get_user_model()
    try:
        return User.objects.get(pk=int(ref))
    except (User.DoesNotExist, ValueError, TypeError):
        return None


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def asaas_customer_id(request):
    """
    Return (or create) the Asaas customer ID for the authenticated user.
    Used by the mobile app for PCI-compliant client-side card tokenization.
    The mobile sends raw card data directly to Asaas, never through our backend.
    """
    from .services.asaas_service import get_or_create_customer, AsaasNotConfiguredError
    try:
        cid = get_or_create_customer(request.user)
        return Response({'customer_id': cid})
    except AsaasNotConfiguredError:
        return Response({'customer_id': None, 'detail': 'Asaas not configured'})
    except Exception as exc:
        logger.error('Failed to get/create Asaas customer for user %s: %s', request.user.id, exc)
        return Response({'customer_id': None, 'detail': 'Service unavailable'}, status=503)


def _get_or_create_individual_subscription(user):
    try:
        return user.subscription
    except Subscription.DoesNotExist:
        from .models import Plan
        try:
            individual = Plan.objects.get(slug=Plan.SLUG_INDIVIDUAL)
        except Plan.DoesNotExist:
            logger.error('CRITICAL: Seed de planos não executado. Plan.SLUG_INDIVIDUAL não encontrado.')
            raise Exception('Erro interno: Configuração de planos incompleta.')

        return Subscription.objects.create(
            user=user,
            plan=individual,
            status=Subscription.STATUS_PENDING,
            start_date=date.today(),
        )


def _log_action(user, action: str, detail: str):
    try:
        AuditLog.objects.create(
            actor=user,
            action=AuditLog.ACTION_UPDATE,
            entity_type='subscription',
            entity_id=str(user.id),
            diff={'action': action, 'detail': detail},
        )
    except Exception:
        pass


# ── Família — gestão de dependentes ────────────────────────────────────────────

def _get_familia_subscription_for(user):
    """Return the user's Família subscription or None.
    Only the responsible payer (Subscription.user) manages the family."""
    try:
        sub = user.subscription
    except Subscription.DoesNotExist:
        return None
    if sub.plan.slug != Plan.SLUG_FAMILIA:
        return None
    return sub


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def family_members(request):
    """
    GET  → list all (non-removed) members under the requesting user's Família subscription.
    POST → add a new dependent by email or user_id.
           Validates plan=Família, max_members limit (titular conta), no duplicates.
    """
    sub = _get_familia_subscription_for(request.user)
    if sub is None:
        return Response(
            {'detail': 'Apenas o titular de uma assinatura Família pode gerenciar dependentes.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == 'GET':
        qs = sub.family_members.exclude(status=FamilyMembership.STATUS_REMOVED).order_by('-created_at')
        return Response(FamilyMembershipSerializer(qs, many=True).data)

    # POST — add member
    ser = FamilyMemberAddSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data

    User = get_user_model()
    target = None
    if d.get('user_id'):
        target = User.objects.filter(pk=d['user_id']).first()
    elif d.get('email'):
        target = User.objects.filter(email__iexact=d['email']).first()

    if target is None:
        return Response(
            {'detail': 'Usuário não encontrado. Peça que ele cadastre antes de adicionar à família.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if target.pk == request.user.pk:
        return Response(
            {'detail': 'O titular não precisa ser adicionado como dependente.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Limit: max_members = titular + active/pending dependents.
    # Allowed dependents = max_members - 1.
    active_count = sub.family_members.filter(
        status__in=[FamilyMembership.STATUS_PENDING, FamilyMembership.STATUS_ACTIVE]
    ).count()
    if active_count >= sub.plan.max_members - 1:
        return Response(
            {'detail': f'Limite de {sub.plan.max_members} membros atingido (titular + dependentes).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Idempotent: revive a removed entry instead of creating a duplicate
    membership, created = FamilyMembership.objects.get_or_create(
        subscription=sub, member_user=target,
        defaults={'status': FamilyMembership.STATUS_PENDING},
    )
    if not created:
        if membership.status == FamilyMembership.STATUS_REMOVED:
            membership.status = FamilyMembership.STATUS_PENDING
            membership.save(update_fields=['status', 'updated_at'])
        else:
            return Response(
                {'detail': 'Esse usuário já é dependente nessa assinatura.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    _log_action(request.user, 'billing.family.add', f'member_id={target.id}')
    return Response(
        FamilyMembershipSerializer(membership).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def family_member_detail(request, pk):
    """
    POST   → accept/activate a pending membership (callable by the dependent).
    DELETE → remove a dependent (callable only by the titular).
    """
    try:
        membership = FamilyMembership.objects.select_related('subscription__user', 'member_user').get(pk=pk)
    except FamilyMembership.DoesNotExist:
        return Response({'detail': 'Membro não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    titular = membership.subscription.user
    dependent = membership.member_user

    if request.method == 'POST':
        # Only the dependent themselves can accept
        if request.user.pk != dependent.pk:
            return Response(
                {'detail': 'Apenas o dependente pode aceitar o convite.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if membership.status != FamilyMembership.STATUS_PENDING:
            return Response(
                {'detail': 'Convite não está pendente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership.status = FamilyMembership.STATUS_ACTIVE
        membership.accepted_at = timezone.now()
        membership.save(update_fields=['status', 'accepted_at', 'updated_at'])
        _log_action(request.user, 'billing.family.accept', f'membership_id={membership.pk}')
        return Response(FamilyMembershipSerializer(membership).data)

    # DELETE — only titular can remove
    if request.user.pk != titular.pk:
        return Response(
            {'detail': 'Apenas o titular pode remover dependentes.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    membership.status = FamilyMembership.STATUS_REMOVED
    membership.save(update_fields=['status', 'updated_at'])
    _log_action(request.user, 'billing.family.remove', f'membership_id={membership.pk}')
    return Response(status=status.HTTP_204_NO_CONTENT)
