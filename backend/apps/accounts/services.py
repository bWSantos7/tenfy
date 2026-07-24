"""Domain rules for parent/child (responsável ↔ jogador/dependente) links.

Business rule (Área 5):
  - A player/dependent may normally be linked to a single responsável.
  - Exception — Tester plan: if the dependent OR any responsável (current or the
    one being added) is on the Tester plan, up to 2 responsáveis are allowed.
  - Exception — Família plan: a Família subscription allows up to
    ``plan.max_responsibles`` (2 today) responsáveis sharing the same subscription.
    The second responsável does not need their own subscription — they inherit the
    titular's via ``FamilyMembership`` (see apps.billing.models.get_effective_subscription).
  - Both exceptions independently cap at their own limit; the effective limit is the
    max of whichever exceptions apply (never a "first match wins").

This is distinct from the dependent-count limit (how many children a family may
have). For Família, the family has plan.max_members profiles total (5 today),
split dynamically between responsáveis and dependentes — with only 1 responsável,
the spare seat can hold an extra dependent instead. Both rules coexist, and both
are scoped to the whole family (shared quota), not per-responsável.
"""
import logging

from django.contrib.auth import get_user_model
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


def _familia_subscription_for_link(child, new_parent):
    """Return the active Família subscription relevant to this link, if any.

    Checked in order: the child's effective subscription, the prospective
    parent's, then every current responsável's. Uses get_effective_subscription so
    an already-linked co-responsável (who has no subscription of their own) is
    still recognised as being "on" the family plan.
    """
    from apps.billing.models import Plan, get_effective_subscription
    from .models import ParentChild

    for candidate in (child, new_parent):
        sub = get_effective_subscription(candidate)
        if sub is not None and sub.plan.slug == Plan.SLUG_FAMILIA and sub.is_active:
            return sub

    current_parents = (
        ParentChild.objects
        .filter(child=child, is_active=True)
        .select_related('parent')
    )
    for link in current_parents:
        sub = get_effective_subscription(link.parent)
        if sub is not None and sub.plan.slug == Plan.SLUG_FAMILIA and sub.is_active:
            return sub
    return None


def familia_exception_applies(child, new_parent) -> bool:
    """Whether the Família exception (up to plan.max_responsibles) applies."""
    return _familia_subscription_for_link(child, new_parent) is not None


def familia_responsible_limit(child, new_parent) -> int:
    sub = _familia_subscription_for_link(child, new_parent)
    return sub.plan.max_responsibles if sub else MAX_RESPONSIBLES_DEFAULT


def responsible_limit(child, new_parent) -> int:
    limit = MAX_RESPONSIBLES_DEFAULT
    if tester_exception_applies(child, new_parent):
        limit = max(limit, MAX_RESPONSIBLES_TESTER)
    if familia_exception_applies(child, new_parent):
        limit = max(limit, familia_responsible_limit(child, new_parent))
    return limit


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
                'Cada jogador pode ter apenas um responsável (até dois nos planos '
                'Tester ou Família).'
            )
        else:
            msg = (
                'Este jogador/dependente já atingiu o limite de responsáveis '
                'vinculados (máximo de dois, nos planos Tester ou Família).'
            )
        raise ValidationError(msg)


def _family_responsible_ids(subscription) -> set:
    """All user ids sharing ``subscription`` as responsáveis: the titular plus any
    active co-responsável (FamilyMembership)."""
    from apps.billing.models import FamilyMembership

    ids = {subscription.user_id}
    ids.update(
        FamilyMembership.objects
        .filter(subscription=subscription, status=FamilyMembership.STATUS_ACTIVE)
        .values_list('member_user_id', flat=True)
    )
    return ids


def family_headcount(subscription) -> tuple:
    """Return (responsible_count, dependent_count) currently active for the family
    anchored on ``subscription``. Both counts are distinct-child/distinct-user."""
    from .models import ParentChild

    responsible_ids = _family_responsible_ids(subscription)
    dependent_count = (
        ParentChild.objects
        .filter(parent_id__in=responsible_ids, is_active=True)
        .values('child').distinct().count()
    )
    return len(responsible_ids), dependent_count


def assert_can_add_dependent(acting_parent, for_update: bool = False) -> None:
    """Raise ValidationError when ``acting_parent`` may not add another dependent.

    The dependent quota is shared by the whole family (titular + active
    co-responsáveis on the same subscription), not counted per-responsável. The
    family has room for max_members profiles total, split dynamically between
    responsáveis and dependentes: with only 1 responsável, the "spare" seat can be
    used for an extra dependent (e.g. max_members=5 → up to 4 dependents with 1
    responsável, or up to 3 with 2 responsáveis).

    Pass ``for_update=True`` (from inside a ``transaction.atomic()`` block, right
    before creating the ParentChild) to lock the family's Subscription row and
    avoid two responsáveis racing past the shared quota concurrently.
    """
    from apps.billing.models import Plan, Subscription, get_effective_subscription
    from .models import ParentChild

    sub = get_effective_subscription(acting_parent)

    if sub is not None and for_update:
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)

    if sub is None:
        # Grace period: allow the very first dependent during onboarding, before
        # any subscription exists. A second one requires an active Família plan.
        current = ParentChild.objects.filter(parent=acting_parent, is_active=True).count()
        if current >= 1:
            raise ValidationError(
                'Você precisa de uma assinatura ativa do Plano Família para '
                'adicionar mais dependentes.',
                code='forbidden',
            )
        return

    if sub.plan.slug == Plan.SLUG_INDIVIDUAL:
        raise ValidationError(
            'O Plano Individual não permite cadastrar dependentes. '
            'Faça upgrade para o Plano Família.',
            code='forbidden',
        )

    responsible_count, current = family_headcount(sub)
    max_dependents = max(sub.plan.max_members - responsible_count, 0)
    if current >= max_dependents:
        raise ValidationError(
            f'Limite de {max_dependents} dependente(s) atingido para o seu plano. '
            'Faça upgrade para adicionar mais.',
            code='limit',
        )


def mirror_to_co_responsibles(child, acting_parent) -> None:
    """Mirror a newly (re)activated child link to every other active responsável
    sharing the same family subscription, so both responsáveis see the same
    dependents.

    Best-effort / non-critical: never raises. A failure here must not undo the
    primary ParentChild link the caller just created.
    """
    try:
        from apps.billing.models import get_effective_subscription
        from .models import ParentChild

        sub = get_effective_subscription(acting_parent)
        if sub is None:
            return

        co_ids = _family_responsible_ids(sub) - {acting_parent.pk}
        if not co_ids:
            return

        User = get_user_model()
        for co_responsible in User.objects.filter(pk__in=co_ids):
            try:
                assert_can_link_responsible(child, co_responsible)
            except ValidationError:
                # Structural cap already guarantees this never happens in practice
                # (family cap is max_responsibles); skip silently if data is stale.
                continue
            ParentChild.objects.get_or_create(
                parent=co_responsible, child=child, defaults={'is_active': True},
            )
    except Exception:  # noqa: BLE001 — housekeeping must never break the caller
        logger.exception(
            'mirror_to_co_responsibles failed: child=%s acting_parent=%s',
            getattr(child, 'id', None), getattr(acting_parent, 'id', None),
        )
