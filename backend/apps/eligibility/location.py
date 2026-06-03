import math
from functools import lru_cache

import requests
from django.conf import settings


NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

ALL_BR_STATES = frozenset({
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO',
    'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI',
    'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO',
})

# Distance status constants (used by compatible endpoint for transparent reporting).
DISTANCE_WITHIN = 'within_radius'
DISTANCE_OUTSIDE = 'outside_radius'
DISTANCE_UNKNOWN = 'unknown'
DISTANCE_NATIONWIDE = 'nationwide'


# ── State-based check (primary, replaces radius for new profiles) ──────────────

def within_profile_states(profile, edition) -> bool:
    """
    Primary location check: profile.travel_states vs edition.venue.state.

    Returns True when the tournament state is among the player's accepted states,
    or when travel_states covers all Brazilian states (Todo o Brasil).

    Returns True (optimistic) when the tournament has no venue/state — caller
    should flag this as DISTANCE_UNKNOWN in the API response.
    """
    states = list(profile.travel_states or [])

    if not states:
        home_state = (getattr(profile, 'home_state', '') or '').upper()
        venue = edition.venue
        if home_state and venue and venue.state:
            return venue.state.upper() == home_state
        if home_state and (not venue or not venue.state):
            return True
        # No state data at all — fall back to legacy radius so old incomplete
        # profiles keep their previous optimistic behaviour.
        return within_profile_radius(profile, edition)

    # "Todo o Brasil" shortcut: all 27 UFs selected
    normalised = {s.upper() for s in states}
    if normalised >= ALL_BR_STATES:
        return True

    venue = edition.venue
    if not venue or not venue.state:
        # Unknown venue state — include optimistically
        return True

    return venue.state.upper() in normalised


def profile_state_result(profile, edition) -> dict:
    """
    Detailed state check result for the API response.
    Returns {'included': bool, 'status': str, 'message': str|None}.
    """
    states = list(profile.travel_states or [])

    if not states:
        home_state = (getattr(profile, 'home_state', '') or '').upper()
        venue = edition.venue
        if home_state and venue and venue.state:
            included = venue.state.upper() == home_state
            return {
                'included': included,
                'status': DISTANCE_WITHIN if included else DISTANCE_OUTSIDE,
                'message': None if included else 'Torneio fora da UF do perfil.',
            }
        if home_state and (not venue or not venue.state):
            return {
                'included': True,
                'status': DISTANCE_UNKNOWN,
                'message': 'Estado do torneio não identificado. Verifique o regulamento oficial.',
            }
        # No state data at all — fall back to radius check; flag as unknown so
        # the UI prompts the user to configure states.
        included = within_profile_radius(profile, edition)
        return {
            'included': included,
            'status': DISTANCE_UNKNOWN,
            'message': 'Selecione os estados onde você aceita jogar para refinar a compatibilidade.',
        }

    normalised = {s.upper() for s in states}
    if normalised >= ALL_BR_STATES:
        return {'included': True, 'status': DISTANCE_NATIONWIDE, 'message': None}

    venue = edition.venue
    if not venue or not venue.state:
        return {
            'included': True,
            'status': DISTANCE_UNKNOWN,
            'message': 'Estado do torneio não identificado. Verifique o regulamento oficial.',
        }

    if venue.state.upper() in normalised:
        return {'included': True, 'status': DISTANCE_WITHIN, 'message': None}

    return {'included': False, 'status': DISTANCE_OUTSIDE, 'message': None}


# ── Legacy radius check (kept for backwards compatibility) ──────────────────────

# Sentinel: travel_radius_km >= this value means "Todo o Brasil" — no distance check.
_BRASIL_RADIUS_KM = 1000


def within_profile_radius(profile, edition) -> bool:
    """Legacy: radius-based check. Used as fallback when travel_states is empty."""
    if (profile.travel_radius_km or 0) >= _BRASIL_RADIUS_KM:
        return True

    if not profile.home_city or not profile.home_state:
        return True
    venue = edition.venue
    if not venue or not venue.city or not venue.state:
        return True

    if _same_city(profile.home_city, venue.city) and profile.home_state.upper() == venue.state.upper():
        return True

    if (
        profile.home_lat is not None and profile.home_lng is not None
        and venue.latitude is not None and venue.longitude is not None
    ):
        distance_km = haversine_km(profile.home_lat, profile.home_lng, venue.latitude, venue.longitude)
        return distance_km <= profile.travel_radius_km

    distance_km = calculate_profile_distance_km(
        profile.home_city, profile.home_state, venue.city, venue.state,
        getattr(venue, 'address', '') or '',
    )
    if distance_km is None:
        return True  # Geocoding failed — include optimistically
    return distance_km <= profile.travel_radius_km


def geocode_and_save_profile(profile) -> bool:
    if not profile.home_city or not profile.home_state:
        return False
    coords = geocode_location(profile.home_city, profile.home_state)
    if not coords:
        return False
    lat, lng = coords
    from apps.players.models import PlayerProfile
    PlayerProfile.objects.filter(pk=profile.pk).update(home_lat=lat, home_lng=lng)
    profile.home_lat = lat
    profile.home_lng = lng
    return True


def calculate_profile_distance_km(
    origin_city: str, origin_state: str,
    venue_city: str, venue_state: str, venue_address: str = '',
):
    origin = geocode_location(origin_city, origin_state)
    destination = geocode_location(venue_city, venue_state, venue_address)
    if not origin or not destination:
        return None
    return haversine_km(origin[0], origin[1], destination[0], destination[1])


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


@lru_cache(maxsize=512)
def geocode_location(city: str, state: str, address: str = ''):
    query_parts = [address.strip(), city.strip(), state.strip(), 'Brasil']
    query = ', '.join(part for part in query_parts if part)
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={'q': query, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'br'},
            headers={'User-Agent': getattr(settings, 'SCRAPER_USER_AGENT', 'TenfyBot/1.0')},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return None
        item = payload[0]
        return float(item['lat']), float(item['lon'])
    except Exception:
        return None


def _same_city(a: str, b: str) -> bool:
    return _normalize_city(a) == _normalize_city(b)


def _normalize_city(value: str) -> str:
    import re
    import unicodedata
    normalized = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^a-zA-Z0-9]+', ' ', normalized).strip().lower()
    return normalized
