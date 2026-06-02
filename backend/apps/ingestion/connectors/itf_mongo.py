"""
ITF MongoDB connector — reads from the external ITF scraper service.

The ITF scraper runs independently on Railway and writes tournament +
acceptance-list data to a MongoDB collection ('itftournaments').
By default reuses the same MongoDB instance used by the COSAT scraper
(COSAT_MONGO_URL / COSAT_MONGO_DB). Override with ITF_MONGO_URL /
ITF_MONGO_DB if the scraper uses a separate instance.

Document schema (scraper Mongoose model → MongoDB collection 'itftournaments'):
  slug_externo*       — stable external ID (e.g. "j-j60-jpn-2026-002")
  nome*               — tournament name (e.g. "J60 Miki City")
  categoria           — grade (e.g. "J60")
  circuito            — circuit label (e.g. "ITF Junior")
  pais                — host country name (e.g. "Japan")
  codigo_pais         — host country ISO-3 code (e.g. "JPN")
  cidade              — host city (e.g. "Miki")
  data_inicio         — start date (YYYY-MM-DD)
  data_fim            — end date (YYYY-MM-DD)
  prazo_inscricao     — entry deadline text (e.g. "Tue 12th May 2026 by 14:00GMT")
  prazo_desistencia   — withdrawal deadline text
  superficie          — surface in PT (e.g. "Piso Duro")
  indoor_outdoor      — "Indoor" / "Outdoor"
  status              — status string in PT/EN
  draw_size           — {masculino: {singles_main_draw, ...}, feminino: {...}}
  url_oficial         — canonical ITF URL
  url_fact_sheet      — fact sheet URL
  url_acceptance_list — acceptance list URL
  inscritos           — acceptance list:
    {
      "masculino": [
        {"secao": "draw_principal", "secao_label": "Draw Principal (Masculino)",
         "jogadores": [{"posicao": 1, "nome": "...", "pais": "Japan",
                        "codigo_pais": "JPN", "ranking": 167, "wtn": 19.06,
                        "wtn_aceites": null, "prioridade": 1, "informacao": ""}]},
        {"secao": "qualifying", ...},
        {"secao": "alternates", ...},
        {"secao": "desistencias", ...}
      ],
      "feminino": [...]
    }
  lastUpdated         — last scrape timestamp

Design:
  - Read-only — never writes to MongoDB.
  - Offline-safe — logs warning, returns empty iterator if unavailable.
  - Short connection timeout (ITF_MONGO_CONNECT_TIMEOUT_MS, default 5s).
  - All credentials via env vars / Django settings. Never hardcoded.
  - Reuses COSAT_MONGO_URL/DB when ITF-specific vars are not set.
"""
import logging
import re
from datetime import datetime
from typing import Iterator, Optional

from django.conf import settings

logger = logging.getLogger('apps.ingestion.itf_mongo')


def _sanitize_exc(exc: Exception) -> str:
    msg = str(exc)
    return re.sub(r'(mongodb(?:\+srv)?://)([^@]+)@', r'\1***:***@', msg)


# ── Surface / status / section maps ──────────────────────────────────────────

_SURFACE_MAP = {
    'clay': 'clay', 'saibro': 'clay', 'terra batida': 'clay', 'piso batido': 'clay',
    'hard': 'hard', 'dura': 'hard', 'rápida': 'hard', 'rapida': 'hard',
    'hard (o)': 'hard', 'hard (i)': 'hard',
    'piso duro': 'hard', 'quadra dura': 'hard', 'piso rígido': 'hard', 'piso rigido': 'hard',
    'grass': 'grass', 'grama': 'grass',
    'carpet': 'carpet', 'carpete': 'carpet', 'carpet (i)': 'carpet',
    'sand': 'sand', 'areia': 'sand',
}

_STATUS_MAP = {
    'accepting entries': 'open',
    'aceitando inscrições': 'open', 'aceitando inscricoes': 'open',
    'inscrições abertas': 'open', 'inscricoes abertas': 'open',
    'entries closed': 'closed',
    'inscrições encerradas': 'closed', 'inscricoes encerradas': 'closed',
    'in progress': 'in_progress', 'em andamento': 'in_progress',
    'completed': 'finished', 'finalizado': 'finished',
    'cancelled': 'canceled', 'canceled': 'canceled', 'cancelado': 'canceled',
    'upcoming': 'announced', 'anunciado': 'announced',
    'draws available': 'draws_published', 'chaves publicadas': 'draws_published',
}

# Scraper section key → (standard_key, portuguese_label)
_SECTION_MAP = {
    'draw_principal': ('main_draw', 'Chave Principal'),
    'main_draw': ('main_draw', 'Chave Principal'),
    'chave_principal': ('main_draw', 'Chave Principal'),
    'qualifying': ('qualifying', 'Qualificação'),
    'qualificacao': ('qualifying', 'Qualificação'),
    'qualificação': ('qualifying', 'Qualificação'),
    'alternates': ('alternates', 'Alternates'),
    'alternativas': ('alternates', 'Alternates'),
    'desistencias': ('withdrawn', 'Desistências'),
    'desistências': ('withdrawn', 'Desistências'),
    'withdrawn': ('withdrawn', 'Desistências'),
}

_GENDER_MAP = {
    'masculino': ('M', 'Masculino'),
    'feminino': ('F', 'Feminino'),
    'male': ('M', 'Masculino'),
    'female': ('F', 'Feminino'),
    'm': ('M', 'Masculino'),
    'f': ('F', 'Feminino'),
    'boys': ('M', 'Masculino'),
    'girls': ('F', 'Feminino'),
}


# ── Connection ────────────────────────────────────────────────────────────────

def _get_itf_client():
    """
    Build a pymongo MongoClient for the ITF collection.
    Falls back to COSAT_MONGO_URL / COSAT_MONGO_DB when ITF-specific vars are empty.
    """
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise ImportError('pymongo not installed. Add pymongo to requirements.txt.') from exc

    url = getattr(settings, 'ITF_MONGO_URL', '') or getattr(settings, 'COSAT_MONGO_URL', '')
    if not url:
        raise ValueError(
            'No MongoDB URL configured for ITF. '
            'Set ITF_MONGO_URL or COSAT_MONGO_URL in Railway Variables.'
        )

    timeout_ms = getattr(settings, 'ITF_MONGO_CONNECT_TIMEOUT_MS', 5000)
    return MongoClient(
        url,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
    )


def _get_itf_db_name() -> str:
    db = getattr(settings, 'ITF_MONGO_DB', '') or getattr(settings, 'COSAT_MONGO_DB', '')
    if not db:
        raise ValueError(
            'No MongoDB DB name configured for ITF. '
            'Set ITF_MONGO_DB or COSAT_MONGO_DB in Railway Variables.'
        )
    return db


# ── Connector class ───────────────────────────────────────────────────────────

class ItfMongoConnector:
    """
    Read-only connector to the ITF scraper MongoDB.

    Usage:
        conn = ItfMongoConnector()
        if not conn.is_available():
            logger.warning('ITF Mongo offline — skipping')
            return
        for t in conn.iter_tournaments():
            ...
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
            self._client = _get_itf_client()
            db_name = _get_itf_db_name()
            self._db = self._client[db_name]
            self._client.admin.command('ping')
            self._available = True
            logger.info('ItfMongoConnector: connected to db=%s', db_name)
        except Exception as exc:
            logger.warning(
                'ItfMongoConnector: MongoDB unavailable — %s. '
                'ITF data will be skipped this run.',
                _sanitize_exc(exc),
            )
            self._available = False
        return self._available

    def is_available(self) -> bool:
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

    def _collection(self):
        name = getattr(settings, 'ITF_MONGO_COLLECTION_TOURNAMENTS', 'itftournaments')
        return self._db[name]

    def iter_tournaments(self, limit: int = 0, slug_externo: str = '') -> Iterator[dict]:
        """
        Yield normalized tournament dicts from the itftournaments collection.

        Yields dicts conforming to the standard connector schema plus
        '_raw' (original doc) and '_inscritos' (raw acceptance list).
        """
        if not self.is_available():
            return

        query = {}
        if slug_externo:
            # Accept both legacy 'slug_externo' and current scraper 'key' field
            query = {'$or': [{'slug_externo': slug_externo}, {'key': slug_externo}]}

        cursor = self._collection().find(query)
        if limit:
            cursor = cursor.limit(limit)

        for doc in cursor:
            try:
                normalized = _normalize_tournament(doc)
                if normalized:
                    yield normalized
                else:
                    logger.debug('ItfMongo: skipped tournament (missing slug_externo/nome): %s',
                                 doc.get('_id'))
            except Exception as exc:
                logger.warning('ItfMongo: failed to normalize tournament %s — %s',
                               doc.get('slug_externo', '?'), exc)

    def count_tournaments(self) -> int:
        if not self.is_available():
            return 0
        return self._collection().count_documents({})

    def sample_raw(self, key: str = '', n: int = 1) -> list:
        """Return up to n raw documents (no normalization) for schema inspection."""
        if not self.is_available():
            return []
        query = {}
        if key:
            query = {'$or': [{'key': key}, {'slug_externo': key}]}
        docs = []
        for doc in self._collection().find(query).limit(n):
            doc['_id'] = str(doc.get('_id', ''))
            docs.append(doc)
        return docs


# ── Document normalizers ──────────────────────────────────────────────────────

def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    s = str(value).strip()
    if not s or s.lower() in ('null', 'none', 'n/a', '-'):
        return None

    # ISO with timezone: "2026-06-03T00:00:00Z"
    if 'T' in s:
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00'))
        except ValueError:
            pass

    # YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # DD/MM/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # "Tue 12th May 2026 by 14:00GMT" / "Mon 19th May 2026 by 14:00GMT"
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})', s)
    if m:
        for fmt in ('%d %B %Y', '%d %b %Y'):
            try:
                return datetime.strptime(
                    f'{m.group(1)} {m.group(2)} {m.group(3)}', fmt
                )
            except ValueError:
                pass

    return None


def _categories_from_inscritos(inscritos: dict) -> list:
    """
    Derive TournamentCategory source_text entries from the inscritos structure.

    ITF Junior tournaments are always U18. The grade (J100, J200…) is the
    circuit tier, not the age category. For each gender × section combination
    present in inscritos we generate a category like "Masculino - Chave Principal - Sub-18".
    This allows the eligibility engine to match the category as CBT/FPT age ≤18.

    inscritos structure (Mongoose schema):
      {"masculino": [{"secao": "draw_principal", "secao_label": "...", "jogadores": [...]}, ...],
       "feminino":  [...]}
    """
    result = []
    seen = set()
    for gender_key, sections in (inscritos or {}).items():
        gender_code, gender_label = _GENDER_MAP.get(gender_key.lower(), ('', gender_key.capitalize()))
        if not isinstance(sections, list):
            continue
        for section_obj in sections:
            if not isinstance(section_obj, dict):
                continue
            section_key = (section_obj.get('secao') or '').lower().strip()
            jogadores = section_obj.get('jogadores') or []
            if not isinstance(jogadores, list) or not jogadores:
                continue
            _, section_label = _SECTION_MAP.get(section_key, (section_key, section_key.capitalize()))
            source_text = f'{gender_label} - {section_label} - Sub-18'
            if source_text not in seen:
                seen.add(source_text)
                result.append({
                    'source_text': source_text,
                    'price_brl': None,
                    'notes': f'gender:{gender_code} section:{section_key}',
                })
    return result


def _normalize_tournament(doc: dict) -> Optional[dict]:
    """
    Convert a MongoDB itftournaments document to the standard connector dict.
    Returns None when mandatory fields (slug_externo, nome) are absent.
    """
    # Accept both 'slug_externo' (legacy) and 'key' (current scraper Mongoose schema)
    slug_externo = (
        str(doc.get('slug_externo') or '').strip()
        or str(doc.get('key') or '').strip()
        or str(doc.get('externalId') or '').strip()
        or str(doc.get('external_id') or '').strip()
        or str(doc.get('id') or '').strip()
    )
    if not slug_externo:
        return None

    nome = (
        doc.get('nome') or doc.get('name') or doc.get('title') or doc.get('titulo') or ''
    ).strip()
    if not nome:
        return None

    circuit = (
        doc.get('circuito') or doc.get('categoria') or doc.get('circuit')
        or doc.get('category') or doc.get('grade') or 'ITF Junior'
    ).strip()
    url_oficial = (
        doc.get('url_oficial') or doc.get('url') or doc.get('officialUrl')
        or doc.get('official_url') or ''
    ).strip()
    cidade = (
        doc.get('cidade') or doc.get('city') or doc.get('location') or ''
    ).strip()
    codigo_pais = (
        doc.get('codigo_pais') or doc.get('country_code') or doc.get('countryCode')
        or doc.get('country') or ''
    ).strip().upper()

    surface_raw = (
        doc.get('superficie') or doc.get('surface') or doc.get('court') or ''
    ).lower().strip()
    surface = _SURFACE_MAP.get(surface_raw, 'unknown')

    status_raw = (doc.get('status') or '').lower().strip()
    status = _STATUS_MAP.get(status_raw, 'unknown')

    start_date = _parse_date(
        doc.get('data_inicio') or doc.get('start_date') or doc.get('startDate')
        or doc.get('start') or doc.get('data_inicio_torneio')
    )
    end_date = _parse_date(
        doc.get('data_fim') or doc.get('end_date') or doc.get('endDate')
        or doc.get('end') or doc.get('data_fim_torneio')
    )
    entry_close = _parse_date(
        doc.get('prazo_inscricao') or doc.get('entry_deadline') or doc.get('entryDeadline')
        or doc.get('deadline') or doc.get('entry_close') or doc.get('entryClose')
    )

    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if isinstance(entry_close, datetime):
        entry_close = entry_close.date()

    season_year = start_date.year if start_date else datetime.now().year

    # Build categories from inscritos structure (gender × section).
    # ITF Junior tournaments are always U18 — the grade (J100, J200…) is the circuit tier,
    # not the player age category. Derive real categories from inscritos when available.
    inscritos_for_cats = doc.get('inscritos') or {}
    categories = _categories_from_inscritos(inscritos_for_cats)
    if not categories:
        # Fallback: one category per gender inferred from circuit label
        grade = (doc.get('grade') or doc.get('categoria') or circuit).strip()
        for gender_text, gender_code in [('Masculino', 'M'), ('Feminino', 'F')]:
            categories.append({
                'source_text': f'{gender_text} - {grade} - Sub-18',
                'price_brl': None,
                'notes': f'grade:{grade}',
            })

    from .base import BaseConnector
    canonical_slug = BaseConnector.slugify(f'itf-{slug_externo}')

    inscritos = doc.get('inscritos') or {}

    url_acceptance_list = (doc.get('url_acceptance_list') or '').strip()
    url_fact_sheet = (doc.get('url_fact_sheet') or '').strip()

    links = []
    if url_oficial:
        links.append({'link_type': 'other', 'url': url_oficial, 'label': 'ITF Tournament'})
    if url_acceptance_list:
        links.append({'link_type': 'acceptance_list', 'url': url_acceptance_list, 'label': 'Acceptance List'})
    if url_fact_sheet:
        links.append({'link_type': 'fact_sheet', 'url': url_fact_sheet, 'label': 'Fact Sheet'})

    return {
        'external_id': f'itf:{slug_externo}',
        'canonical_name': nome,
        'canonical_slug': canonical_slug,
        'circuit': circuit,
        'modality': 'tennis',
        'season_year': season_year,
        'title': nome,
        'start_date': start_date.isoformat() if start_date else None,
        'end_date': end_date.isoformat() if end_date else None,
        'entry_open_at': None,
        'entry_close_at': entry_close.isoformat() if entry_close else None,
        'status': status,
        'surface': surface,
        'venue': {
            'name': '',
            'city': cidade[:120],
            'state': '',
            'address': '',
            'country_code': codigo_pais[:3],
        } if cidade else None,
        'base_price_brl': None,
        'official_source_url': url_oficial,
        'categories': categories,
        'links': links,
        '_raw': {
            'slug_externo': slug_externo,
            'circuito': circuit,
            'cidade': cidade,
            'codigo_pais': codigo_pais,
            'superficie': surface_raw,
            'source': 'itf_mongo',
        },
        '_inscritos': inscritos,
    }


def normalize_acceptance_list(inscritos: dict) -> list:
    """
    Convert the scraper's 'inscritos' dict to the TournamentEdition.acceptance_list format.

    Input (Mongoose schema — each gender maps to a list of section objects):
        {
          "masculino": [
            {"secao": "draw_principal", "secao_label": "Draw Principal (Masculino)",
             "jogadores": [{"nome": "...", "pais": "Japan", "codigo_pais": "JPN",
                            "ranking": 167, "wtn": 19.06, "prioridade": 1, "informacao": ""}]},
            {"secao": "qualifying", ...},
            {"secao": "alternates", ...},
            {"secao": "desistencias", ...}
          ],
          "feminino": [...]
        }

    Output (TournamentEdition.acceptance_list format):
        [
          {"section": "main_draw", "gender": "M", "section_label": "Masculino - Chave Principal",
           "players": [{"name": "...", "country": "Japan", "country_code": "JPN",
                        "ranking": 167, "wtn": 19.06, "priority": 1, "information": ""}]},
          ...
        ]
    """
    result = []
    if not inscritos or not isinstance(inscritos, dict):
        return result

    for gender_key, sections in inscritos.items():
        gender_code, gender_label = _GENDER_MAP.get(gender_key.lower(), ('', gender_key))
        if not isinstance(sections, list):
            continue

        for section_obj in sections:
            if not isinstance(section_obj, dict):
                continue
            section_key = (section_obj.get('secao') or '').lower().strip()
            players = section_obj.get('jogadores') or []
            std_section, section_label = _SECTION_MAP.get(
                section_key, (section_key, section_key.capitalize())
            )
            if not isinstance(players, list):
                continue

            normalized_players = []
            for p in players:
                if not isinstance(p, dict):
                    continue
                name = (p.get('nome') or p.get('name') or '').strip()
                if not name:
                    continue
                normalized_players.append({
                    'name': name,
                    'country': (p.get('pais') or p.get('country') or '').strip(),
                    'country_code': (p.get('codigo_pais') or p.get('country_code') or '').strip().upper(),
                    'ranking': p.get('ranking') if p.get('ranking') is not None else p.get('rank'),
                    'wtn': p.get('wtn'),
                    'priority': p.get('prioridade') if p.get('prioridade') is not None else p.get('priority'),
                    'information': (p.get('informacao') or p.get('information') or '').strip(),
                    'position': p.get('posicao') or p.get('position'),
                    'wtn_aceites': p.get('wtn_aceites'),
                })

            if normalized_players:
                result.append({
                    'section': std_section,
                    'gender': gender_code,
                    'section_label': f'{gender_label} - {section_label}',
                    'players': normalized_players,
                })

    return result


def iter_player_entries(inscritos: dict, slug_externo: str) -> Iterator[dict]:
    """
    Yield FederationEntry-compatible dicts from the inscritos structure.

    Each yielded dict has:
      player_name, player_external_id, category_text, gender,
      ranking_position, payment_status, removed_or_replaced,
      player_country_code, player_country_name, source, confidence.

    inscritos structure: {"masculino": [section_obj, ...], "feminino": [...]}
    section_obj: {"secao": "draw_principal", "secao_label": "...", "jogadores": [...]}
    player: {"posicao": 1, "nome": "...", "pais": "...", "codigo_pais": "...",
             "ranking": 167, "wtn": 19.06, "prioridade": 1, "informacao": ""}
    """
    import unicodedata as _ud
    import re as _re

    if not inscritos or not isinstance(inscritos, dict):
        return

    for gender_key, sections in inscritos.items():
        gender_code, gender_label = _GENDER_MAP.get(gender_key.lower(), ('', gender_key))
        if not isinstance(sections, list):
            continue

        for section_obj in sections:
            if not isinstance(section_obj, dict):
                continue
            section_key = (section_obj.get('secao') or '').lower().strip()
            players = section_obj.get('jogadores') or []
            std_section, section_label = _SECTION_MAP.get(
                section_key, (section_key, section_key.capitalize())
            )
            is_withdrawn = std_section == 'withdrawn'

            if not isinstance(players, list):
                continue

            for idx, p in enumerate(players):
                if not isinstance(p, dict):
                    continue
                name = (p.get('nome') or p.get('name') or '').strip()
                if not name:
                    continue

                country_code = (p.get('codigo_pais') or p.get('country_code') or '').strip().upper()
                country_name = (p.get('pais') or p.get('country') or '').strip()

                try:
                    ranking = int(p['ranking']) if p.get('ranking') is not None else None
                except (TypeError, ValueError):
                    ranking = None

                # Use posicao (1-based) as stable position; fall back to enumerate index
                position = p.get('posicao') or (idx + 1)

                # Stable external ID: itf:section:slug(name):country:position
                slug_name = _re.sub(r'[^a-z0-9]+', '-',
                    _ud.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode()
                ).strip('-')[:40]
                ext_id = f'itf:{std_section}:{slug_name}:{country_code.lower()}:{position}'

                category_text = f'{gender_label} - {section_label}'

                yield {
                    'player_name': name,
                    'player_external_id': ext_id,
                    'category_text': category_text,
                    'gender': gender_code,
                    'ranking_position': ranking,
                    'payment_status': 'unknown',
                    'removed_or_replaced': is_withdrawn,
                    'replacement_reason': 'Desistência / Withdrawn' if is_withdrawn else '',
                    'player_country_code': country_code,
                    'player_country_name': country_name,
                    'source': 'itf',
                    'confidence': 'high',
                    'source_url': '',
                    '_raw': dict(p),
                }
