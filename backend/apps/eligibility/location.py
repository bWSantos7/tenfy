import logging
import math
from functools import lru_cache
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger('apps.eligibility.location')

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

# distance_status values
DISTANCE_WITHIN     = 'within_radius'
DISTANCE_OUTSIDE    = 'outside_radius'
DISTANCE_UNKNOWN    = 'unknown'
DISTANCE_NATIONWIDE = 'nationwide'

# Sentinel value stored in PlayerProfile.travel_radius_km for "Todo o Brasil".
# When set to this value, no distance check is applied — all Brazilian tournaments included.
_BRASIL_RADIUS_KM = 1000

_MSG_UNKNOWN = (
    'Compatível por segurança: a distância não pôde ser calculada. '
    'Verifique a localização do torneio.'
)

_NATIONWIDE_RESULT = {'included': True, 'status': DISTANCE_NATIONWIDE, 'message': None}


def profile_distance_result(profile, edition) -> dict:
    """Return a dict with keys: included (bool), status (str), message (str|None).

    Status values:
      nationwide     — travel_radius_km == 1000 ('Todo o Brasil'); no distance check applied.
      within_radius  — distance computed and within travel_radius_km.
      outside_radius — distance computed and exceeds travel_radius_km.
      unknown        — cannot determine distance; tournament included conservatively.

    Safe fallback rules (all result in included=True, status=unknown):
      - profile has no home city/state.
      - venue missing or has no city/state.
      - geocoding fails or coordinates not stored.
    """
    # "Todo o Brasil": no distance limit — include without any calculation.
    if getattr(profile, 'travel_radius_km', 0) >= _BRASIL_RADIUS_KM:
        return _NATIONWIDE_RESULT

    def _unknown(reason: str = '') -> dict:
        if reason:
            logger.debug('Distance unknown — %s', reason)
        return {'included': True, 'status': DISTANCE_UNKNOWN, 'message': _MSG_UNKNOWN}

    if not profile.home_city or not profile.home_state:
        return _unknown('profile has no home city/state')

    venue = edition.venue
    if not venue or not venue.city or not venue.state:
        return _unknown('venue missing or has no city/state')

    if _same_city(profile.home_city, venue.city) and profile.home_state.upper() == venue.state.upper():
        return {'included': True, 'status': DISTANCE_WITHIN, 'message': None}

    # Fast path: pre-stored coordinates
    if (
        profile.home_lat is not None and profile.home_lng is not None
        and venue.latitude is not None and venue.longitude is not None
    ):
        distance_km = haversine_km(
            profile.home_lat, profile.home_lng,
            venue.latitude, venue.longitude,
        )
        within = distance_km <= profile.travel_radius_km
        return {
            'included': within,
            'status': DISTANCE_WITHIN if within else DISTANCE_OUTSIDE,
            'message': None,
        }

    # Slow path: geocode via Nominatim
    distance_km = calculate_profile_distance_km(
        profile.home_city,
        profile.home_state,
        venue.city,
        venue.state,
        getattr(venue, 'address', '') or '',
    )
    if distance_km is None:
        return _unknown(
            f'geocoding failed for profile={profile.home_city}/{profile.home_state} '
            f'venue={venue.city}/{venue.state}'
        )

    within = distance_km <= profile.travel_radius_km
    return {
        'included': within,
        'status': DISTANCE_WITHIN if within else DISTANCE_OUTSIDE,
        'message': None,
    }


def within_profile_radius(profile, edition) -> bool:
    """Bool convenience wrapper around profile_distance_result.
    Kept for backwards compatibility — prefer profile_distance_result() for new callers."""
    return profile_distance_result(profile, edition)['included']


def geocode_and_save_profile(profile) -> bool:
    """
    Geocode a profile's home_city/state and persist lat/lng.
    Called from profile post-save signal when city or state changes.
    Returns True if coordinates were updated.
    """
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
    origin_city: str,
    origin_state: str,
    venue_city: str,
    venue_state: str,
    venue_address: str = '',
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
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
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
            params={
                'q': query,
                'format': 'jsonv2',
                'limit': 1,
                'countrycodes': 'br',
            },
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
