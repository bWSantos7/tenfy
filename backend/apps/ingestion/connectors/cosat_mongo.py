"""
COSAT MongoDB connector — reads from the external crawler service.

The crawler (https://github.com/bWSantos7/crawler.git) runs independently
on Railway and writes COSAT tournament/player/ranking data to a dedicated
MongoDB. This module provides read-only access to that MongoDB.

Collections (crawler Mongoose models → MongoDB collection names):
  Tournament   → 'tournaments'   (COSAT_MONGO_COLLECTION_TOURNAMENTS)
  Player       → 'players'       (COSAT_MONGO_COLLECTION_ENTRIES)
  RankingEntry → 'rankingentries'(COSAT_MONGO_COLLECTION_RANKINGS)

Document schemas (from crawler /src/models/):
  Tournament:
    cosatId*, name*, url*, organization, location, country, dateRange,
    events[{eventId, name, draws, entries}], categoriesCount, entriesCount,
    playersCount, lastUpdated, createdAt, updatedAt

  Player:
    name*, tournamentId, tournamentPlayerId, rankingPlayerId, profileId,
    dob, rankingCategory, lastUpdated, createdAt, updatedAt

  RankingEntry:
    rankingId, rankingDate, updatedText, category*, rank*, playerName*,
    playerId, profileId, country, dob, singlesPoints, doublesPoints,
    bonusPoints, totalPoints, sourceUrl*, lastUpdated, createdAt, updatedAt

Design:
  - Read-only — never writes to MongoDB.
  - Offline-safe — logs warning, returns empty iterator if unavailable.
  - Short connection timeout (COSAT_MONGO_CONNECT_TIMEOUT_MS, default 5s).
  - All credentials via env vars / Django settings. Never hardcoded.
"""
import logging
import re
from datetime import datetime
from typing import Iterator, Optional

from django.conf import settings

logger = logging.getLogger('apps.ingestion.cosat_mongo')

def _sanitize_exc(exc: Exception) -> str:
    """Return str(exc) with MongoDB credentials redacted.

    pymongo embeds the full connection URI in some error messages.
    Replace user:password@ with ***:***@ before logging.
    """
    msg = str(exc)
    # Pattern: mongodb[+srv]://user:pass@host or mongodb://user:pass@host
    sanitized = re.sub(
        r'(mongodb(?:\+srv)?://)([^@]+)@',
        r'\1***:***@',
        msg,
    )
    return sanitized


# Month abbreviation map (EN + ES/PT abbreviations from COSAT)
# Spanish months added: ene, abr, may, jun, jul, ago, sep, oct, nov, dic
_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'ene': 1, 'abr': 4, 'ago': 8, 'set': 9, 'out': 10, 'dez': 12,
    'dic': 12,  # Spanish December
}

# COSAT event code → Portuguese description
# Used to normalize BS/GS/BD/GD codes to human-readable category names.
_COSAT_EVENT_CODES = {
    'BS': 'Masculino Simples',   # Boys Singles
    'GS': 'Feminino Simples',    # Girls Singles
    'BD': 'Masculino Duplas',    # Boys Doubles
    'GD': 'Feminino Duplas',     # Girls Doubles
    'XD': 'Duplas Mistas',       # Mixed Doubles
    'MS': 'Masculino Simples',   # alternate notation
    'WS': 'Feminino Simples',
    'MD': 'Masculino Duplas',
    'WD': 'Feminino Duplas',
}


# ── Connection ────────────────────────────────────────────────────────────────

def _get_client():
    """
    Build and return a pymongo MongoClient.
    Raises ImportError if pymongo is missing.
    Raises ValueError if COSAT_MONGO_URL is not configured.
    The caller is responsible for handling ConnectionFailure.
    """
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise ImportError(
            'pymongo not installed. Add pymongo to requirements.txt.'
        ) from exc

    url = getattr(settings, 'COSAT_MONGO_URL', '')
    if not url:
        raise ValueError(
            'COSAT_MONGO_URL is not configured. '
            'Set it in Railway Variables for the backend service.'
        )

    timeout_ms = getattr(settings, 'COSAT_MONGO_CONNECT_TIMEOUT_MS', 5000)
    return MongoClient(
        url,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
    )


# ── Connector class ───────────────────────────────────────────────────────────

class CosatMongoConnector:
    """
    Read-only connector to the COSAT crawler MongoDB.

    Usage:
        conn = CosatMongoConnector()
        if not conn.is_available():
            logger.warning('COSAT Mongo offline — skipping')
            return
        for t in conn.iter_tournaments(limit=10):
            ...  # normalized tournament dict
        conn.close()
    """

    def __init__(self):
        self._client = None
        self._db = None
        self._available: Optional[bool] = None

    def _connect(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            self._client = _get_client()
            db_name = getattr(settings, 'COSAT_MONGO_DB', '')
            if not db_name:
                raise ValueError(
                    'COSAT_MONGO_DB is empty. '
                    'Set it in Railway Variables (e.g. COSAT_MONGO_DB=cosat_db).'
                )
            self._db = self._client[db_name]
            # Trigger actual network check (throws ServerSelectionTimeoutError if down)
            self._client.admin.command('ping')
            self._available = True
            logger.info('CosatMongoConnector: connected to db=%s', db_name)
        except Exception as exc:
            # Sanitize: never log the raw URI which may contain credentials
            safe_exc = _sanitize_exc(exc)
            logger.warning(
                'CosatMongoConnector: MongoDB unavailable — %s. '
                'COSAT data will be skipped this run. '
                'Check COSAT_MONGO_URL and Railway connectivity.',
                safe_exc,
            )
            self._available = False

        return self._available

    def is_available(self) -> bool:
        """True when MongoDB is reachable. Safe to call multiple times."""
        return self._connect()

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._db = None
            self._available = None

    def _collection(self, setting_key: str, default: str):
        name = getattr(settings, setting_key, default)
        return self._db[name]

    # ── Tournament iteration ──────────────────────────────────────────────────

    def iter_tournaments(self, limit: int = 0, cosat_id: str = '') -> Iterator[dict]:
        """
        Yield normalized tournament dicts from the tournaments collection.

        Args:
            limit: max documents to return (0 = all)
            cosat_id: filter to a specific tournament (by cosatId field)

        Yields:
            dict conforming to connector base schema + '_raw' key for extras
        """
        if not self.is_available():
            return

        coll = self._collection('COSAT_MONGO_COLLECTION_TOURNAMENTS', 'tournaments')
        query = {}
        if cosat_id:
            query['cosatId'] = cosat_id

        cursor = coll.find(query)
        if limit:
            cursor = cursor.limit(limit)

        for doc in cursor:
            try:
                normalized = _normalize_tournament(doc)
                if normalized:
                    yield normalized
                else:
                    logger.debug('CosatMongo: skipped tournament (missing cosatId/name): %s',
                                 doc.get('_id'))
            except Exception as exc:
                logger.warning('CosatMongo: failed to normalize tournament %s — %s',
                               doc.get('cosatId', '?'), exc)

    def iter_players(self, tournament_id: str = '', limit: int = 0) -> Iterator[dict]:
        """
        Yield normalized player/entry dicts from the players collection.

        Args:
            tournament_id: filter by tournamentId (= cosatId of parent tournament)
            limit: max documents to return (0 = all)
        """
        if not self.is_available():
            return

        coll = self._collection('COSAT_MONGO_COLLECTION_ENTRIES', 'players')
        query = {}
        if tournament_id:
            query['tournamentId'] = tournament_id

        cursor = coll.find(query)
        if limit:
            cursor = cursor.limit(limit)

        for doc in cursor:
            try:
                normalized = _normalize_player(doc)
                if normalized:
                    yield normalized
            except Exception as exc:
                logger.warning('CosatMongo: failed to normalize player %s — %s',
                               doc.get('name', '?'), exc)

    def iter_rankings(self, category: str = '', limit: int = 0) -> Iterator[dict]:
        """
        Yield normalized ranking entry dicts from the rankingentries collection.

        Args:
            category: filter by category field (e.g. 'Singles', 'Doubles')
            limit: max documents to return (0 = all)
        """
        if not self.is_available():
            return

        coll = self._collection('COSAT_MONGO_COLLECTION_RANKINGS', 'rankingentries')
        query = {}
        if category:
            query['category'] = category

        cursor = coll.find(query)
        if limit:
            cursor = cursor.limit(limit)

        for doc in cursor:
            try:
                normalized = _normalize_ranking(doc)
                if normalized:
                    yield normalized
            except Exception as exc:
                logger.warning('CosatMongo: failed to normalize ranking %s — %s',
                               doc.get('playerName', '?'), exc)

    def count_tournaments(self) -> int:
        if not self.is_available():
            return 0
        coll = self._collection('COSAT_MONGO_COLLECTION_TOURNAMENTS', 'tournaments')
        return coll.count_documents({})

    def count_players(self) -> int:
        if not self.is_available():
            return 0
        coll = self._collection('COSAT_MONGO_COLLECTION_ENTRIES', 'players')
        return coll.count_documents({})

    def count_rankings(self) -> int:
        if not self.is_available():
            return 0
        coll = self._collection('COSAT_MONGO_COLLECTION_RANKINGS', 'rankingentries')
        return coll.count_documents({})

    def sample_players_raw(self, tournament_id: str = '', n: int = 3) -> list[dict]:
        """
        Return up to n raw player documents from MongoDB (no normalization).

        Used by --debug-sample to discover real field structure.
        Returns dicts with MongoDB ObjectId stringified to avoid serialization issues.
        """
        if not self.is_available():
            return []
        coll = self._collection('COSAT_MONGO_COLLECTION_ENTRIES', 'players')
        query = {'tournamentId': tournament_id} if tournament_id else {}
        docs = []
        for doc in coll.find(query).limit(n):
            # Convert ObjectId to string — safe for printing
            doc['_id'] = str(doc.get('_id', ''))
            docs.append(doc)
        return docs

    def sample_tournament_raw(self, cosat_id: str) -> Optional[dict]:
        """Return raw tournament document for debug inspection."""
        if not self.is_available():
            return None
        coll = self._collection('COSAT_MONGO_COLLECTION_TOURNAMENTS', 'tournaments')
        doc = coll.find_one({'cosatId': cosat_id})
        if doc:
            doc['_id'] = str(doc.get('_id', ''))
        return doc


# ── Document normalizers (module-level, testable without MongoDB) ─────────────

def _trunc(value: str, max_len: int, label: str = '') -> str:
    """
    Normalize whitespace and truncate to max_len.

    Used to guard CharField values against DB varchar overflow before saving.
    Logs a WARNING when truncation occurs so the raw value is traceable in logs.
    Callers must preserve the original value in _raw for audit.
    """
    if not value:
        return value
    v = ' '.join(value.split())  # collapse whitespace
    if len(v) <= max_len:
        return v
    logger.warning(
        'CosatMongo: field "%s" truncated %d->%d chars: %r...',
        label, len(v), max_len, v[:60],
    )
    return v[:max_len]


def _normalize_tournament(doc: dict) -> Optional[dict]:
    """
    Convert a MongoDB tournaments document to the standard connector dict schema.

    Returns None when mandatory fields (cosatId, name) are absent.
    All date/location parsing is best-effort — missing fields use safe defaults.
    """
    cosat_id = str(doc.get('cosatId') or '').strip()
    if not cosat_id:
        return None

    name = (doc.get('name') or '').strip()
    if not name:
        return None

    source_url = (doc.get('url') or '').strip()
    organization = _strip_emails((doc.get('organization') or 'COSAT').strip())
    if not organization:
        organization = 'COSAT'
    location = (doc.get('location') or '').strip()
    country = (doc.get('country') or 'BR').strip()

    city, state = _parse_location(location, country)

    # Guard DB varchar limits — originals preserved in _raw below.
    # Venue.city max_length=120, Venue.name max_length=200
    city = _trunc(city, 120, f'cosat:{cosat_id}/venue.city')
    organization = _trunc(organization, 200, f'cosat:{cosat_id}/venue.name')

    last_updated = doc.get('lastUpdated') or doc.get('updatedAt') or doc.get('createdAt')

    # Extract year hint from lastUpdated/createdAt for Spanish dateRange parsing
    year_hint = 0
    if isinstance(last_updated, datetime):
        year_hint = last_updated.year
    elif isinstance(last_updated, str) and len(last_updated) >= 4:
        try:
            year_hint = int(last_updated[:4])
        except (ValueError, TypeError):
            pass

    date_range = (doc.get('dateRange') or '').strip()
    
    start_date = None
    end_date = None
    if doc.get('tournament_start_at'):
        start_date = _parse_inscription_date(doc.get('tournament_start_at'), year_hint)
    if doc.get('tournament_end_at'):
        end_date = _parse_inscription_date(doc.get('tournament_end_at'), year_hint)
    
    if not start_date or not end_date:
        parsed_start, parsed_end = _parse_date_range(date_range, year_hint=year_hint)
        start_date = start_date or parsed_start
        end_date = end_date or parsed_end
        
    # Convert datetime to date if needed for start_date and end_date since Django model expects DateField
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
        
    entry_open, entry_close = _parse_inscription_dates(doc, year_hint=year_hint)

    # Categories from embedded events array — normalize COSAT codes to human-readable names
    events = doc.get('events') or []
    categories = [
        {
            'source_text': _normalize_cosat_event_name(str(e.get('name', '')).strip()),
            'price_brl': None,
            'notes': f'COSAT event code: {e.get("name", "")}' if e.get('name') else '',
        }
        for e in events if e.get('name')
    ]

    from .base import BaseConnector
    slug = BaseConnector.slugify(f'cosat-{cosat_id}-{name}')

    return {
        'external_id': f'cosat:{cosat_id}',
        'canonical_name': name,
        'canonical_slug': slug,
        'circuit': 'COSAT',
        'modality': 'tennis',
        'season_year': start_date.year if start_date else datetime.now().year,
        'title': name,
        'start_date': start_date.isoformat() if start_date else None,
        'end_date': end_date.isoformat() if end_date else None,
        'entry_open_at': entry_open.isoformat() if entry_open else None,
        'entry_close_at': entry_close.isoformat() if entry_close else None,
        'status': 'unknown',
        'surface': 'unknown',
        'venue': {
            'name': organization,
            'city': city,
            'state': state,
            'address': '',
        } if city or state else None,
        'base_price_brl': None,
        'official_source_url': source_url,
        'categories': categories,
        'links': (
            [{'link_type': 'other', 'url': source_url, 'label': 'COSAT TournamentSoftware'}]
            if source_url else []
        ),
        '_raw': {
            'cosatId': cosat_id,
            'organization': organization,
            'location': location,
            'country': country,
            'dateRange': date_range,
            'inscriptionFields': {
                f: str(doc[f]) for f in (
                    _INSCRIPTION_OPEN_FIELDS
                    + _INSCRIPTION_CLOSE_FIELDS
                    + _WITHDRAWAL_FIELDS  # withdrawal not mapped to entry_close_at, preserved for audit
                ) if doc.get(f)
            },
            'categoriesCount': doc.get('categoriesCount'),
            'entriesCount': doc.get('entriesCount'),
            'lastUpdated': (
                last_updated.isoformat()
                if isinstance(last_updated, datetime) else str(last_updated or '')
            ),
            'source': 'cosat_mongo',
        },
    }


# Priority-ordered list of MongoDB fields that may contain the player's category.
# Tried in order; first non-empty string wins.
_PLAYER_CATEGORY_FIELDS = [
    'rankingCategory',   # crawler schema primary field
    'category',          # common alternative
    'categoryName',      # verbose variant
    'eventName',         # TournamentSoftware event = category
    'event',             # shorter form
    'drawName',          # draw name often equals category
    'draw',              # TournamentSoftware draw type
    'discipline',        # ITF / TS discipline field
    'ageCategory',       # age-based classification
    'group',             # group/level in some systems
    'division',          # division = category in some
    'class',             # class field
    'grade',             # grade used by some federations
    'eventId',           # last resort: use the ID as category text
]


def _extract_category_text(doc: dict) -> tuple[str, str]:
    """
    Try all known category field candidates in priority order.
    Returns (category_text, field_name) where field_name is the source field.
    Returns ('', '') if no category found.
    Never invents or infers a category from tournament name.
    """
    for field in _PLAYER_CATEGORY_FIELDS:
        value = doc.get(field)
        if value and str(value).strip():
            text = str(value).strip()
            # Skip if it looks like a raw UUID/ObjectId — not a meaningful category
            if _is_id_like(text) and field == 'eventId':
                continue
            if len(text) >= 2:
                return text, field
    return '', ''


def _is_id_like(text: str) -> bool:
    """True if the text looks like a UUID or hex ID rather than a category name."""
    import re
    # UUID pattern: 8-4-4-4-12 hex chars
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                text, re.IGNORECASE):
        return True
    # Pure hex string > 16 chars
    if re.match(r'^[0-9a-f]{16,}$', text, re.IGNORECASE):
        return True
    return False


# Priority-ordered list of country name fields in player documents
_PLAYER_COUNTRY_NAME_FIELDS = [
    'countryName',   # verbose form
    'country',       # most common single-field form
    'nationality',   # nationality string
    'nation',        # some COSAT docs use 'nation'
]

# Priority-ordered list of country code fields
_PLAYER_COUNTRY_CODE_FIELDS = [
    'countryCode',   # ISO 3166-1 alpha-3 or alpha-2
    'iocCode',       # IOC 3-letter code
    'country',       # sometimes IS the code (e.g. "ARG")
    'flag',          # sometimes country code stored as flag field
]


def _extract_country(doc: dict) -> tuple[str, str]:
    """
    Extract (country_name, country_code) from a player document.

    country_name: full country name (e.g. "Argentina")
    country_code: ISO/IOC code (e.g. "ARG")

    Returns ('', '') when absent. Never invents data.
    """
    # Country name
    country_name = ''
    for field in _PLAYER_COUNTRY_NAME_FIELDS:
        val = (doc.get(field) or '').strip()
        if val and len(val) > 1 and not val.isdigit():
            # Treat values that look like codes (≤3 uppercase chars) as codes not names
            if len(val) <= 3 and val.isupper():
                continue
            country_name = val
            break

    # Country code
    country_code = ''
    for field in _PLAYER_COUNTRY_CODE_FIELDS:
        val = (doc.get(field) or '').strip()
        if val and 2 <= len(val) <= 3 and val.isalpha():
            country_code = val.upper()
            break
    # Fallback: derive code from name first 3 chars if we have a name but no code
    # (Not done — never invent a code that's not in the source)

    return country_name, country_code


def player_field_inventory(doc: dict) -> dict:
    """
    Return a safe field inventory of a player doc for debug/reporting.

    Redacts name and DOB — keeps structural/category/country fields visible
    since country is published publicly on the COSAT site.
    Used by --debug-sample to show what fields are present without
    leaking personal data.
    """
    # Redact personal data (name, DOB) — country is public (shown on COSAT site)
    REDACTED = {'name', 'dob'}
    inventory = {}
    for key, value in doc.items():
        if key in REDACTED:
            inventory[key] = '<redacted>'
        elif key == '_id':
            inventory[key] = str(value)
        elif value is None or value == '':
            inventory[key] = None
        else:
            inventory[key] = str(value)[:80]
    return inventory


def _normalize_player(doc: dict) -> Optional[dict]:
    """
    Convert a MongoDB players document to a FederationEntry-compatible dict.

    tournament_cosat_id links this entry to the parent tournament for upsert.
    payment_status is always 'unknown' — crawler does not capture payment info.

    category_text is extracted via _extract_category_text() which tries
    multiple field candidates in priority order. If no category found,
    returns None — entries without category are always rejected.
    """
    name = (doc.get('name') or '').strip()
    if not name:
        return None

    tournament_id = str(doc.get('tournamentId') or '').strip()
    raw_ext_id = (
        doc.get('profileId')
        or doc.get('tournamentPlayerId')
        or ''
    )
    player_external_id = f'cosat:{raw_ext_id}' if raw_ext_id else ''
    category_text, category_field = _extract_category_text(doc)
    country_name, country_code = _extract_country(doc)

    last_updated = doc.get('lastUpdated') or doc.get('updatedAt')

    return {
        'player_name': name,
        'tournament_cosat_id': tournament_id,
        'player_external_id': player_external_id,
        'category_text': category_text,
        '_category_field': category_field,  # which field provided the category (for debug)
        'player_country_name': country_name,
        'player_country_code': country_code,
        'ranking_position': None,
        'payment_status': 'unknown',
        'removed_or_replaced': False,
        'replacement_reason': '',
        'source_url': '',
        'confidence': 'medium',
        'synced_at': (
            last_updated.isoformat()
            if isinstance(last_updated, datetime) else None
        ),
        '_raw': {
            'profileId': doc.get('profileId'),
            'tournamentPlayerId': doc.get('tournamentPlayerId'),
            'rankingPlayerId': doc.get('rankingPlayerId'),
            'dob': doc.get('dob'),
            'country': doc.get('country'),
            'countryCode': doc.get('countryCode'),
        },
    }


def _normalize_ranking(doc: dict) -> Optional[dict]:
    """
    Convert a MongoDB rankingentries document to a FederationEntry-compatible dict.

    These are standalone ranking entries not tied to a specific tournament edition.
    ranking_position maps to the 'rank' field.
    confidence='high' because ranking data comes directly from COSAT.
    """
    player_name = (doc.get('playerName') or '').strip()
    if not player_name:
        return None

    raw_ext_id = (doc.get('profileId') or doc.get('playerId') or '').strip()
    player_external_id = f'cosat:{raw_ext_id}' if raw_ext_id else ''
    category_text = (doc.get('category') or '').strip()

    try:
        ranking_position = int(doc.get('rank') or 0) or None
    except (TypeError, ValueError):
        ranking_position = None

    source_url = (doc.get('sourceUrl') or '').strip()
    last_updated = doc.get('lastUpdated') or doc.get('updatedAt')

    return {
        'player_name': player_name,
        'tournament_cosat_id': '',
        'player_external_id': player_external_id,
        'category_text': category_text,
        'ranking_position': ranking_position,
        'payment_status': 'unknown',
        'removed_or_replaced': False,
        'replacement_reason': '',
        'source_url': source_url,
        'confidence': 'high',
        'synced_at': (
            last_updated.isoformat()
            if isinstance(last_updated, datetime) else None
        ),
        '_raw': {
            'rankingId': doc.get('rankingId'),
            'rankingDate': doc.get('rankingDate'),
            'singlesPoints': doc.get('singlesPoints'),
            'doublesPoints': doc.get('doublesPoints'),
            'totalPoints': doc.get('totalPoints'),
            'country': doc.get('country'),
            'dob': doc.get('dob'),
        },
    }


# ── Date / location helpers ───────────────────────────────────────────────────

def _normalize_cosat_event_name(name: str) -> str:
    """
    Normalize COSAT event code to Portuguese display name.

    Examples:
      'BS 14' → 'Sub-14 Masculino Simples'
      'GS 14' → 'Sub-14 Feminino Simples'
      'BD 16' → 'Sub-16 Masculino Duplas'
      'GD 12' → 'Sub-12 Feminino Duplas'

    Returns the original name unchanged when the pattern is not recognized,
    so unknown codes are preserved without data loss.
    """
    if not name:
        return name
    m = re.match(r'^([A-Za-z]{2})\s*(\d{1,2})$', name.strip())
    if not m:
        return name
    code = m.group(1).upper()
    age = m.group(2)
    event_type = _COSAT_EVENT_CODES.get(code)
    if not event_type:
        return name
    return f'Sub-{age} {event_type}'


def _parse_spanish_date(text: str, year: int):
    """
    Extract a date from a Spanish-format text fragment.

    Handles: "lun. 27 de abr.", "sáb. 2 de may.", "27 de abr."
    Returns datetime.date or None.
    """
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)', text, re.IGNORECASE)
    if not m:
        return None
    day = int(m.group(1))
    month_str = m.group(2).lower()[:3]
    month = _MONTH_MAP.get(month_str)
    if not month or not year:
        return None
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def _parse_date_range(date_range: str, year_hint: int = 0):
    """
    Parse COSAT dateRange strings into (start_date, end_date).

    Supported formats:
      "10 - 15 Nov 2025"        → (2025-11-10, 2025-11-15)
      "10 Nov - 15 Nov 2025"    → (2025-11-10, 2025-11-15)
      "30 Nov - 5 Dec 2025"     → (2025-11-30, 2025-12-05)
      "Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may."
                                 → uses year_hint (2026-04-27, 2026-05-02)

    year_hint: preferred year for formats without explicit year (e.g. Spanish).
               Falls back to current year when 0.

    Returns (None, None) when format is not recognised.
    """
    if not date_range:
        return None, None

    s = date_range.strip()

    # Format 1: "DD - DD Mon YYYY"  or  "DD Mon - DD Mon YYYY"
    m1 = re.match(
        r'(\d{1,2})\s*(?:(\w+)\s*)?-\s*(\d{1,2})\s+(\w+)\s+(\d{4})',
        s, re.IGNORECASE,
    )
    if m1:
        d1, mon1_str, d2, mon2_str, year = m1.groups()
        mon2 = _MONTH_MAP.get((mon2_str or '').lower()[:3])
        mon1 = _MONTH_MAP.get((mon1_str or '').lower()[:3]) if mon1_str else mon2
        if mon1 and mon2:
            try:
                start = datetime(int(year), mon1, int(d1)).date()
                end = datetime(int(year), mon2, int(d2)).date()
                return start, end
            except ValueError:
                pass

    # Format 2: Spanish — "Inicio del torneo X. DD de MMM. | Final del torneo X. DD de MMM."
    # The year comes from year_hint (lastUpdated/createdAt of the Mongo document).
    if '|' in s:
        parts = s.split('|', 1)
        year = year_hint or datetime.now().year
        start = _parse_spanish_date(parts[0], year)
        end = _parse_spanish_date(parts[1], year)
        if start and end:
            # Sanity: if end < start, end spans into the next year
            if end < start:
                end = _parse_spanish_date(parts[1], year + 1) or end
            return start, end

    return None, None


# Inscription date fields — tried in priority order (open/start and close/end).
# Supports all field name conventions from the COSAT crawler schema.
_INSCRIPTION_OPEN_FIELDS = [
    'Inscrição_Inicio',
    'Inscricao_Inicio', 'InscricaoInicio',
    'registration_open_at', 'entry_open_at',
    'registrationOpen', 'registration_open',
    'inscriptionOpen', 'inscriptionStart',
    'Entry open', 'Entries open', 'Registration open',
    'registrationFrom', 'registration_from',
    'inscricao_inicio', 'inscrição_inicio',
]
_INSCRIPTION_CLOSE_FIELDS = [
    'Inscrição_Fim',
    'Inscricao_Fim', 'InscricaoFim',
    'registration_close_at', 'entry_close_at',
    'registrationClose', 'registration_close',
    'inscriptionClose', 'inscriptionEnd',
    'Entry close', 'Entries close', 'Registration close',
    'registrationTo', 'registration_to', 'registrationDeadline',
    'inscricao_fim', 'inscrição_fim',
]

# Withdrawal deadline is NOT a registration open/close date — it is the deadline
# for withdrawing from a tournament after registering. Preserved in _raw only.
_WITHDRAWAL_FIELDS = ['Withdrawal deadline', 'withdrawal_deadline']


def _parse_inscription_date(value, year_hint: int = 0):
    """
    Parse a single inscription date field value to a date or datetime object.

    Supported formats:
      ISO:        2026-04-27 / 2026-04-27T00:00:00Z / 2026-04-27T23:59:00-05:00
      BR:         27/04/2026
      ES/PT year: "27 de abr. 2026" / "sáb. 2 de may. 2026"
      ES/PT bare: "lun. 27 de abr." / "2 de may." (uses year_hint)
      Prefixed:   "Entries close: sáb. 2 de may."

    Returns date/datetime or None — never invents data.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s.lower() in ('null', 'none', 'não informado', 'inscrição não informada',
                               'n/a', '-'):
        return None

    # Strip label prefixes like "Entries close: " or "Withdrawal deadline: ".
    # Guard: only strip when string starts with a non-digit.
    # ISO dates (2026-04-27) and BR dates (27/04/2026) start with digits — do not strip.
    if ':' in s and not s[0].isdigit():
        s = s.split(':', 1)[1].strip()
    if not s:
        return None

    # ISO: 2026-04-27 or 2026-04-27T23:59:00-05:00
    if 'T' in s:
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass

    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            pass

    # BR: 27/04/2026
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
        except ValueError:
            pass

    # ES/PT with explicit year: "27 de abr. 2026" / "sáb. 2 de may. 2026"
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\.?\s*(\d{4})', s, re.IGNORECASE)
    if m:
        month = _MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1))).date()
            except ValueError:
                pass

    # ES/PT without year — use year_hint or current year
    year = year_hint or datetime.now().year
    return _parse_spanish_date(s, year)


def _parse_inscription_dates(doc: dict, year_hint: int = 0):
    """
    Extract (entry_open_at, entry_close_at) from a Mongo tournament document.

    Tries all known field name variants in priority order.
    Returns (date | None, date | None).
    Never invents data — returns (None, None) if fields absent or unparseable.
    When the crawler starts populating Inscrição_Inicio/Inscrição_Fim,
    the next sync will automatically populate these fields without code changes.
    """
    open_date = None
    for field in _INSCRIPTION_OPEN_FIELDS:
        val = doc.get(field)
        if val:
            open_date = _parse_inscription_date(val, year_hint)
            if open_date:
                break

    close_date = None
    for field in _INSCRIPTION_CLOSE_FIELDS:
        val = doc.get(field)
        if val:
            close_date = _parse_inscription_date(val, year_hint)
            if close_date:
                break

    return open_date, close_date


_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')


def _strip_emails(text: str) -> str:
    """Remove email addresses from a string — they must not appear in venue/address fields."""
    return _EMAIL_RE.sub('', text).strip(' ,;/')


def _parse_location(location: str, country: str):
    """
    Extract (city, state_or_country_code) from a location string.

    Examples:
      "Buenos Aires, AR" → ("Buenos Aires", "AR")
      "São Paulo"        → ("São Paulo", "BR")
      ""                 → ("", "")
    """
    if not location:
        return '', ''
    # Strip emails that may appear in location strings from COSAT data
    location = _strip_emails(location)
    if not location:
        return '', ''
    parts = [p.strip() for p in location.split(',')]
    city = parts[0] if parts else ''
    state = parts[1].strip() if len(parts) > 1 else ''
    if not state and country:
        state = country[:2].upper()
    return city, state[:2].upper() if state else ''
