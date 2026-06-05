import math
import re
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
# Distance/scope statuses (when the profile has a single federation).
DISTANCE_NATIONAL = 'national'              # CBT/confederação nacional — aberto a qualquer federação
DISTANCE_INTERNATIONAL = 'international'      # ITF/COSAT — aberto a qualquer federação, inscrição por aceitação
DISTANCE_OWN_FEDERATION = 'own_federation'   # estadual da própria federação do atleta
DISTANCE_OTHER_FEDERATION = 'other_federation'  # estadual de outra federação — incompatível

# Entry model: distinguishes guaranteed entry from acceptance-list circuits.
ENTRY_MODEL_DIRECT = 'direct'                # inscrição direta (vaga conforme regras da fonte)
ENTRY_MODEL_ACCEPTANCE = 'acceptance_list'   # vaga sujeita a ranking/lista/quali/wild card/IPIN

_ENTRY_ACCEPTANCE_MESSAGE = (
    'Inscrição sujeita à aceitação por ranking/lista de entrada e regras do torneio.'
)


# ── Federation-scope helpers ────────────────────────────────────────────────────
# Organization.type values (apps.sources.models.Organization) referenced as
# literals to avoid an import cycle (sources ← eligibility).
_ORG_CONFEDERATION = 'confederation'   # CBT, COSAT, ITF — nacional/internacional
_ORG_FEDERATION = 'federation'         # federação estadual (tem UF)
_ORG_PLATFORM = 'platform'             # UTR — torneios por rating, não atrelados a federação

# Confederations whose circuits are international official tours: any compatible
# athlete may try to enter, but a vaga depende de aceitação (ranking/lista/quali/
# wild card/IPIN). Matched by Organization.short_name.
_INTERNATIONAL_CONFED = {'ITF', 'COSAT'}

# Whole-word patterns that flag a tournament as national (open to athletes of any
# federation). Word boundaries (\b) avoid false positives such as matching
# "nacional" inside "internacional" or a substring inside an unrelated club name.
# The primary, reliable national signal is org.type == confederation; this keyword
# pattern is only a safety net for nationally-titled events that happen to be
# linked to a state federation org.
#
# NB: "Aberto/Abertos" is intentionally NOT a compatibility signal — a tournament
# from another federation is incompatible even when titled "Aberto" (produto).
_NATIONAL_RE = re.compile(r'\b(nacional|brasileiro|brasileira)\b')


def _edition_organization(edition):
    tournament = getattr(edition, 'tournament', None)
    return getattr(tournament, 'organization', None) if tournament is not None else None


def _scope_text(edition) -> str:
    """Lowercased haystack of circuit/name/title to detect national/open scope.
    Coerces every part to str so MagicMock-based unit tests never raise on join."""
    parts = []
    tournament = getattr(edition, 'tournament', None)
    if tournament is not None:
        parts.append(str(getattr(tournament, 'circuit', '') or ''))
        parts.append(str(getattr(tournament, 'canonical_name', '') or ''))
    parts.append(str(getattr(edition, 'title', '') or ''))
    return ' '.join(parts).lower()


def _is_national_scope(edition, org) -> bool:
    org_type = getattr(org, 'type', None) if org is not None else None
    if org_type == _ORG_CONFEDERATION:
        return True
    return bool(_NATIONAL_RE.search(_scope_text(edition)))


def federation_compatibility(profile, edition):
    """
    Federation-aware compatibility for a profile that competes for a single
    federation. Returns the same {'included', 'status', 'message'} shape as
    profile_state_result, or None when the profile has no federation (caller
    then falls back to the legacy travel_states/home_state logic).

    Rules (per produto):
      1. Internacional (ITF/COSAT) → compatível para qualquer federação, mas a
         inscrição é "sujeita à aceitação" (entry_guarantee=False).
      2. Nacional/CBT (confederação) ou plataforma (UTR) → compatível para
         qualquer federação.
      3. Estadual da própria federação do atleta → compatível.
      4. Estadual de outra federação → NÃO compatível, mesmo quando "Aberto".
      5. Sem organização identificada → cai para a UF do local vs UF da federação.

    The returned dict may carry 'entry_guarantee' (bool) and 'entry_model'
    (ENTRY_MODEL_*). When absent, the caller treats entry as guaranteed/direct.
    """
    fed_state = (getattr(profile, 'federation_state', '') or '').upper()
    if not fed_state:
        return None

    org = _edition_organization(edition)
    org_type = getattr(org, 'type', None) if org is not None else None
    org_short = (getattr(org, 'short_name', '') or '').upper() if org is not None else ''

    # 1) International official tours (ITF/COSAT) → compatible for any federation,
    # but entry is subject to acceptance (ranking/lista/quali/wild card/IPIN).
    if org_type == _ORG_CONFEDERATION and org_short in _INTERNATIONAL_CONFED:
        return {
            'included': True,
            'status': DISTANCE_INTERNATIONAL,
            'message': _ENTRY_ACCEPTANCE_MESSAGE,
            'entry_guarantee': False,
            'entry_model': ENTRY_MODEL_ACCEPTANCE,
        }

    # 2) National (CBT/other confederation) / rating-based (UTR) → open to everyone.
    if _is_national_scope(edition, org) or org_type == _ORG_PLATFORM:
        return {'included': True, 'status': DISTANCE_NATIONAL, 'message': None}

    # 3/4) State federation tournament — only the athlete's own federation is
    # compatible. Other federations are excluded even when titled "Aberto":
    # apenas torneios nacionais/CBT abrem para atletas de qualquer federação.
    if org_type == _ORG_FEDERATION:
        prof_fed_id = getattr(profile, 'federation_id', None)
        org_id = getattr(org, 'id', None)
        org_state = (getattr(org, 'state', '') or '').upper()
        # Match by UF first — the canonical key. This is robust to duplicate
        # federation orgs (e.g. accented "Federação Paulista de Tênis" vs the
        # ingestion-created "Federacao Paulista de Tenis"), which would otherwise
        # fail an id-only comparison and wrongly exclude the athlete's own
        # federation. Falls back to id match when the org has no UF.
        same_federation = (
            (org_state and org_state == fed_state)
            or (prof_fed_id and org_id and prof_fed_id == org_id)
        )
        if same_federation:
            return {'included': True, 'status': DISTANCE_OWN_FEDERATION, 'message': None}
        return {
            'included': False,
            'status': DISTANCE_OTHER_FEDERATION,
            'message': 'Torneio estadual de outra federação.',
        }

    # 4) Organization unknown — compare the venue UF to the federation UF.
    venue = edition.venue
    if not venue or not venue.state:
        return {
            'included': True,
            'status': DISTANCE_UNKNOWN,
            'message': 'Estado do torneio não identificado. Verifique o regulamento oficial.',
        }
    included = venue.state.upper() == fed_state
    return {
        'included': included,
        'status': DISTANCE_WITHIN if included else DISTANCE_OUTSIDE,
        'message': None if included else 'Torneio fora da UF da sua federação.',
    }


# ── State-based check (primary, replaces radius for new profiles) ──────────────

def within_profile_states(profile, edition) -> bool:
    """
    Primary location check: profile.federation (UF) / travel_states vs edition.venue.state.

    Priority:
      1. profile.federation_state — the player competes for a single federation;
         only its UF is considered in-region.
      2. profile.travel_states — legacy multi-state selection (fallback).
      3. home_state / radius — fallback for incomplete profiles.

    Returns True (optimistic) when the tournament has no venue/state — caller
    should flag this as DISTANCE_UNKNOWN in the API response.
    """
    fed = federation_compatibility(profile, edition)
    if fed is not None:
        return fed['included']

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

    The player's federation drives compatibility (see federation_compatibility);
    it falls back to the legacy travel_states when no federation is set.
    """
    fed = federation_compatibility(profile, edition)
    if fed is not None:
        return fed

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
