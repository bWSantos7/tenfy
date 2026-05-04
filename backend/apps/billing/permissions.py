"""
Feature-gate permission system.

Usage in views:
    from apps.billing.permissions import requires_feature, user_has_feature

    @api_view(['GET'])
    @requires_feature('advanced_stats')
    def my_view(request):
        ...

    # Programmatic check:
    if user_has_feature(request.user, 'ranking_access'):
        ...
"""
import functools
import logging

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from .models import Feature, Subscription

logger = logging.getLogger('apps.billing')

_FEATURE_CACHE_TTL = 300   # 5 minutes — short enough to reflect plan changes quickly
_PLAN_FEATURE_CACHE_TTL = 3600  # plan features rarely change


def _user_features_cache_key(user_id: int) -> str:
    return f'billing:features:{user_id}'


def _invalidate_user_features_cache(user_id: int):
    """Call this whenever a user's subscription changes."""
    cache.delete(_user_features_cache_key(user_id))


def get_user_subscription(user) -> 'Subscription | None':
    """Return the user's active Subscription, or None."""
    try:
        return user.subscription
    except Subscription.DoesNotExist:
        return None


def _get_plan_feature_codes(plan) -> set:
    """Return the set of feature codes for a plan (cached per plan slug)."""
    cache_key = f'billing:plan_features:{plan.slug}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    codes = set(plan.plan_features.values_list('feature__code', flat=True))
    cache.set(cache_key, codes, _PLAN_FEATURE_CACHE_TTL)
    return codes


def _get_user_active_feature_codes(user) -> set:
    """
    Return the set of feature codes available to this user.
    Result is cached per user for _FEATURE_CACHE_TTL seconds.
    """
    cache_key = _user_features_cache_key(user.id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sub = get_user_subscription(user)
    if sub is None or not sub.is_active:
        from .models import Plan
        try:
            individual_plan = Plan.objects.prefetch_related('plan_features__feature').get(slug=Plan.SLUG_INDIVIDUAL)
            codes = _get_plan_feature_codes(individual_plan)
        except Plan.DoesNotExist:
            codes = set()
    else:
        codes = set(
            sub.plan.plan_features.values_list('feature__code', flat=True)
        )

    cache.set(cache_key, codes, _FEATURE_CACHE_TTL)
    return codes


def user_has_feature(user, feature_code: str) -> bool:
    """
    Return True if the user's current subscription includes the feature.
    Result is cached per user for 5 minutes.
    """
    return feature_code in _get_user_active_feature_codes(user)


def user_feature_limit(user, feature_code: str):
    """
    Return usage limit for a feature (None = unlimited, 0 = no access).
    Not cached individually — used rarely compared to user_has_feature.
    """
    sub = get_user_subscription(user)
    if sub is None or not sub.is_active:
        from .models import Plan
        try:
            individual_plan = Plan.objects.get(slug=Plan.SLUG_INDIVIDUAL)
            pf = individual_plan.plan_features.filter(feature__code=feature_code).first()
            return pf.limit if pf else 0
        except Plan.DoesNotExist:
            return 0

    return sub.feature_limit(feature_code)


def requires_feature(feature_code: str):
    """
    Decorator for DRF api_view functions.
    Returns HTTP 403 with upgrade prompt if feature is not available.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'detail': 'Autenticação necessária.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not user_has_feature(request.user, feature_code):
                sub = get_user_subscription(request.user)
                current_plan = sub.plan.name if sub else 'Individual'
                return Response(
                    {
                        'detail': f'Recurso "{feature_code}" não está disponível no plano {current_plan}.',
                        'feature_code': feature_code,
                        'current_plan': current_plan,
                        'upgrade_required': True,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class HasFeature:
    """
    DRF permission class for use in ViewSets:

        permission_classes = [IsAuthenticated, HasFeature('tournament_creation')]
    """
    def __init__(self, feature_code: str):
        self.feature_code = feature_code

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return user_has_feature(request.user, self.feature_code)

    def __call__(self):
        return self
