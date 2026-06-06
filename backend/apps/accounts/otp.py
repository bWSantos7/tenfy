"""OTP utilities: generate and verify 6-digit codes stored in Redis."""
import hashlib
import hmac
import logging
import secrets

from django.core.cache import cache

logger = logging.getLogger('apps.accounts')

OTP_TTL = 600        # seconds (10 minutes)
MAX_ATTEMPTS = 3     # reduced from 5 — fewer brute-force attempts allowed
LOCKOUT_TTL = 900    # 15-minute lockout after MAX_ATTEMPTS failures

# 'dependent_email' is keyed by the e-mail (not a user) — used to confirm a new
# dependent's e-mail BEFORE the account exists (Task 10).
VALID_OTP_TYPES = frozenset({'email', 'phone', 'password_reset', 'dependent_email'})


def _email_identifier(email: str) -> str:
    """Stable, key-safe identifier for an e-mail (no user yet)."""
    return 'eml-' + hashlib.sha256((email or '').strip().lower().encode()).hexdigest()[:24]


def generate_email_code(email: str) -> str:
    """Generate + store a 6-digit code for confirming an e-mail address."""
    return generate_and_store(_email_identifier(email), 'dependent_email')


def verify_email_code(email: str, code: str) -> bool:
    """Verify the code sent to confirm an e-mail address."""
    return verify(_email_identifier(email), 'dependent_email', code)


def _code_key(user_id: int, otp_type: str) -> str:
    return f'otp:code:{otp_type}:{user_id}'


def _attempts_key(user_id: int, otp_type: str) -> str:
    return f'otp:attempts:{otp_type}:{user_id}'


def _lockout_key(user_id: int, otp_type: str) -> str:
    return f'otp:lockout:{otp_type}:{user_id}'


def generate_and_store(user_id: int, otp_type: str) -> str:
    """Generate a cryptographically secure 6-digit OTP, store in Redis and return the plain code."""
    if otp_type not in VALID_OTP_TYPES:
        raise ValueError(f'Invalid OTP type: {otp_type!r}. Must be one of {VALID_OTP_TYPES}')
    # secrets.randbelow is cryptographically secure (uses os.urandom)
    code = f'{secrets.randbelow(1_000_000):06d}'
    cache.set(_code_key(user_id, otp_type), code, OTP_TTL)
    cache.delete(_attempts_key(user_id, otp_type))
    cache.delete(_lockout_key(user_id, otp_type))
    return code


def verify(user_id: int, otp_type: str, code: str) -> bool:
    """
    Verify OTP. Returns True on match (deletes code).
    Returns False on mismatch, exceeded attempts, or lockout.
    Uses constant-time comparison to prevent timing attacks.
    """
    # Check lockout first
    if cache.get(_lockout_key(user_id, otp_type)):
        logger.warning('OTP verify blocked — user %s locked out for %s', user_id, otp_type)
        return False

    attempts_key = _attempts_key(user_id, otp_type)
    attempts = cache.get(attempts_key, 0)
    if attempts >= MAX_ATTEMPTS:
        # Escalate to lockout and clear attempts counter
        cache.set(_lockout_key(user_id, otp_type), True, LOCKOUT_TTL)
        cache.delete(attempts_key)
        logger.warning('OTP max attempts reached — user %s locked out 15 min for %s', user_id, otp_type)
        return False

    stored = cache.get(_code_key(user_id, otp_type))
    if stored is None:
        return False

    # Constant-time comparison — prevents timing side-channel attacks
    if hmac.compare_digest(stored, code.strip()):
        cache.delete(_code_key(user_id, otp_type))
        cache.delete(attempts_key)
        return True

    cache.set(attempts_key, attempts + 1, OTP_TTL)
    logger.info('OTP mismatch for user %s type %s — attempt %d/%d', user_id, otp_type, attempts + 1, MAX_ATTEMPTS)
    return False
