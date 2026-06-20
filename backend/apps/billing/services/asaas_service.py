"""
Asaas Payment Gateway Service
==============================
Production-ready implementation with:
- Exponential backoff retry (1s/2s/4s) on network errors
- Circuit breaker: opens after 5 consecutive failures, resets after 60s
- hmac.compare_digest for webhook token validation
- PCI-DSS: backend only accepts card_token, never raw card data

Asaas docs: https://docs.asaas.com/reference/
Sandbox:    https://sandbox.asaas.com
Production: https://api.asaas.com
"""
import logging
import time
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('apps.billing.asaas')

# ── Circuit Breaker ─────────────────────────────────────────────────────────────
_CB_FAILURES_KEY = 'asaas:cb:failures'
_CB_OPEN_KEY     = 'asaas:cb:open'
_CB_THRESHOLD    = 5   # open after N consecutive failures
_CB_RESET_TTL    = 60  # seconds before circuit resets


def _cb_is_open() -> bool:
    return bool(cache.get(_CB_OPEN_KEY))


def _cb_record_failure():
    failures = cache.get(_CB_FAILURES_KEY, 0) + 1
    cache.set(_CB_FAILURES_KEY, failures, _CB_RESET_TTL * 2)
    if failures >= _CB_THRESHOLD:
        cache.set(_CB_OPEN_KEY, True, _CB_RESET_TTL)
        logger.error('Asaas circuit breaker OPENED after %d failures — pausing for %ds', failures, _CB_RESET_TTL)


def _cb_record_success():
    cache.delete(_CB_FAILURES_KEY)
    cache.delete(_CB_OPEN_KEY)


def _base_url() -> str:
    env = getattr(settings, 'ASAAS_ENVIRONMENT', 'sandbox')
    if env == 'production':
        return 'https://api.asaas.com/v3'
    return 'https://sandbox.asaas.com/api/v3'


def _headers() -> dict:
    api_key = getattr(settings, 'ASAAS_API_KEY', '')
    return {
        'access_token': api_key,
        'Content-Type': 'application/json',
        'User-Agent': 'Tenfy/1.0',
    }


def _is_configured() -> bool:
    return bool(getattr(settings, 'ASAAS_API_KEY', ''))


def _request(method: str, path: str, _retries: int = 3, **kwargs):
    """
    Generic HTTP call to Asaas API with:
    - Circuit breaker (opens after 5 failures, resets after 60s)
    - Exponential backoff retry (1s/2s/4s) on network errors
    - No retry on 4xx (client errors)
    """
    if _cb_is_open():
        raise AsaasAPIError('Asaas circuit breaker is open — service temporarily paused. Try again shortly.')

    if not _is_configured():
        raise AsaasNotConfiguredError(
            'ASAAS_API_KEY not set. Configure the variable and set ASAAS_ENVIRONMENT=sandbox|production.'
        )
    url = f'{_base_url()}{path}'

    last_exc = None
    for attempt in range(_retries):
        try:
            response = requests.request(
                method, url, headers=_headers(), timeout=30, **kwargs,
            )
            # 4xx = client error — don't retry, don't trip circuit breaker
            if 400 <= response.status_code < 500:
                body = {}
                try:
                    body = response.json()
                except Exception:
                    pass
                logger.error('Asaas client error %s %s -> %s: %s', method, path, response.status_code, body)
                raise AsaasAPIError(f'Asaas returned {response.status_code}', body)

            response.raise_for_status()
            _cb_record_success()
            return response.json()

        except AsaasAPIError:
            raise  # propagate 4xx immediately — no retry

        except requests.RequestException as exc:
            last_exc = exc
            _cb_record_failure()
            if attempt < _retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    'Asaas request failed (attempt %d/%d), retrying in %ds: %s %s — %s',
                    attempt + 1, _retries, wait, method, path, exc,
                )
                time.sleep(wait)
            else:
                logger.exception('Asaas request failed after %d attempts: %s %s', _retries, method, path)

    raise AsaasAPIError(str(last_exc)) from last_exc


# ── Exceptions ─────────────────────────────────────────────────────────────────

class AsaasError(Exception):
    pass


class AsaasNotConfiguredError(AsaasError):
    """Raised when ASAAS_API_KEY is not configured."""
    pass


class AsaasAPIError(AsaasError):
    def __init__(self, message: str, body: dict = None):
        super().__init__(message)
        self.body = body or {}


# ── Customer ───────────────────────────────────────────────────────────────────

def create_customer(user) -> dict:
    """
    Create or retrieve an Asaas customer for the given user.
    https://docs.asaas.com/reference/criar-novo-cliente

    Returns the Asaas customer object dict.
    """
    payload = {
        'name': user.full_name or user.email,
        'email': user.email,
        'phone': user.phone or '',
        'externalReference': str(user.id),
    }
    # CPF é exigido pelo Asaas para gerar cobranças.
    cpf = getattr(user, 'cpf', '') or ''
    if cpf:
        payload['cpfCnpj'] = cpf
    logger.info('Creating Asaas customer for user %s', user.id)
    return _request('POST', '/customers', json=payload)


def get_or_create_customer(user) -> str:
    """
    Return existing asaas_customer_id from the user's subscription,
    or create a new customer and persist the ID.
    Returns the Asaas customer ID string.
    """
    from apps.billing.models import Subscription
    try:
        sub = user.subscription
        if sub.asaas_customer_id:
            return sub.asaas_customer_id
    except Subscription.DoesNotExist:
        pass

    customer = create_customer(user)
    cid = customer['id']

    # Persist immediately
    Subscription.objects.filter(user=user).update(asaas_customer_id=cid)
    logger.info('Asaas customer %s created for user %s', cid, user.id)
    return cid


# ── Subscriptions ──────────────────────────────────────────────────────────────

def create_subscription(
    user,
    plan,
    billing_period: str,
    payment_method: str,
    card_token: str = '',
) -> dict:
    """
    Create an Asaas subscription (recorrência).
    https://docs.asaas.com/reference/criar-assinatura-com-cartao-de-credito

    PCI-DSS: only card_token accepted. Raw card data must never reach this function.
    Client-side tokenization is performed by the mobile app directly with Asaas.

    Args:
        user: Django user instance
        plan: billing.Plan instance
        billing_period: 'monthly' or 'yearly'
        payment_method: 'CREDIT_CARD' | 'PIX' | 'BOLETO'
        card_token: tokenized card reference from Asaas client-side SDK

    Returns Asaas subscription response dict.
    """
    from datetime import date

    if payment_method.upper() == 'CREDIT_CARD' and not card_token:
        raise ValueError('card_token is required for CREDIT_CARD payment — raw card data is never accepted.')

    customer_id = get_or_create_customer(user)
    price = float(plan.price_for_period(billing_period))
    cycle = 'MONTHLY' if billing_period == 'monthly' else 'YEARLY'

    payload = {
        'customer': customer_id,
        'billingType': payment_method.upper(),
        'value': price,
        'nextDueDate': date.today().isoformat(),
        'cycle': cycle,
        'description': f'Tenfy — Plano {plan.name}',
        'externalReference': str(user.id),
    }
    if payment_method.upper() == 'CREDIT_CARD':
        payload['creditCardToken'] = card_token

    logger.info('Creating Asaas subscription for user %s plan %s', user.id, plan.slug)
    return _request('POST', '/subscriptions', json=payload)


def create_subscription_with_first_discount(
    user,
    plan,
    billing_period: str,
    payment_method: str,
    discount_amount,
    card_token: str = '',
) -> dict:
    """
    Programa de parceiros — desconto só na 1ª mensalidade (decisão fixada):
    cria uma COBRANÇA AVULSA descontada para o 1º ciclo e uma ASSINATURA a preço
    cheio começando no ciclo seguinte (nextDueDate = hoje + 1 ciclo).

    Assim o desconto incide apenas no 1º pagamento (base da comissão) e a
    recorrência segue cheia, sem reestruturar o domínio (RN-006/RN-010).

    Retorna {'subscription': <dict>, 'first_payment': <dict>}.
    Se discount_amount <= 0, recai no fluxo normal de assinatura.
    """
    from datetime import date
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta

    discount = Decimal(discount_amount or 0)
    if discount <= 0:
        return {'subscription': create_subscription(
            user, plan, billing_period, payment_method, card_token,
        ), 'first_payment': {}}

    if payment_method.upper() == 'CREDIT_CARD' and not card_token:
        raise ValueError('card_token is required for CREDIT_CARD payment — raw card data is never accepted.')

    customer_id = get_or_create_customer(user)
    full_price = Decimal(plan.price_for_period(billing_period))
    first_price = (full_price - discount)
    if first_price < 0:
        first_price = Decimal('0')
    cycle = 'MONTHLY' if billing_period == 'monthly' else 'YEARLY'
    delta = relativedelta(months=1) if billing_period == 'monthly' else relativedelta(years=1)
    next_due = (date.today() + delta).isoformat()
    billing_type = payment_method.upper()

    # 1) Cobrança avulsa descontada — 1º pagamento
    first_payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'value': float(first_price.quantize(Decimal('0.01'))),
        'dueDate': date.today().isoformat(),
        'description': f'Tenfy — Plano {plan.name} (1ª mensalidade c/ cupom)',
        'externalReference': str(user.id),
    }
    if billing_type == 'CREDIT_CARD':
        first_payload['creditCardToken'] = card_token
    logger.info('Creating discounted first charge for user %s plan %s', user.id, plan.slug)
    first_payment = _request('POST', '/payments', json=first_payload)

    # 2) Assinatura a preço cheio, começando no próximo ciclo
    sub_payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'value': float(full_price.quantize(Decimal('0.01'))),
        'nextDueDate': next_due,
        'cycle': cycle,
        'description': f'Tenfy — Plano {plan.name}',
        'externalReference': str(user.id),
    }
    if billing_type == 'CREDIT_CARD':
        sub_payload['creditCardToken'] = card_token
    logger.info('Creating full-price recurrence for user %s starting %s', user.id, next_due)
    subscription = _request('POST', '/subscriptions', json=sub_payload)

    return {'subscription': subscription, 'first_payment': first_payment}


def create_checkout_session(
    user,
    plan,
    billing_period: str,
    discount_amount,
    success_url: str,
    cancel_url: str,
) -> dict:
    """
    Cria uma sessão de Checkout HOSPEDADO do Asaas (Pix + Cartão) para o 1º
    pagamento (com desconto do cupom embutido no valor). PCI-safe: o cartão é
    coletado na página do Asaas, nunca no nosso backend/front.

    externalReference = user.id permite o webhook mapear o pagamento → usuário →
    assinatura (ativação + comissão). Retorna o dict do checkout (inclui 'link').
    """
    from decimal import Decimal

    full_price = Decimal(plan.price_for_period(billing_period))
    discount = Decimal(discount_amount or 0)
    value = full_price - discount
    if value < 0:
        value = Decimal('0')

    payload = {
        'billingTypes': ['CREDIT_CARD', 'PIX'],
        'chargeTypes': ['DETACHED'],
        'minutesToExpire': 60,
        'callback': {'successUrl': success_url, 'cancelUrl': cancel_url},
        'items': [{
            'name': f'Plano {plan.name}'[:30],
            'description': f'Tenfy — Plano {plan.name} (1ª mensalidade)'[:255],
            'quantity': 1,
            'value': float(value.quantize(Decimal('0.01'))),
        }],
        'externalReference': str(user.id),
    }
    logger.info('Creating Asaas checkout session for user %s plan %s', user.id, plan.slug)
    return _request('POST', '/checkouts', json=payload)


def ensure_customer_for_pending(pending) -> str:
    """Cria (ou retorna) o cliente Asaas a partir de um PendingRegistration (sem User)."""
    if pending.asaas_customer_id:
        return pending.asaas_customer_id
    payload = {
        'name': pending.full_name or pending.email,
        'email': pending.email,
        'phone': pending.phone or '',
        'externalReference': f'reg:{pending.token}',
    }
    if pending.cpf:
        payload['cpfCnpj'] = pending.cpf
    cust = _request('POST', '/customers', json=payload)
    cid = cust.get('id', '')
    pending.asaas_customer_id = cid
    pending.save(update_fields=['asaas_customer_id', 'updated_at'])
    return cid


def create_pending_first_pix(pending, plan, discount_amount) -> dict:
    """Cobrança avulsa Pix descontada do 1º pagamento p/ um cadastro pendente. Retorna {payment, qr}."""
    from datetime import date
    from decimal import Decimal
    cid = ensure_customer_for_pending(pending)
    full = Decimal(plan.price_for_period(pending.billing_period))
    value = full - Decimal(discount_amount or 0)
    if value < 0:
        value = Decimal('0')
    payload = {
        'customer': cid, 'billingType': 'PIX',
        'value': float(value.quantize(Decimal('0.01'))),
        'dueDate': date.today().isoformat(),
        'description': f'Tenfy — Plano {plan.name} (1ª mensalidade)'[:255],
        'externalReference': f'reg:{pending.token}',
    }
    payment = _request('POST', '/payments', json=payload)
    qr = {}
    if payment.get('id'):
        try:
            qr = get_pix_qr_code(payment['id'])
        except Exception:  # noqa: BLE001
            qr = {}
    return {'payment': payment, 'qr': qr}


def create_pending_checkout_session(pending, plan, discount_amount, success_url, cancel_url) -> dict:
    """Checkout hospedado (Pix+Cartão) p/ um cadastro pendente (sem User). Retorna o checkout (com 'link')."""
    from decimal import Decimal
    full = Decimal(plan.price_for_period(pending.billing_period))
    value = full - Decimal(discount_amount or 0)
    if value < 0:
        value = Decimal('0')
    payload = {
        'billingTypes': ['CREDIT_CARD', 'PIX'],
        'chargeTypes': ['DETACHED'],
        'minutesToExpire': 60,
        'callback': {'successUrl': success_url, 'cancelUrl': cancel_url},
        'items': [{
            'name': f'Plano {plan.name}'[:30],
            'description': f'Tenfy — Plano {plan.name} (1ª mensalidade)'[:255],
            'quantity': 1,
            'value': float(value.quantize(Decimal('0.01'))),
        }],
        'externalReference': f'reg:{pending.token}',
    }
    return _request('POST', '/checkouts', json=payload)


def create_recurrence_after_first_payment(
    user,
    plan,
    billing_period: str,
    billing_type: str,
    card_token: str = '',
    customer_id: str = '',
) -> dict:
    """
    Cria a assinatura RECORRENTE a preço cheio começando no próximo ciclo, após o
    1º pagamento (hosted checkout / avulsa) ter sido confirmado.

    - PIX: o Asaas gera uma nova cobrança Pix a cada ciclo.
    - CREDIT_CARD: usa o creditCardToken retornado no 1º pagamento p/ débito
      automático recorrente.

    O ``creditCardToken`` é vinculado ao cliente Asaas do pagamento, então
    ``customer_id`` DEVE ser o mesmo cliente que pagou (vem do webhook). Criar um
    cliente novo aqui resulta em 400 "CreditCardToken não encontrado".

    Chamada de dentro do webhook — quem chama deve proteger com try/except para
    não derrubar a ativação/comissão se o Asaas falhar.
    """
    from datetime import date
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta

    customer_id = customer_id or get_or_create_customer(user)
    full_price = float(Decimal(plan.price_for_period(billing_period)).quantize(Decimal('0.01')))
    cycle = 'MONTHLY' if billing_period == 'monthly' else 'YEARLY'
    delta = relativedelta(months=1) if billing_period == 'monthly' else relativedelta(years=1)
    next_due = (date.today() + delta).isoformat()
    bt = (billing_type or 'PIX').upper()

    payload = {
        'customer': customer_id,
        'billingType': bt if bt in ('CREDIT_CARD', 'PIX', 'BOLETO') else 'PIX',
        'value': full_price,
        'nextDueDate': next_due,
        'cycle': cycle,
        'description': f'Tenfy — Plano {plan.name}',
        'externalReference': str(user.id),
    }
    if bt == 'CREDIT_CARD' and card_token:
        payload['creditCardToken'] = card_token
    elif bt == 'CREDIT_CARD' and not card_token:
        # Sem token não dá p/ recorrência no cartão — cai para Pix.
        payload['billingType'] = 'PIX'
    logger.info('Creating recurrence subscription for user %s starting %s (%s)', user.id, next_due, payload['billingType'])
    return _request('POST', '/subscriptions', json=payload)


def get_subscription_first_pix_qr(asaas_subscription_id: str, max_attempts: int = 3) -> dict:
    """
    Fetch the Pix QR code for the first pending payment of a subscription.
    Returns dict with encodedImage, payload (copia e cola) and expirationDate.

    Retries up to max_attempts times with 2s delay because Asaas (especially sandbox)
    may not generate the first payment synchronously right after subscription creation.
    """
    for attempt in range(max_attempts):
        try:
            payments = _request('GET', '/payments', params={
                'subscription': asaas_subscription_id,
                'limit': 1,
                'offset': 0,
            })
            payment_list = payments.get('data', [])
            if not payment_list:
                if attempt < max_attempts - 1:
                    logger.info(
                        'No payments yet for subscription %s (attempt %d/%d), retrying in 2s…',
                        asaas_subscription_id, attempt + 1, max_attempts,
                    )
                    time.sleep(2)
                    continue
                logger.warning('No payments found for subscription %s after %d attempts', asaas_subscription_id, max_attempts)
                return {}
            payment_id = payment_list[0]['id']
            qr = _request('GET', f'/payments/{payment_id}/pixQrCode')
            return qr
        except AsaasAPIError as exc:
            logger.warning('Could not fetch Pix QR for subscription %s (attempt %d): %s', asaas_subscription_id, attempt + 1, exc)
            if attempt < max_attempts - 1:
                time.sleep(2)
    return {}


def cancel_subscription(asaas_subscription_id: str) -> dict:
    """
    Cancel an Asaas subscription immediately.
    https://docs.asaas.com/reference/remover-assinatura
    """
    logger.info('Canceling Asaas subscription %s', asaas_subscription_id)
    return _request('DELETE', f'/subscriptions/{asaas_subscription_id}')


def get_subscription(asaas_subscription_id: str) -> dict:
    """Retrieve subscription details from Asaas."""
    return _request('GET', f'/subscriptions/{asaas_subscription_id}')


def update_subscription(asaas_subscription_id: str, **fields) -> dict:
    """
    Update subscription (e.g. change plan, billing type).
    https://docs.asaas.com/reference/atualizar-assinatura-existente
    """
    logger.info('Updating Asaas subscription %s: %s', asaas_subscription_id, fields)
    return _request('POST', f'/subscriptions/{asaas_subscription_id}', json=fields)


# ── Payments ───────────────────────────────────────────────────────────────────

def get_payment(asaas_payment_id: str) -> dict:
    """Retrieve payment details from Asaas."""
    return _request('GET', f'/payments/{asaas_payment_id}')


def list_subscription_payments(asaas_subscription_id: str) -> list:
    """List all payments for a subscription."""
    data = _request('GET', f'/payments', params={'subscription': asaas_subscription_id})
    return data.get('data', [])


def create_pix_payment(user, amount: Decimal, description: str) -> dict:
    """
    Create a one-time Pix payment (for plan upgrade, etc.).
    https://docs.asaas.com/reference/criar-nova-cobranca
    """
    from datetime import date
    customer_id = get_or_create_customer(user)
    payload = {
        'customer': customer_id,
        'billingType': 'PIX',
        'value': float(amount),
        'dueDate': date.today().isoformat(),
        'description': description,
    }
    logger.info('Creating Pix payment for user %s R$%.2f', user.id, amount)
    result = _request('POST', '/payments', json=payload)
    return result


def get_pix_qr_code(asaas_payment_id: str) -> dict:
    """Retrieve Pix QR code and copia-e-cola string for a payment."""
    return _request('GET', f'/payments/{asaas_payment_id}/pixQrCode')


def refund_payment(asaas_payment_id: str) -> dict:
    """Refund a payment."""
    logger.info('Refunding Asaas payment %s', asaas_payment_id)
    return _request('POST', f'/payments/{asaas_payment_id}/refund')


# ── Webhook signature validation ───────────────────────────────────────────────

def validate_webhook_token(token: str) -> bool:
    """
    Asaas sends the configured authToken in the ``asaas-access-token`` HTTP
    header on every webhook POST.  Compare it against our ASAAS_WEBHOOK_TOKEN
    env var using hmac.compare_digest (constant-time) to prevent timing
    side-channel attacks.

    If ASAAS_WEBHOOK_TOKEN is not configured we REJECT all requests — this
    avoids silently accepting unverified payloads.

    Ref: https://docs.asaas.com/reference/webhook

    Troubleshooting 401:
      1. Ensure ASAAS_WEBHOOK_TOKEN is set in Railway backend variables.
      2. Ensure the Asaas webhook panel 'authToken' field has the EXACT same value.
      3. Redeploy the backend service after changing Railway variables.
    """
    import hmac as _hmac
    # .strip() guards against accidental whitespace from copy-paste in Railway panel
    expected = getattr(settings, 'ASAAS_WEBHOOK_TOKEN', '').strip()
    if not expected:
        logger.error(
            '[webhook:config] ASAAS_WEBHOOK_TOKEN is not set in Railway env vars — '
            'all webhook requests will be rejected. '
            'Fix: Railway → backend service → Variables → add ASAAS_WEBHOOK_TOKEN. '
            'Set the same value in Asaas webhook panel → authToken field.'
        )
        return False
    if not token:
        # No token received — Asaas webhook panel authToken may not be configured
        logger.warning(
            '[webhook:auth] Request missing asaas-access-token header. '
            'Fix: Asaas panel → Integrações → Webhooks → edit webhook → set authToken.'
        )
        return False
    # Strip received token too — some reverse proxies add trailing whitespace
    result = _hmac.compare_digest(token.strip().encode(), expected.encode())
    if not result:
        logger.warning(
            '[webhook:auth] Token mismatch — received token does not match ASAAS_WEBHOOK_TOKEN. '
            'Fix: copy the EXACT value from Railway ASAAS_WEBHOOK_TOKEN to Asaas webhook authToken '
            '(case-sensitive, no extra spaces).'
        )
    return result
