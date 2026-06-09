"""Domain rules for parent/child (responsável ↔ jogador/dependente) links.

Business rule (Área 5):
  - A player/dependent may normally be linked to a single responsável.
  - Exception — Tester plan: if the dependent OR any responsável (current or the
    one being added) is on the Tester plan, up to 2 responsáveis are allowed.
  - Hard cap is always 2: the 3rd link is blocked even on the Tester plan.

This is distinct from the dependent-count limit (how many children a parent may
have, driven by plan.max_members). Both rules coexist.
"""
import logging

from django.core.exceptions import ValidationError

logger = logging.getLogger('apps.accounts')

MAX_RESPONSIBLES_DEFAULT = 1
MAX_RESPONSIBLES_TESTER = 2  # hard cap — never exceeded, even on Tester


def _has_active_tester(user) -> bool:
    """True when the user holds an active/trial subscription on the Tester plan."""
    if user is None:
        return False
    try:
        from apps.billing.models import Plan, Subscription
        sub = user.subscription
    except Exception:  # noqa: BLE001 — no subscription row, etc.
        return False
    return (
        sub.plan_id is not None
        and sub.plan.slug == Plan.SLUG_TESTER
        and sub.status in (Subscription.STATUS_ACTIVE, Subscription.STATUS_TRIAL)
    )


def tester_exception_applies(child, new_parent) -> bool:
    """Whether the Tester exception (up to 2 responsáveis) applies for this link.

    Applies when the child OR the prospective parent OR any current responsável
    is on the Tester plan.
    """
    from .models import ParentChild

    if _has_active_tester(child) or _has_active_tester(new_parent):
        return True

    current_parents = (
        ParentChild.objects
        .filter(child=child, is_active=True)
        .select_related('parent')
    )
    return any(_has_active_tester(link.parent) for link in current_parents)


def responsible_limit(child, new_parent) -> int:
    return (
        MAX_RESPONSIBLES_TESTER
        if tester_exception_applies(child, new_parent)
        else MAX_RESPONSIBLES_DEFAULT
    )


def assert_can_link_responsible(child, new_parent) -> None:
    """Raise ValidationError when linking ``new_parent`` as a responsável of
    ``child`` would violate the responsible-count rule.

    Idempotent: an already-active link between the same pair does not count, so
    re-finalising an existing link never fails.
    """
    from .models import ParentChild

    active_parents = ParentChild.objects.filter(child=child, is_active=True)
    # Re-linking the same parent is a no-op for the count.
    other_parents = active_parents.exclude(parent=new_parent)
    count = other_parents.count()

    limit = responsible_limit(child, new_parent)
    if count >= limit:
        logger.info(
            'Blocked responsible link: child=%s new_parent=%s current=%d limit=%d',
            getattr(child, 'id', None), getattr(new_parent, 'id', None), count, limit,
        )
        if limit == MAX_RESPONSIBLES_DEFAULT:
            msg = (
                'Este jogador/dependente já está vinculado a um responsável. '
                'Cada jogador pode ter apenas um responsável (até dois no plano Tester).'
            )
        else:
            msg = (
                'Este jogador/dependente já atingiu o limite de responsáveis '
                'vinculados (máximo de dois no plano Tester).'
            )
        raise ValidationError(msg)
