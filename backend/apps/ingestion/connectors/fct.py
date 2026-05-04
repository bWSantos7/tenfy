"""
FCT connector backed by Tenis Integrado federation profile + official detail page.
"""
from datetime import date, datetime
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseConnector, register_connector


@register_connector
class FCTPublicConnector(BaseConnector):
    key = 'fct_public'

    BASE_URL = 'https://www.tenisintegrado.com.br'
    PROFILE_PATH = '/perfil2/torneios/{site_id}/{month}/{year}/{entity_type}/{state_id}/'
    MONTH_MAP = {
        'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
        'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12,
    }
    STATUS_MAP = {
        'inscricoes abertas': 'open',
        'inscricoes encerradas': 'closed',
        'confirmado': 'open',
        'planejado': 'announced',
        'finalizado': 'finished',
        'iniciado': 'in_progress',
        'cancelado': 'canceled',
    }
    SURFACE_MAP = {
        'saibro': 'clay',
        'rapida': 'hard',
        'duro': 'hard',
        'grama': 'grass',
        'areia': 'sand',
        'carpete': 'carpet',
    }

    def extract(self):
        today = date.today()
        site_id = int(self.config.get('site_id', 4183))
        entity_type = int(self.config.get('entity_type', 2))
        state_id = int(self.config.get('state_id', 24))
        months_ahead = int(self.config.get('months_ahead', 5))

        seen = set()
        for offset in range(0, months_ahead + 1):
            year, month = self._shift_month(today.year, today.month, offset)
            url = urljoin(
                self.BASE_URL,
                self.PROFILE_PATH.format(
                    site_id=site_id,
                    month=month,
                    year=year,
                    entity_type=entity_type,
                    state_id=state_id,
                ),
            )
            response = self.fetch(url)
            if response.status_code >= 400:
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            for item in soup.select('li.list-group-item.list-group-item-link'):
                parsed = self._parse_item(item, year)
                if not parsed or parsed['external_id'] in seen:
                    continue
                seen.add(parsed['external_id'])
                yield parsed

    def _parse_item(self, item, fallback_year: int):
        anchor = item.find('a', href=True)
        title_el = item.find('h5')
        info_el = item.select_one('.info')
        status_el = item.select_one('.label.status')
        if not anchor or not title_el or not info_el:
            return None

        title = ' '.join(title_el.get_text(' ', strip=True).split())
        info_text = ' '.join(info_el.get_text(' ', strip=True).split())
        status_text = status_el.get_text(' ', strip=True) if status_el else ''
        external_match = re.search(r'/(\d+)$', anchor.get('href') or '')
        if not title or not info_text or not external_match:
            return None

        external_id = external_match.group(1)
        full_url = urljoin(self.BASE_URL, anchor['href'])
        detail = self._fetch_detail(full_url)

        city, state, start_date, end_date = self._parse_info(info_text, fallback_year)
        entry_close = self._parse_detail_deadline(detail.get('deadline'))
        modality = 'beach_tennis' if 'BEACH' in title.upper() else 'tennis'
        circuit = self._infer_circuit(title)
        status = self._infer_status(detail.get('status_text') or status_text, start_date, end_date, entry_close)

        return {
            'external_id': f'fct:{external_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'fct-{external_id}-{title}'),
            'circuit': circuit,
            'modality': modality,
            'season_year': start_date.year if start_date else fallback_year,
            'title': title,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'entry_open_at': None,
            'entry_close_at': entry_close.isoformat() if entry_close else None,
            'status': status,
            'surface': self._normalize_surface(detail.get('surface')),
            'venue': {
                'name': detail.get('venue_name') or 'FCT',
                'city': detail.get('city') or city,
                'state': detail.get('state') or state,
                'address': detail.get('address', ''),
            },
            'base_price_brl': self._extract_base_price(detail.get('price_text')),
            'official_source_url': full_url,
            'categories': self._extract_categories(detail.get('categories', [])),
            'links': [
                {
                    'link_type': 'registration',
                    'url': full_url,
                    'label': 'Pagina oficial FCT',
                },
            ],
        }

    def _fetch_detail(self, url: str):
        response = self.fetch(url)
        if response.status_code >= 400:
            return {}
        soup = BeautifulSoup(response.text, 'html.parser')
        text = ' '.join(soup.get_text(' ', strip=True).split())

        categories = []
        for row in soup.select('table tr')[1:]:
            cols = [' '.join(td.get_text(' ', strip=True).split()) for td in row.select('td')]
            if cols and cols[0]:
                categories.append(cols[0])

        venue_name = ''
        address = ''
        city = ''
        state = ''
        surface = ''
        for node in soup.select('.list-group-item'):
            item_text = ' '.join(node.get_text(' ', strip=True).split())
            low = item_text.lower()
            if low.startswith('clube '):
                venue_name = item_text.replace('Clube ', '', 1)
            elif low.startswith('endereco '):
                address = item_text.replace('Endereco ', '', 1)
            elif low.startswith('piso de '):
                surface = item_text.replace('Piso de ', '', 1)
            else:
                surface = ''
        city_state_match = re.search(r'([A-Za-zÀ-ÿ ]+)-([A-Z]{2})', text)
        if city_state_match:
            city = city_state_match.group(1).strip()
            state = city_state_match.group(2).strip()

        return {
            'status_text': self._find_text(text, [r'\b(Finalizado|Iniciado|Confirmado|Planejado|Cancelado)\b']),
            'deadline': self._find_text(text, [r'Inscric(?:oes|ões) abertas at[eé] \d{2}/\d{2}/\d{4}']),
            'price_text': self._find_text(text, [r'R\$ [\d\.,]+']),
            'surface': surface,
            'venue_name': venue_name,
            'address': address,
            'city': city,
            'state': state,
            'categories': categories,
        }

    def _parse_info(self, info_text: str, fallback_year: int):
        parts = [part.strip() for part in info_text.split('/')]
        location = parts[0] if parts else ''
        range_text = parts[1] if len(parts) > 1 else ''

        state_match = re.search(r'(.+?)\s*-\s*([A-Z]{2})$', location)
        city = state_match.group(1).strip() if state_match else location.strip()
        state = state_match.group(2).strip() if state_match else ''

        date_match = re.search(
            r'(\d{1,2})\s+([A-Za-z]{3})\s*-\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})',
            range_text,
            re.IGNORECASE,
        )
        if not date_match:
            return city, state, None, None

        start_day, start_month, end_day, end_month, year = date_match.groups()
        year = int(year or fallback_year)
        start_date = date(year, self.MONTH_MAP.get(start_month.upper(), 1), int(start_day))
        end_date = date(year, self.MONTH_MAP.get(end_month.upper(), 1), int(end_day))
        return city, state, start_date, end_date

    def _parse_detail_deadline(self, text: str | None):
        if not text:
            return None
        match = re.search(r'(\d{2})/(\d{2})/(\d{4})', text)
        if not match:
            return None
        day, month, year = [int(part) for part in match.groups()]
        return datetime(year, month, day, 23, 59)

    def _infer_circuit(self, title: str) -> str:
        upper = title.upper()
        if 'KIDS' in upper:
            return 'Kids'
        if 'INFANTO' in upper or 'JUVENIL' in upper:
            return 'Infantojuvenil'
        if 'INTERCLUBES' in upper:
            return 'Interclubes'
        if 'BEACH' in upper:
            return 'Beach Tennis'
        if 'REGIONAL' in upper:
            return 'Regional FCT'
        return 'FCT'

    def _infer_status(self, text: str, start_date, end_date, entry_close):
        lowered = (text or '').lower()
        for source, normalized in self.STATUS_MAP.items():
            if source in lowered:
                return normalized

        today = date.today()
        now = datetime.now()
        if end_date and today > end_date:
            return 'finished'
        if start_date and today >= start_date:
            return 'in_progress'
        if entry_close and now <= entry_close:
            return 'open'
        if entry_close and now > entry_close:
            return 'closed'
        return 'announced'

    def _normalize_surface(self, text: str | None):
        if not text:
            return 'unknown'
        lowered = text.lower().strip()
        for key, value in self.SURFACE_MAP.items():
            if key in lowered:
                return value
        return 'unknown'

    def _extract_base_price(self, text: str | None):
        return self.parse_price_brl(text)

    def _extract_categories(self, categories: list[str]):
        return [
            {
                'source_text': category[:200],
                'price_brl': None,
                'notes': '',
                'order': order,
            }
            for order, category in enumerate(categories)
            if category
        ]

    @staticmethod
    def _shift_month(year: int, month: int, offset: int):
        raw = (year * 12 + (month - 1)) + offset
        return raw // 12, (raw % 12) + 1

    @staticmethod
    def _find_text(text: str, patterns: list[str]):
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return ''
