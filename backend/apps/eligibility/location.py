import math
from functools import lru_cache

import requests
from django.conf import settings


NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'


def within_profile_radius(profile, edition) -> bool:
    if not profile.home_city or not profile.home_state:
        return True
    venue = edition.venue
    if not venue or not venue.city or not venue.state:
        return False

    if _same_city(profile.home_city, venue.city) and profile.home_state.upper() == venue.state.upper():
        return True

    # Fast path: use pre-stored coordinates when available on both sides
    if (
        profile.home_lat is not None and profile.home_lng is not None
        and venue.latitude is not None and venue.longitude is not None
    ):
        distance_km = haversine_km(profile.home_lat, profile.home_lng, venue.latitude, venue.longitude)
        return distance_km <= profile.travel_radius_km

    # Slow path: geocode via Nominatim (results are LRU-cached per process)
    distance_km = calculate_profile_distance_km(
        profile.home_city,
        profile.home_state,
        venue.city,
        venue.state,
        venue.address,
    )
    if distance_km is None:
        return False
    return distance_km <= profile.travel_radius_km


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
