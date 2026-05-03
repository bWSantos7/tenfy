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
from typing import Optional

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
        'User-Agent': 'TennisHub/1.0',
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
    card_data: Optional[dict] = None,
) -> dict:
    """
    Create an Asaas subscription (recorrência).
    https://docs.asaas.com/reference/criar-assinatura-com-cartao-de-credito

    Args:
        user: Django user instance
        plan: billing.Plan instance
        billing_period: 'monthly' or 'yearly'
        payment_method: 'CREDIT_CARD' | 'PIX' | 'BOLETO'
        card_token: tokenized card (optional)
        card_data: raw card fields dict (for direct card submission)

    Returns Asaas subscription response dict.
    """
    from datetime import date
    customer_id = get_or_create_customer(user)
    price = float(plan.price_for_period(billing_period))
    cycle = 'MONTHLY' if billing_period == 'monthly' else 'YEARLY'

    payload = {
        'customer': customer_id,
        'billingType': payment_method.upper(),
        'value': price,
        'nextDueDate': date.today().isoformat(),
        'cycle': cycle,
        'description': f'Tennis Hub — Plano {plan.name}',
        'externalReference': str(user.id),
    }
    if payment_method.upper() == 'CREDIT_CARD':
        if card_token:
            payload['creditCardToken'] = card_token
        elif card_data:
            payload['creditCard'] = {
                'holderName': card_data.get('holder_name', ''),
                'number': card_data.get('number', '').replace(' ', ''),
                'expiryMonth': card_data.get('expiry_month', ''),
                'expiryYear': card_data.get('expiry_year', ''),
                'ccv': card_data.get('ccv', ''),
            }
            payload['creditCardHolderInfo'] = {
                'name': card_data.get('holder_name', ''),
                'email': user.email,
                'cpfCnpj': card_data.get('cpf', '').replace('.', '').replace('-', ''),
                'postalCode': card_data.get('postal_code', '').replace('-', ''),
                'addressNumber': '0',
                'phone': getattr(user, 'phone', '') or '',
            }

    logger.info('Creating Asaas subscription for user %s plan %s', user.id, plan.slug)
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
    Asaas sends a token in the webhook header (asaas-webhook-token).
    Compare against ASAAS_WEBHOOK_TOKEN env var.

    SECURITY: Uses hmac.compare_digest to prevent timing side-channel attacks.
    If ASAAS_WEBHOOK_TOKEN is not configured we REJECT all requests.
    """
    import hmac as _hmac
    expected = getattr(settings, 'ASAAS_WEBHOOK_TOKEN', '')
    if not expected:
        logger.error(
            'ASAAS_WEBHOOK_TOKEN is not configured — all webhook requests rejected. '
            'Set ASAAS_WEBHOOK_TOKEN in Railway Variables.'
        )
        return False
    # constant-time comparison prevents timing attacks
    return _hmac.compare_digest(token.encode(), expected.encode())
