"""Login brute-force protection.

A user may make at most ``MAX_LOGIN_ATTEMPTS`` invalid login attempts. After that
the account login is temporarily locked for ``LOGIN_LOCKOUT_TTL`` seconds. The
block is persisted on the ``User`` row (``login_locked_until``) so it survives a
cache flush and can be released early by an admin.

This mirrors the OTP throttling philosophy in ``apps.accounts.otp`` but uses the
database (not Redis) because the requirement is to register the block in the DB
and allow administrative release.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger('apps.accounts')

# Reduced to 3 — matches the product requirement (max 3 invalid attempts).
MAX_LOGIN_ATTEMPTS = 3
# 15-minute lockout after MAX_LOGIN_ATTEMPTS failures (same window as the OTP lockout).
LOGIN_LOCKOUT_TTL = 900  # seconds


def is_locked(user) -> bool:
    """True when the user currently has an active login lock."""
    locked_until = getattr(user, 'login_locked_until', None)
    return bool(locked_until and timezone.now() < locked_until)


def seconds_remaining(user) -> int:
    """Whole seconds left on the active lock (0 when not locked)."""
    locked_until = getattr(user, 'login_locked_until', None)
    if not locked_until:
        return 0
    delta = (locked_until - timezone.now()).total_seconds()
    return max(0, int(delta))


def register_failed_attempt(user) -> dict:
    """Record one invalid login attempt.

    Returns a dict describing the new state:
      {'locked': bool, 'attempts': int, 'remaining_attempts': int, 'lock_seconds': int}
    When the threshold is reached the account is locked for LOGIN_LOCKOUT_TTL.
    """
    now = timezone.now()
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    user.last_failed_login_at = now

    locked = False
    if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
        user.login_locked_until = now + timedelta(seconds=LOGIN_LOCKOUT_TTL)
        locked = True
        logger.warning(
            'Login locked for user %s after %d failed attempts',
            user.id, user.failed_login_attempts,
        )
    else:
        logger.info(
            'Failed login for user %s — attempt %d/%d',
            user.id, user.failed_login_attempts, MAX_LOGIN_ATTEMPTS,
        )

    user.save(update_fields=[
        'failed_login_attempts', 'last_failed_login_at', 'login_locked_until',
    ])

    remaining = max(0, MAX_LOGIN_ATTEMPTS - user.failed_login_attempts)
    return {
        'locked': locked,
        'attempts': user.failed_login_attempts,
        'remaining_attempts': remaining,
        'lock_seconds': seconds_remaining(user) if locked else 0,
    }


def reset_attempts(user) -> None:
    """Clear the failure counter and any active lock (called on successful login
    and on administrative unlock)."""
    if user.failed_login_attempts or user.login_locked_until:
        user.failed_login_attempts = 0
        user.login_locked_until = None
        user.save(update_fields=['failed_login_attempts', 'login_locked_until'])
