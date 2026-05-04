"""
ITF connector — International Tennis Federation.

Source: https://www.itftennis.com/en/
Uses the public tournament calendar search API (JSON).

Supports: Junior (Boys/Girls U14/U16/U18), Pro Circuit (M/W ITF).
Focus for Brazil MVP: Junior circuit in South America.

NOTE: For stable production access, use the ITF Data API (requires partnership).
This connector uses the public calendar endpoint.
Kill switch: DataSource.enabled = False
"""
import logging
from datetime import date, datetime

from .base import BaseConnector, ConnectorError, register_connector

logger = logging.getLogger('apps.ingestion.itf')


@register_connector
class ITFJuniorConnector(BaseConnector):
    key = 'itf_junior'

    # ITF public tournament search API
    CALENDAR_API = 'https://www.itftennis.com/api/api/en/tournament-calendar-search/'
    BASE_URL = 'https://www.itftennis.com'

    # ITF circuit codes
    CIRCUIT_CODES = {
        'itf_junior': 'JT',    # Junior circuit
        'itf_mens': 'MT',      # Men's ITF
        'itf_womens': 'WT',    # Women's ITF
    }

    STATUS_MAP = {
        'accepting entries': 'open',
        'entries closed': 'closed',
        'in progress': 'in_progress',
        'completed': 'finished',
        'cancelled': 'canceled',
        'upcoming': 'announced',
        'draws available': 'draws_published',
    }

    SURFACE_MAP = {
        'clay': 'clay',
        'hard (o)': 'hard',
        'hard (i)': 'hard',
        'hard': 'hard',
        'grass': 'grass',
        'carpet (i)': 'carpet',
        'carpet': 'carpet',
    }

    def extract(self):
        year = self.config.get('year') or date.today().year
        circuit = self.config.get('circuit', 'JT')  # Junior by default
        zone = self.config.get('zone', 'SAM')        # South America

        params = {
            'circuit': circuit,
            'zone': zone,
            'year': str(year),
            'pageSize': 50,
            'page': 1,
        }

        # ITF requires browser-like headers to avoid 403
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.itftennis.com/en/tournament-calendar/',
            'Origin': 'https://www.itftennis.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        })

        seen = set()
        while True:
            try:
                resp = self.fetch(self.CALENDAR_API, params=params)
                if resp.status_code == 403:
                    logger.warning('ITF calendar blocked (403) — mark for API partnership. Stopping.')
                    break
                if resp.status_code >= 400:
                    logger.warning('ITF calendar returned %s, stopping.', resp.status_code)
                    break
                data = resp.json()
            except (ConnectorError, ValueError) as exc:
                logger.warning('ITF fetch failed: %s', exc)
                break

            # ITF API wraps results in different keys depending on circuit
            items = (
                data.get('results')
                or data.get('tournaments')
                or data.get('items')
                or (data if isinstance(data, list) else [])
            )
            if not items:
                break

            for item in items:
                parsed = self._parse_item(item, year, circuit)
                if parsed and parsed['external_id'] not in seen:
                    seen.add(parsed['external_id'])
                    yield parsed

            # Pagination
            total = data.get('count', 0) if isinstance(data, dict) else 0
            page_size = params['pageSize']
            if total and len(seen) >= total:
                break
            if len(items) < page_size:
                break
            params['page'] += 1

    def _parse_item(self, item: dict, year: int, circuit: str) -> dict | None:
        ext_id = str(item.get('id') or item.get('tournamentId') or '')
        if not ext_id:
            return None

        title = item.get('name') or item.get('tournamentName') or ''
        if not title:
            return None

        start_raw = item.get('startDate') or item.get('start')
        end_raw = item.get('endDate') or item.get('end')
        deadline_raw = item.get('entryDeadline') or item.get('deadline')

        start_date = self._parse_date(start_raw)
        end_date = self._parse_date(end_raw)
        entry_close_at = self._parse_date(deadline_raw)

        status_raw = (item.get('status') or '').lower().strip()
        status = self.STATUS_MAP.get(status_raw, 'unknown')

        nation = item.get('nation') or item.get('country') or {}
        city = item.get('city') or (nation.get('name') if isinstance(nation, dict) else '')
        country_code = (nation.get('code') if isinstance(nation, dict) else nation) or 'BR'
        state = item.get('state') or ''

        surface_raw = (item.get('surface') or item.get('courtSurface') or '').lower()
        surface = self.SURFACE_MAP.get(surface_raw, surface_raw or 'unknown')

        grade = item.get('grade') or item.get('category') or ''
        categories = self._build_categories(item, grade)

        prize_money = item.get('prizeMoney') or item.get('totalPrizeMoney')

        source_path = item.get('url') or f'/en/tournament/{ext_id}'
        if not source_path.startswith('http'):
            source_path = f'{self.BASE_URL}{source_path}'

        circuit_label = 'ITF Junior' if 'JT' in circuit else 'ITF Pro'

        return {
            'external_id': f'itf:{ext_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'itf-{ext_id}-{title}'),
            'circuit': circuit_label,
            'modality': 'tennis',
            'season_year': year,
            'title': title,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'entry_open_at': None,
            'entry_close_at': entry_close_at.isoformat() if entry_close_at else None,
            'status': status,
            'surface': surface,
            'venue': {
                'name': '',
                'city': city,
                'state': state,
                'address': '',
            } if city else None,
            'base_price_brl': None,  # ITF uses USD prize money, not entry fee
            'official_source_url': source_path,
            'categories': categories,
            'links': [{'link_type': 'other', 'url': source_path, 'label': 'ITF Tournament'}],
        }

    def _parse_date(self, val):
        if not val:
            return None
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%d %b %Y'):
            try:
                return datetime.strptime(str(val)[:10], fmt[:len(fmt)])
            except ValueError:
                pass
        # ISO with timezone
        try:
            from dateutil.parser import parse
            return parse(str(val)).replace(tzinfo=None)
        except Exception:
            return None

    def _build_categories(self, item: dict, grade: str) -> list:
        cats = []
        # Junior draws: Boys/Girls per age group
        for draw_field in ['draws', 'events', 'categories']:
            draws = item.get(draw_field, [])
            if isinstance(draws, list):
                for draw in draws:
                    name = draw.get('name') or draw.get('drawType') or ''
                    if name:
                        cats.append({'source_text': name, 'price_brl': None, 'notes': ''})
        if not cats and grade:
            cats.append({'source_text': f'Grade {grade}', 'price_brl': None, 'notes': ''})
        return cats
