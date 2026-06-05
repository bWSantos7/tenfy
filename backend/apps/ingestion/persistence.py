"""
Persistence layer: turns normalized dicts (from connectors) into database rows,
detects material changes, records TournamentChangeEvent rows and fans out alerts.
"""
import json
import logging
import re
import unicodedata
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.core.utils import compute_content_hash, diff_dicts
from apps.sources.models import DataSource
from apps.tournaments.models import (
    Tournament,
    TournamentEdition,
    TournamentCategory,
    TournamentLink,
    TournamentChangeEvent,
    Venue,
)
from apps.players.models import PlayerCategory
from .models import IngestionRun

logger = logging.getLogger('apps.ingestion.persist')


def _trunc(value: str, max_len: int, label: str = '') -> str:
    if value and len(value) > max_len:
        logger.warning('Truncating %s from %d to %d chars', label or 'field', len(value), max_len)
        return value[:max_len]
    return value or ''


MATERIAL_FIELDS = {
    'start_date', 'end_date', 'entry_open_at', 'entry_close_at',
    'withdrawal_deadline_at',
    'status', 'surface', 'base_price_brl', 'title',
}

_DEDUP_STRIP = re.compile(r'[^a-z0-9]+')


def _dedup_fingerprint(title: str, start_date, city: str, state: str) -> str:
    """
    Stable fingerprint for cross-source deduplication.
    Two editions from different sources that share title + date + location
    will produce the same fingerprint and be merged.
    """
    norm_title = _DEDUP_STRIP.sub('', unicodedata.normalize('NFKD', title.lower()).encode('ascii', 'ignore').decode())
    norm_city = _DEDUP_STRIP.sub('', unicodedata.normalize('NFKD', city.lower()).encode('ascii', 'ignore').decode())
    date_str = str(start_date)[:10] if start_date else ''
    raw = f'{norm_title}|{date_str}|{norm_city}|{state.upper()[:2]}'
    import hashlib
    return hashlib.sha1(raw.encode()).hexdigest()[:16]

_YOUTH_KEYWORDS = {
    'infantojuvenil', 'infanto', 'juvenil', 'junior', 'júnior',
    'sub-', 'kids', 'mirim', 'petiz', 'escolinha', 'infantil',
    'youth', 'boys', 'girls',
}

# COSAT event codes that indicate youth categories (BS/GS/BD/GD = Boys/Girls Singles/Doubles)
_COSAT_YOUTH_CAT_PATTERN = re.compile(r'\b(BS|GS|BD|GD)\s*[Uu]?\s*\d{1,2}\b', re.IGNORECASE)

# ITF Junior grade patterns: J1–J5, ITF Junior, ITF Boys/Girls
_ITF_JUNIOR_PATTERN = re.compile(r'\b(J[1-5]|Junior|Boys|Girls|Youth)\b', re.IGNORECASE)


def _classify_is_youth(circuit: str, title: str, categories: list, source_name: str = '') -> bool:
    """Return True if the tournament appears to be for players up to 18 years old."""
    combined = (circuit + ' ' + title + ' ' + source_name).lower()

    # COSAT tournaments are predominantly youth (the platform focuses on juniors)
    if 'cosat' in combined:
        return True

    # ITF Junior grade
    if 'itf' in combined and _ITF_JUNIOR_PATTERN.search(title):
        return True

    if any(kw in combined for kw in _YOUTH_KEYWORDS):
        return True

    # Age in title: "14 anos" (PT), "14 años" (ES), "U14", "Sub-16"
    if re.search(r'\b(8|9|10|11|12|13|14|15|16|17|18)\s*a[ñn]os?\b', combined):
        return True
    if re.search(r'\b[Uu](8|9|10|11|12|13|14|15|16|17|18)\b', combined):
        return True
    if re.search(r'\bsub[- ]?(8|9|10|11|12|13|14|15|16|17|18)\b', combined):
        return True

    for cat in categories:
        cat_text = (cat.get('source_text') or '').lower()
        if any(kw in cat_text for kw in _YOUTH_KEYWORDS):
            return True
        # COSAT compact codes: BS U12, GS U14, BD16, etc.
        if _COSAT_YOUTH_CAT_PATTERN.search(cat.get('source_text') or ''):
            return True
        # Category descriptions with specific age ≤ 18 (PT + ES + U-prefix)
        if re.search(r'\b(8|9|10|11|12|13|14|15|16|17|18)\s*a[ñn]os?\b', cat_text):
            return True
        if re.search(r'\b[Uu](8|9|10|11|12|13|14|15|16|17|18)\b', cat_text):
            return True
        if re.search(r'\bsub[- ]?(8|9|10|11|12|13|14|15|16|17|18)\b', cat_text):
            return True
    return False


class TournamentPersister:
    def __init__(self, data_source: DataSource, run: IngestionRun):
        self.data_source = data_source
        self.run = run

    @transaction.atomic
    def upsert(self, data: dict):
        new_modality = (data.get('modality') or 'tennis').strip()
        new_circuit = (data.get('circuit') or '').strip()[:100]

        tournament, created_t = Tournament.objects.get_or_create(
            canonical_slug=data['canonical_slug'],
            defaults={
                'canonical_name': data['canonical_name'],
                'organization': self.data_source.organization,
                'circuit': new_circuit,
                'modality': new_modality,
            },
        )

        # Always sync modality and circuit from the connector on re-ingestion.
        # This fixes tournaments that were created with an incorrect modality
        # (e.g. beach_tennis imported as tennis before the inference was improved).
        if not created_t:
            t_updates: dict = {}
            if new_modality and tournament.modality != new_modality:
                t_updates['modality'] = new_modality
                logger.info(
                    'Modality corrected for tournament %s: %s → %s',
                    tournament.canonical_slug, tournament.modality, new_modality,
                )
            if new_circuit and tournament.circuit != new_circuit:
                t_updates['circuit'] = new_circuit
            if t_updates:
                for k, v in t_updates.items():
                    setattr(tournament, k, v)
                tournament.save(update_fields=list(t_updates.keys()) + ['updated_at'])

        venue = None
        v = data.get('venue') or {}
        if v.get('city') or v.get('state') or v.get('name') or v.get('country'):
            venue, created_v = Venue.objects.get_or_create(
                name=_trunc(v.get('name') or '—', 200, 'Venue.name'),
                city=_trunc(v.get('city', ''), 120, 'Venue.city'),
                state=(v.get('state') or '').upper()[:2],
                defaults={
                    'address': (v.get('address') or '')[:300],
                    'country': _trunc(v.get('country') or '', 120, 'Venue.country'),
                    'country_code': (v.get('country_code') or '')[:3].upper(),
                },
            )
            # Update country fields if venue already existed without them
            if not created_v and (v.get('country') or v.get('country_code')):
                venue_updates = {}
                if v.get('country') and not venue.country:
                    venue_updates['country'] = _trunc(v.get('country'), 120, 'Venue.country')
                if v.get('country_code') and not venue.country_code:
                    venue_updates['country_code'] = v.get('country_code', '')[:3].upper()
                if venue_updates:
                    for k, val in venue_updates.items():
                        setattr(venue, k, val)
                    venue.save(update_fields=list(venue_updates.keys()) + ['updated_at'])

        hash_payload = {
            k: data.get(k) for k in [
                'title', 'start_date', 'end_date',
                'entry_open_at', 'entry_close_at',
                'status', 'surface', 'base_price_brl',
                'venue', 'categories', 'official_source_url',
            ]
        }
        content_hash = compute_content_hash(
            json.dumps(hash_payload, sort_keys=True, default=str)
        )

        external_id = _trunc(data.get('external_id', ''), 120, 'external_id')
        season_year = int(data.get('season_year') or timezone.now().year)
        ed = TournamentEdition.objects.filter(
            tournament=tournament,
            season_year=season_year,
            external_id=external_id,
        ).first()

        # Cross-source deduplication: if no edition found by external_id, look for a
        # fingerprint match from any other source to avoid creating duplicates.
        if not ed and external_id:
            v_city = (data.get('venue') or {}).get('city', '')
            v_state = (data.get('venue') or {}).get('state', '')
            fp = _dedup_fingerprint(
                data.get('title') or data.get('canonical_name', ''),
                data.get('start_date'),
                v_city,
                v_state,
            )
            if fp:
                candidate = TournamentEdition.objects.filter(
                    season_year=season_year,
                    dedup_fingerprint=fp,
                ).exclude(data_source=self.data_source).first()
                if candidate:
                    logger.info(
                        'Dedup: merging %s (ext_id=%s) into existing edition %s (ext_id=%s)',
                        self.data_source.connector_key, external_id,
                        candidate.data_source.connector_key if candidate.data_source else '?',
                        candidate.external_id,
                    )
                    ed = candidate

        created = False
        changes: dict = {}

        is_youth = _classify_is_youth(
            data.get('circuit', ''),
            data.get('title', ''),
            data.get('categories') or [],
            source_name=data.get('source_name', '') or getattr(self.data_source, 'source_name', ''),
        )

        v_city = (data.get('venue') or {}).get('city', '')
        v_state = (data.get('venue') or {}).get('state', '').upper()[:2]

        # Detect UF mismatch: org has a state but the venue is in a different state.
        # This often signals a wrong source assignment or bad scraping.
        # We store the warning in validation_errors rather than blocking ingestion.
        ingest_validation_errors: list = []
        org_state = (getattr(self.data_source.organization, 'state', None) or '').upper()[:2]
        if org_state and v_state and org_state != v_state:
            warn = (
                f'uf_mismatch: org_state={org_state} venue_state={v_state} '
                f'(org={self.data_source.organization.short_name or self.data_source.organization.name})'
            )
            ingest_validation_errors.append(warn)
            logger.warning(
                'UF mismatch for %s: org_state=%s venue_state=%s title=%s',
                self.data_source.connector_key, org_state, v_state,
                data.get('title', ''),
            )

        fingerprint = _dedup_fingerprint(
            data.get('title') or data.get('canonical_name', ''),
            data.get('start_date'),
            v_city,
            v_state,
        )

        acceptance_list = data.get('acceptance_list') or []

        if not ed:
            ed = TournamentEdition.objects.create(
                tournament=tournament,
                season_year=season_year,
                external_id=external_id,
                title=_trunc(data.get('title') or data.get('canonical_name') or '', 300, 'title'),
                start_date=self._parse_date(data.get('start_date')),
                end_date=self._parse_date(data.get('end_date')),
                entry_open_at=self._parse_dt(data.get('entry_open_at')),
                entry_close_at=self._parse_dt(data.get('entry_close_at')),
                withdrawal_deadline_at=self._parse_dt(data.get('withdrawal_deadline_at')),
                has_online_entry=bool(data.get('has_online_entry', False)),
                status=data.get('status') or TournamentEdition.STATUS_UNKNOWN,
                surface=data.get('surface') or TournamentEdition.SURFACE_UNKNOWN,
                venue=venue,
                base_price_brl=data.get('base_price_brl'),
                price_notes=_trunc(data.get('price_notes') or '', 300, 'price_notes'),
                data_source=self.data_source,
                official_source_url=data.get('official_source_url', ''),
                source_name=_trunc(self.data_source.source_name, 120, 'source_name'),
                fetched_at=timezone.now(),
                raw_content_hash=content_hash,
                raw_payload=data,
                data_confidence=TournamentEdition.CONFIDENCE_MED,
                is_youth=is_youth,
                dedup_fingerprint=fingerprint,
                validation_errors=ingest_validation_errors,
                acceptance_list=acceptance_list,
            )
            created = True
            TournamentChangeEvent.objects.create(
                edition=ed,
                event_type=TournamentChangeEvent.EVENT_CREATED,
                field_changes={'created': True},
                ingestion_run=self.run,
            )
        else:
            if ed.is_manual_override:
                ed.fetched_at = timezone.now()
                ed.raw_payload = data
                ed.save(update_fields=['fetched_at', 'raw_payload', 'updated_at'])
            else:
                before = {
                    'title': ed.title,
                    'start_date': ed.start_date.isoformat() if ed.start_date else None,
                    'end_date': ed.end_date.isoformat() if ed.end_date else None,
                    'entry_open_at': ed.entry_open_at.isoformat() if ed.entry_open_at else None,
                    'entry_close_at': ed.entry_close_at.isoformat() if ed.entry_close_at else None,
                    'withdrawal_deadline_at': ed.withdrawal_deadline_at.isoformat() if ed.withdrawal_deadline_at else None,
                    'status': ed.status,
                    'surface': ed.surface,
                    'base_price_brl': float(ed.base_price_brl) if ed.base_price_brl else None,
                }
                after = {
                    'title': data.get('title') or data.get('canonical_name'),
                    'start_date': data.get('start_date'),
                    'end_date': data.get('end_date'),
                    'entry_open_at': data.get('entry_open_at'),
                    'entry_close_at': data.get('entry_close_at'),
                    'withdrawal_deadline_at': data.get('withdrawal_deadline_at'),
                    'status': data.get('status') or ed.status,
                    'surface': data.get('surface') or ed.surface,
                    'base_price_brl': data.get('base_price_brl'),
                }
                changes = {
                    k: v for k, v in diff_dicts(before, after).items()
                    if k in MATERIAL_FIELDS
                }

                ed.title = _trunc(after['title'] or ed.title, 300, 'title')
                ed.start_date = self._parse_date(after['start_date']) or ed.start_date
                ed.end_date = self._parse_date(after['end_date']) or ed.end_date
                ed.entry_open_at = self._parse_dt(after['entry_open_at']) or ed.entry_open_at
                ed.entry_close_at = self._parse_dt(after['entry_close_at']) or ed.entry_close_at
                new_wd = self._parse_dt(data.get('withdrawal_deadline_at'))
                if new_wd:
                    ed.withdrawal_deadline_at = new_wd
                if 'has_online_entry' in data:
                    ed.has_online_entry = bool(data['has_online_entry'])
                if after['status']:
                    ed.status = after['status']
                if after['surface']:
                    ed.surface = after['surface']
                if after['base_price_brl'] is not None:
                    ed.base_price_brl = after['base_price_brl']
                if data.get('price_notes'):
                    ed.price_notes = _trunc(data['price_notes'], 300, 'price_notes')
                if venue:
                    ed.venue = venue
                ed.official_source_url = data.get('official_source_url') or ed.official_source_url
                ed.fetched_at = timezone.now()
                ed.raw_content_hash = content_hash
                ed.raw_payload = data
                # Update acceptance list if new data provided
                if acceptance_list:
                    ed.acceptance_list = acceptance_list
                # Always update is_youth from classifier unless manual override.
                # This ensures a corrected classifier fixes existing editions on re-sync.
                if not ed.is_manual_override:
                    ed.is_youth = is_youth
                if fingerprint and not ed.dedup_fingerprint:
                    ed.dedup_fingerprint = fingerprint
                # Refresh validation_errors so stale UF mismatches are resolved if
                # the organisation or venue data was corrected in a later run.
                ed.validation_errors = ingest_validation_errors
                ed.save()

                if changes:
                    event_type = self._pick_event_type(changes)
                    TournamentChangeEvent.objects.create(
                        edition=ed,
                        event_type=event_type,
                        field_changes=changes,
                        ingestion_run=self.run,
                    )

        new_cats = data.get('categories') or []
        if new_cats:
            existing = {tc.source_category_text: tc for tc in ed.categories.all()}
            seen = set()
            for order, c in enumerate(new_cats):
                text = (c.get('source_text') or '').strip()
                if not text:
                    continue
                seen.add(text)
                tc = existing.get(text)
                norm = self._match_category(text)
                if tc:
                    tc.price_brl = c.get('price_brl') if c.get('price_brl') is not None else tc.price_brl
                    tc.visibility_order = c.get('order', order)
                    tc.notes = c.get('notes', '')
                    if norm and not tc.normalized_category_id:
                        tc.normalized_category = norm
                    tc.save()
                else:
                    TournamentCategory.objects.create(
                        edition=ed,
                        source_category_text=text,
                        normalized_category=norm,
                        price_brl=c.get('price_brl'),
                        visibility_order=c.get('order', order),
                        notes=c.get('notes', ''),
                    )
            for text, tc in existing.items():
                if text not in seen:
                    tc.delete()

        for link in data.get('links') or []:
            TournamentLink.objects.update_or_create(
                edition=ed,
                link_type=link.get('link_type', 'other'),
                url=link.get('url', ''),
                defaults={
                    'label': link.get('label', ''),
                    'is_official': link.get('is_official', True),
                    'source_name': self.data_source.source_name,
                    'fetched_at': timezone.now(),
                },
            )

        return ed, created, changes

    @staticmethod
    def _parse_date(v):
        if not v:
            return None
        if hasattr(v, 'year') and hasattr(v, 'month') and not hasattr(v, 'hour'):
            return v
        from datetime import datetime, date
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        try:
            return datetime.strptime(str(v)[:10], '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _parse_dt(v):
        if not v:
            return None
        if hasattr(v, 'tzinfo'):
            return v
        from datetime import datetime
        s = str(v)
        for fmt in ('%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(s[:len(fmt) + 2], fmt)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                return dt
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _pick_event_type(changes: dict) -> str:
        if 'status' in changes:
            new_status = changes['status'].get('new')
            if new_status == 'canceled':
                return TournamentChangeEvent.EVENT_CANCELED
            if new_status == 'draws_published':
                return TournamentChangeEvent.EVENT_DRAWS
            return TournamentChangeEvent.EVENT_STATUS
        if 'entry_close_at' in changes or 'entry_open_at' in changes:
            return TournamentChangeEvent.EVENT_DEADLINE
        if 'start_date' in changes or 'end_date' in changes:
            return TournamentChangeEvent.EVENT_DATE
        if 'base_price_brl' in changes:
            return TournamentChangeEvent.EVENT_PRICE
        return TournamentChangeEvent.EVENT_OTHER

    _CATEGORY_CACHE: Optional[dict] = None

    @classmethod
    def _load_category_cache(cls):
        if cls._CATEGORY_CACHE is not None:
            return cls._CATEGORY_CACHE
        cache = {}
        for cat in PlayerCategory.objects.all():
            cache[cat.code.upper()] = cat
        cls._CATEGORY_CACHE = cache
        return cache

    @classmethod
    def invalidate_category_cache(cls):
        cls._CATEGORY_CACHE = None

    def _match_category(self, source_text: str) -> Optional[PlayerCategory]:
        cache = self._load_category_cache()
        t = source_text.upper().strip()
        if t in cache:
            return cache[t]
        t2 = re.sub(r'\s+', '', t)
        if t2 in cache:
            return cache[t2]
        m = re.match(r'^(\d)([MF])(\d?)$', t2)
        if m:
            key = m.group(1) + m.group(2) + m.group(3)
            if key in cache:
                return cache[key]
        m = re.match(r'^(\d{1,2})([MF])$', t2)
        if m:
            key = m.group(1) + m.group(2)
            if key in cache:
                return cache[key]
        m = re.match(r'^(\d{2})\+([MF]?)$', t2)
        if m:
            key = m.group(1) + '+' + (m.group(2) or '')
            if key in cache:
                return cache[key]
        inferred = self._infer_category_code(source_text)
        if inferred and inferred in cache:
            return cache[inferred]
        return None

    @staticmethod
    def _infer_category_code(source_text: str) -> Optional[str]:
        normalized = TournamentPersister._normalize_category_text(source_text)

        age_match = re.search(r'\b(8|9|10|11|12|14|16|18)\s*ANOS?\b', normalized)
        gender = TournamentPersister._extract_gender(normalized)
        if age_match and gender in {'M', 'F'}:
            return f'{age_match.group(1)}{gender}'

        age_gender_match = re.search(r'\b(10|12|14|16|18)\s*([MF])\b', normalized)
        if age_gender_match:
            return f'{age_gender_match.group(1)}{age_gender_match.group(2)}'

        senior_match = re.search(r'\b(30|35|40|45|50|55|60|65|70|75)\+\b', normalized)
        if senior_match:
            if gender in {'M', 'F'}:
                return f'{senior_match.group(1)}+{gender}'
            return f'{senior_match.group(1)}+'

        class_match = re.search(r'\b([1-5])\s*A?\s*CLASSE\b', normalized)
        if class_match and gender in {'M', 'F'}:
            suffix = '1' if ' M1' in normalized else '2' if ' M2' in normalized else ''
            return f'{class_match.group(1)}{gender}{suffix}'

        if 'PRINCIPIANTE' in normalized and gender in {'M', 'F'}:
            return f'PR{gender}'

        if 'OPEN' in normalized and gender in {'M', 'F'}:
            return f'OPEN{gender}'

        return None

    @staticmethod
    def _normalize_category_text(source_text: str) -> str:
        normalized = unicodedata.normalize('NFKD', source_text).encode('ascii', 'ignore').decode('ascii')
        normalized = normalized.upper()
        normalized = re.sub(r'[^A-Z0-9+\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    @staticmethod
    def _extract_gender(normalized_text: str) -> Optional[str]:
        if 'MASCULINO' in normalized_text:
            return 'M'
        if 'FEMININO' in normalized_text:
            return 'F'
        if 'MISTA' in normalized_text:
            return None
        return None
