"""
UTR Sports connector — Universal Tennis Rating.

Source: https://www.utrsports.net/
Uses the public UTR Events search API.

UTR focuses on rating-based events accessible worldwide.
For Brazil MVP, fetches events in Brazil (countryCode=BRA).

NOTE: Full access requires a UTR account/API key for some endpoints.
This connector uses the public search endpoint.
Kill switch: DataSource.enabled = False
"""
import logging
from datetime import date, datetime

from .base import BaseConnector, ConnectorError, register_connector

logger = logging.getLogger('apps.ingestion.utr')


@register_connector
class UTRConnector(BaseConnector):
    key = 'utr_public'

    # UTR public events search API
    EVENTS_API = 'https://api.utrsports.net/v1/search/events'
    BASE_URL = 'https://app.utrsports.net'

    STATUS_MAP = {
        'accepting': 'open',
        'open': 'open',
        'closed': 'closed',
        'in-progress': 'in_progress',
        'completed': 'finished',
        'cancelled': 'canceled',
        'upcoming': 'announced',
    }

    SURFACE_MAP = {
        'clay': 'clay',
        'hard': 'hard',
        'grass': 'grass',
        'carpet': 'carpet',
        'indoor': 'hard',
    }

    def extract(self):
        year = self.config.get('year') or date.today().year
        country = self.config.get('country', 'BRA')  # ISO 3166-1 alpha-3

        params = {
            'top': 50,
            'skip': 0,
            'countryCode': country,
            'startDate': f'{year}-01-01',
            'endDate': f'{year}-12-31',
            'sport': 'tennis',
        }

        # UTR requires session-like headers — update session for all requests
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8',
            'Origin': 'https://app.utrsports.net',
            'Referer': 'https://app.utrsports.net/events',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
        })

        seen = set()
        max_pages = 20  # Safety limit

        for _ in range(max_pages):
            try:
                resp = self.fetch(self.EVENTS_API, params=params)
                if resp.status_code == 401 or resp.status_code == 403:
                    logger.warning('UTR API requires auth (status %s) — stopping. Add API key to config.', resp.status_code)
                    break
                if resp.status_code >= 400:
                    logger.warning('UTR API returned %s — stopping.', resp.status_code)
                    break
                data = resp.json()
            except (ConnectorError, ValueError) as exc:
                logger.warning('UTR fetch failed: %s', exc)
                break

            # UTR response structure
            hits = (
                data.get('hits')
                or data.get('events')
                or data.get('results')
                or (data if isinstance(data, list) else [])
            )
            if not hits:
                break

            for hit in hits:
                # UTR wraps in _source for Elasticsearch-style results
                item = hit.get('_source') or hit.get('source') or hit
                if not isinstance(item, dict):
                    continue
                parsed = self._parse_item(item, year)
                if parsed and parsed['external_id'] not in seen:
                    seen.add(parsed['external_id'])
                    yield parsed

            # Check if more pages exist
            total = data.get('total', {})
            if isinstance(total, dict):
                total_val = total.get('value', 0)
            else:
                total_val = total or 0

            params['skip'] += params['top']
            if params['skip'] >= total_val:
                break
            if len(hits) < params['top']:
                break

    def _parse_item(self, item: dict, year: int) -> dict | None:
        ext_id = str(item.get('id') or item.get('eventId') or '')
        if not ext_id:
            return None

        title = item.get('name') or item.get('title') or item.get('eventName') or ''
        if not title:
            return None

        start_date = self._parse_date(item.get('startDate') or item.get('start'))
        end_date = self._parse_date(item.get('endDate') or item.get('end'))
        entry_close_at = self._parse_date(item.get('registrationClosesAt') or item.get('deadline'))

        status_raw = (item.get('status') or item.get('statusType') or '').lower().replace(' ', '-')
        status = self.STATUS_MAP.get(status_raw, 'unknown')

        location = item.get('location') or {}
        if isinstance(location, str):
            city = location
            state = ''
        else:
            city = location.get('city') or item.get('city') or ''
            state = location.get('state') or item.get('state') or ''

        surface_raw = (item.get('surface') or '').lower()
        surface = self.SURFACE_MAP.get(surface_raw, surface_raw or 'unknown')

        utr_rating = item.get('ratingMin') or item.get('minUtr')
        price_usd = item.get('registrationFee') or item.get('entryFee')

        categories = self._build_categories(item)

        source_url = f'{self.BASE_URL}/events/{ext_id}'

        notes = f'UTR min: {utr_rating}' if utr_rating else ''

        return {
            'external_id': f'utr:{ext_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'utr-{ext_id}-{title}'),
            'circuit': 'UTR',
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
                'name': item.get('facility') or item.get('venueName') or '',
                'city': city,
                'state': state,
                'address': '',
            } if city or state else None,
            'base_price_brl': None,  # UTR fees are in USD; no reliable BRL conversion
            'official_source_url': source_url,
            'categories': categories,
            'links': [{'link_type': 'registration', 'url': source_url, 'label': 'UTR Sports Event'}],
        }

    def _parse_date(self, val):
        if not val:
            return None
        s = str(val)[:19]
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(s[:len(fmt) - 2], fmt[:len(fmt) - 2])
            except ValueError:
                pass
        try:
            from dateutil.parser import parse
            return parse(str(val)).replace(tzinfo=None)
        except Exception:
            return None

    def _build_categories(self, item: dict) -> list:
        cats = []
        # UTR events have draws/pools by rating level
        for field in ['draws', 'pools', 'flights', 'events', 'categories']:
            field_data = item.get(field)
            if isinstance(field_data, list):
                for cat in field_data:
                    if isinstance(cat, dict):
                        name = cat.get('name') or cat.get('drawName') or cat.get('flightName') or ''
                    else:
                        name = str(cat)
                    if name:
                        cats.append({'source_text': name, 'price_brl': None, 'notes': ''})

        # Fallback: level/category field
        if not cats:
            level = item.get('level') or item.get('eventType') or item.get('category') or ''
            if level:
                cats.append({'source_text': str(level), 'price_brl': None, 'notes': ''})

        # Rating range as category context
        rating_min = item.get('ratingMin') or item.get('minUtr')
        rating_max = item.get('ratingMax') or item.get('maxUtr')
        if rating_min or rating_max:
            rating_text = f'UTR {rating_min or "?"} – {rating_max or "?"}'
            if not any(c['source_text'] == rating_text for c in cats):
                cats.append({'source_text': rating_text, 'price_brl': None, 'notes': 'UTR rating range'})

        return cats
