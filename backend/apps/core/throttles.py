from rest_framework.throttling import UserRateThrottle


class HeavyUserThrottle(UserRateThrottle):
    """30 req/min for CPU-intensive endpoints (eligibility engine, calendar)."""
    scope = 'heavy_user'


class HeavyAnonThrottle(UserRateThrottle):
    """10 req/min for unauthenticated access to heavy endpoints."""
    scope = 'heavy_anon'
