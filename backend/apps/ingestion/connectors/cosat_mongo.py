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

# Month abbreviation map (EN + ES/PT abbreviations from COSAT)
_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'ene': 1, 'abr': 4, 'ago': 8, 'set': 9, 'out': 10, 'dez': 12,
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
            db_name = getattr(settings, 'COSAT_MONGO_DB', 'cosat_db')
            self._db = self._client[db_name]
            # Trigger actual network check (throws ServerSelectionTimeoutError if down)
            self._client.admin.command('ping')
            self._available = True
            logger.info('CosatMongoConnector: connected to db=%s', db_name)
        except Exception as exc:
            logger.warning(
                'CosatMongoConnector: MongoDB unavailable — %s. '
                'COSAT data will be skipped this run. '
                'Check COSAT_MONGO_URL and Railway connectivity.',
                exc,
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


# ── Document normalizers (module-level, testable without MongoDB) ─────────────

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
    organization = (doc.get('organization') or 'COSAT').strip()
    location = (doc.get('location') or '').strip()
    country = (doc.get('country') or 'BR').strip()

    city, state = _parse_location(location, country)

    date_range = (doc.get('dateRange') or '').strip()
    start_date, end_date = _parse_date_range(date_range)

    # Categories from embedded events array
    events = doc.get('events') or []
    categories = [
        {'source_text': str(e.get('name', '')).strip(), 'price_brl': None, 'notes': ''}
        for e in events if e.get('name')
    ]

    last_updated = doc.get('lastUpdated') or doc.get('updatedAt')

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
        'entry_open_at': None,
        'entry_close_at': None,
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
            'categoriesCount': doc.get('categoriesCount'),
            'entriesCount': doc.get('entriesCount'),
            'lastUpdated': (
                last_updated.isoformat()
                if isinstance(last_updated, datetime) else str(last_updated or '')
            ),
            'source': 'cosat_mongo',
        },
    }


def _normalize_player(doc: dict) -> Optional[dict]:
    """
    Convert a MongoDB players document to a FederationEntry-compatible dict.

    tournament_cosat_id links this entry to the parent tournament for upsert.
    payment_status is always 'unknown' — crawler does not capture payment info.
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
    category_text = (doc.get('rankingCategory') or '').strip()

    last_updated = doc.get('lastUpdated') or doc.get('updatedAt')

    return {
        'player_name': name,
        'tournament_cosat_id': tournament_id,
        'player_external_id': player_external_id,
        'category_text': category_text,
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

def _parse_date_range(date_range: str):
    """
    Parse COSAT dateRange strings into (start_date, end_date).

    Known crawler formats:
      "10 - 15 Nov 2025"           → same month both ends
      "10 Nov - 15 Nov 2025"       → explicit month both ends
      "30 Nov - 5 Dec 2025"        → cross-month
    Returns (None, None) when format is not recognised.
    """
    if not date_range:
        return None, None

    s = date_range.strip()

    # "DD - DD Mon YYYY"  or  "DD Mon - DD Mon YYYY"
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

    return None, None


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
    parts = [p.strip() for p in location.split(',')]
    city = parts[0] if parts else ''
    state = parts[1].strip() if len(parts) > 1 else ''
    if not state and country:
        state = country[:2].upper()
    return city, state[:2].upper() if state else ''
