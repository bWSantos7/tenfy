"""
UTR Sports connector — Universal Tennis Rating (v2 events API).

Source: https://app.utrsports.net / https://api.utrsports.net/v2/search/events

The legacy v1 API was retired (HTTP 410). This connector uses the v2 events
search, which is the only public-ish surface: it returns event summaries AND,
when the session is authenticated, the entrant list (`registeredMembers`) and
event divisions. Per-event detail endpoints require auth and are not used.

Authentication (backend-only, never exposed to clients):
  - settings.UTR_API_TOKEN → sent as Bearer, OR
  - settings.UTR_EMAIL + settings.UTR_PASSWORD → POST /api/v1/auth/login sets a
    `jwt` cookie on the session.
Without credentials the connector still ingests public summary fields but the
entrant list comes back empty.

Scope (config_json):
  - country_code3:  ISO-3 country filter, default 'BRA' (client-side; the v2
                    search has no working server-side country param).
  - youth_only:     keep only infantojuvenil events (ages 12–18), default True.
  - youth_min/max:  age window, default 12–18.
  - start_date/end_date: ISO date window (default: this month → +12 months).
  - max_pages / page_size: paging guard.

Kill switch: DataSource.enabled = False.
"""
import logging
import re
from datetime import date, datetime, timedelta

from django.conf import settings

from .base import BaseConnector, ConnectorError, register_connector

logger = logging.getLogger('apps.ingestion.utr')

# Age tokens in a division/event name: "Sub 14", "U16", "14U", "16 anos", "12&under".
_AGE_PATTERNS = [
    re.compile(r'\bsub[\s\-]?(\d{1,2})\b', re.I),
    re.compile(r'\bu[\s\-]?(\d{1,2})\b', re.I),
    re.compile(r'\b(\d{1,2})\s*u\b', re.I),
    re.compile(r'\b(\d{1,2})\s*(?:anos|años|years)\b', re.I),
    re.compile(r'\b(\d{1,2})\s*&?\s*under\b', re.I),
]
# Words that signal a youth event even without an explicit number.
_YOUTH_WORDS = re.compile(r'\b(infanto[\s\-]?juvenil|infantojuvenil|juvenil|infantil|junior|j[uú]nior)\b', re.I)
# Words that signal an adult/open event (used to exclude when no youth age found).
_ADULT_WORDS = re.compile(r'\b(livre|adulto|open|profissional|professional|atp|wta|sen[ií]or|veterano|\d{2}\+)\b', re.I)


@register_connector
class UTRConnector(BaseConnector):
    key = 'utr_public'

    LOGIN_URL = 'https://app.utrsports.net/api/v1/auth/login'
    EVENTS_API = 'https://api.utrsports.net/v2/search/events'
    APP_BASE = 'https://app.utrsports.net'

    # eventState.registrationState.value / eventState.value → TournamentEdition status
    STATUS_MAP = {
        'open_registration': 'open',
        'open': 'open',
        'accepting': 'open',
        'registration_closed': 'closed',
        'closed': 'closed',
        'in_progress': 'in_progress',
        'inprogress': 'in_progress',
        'completed': 'finished',
        'complete': 'finished',
        'finished': 'finished',
        'cancelled': 'canceled',
        'canceled': 'canceled',
        'upcoming': 'announced',
        'not_open': 'announced',
        'draft': 'announced',
    }

    SURFACE_MAP = {
        'clay': 'clay', 'hard': 'hard', 'grass': 'grass',
        'carpet': 'carpet', 'indoor': 'hard', 'sand': 'sand',
    }

    def _headers(self):
        return {
            'Accept': 'application/json, text/plain, */*',
            'Origin': self.APP_BASE,
            'Referer': f'{self.APP_BASE}/',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            ),
        }

    def _authenticate(self) -> bool:
        """Set up an authenticated session. Returns True when the entrant list
        should be available (token or successful login)."""
        self.session.headers.update(self._headers())
        token = getattr(settings, 'UTR_API_TOKEN', '') or ''
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'
            return True
        email = getattr(settings, 'UTR_EMAIL', '') or ''
        password = getattr(settings, 'UTR_PASSWORD', '') or ''
        if not (email and password):
            logger.warning('UTR: no credentials configured — entrants will be empty.')
            return False
        try:
            resp = self.session.post(
                self.LOGIN_URL, json={'email': email, 'password': password},
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning('UTR login request failed: %s', exc)
            return False
        if resp.status_code != 200:
            logger.warning('UTR login failed (status %s) — entrants will be empty.', resp.status_code)
            return False
        # Success sets a `jwt` cookie on the session, reused for subsequent calls.
        return True

    def extract(self):
        country = (self.config.get('country_code3') or 'BRA').upper()
        youth_only = self.config.get('youth_only', True)
        youth_min = int(self.config.get('youth_min', 12))
        youth_max = int(self.config.get('youth_max', 18))
        page_size = int(self.config.get('page_size', 100))
        max_pages = int(self.config.get('max_pages', 60))

        today = date.today()
        start_date = self.config.get('start_date') or today.replace(day=1).isoformat()
        end_date = self.config.get('end_date') or (today + timedelta(days=365)).isoformat()

        self._authenticate()

        seen = set()
        skip = 0
        for _ in range(max_pages):
            params = {
                'top': page_size, 'skip': skip,
                'startDate': start_date, 'endDate': end_date, 'sport': 'tennis',
            }
            try:
                resp = self.fetch(self.EVENTS_API, params=params)
                if resp.status_code >= 400:
                    logger.warning('UTR events API returned %s — stopping.', resp.status_code)
                    break
                data = resp.json()
            except (ConnectorError, ValueError) as exc:
                logger.warning('UTR fetch failed: %s', exc)
                break

            hits = data.get('hits') or []
            if not hits:
                break

            for hit in hits:
                src = hit.get('source') or hit.get('_source') or hit
                if not isinstance(src, dict):
                    continue
                loc = (src.get('eventLocations') or [{}])
                loc0 = loc[0] if loc else {}
                if country and (loc0.get('countryCode3') or '').upper() != country:
                    continue
                parsed = self._parse_event(src, loc0, youth_only, youth_min, youth_max)
                if not parsed:
                    continue
                if parsed['external_id'] in seen:
                    continue
                seen.add(parsed['external_id'])
                yield parsed

            total = data.get('total')
            total_val = total.get('value', 0) if isinstance(total, dict) else (total or 0)
            skip += page_size
            if skip >= total_val or len(hits) < page_size:
                break

    # ── Parsing ──────────────────────────────────────────────────────────────

    def _division_names(self, src: dict) -> list:
        names = []
        for field in ('eventDivisions', 'divisions'):
            data = src.get(field)
            if isinstance(data, list):
                for d in data:
                    if isinstance(d, dict) and d.get('name'):
                        names.append(str(d['name']))
                    elif isinstance(d, str):
                        names.append(d)
        return names

    def _matches_youth(self, title: str, division_names: list, lo: int, hi: int) -> bool:
        """True when title/divisions reference an age within [lo, hi]."""
        haystack = ' '.join([title or ''] + division_names)
        ages = set()
        for pat in _AGE_PATTERNS:
            for m in pat.finditer(haystack):
                try:
                    ages.add(int(m.group(1)))
                except (TypeError, ValueError):
                    pass
        if any(lo <= a <= hi for a in ages):
            return True
        # No explicit age: accept generic youth words, but only when no adult
        # marker is present (avoid "Livre"/"Open"/"ATP").
        if _YOUTH_WORDS.search(haystack) and not _ADULT_WORDS.search(haystack):
            return True
        return False

    def _parse_event(self, src: dict, loc0: dict, youth_only: bool, lo: int, hi: int):
        ext_id = str(src.get('id') or '')
        title = (src.get('name') or '').strip()
        if not ext_id or not title:
            return None

        division_names = self._division_names(src)
        if youth_only and not self._matches_youth(title, division_names, lo, hi):
            return None

        schedule = src.get('eventSchedule') or {}
        start_dt = self._parse_dt(schedule.get('eventStartUtc'))
        end_dt = self._parse_dt(schedule.get('eventEndUtc'))
        reg_open = self._parse_dt(schedule.get('registrationStartUtc'))
        reg_close = self._parse_dt(schedule.get('registrationEndUtc'))

        season_year = (start_dt or date.today()).year

        state_raw = (src.get('eventState') or {})
        reg_state = (state_raw.get('registrationState') or {}).get('value') or ''
        status = self.STATUS_MAP.get(reg_state.lower()) \
            or self.STATUS_MAP.get(str(state_raw.get('value') or '').lower()) \
            or 'unknown'

        surface_raw = (src.get('surfaceType') or '')
        if isinstance(surface_raw, dict):
            surface_raw = surface_raw.get('value') or ''
        surface = self.SURFACE_MAP.get(str(surface_raw).lower(), 'unknown')

        # Price: UTR fees are commonly in USD; only set BRL when the currency says so.
        price_text = (src.get('priceRange') or src.get('priceRangeShort') or '').strip()
        currency = ((src.get('currencyInfo') or {}).get('abbreviation') or '').upper()
        base_price_brl = self.parse_price_brl(price_text) if currency == 'BRL' else None
        price_notes = price_text if price_text else ''
        if price_text and currency and currency != 'BRL':
            price_notes = f'{price_text} ({currency})'

        venue = {
            'name': (src.get('club') or {}).get('name') or loc0.get('placeName') or '',
            'city': loc0.get('cityName') or '',
            'state': (loc0.get('stateAbbr') or '')[:2].upper(),
            'address': loc0.get('streetAddress') or '',
            'country': loc0.get('countryName') or '',
            'country_code': (loc0.get('countryCode3') or '')[:3].upper(),
        }
        latlng = loc0.get('latLng') or []
        # (lat, lng captured for future geocoding; persistence ignores unknown keys)

        categories = []
        for name in division_names:
            categories.append({'source_text': name, 'price_brl': None, 'notes': ''})
        utr_range = src.get('utrRange')
        gender = src.get('gender')
        ctx = ' · '.join(filter(None, [
            f'UTR {utr_range}' if utr_range else '',
            f'Gênero: {gender}' if gender else '',
        ]))
        if ctx:
            categories.append({'source_text': ctx, 'price_brl': None, 'notes': 'UTR context'})

        acceptance_list = self._build_acceptance_list(src)

        source_url = f'{self.APP_BASE}/events/{ext_id}'

        return {
            'external_id': f'utr:{ext_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'utr-{ext_id}-{title}'),
            'circuit': 'UTR',
            'modality': 'tennis',
            'season_year': season_year,
            'title': title,
            'start_date': start_dt.date().isoformat() if start_dt else None,
            'end_date': end_dt.date().isoformat() if end_dt else None,
            'entry_open_at': reg_open.isoformat() + 'Z' if reg_open else None,
            'entry_close_at': reg_close.isoformat() + 'Z' if reg_close else None,
            'status': status,
            'surface': surface,
            'venue': venue if (venue['city'] or venue['country']) else None,
            'base_price_brl': base_price_brl,
            'price_notes': price_notes[:300],
            'official_source_url': source_url,
            'source_name': 'UTR Sports',
            'categories': categories,
            'acceptance_list': acceptance_list,
            'links': [{'link_type': 'registration', 'url': source_url, 'label': 'UTR Sports Event'}],
        }

    def _build_acceptance_list(self, src: dict) -> list:
        """Map UTR `registeredMembers` to the edition acceptance_list shape."""
        members = src.get('registeredMembers') or []
        players = []
        for m in members:
            if not isinstance(m, dict):
                continue
            name = ' '.join(filter(None, [m.get('firstName'), m.get('lastName')])).strip()
            if not name:
                continue
            players.append({
                'name': name,
                'country': '',
                'country_code': '',
                'ranking': None,
                'wtn': '',
                'priority': None,
                'information': f'UTR member {m.get("memberId")}' if m.get('memberId') else '',
            })
        if not players:
            return []
        return [{'section': 'registered', 'players': players}]

    def _parse_dt(self, val):
        if not val:
            return None
        s = str(val)
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(s[:len('2026-01-01T00:00:00') if 'T' in s else 10], fmt)
            except ValueError:
                continue
        try:
            from dateutil.parser import parse
            return parse(s).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            return None
