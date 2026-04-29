"""
COSAT connector — Confederación Sudamericana de Tenis.

Source: https://cosat.tournamentsoftware.com/

⚠️  STATUS: DISABLED — robots.txt restriction + API endpoint unavailable.

robots.txt (User-agent: *) disallows:
  /sport/, /tournament/, /ranking/, /player/, /profile/
  These are exactly the paths needed for tournament and entry data.

The search API endpoint (/api/tournament/search?organisationId=6) returns HTTP 404
as of 2026-04-28 — no longer publicly available.

Paths to 10/10:
  Option A: Official API partnership with COSAT / TournamentSoftware
  Option B: Manual admin import via bulk-import endpoint
  Option C: Website Content Crawler service with official permission
  Option D: ITF Junior API (COSAT tournaments sometimes appear in ITF feed)

The connector class is kept to preserve the registered_connectors() registry
and allow future activation. It will abort immediately with a clear log message
when called, respecting robots.txt and not accessing disallowed paths.
"""
import logging
import re
from datetime import datetime, date

from .base import BaseConnector, ConnectorError, register_connector

logger = logging.getLogger('apps.ingestion.cosat')


@register_connector
class COSATConnector(BaseConnector):
    key = 'cosat_public'

    # TournamentSoftware public search API used by COSAT
    SEARCH_URL = 'https://cosat.tournamentsoftware.com/api/tournament/search'
    BASE_URL = 'https://cosat.tournamentsoftware.com'

    CATEGORY_MAP = {
        '12': '12', '14': '14', '16': '16', '18': '18',
        'boys': 'M', 'girls': 'F',
        'junior': 'juvenile',
        'u12': '12', 'u14': '14', 'u16': '16', 'u18': '18',
    }

    STATUS_MAP = {
        'upcoming': 'announced',
        'accepting entries': 'open',
        'entry closed': 'closed',
        'in progress': 'in_progress',
        'completed': 'finished',
        'cancelled': 'canceled',
    }

    def extract(self):
        """
        COSAT extraction is disabled:
          - robots.txt (User-agent: *) disallows /sport/, /tournament/, /ranking/
          - /api/tournament/search endpoint returns HTTP 404 (unavailable)
          - Accessing disallowed paths would violate the site's crawl policy

        To re-enable, obtain official API access from COSAT/TournamentSoftware
        and update DataSource.enabled=True via the admin panel.
        """
        logger.error(
            'COSAT connector called but is DISABLED: robots.txt disallows /sport/ and '
            '/tournament/ for all crawlers, and the search API endpoint returned 404. '
            'Action required: obtain official API partnership with COSAT to re-enable. '
            'Manual import is available via /api/registrations/federation/bulk-import/'
        )
        # Yield nothing — connector is intentionally non-functional
        return
        yield  # make this a generator

    def _parse_item(self, item: dict, year: int) -> dict | None:
        ext_id = str(item.get('id') or item.get('tournamentId') or '')
        if not ext_id:
            return None

        title = item.get('name') or item.get('title') or ''
        if not title:
            return None

        start_date = self._parse_ts(item.get('startDate') or item.get('start_date'))
        end_date = self._parse_ts(item.get('endDate') or item.get('end_date'))
        entry_close_at = self._parse_ts(item.get('entryDeadline') or item.get('deadlineDate'))

        status_raw = (item.get('status') or item.get('statusText') or '').lower().strip()
        status = self.STATUS_MAP.get(status_raw, 'unknown')

        city = item.get('city') or item.get('venue', {}).get('city', '') if isinstance(item.get('venue'), dict) else item.get('location', '')
        country = item.get('country') or item.get('countryCode') or 'BR'
        state = item.get('state') or item.get('region') or ''

        # Categories from grade/level fields
        categories = self._extract_categories(item)

        source_url = item.get('url') or f'{self.BASE_URL}/tournament/{ext_id}'

        return {
            'external_id': f'cosat:{ext_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'cosat-{ext_id}-{title}'),
            'circuit': 'COSAT',
            'modality': 'tennis',
            'season_year': year,
            'title': title,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'entry_open_at': None,
            'entry_close_at': entry_close_at.isoformat() if entry_close_at else None,
            'status': status,
            'surface': self._normalize_surface(item.get('surface') or item.get('courtSurface') or ''),
            'venue': {
                'name': item.get('venueName') or '',
                'city': city,
                'state': state,
                'address': '',
            } if city or state else None,
            'base_price_brl': None,  # COSAT is international; price in USD/local currency
            'official_source_url': source_url,
            'categories': categories,
            'links': [{'link_type': 'other', 'url': source_url, 'label': 'COSAT TournamentSoftware'}],
        }

    def _parse_ts(self, ts):
        if not ts:
            return None
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(str(ts)[:19], fmt)
                return dt
            except ValueError:
                continue
        return None

    def _extract_categories(self, item: dict) -> list:
        cats = []
        # Grade/draw type fields common in TournamentSoftware responses
        for field in ['categories', 'draws', 'events', 'grades']:
            field_data = item.get(field)
            if isinstance(field_data, list):
                for cat in field_data:
                    name = cat.get('name') or cat.get('drawType') or cat.get('category') or ''
                    if name:
                        cats.append({'source_text': name, 'price_brl': None, 'notes': ''})
        # Fallback: grade field
        if not cats and item.get('grade'):
            cats.append({'source_text': f"Grade {item['grade']}", 'price_brl': None, 'notes': ''})
        return cats

    def _normalize_surface(self, surface: str) -> str:
        s = surface.lower().strip()
        mapping = {
            'clay': 'clay', 'terre battue': 'clay', 'polvo de ladrillo': 'clay',
            'hard': 'hard', 'cemento': 'hard', 'ciment': 'hard',
            'grass': 'grass', 'cesped': 'grass', 'gazon': 'grass',
            'carpet': 'carpet', 'indoor': 'hard',
        }
        for key, val in mapping.items():
            if key in s:
                return val
        return s or 'unknown'
