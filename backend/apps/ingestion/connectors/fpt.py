"""
FPT connector using the public tournament calendar and official detail page.
"""
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseConnector, register_connector


@register_connector
class FPTPublicConnector(BaseConnector):
    key = 'fpt_public'

    CALENDAR_URL = 'https://fpt.com.br/Torneio/Calendario/{year}'
    STATUS_MAP = {
        'inscricoes abertas': 'open',
        'inscricoes encerradas': 'closed',
        'finalizado': 'finished',
        'iniciado': 'in_progress',
        'confirmado': 'open',
        'planejado': 'announced',
    }
    SURFACE_MAP = {
        'saibro': 'clay',
        'rapida': 'hard',
        'rapida / sintetica': 'hard',
        'sintetica': 'hard',
        'grama': 'grass',
        'areia': 'sand',
        'carpete': 'carpet',
    }

    def extract(self):
        years = self.config.get('years') or [date.today().year]
        seen = set()
        for year in years:
            response = self.fetch(self.CALENDAR_URL.format(year=year))
            if response.status_code >= 400:
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            for card in soup.select('div.box_options_01'):
                parsed = self._parse_card(card, int(year))
                if not parsed:
                    continue
                if parsed['external_id'] in seen:
                    continue
                seen.add(parsed['external_id'])
                yield parsed

    def _parse_card(self, card, year: int):
        title_links = card.select('div.font_14 a[href*="/Torneio/Info/"]')
        if not title_links:
            return None

        badge = title_links[0].get_text(' ', strip=True)
        title = title_links[-1].get_text(' ', strip=True)
        info_href = title_links[-1].get('href') or title_links[0].get('href') or ''
        full_info_url = urljoin('https://fpt.com.br', info_href)
        external_match = re.search(r'-(\d+)$', info_href)
        if not external_match:
            return None
        external_id = external_match.group(1)

        detail = self._fetch_detail(full_info_url)

        period_text = self._card_text(card, '.aba_01 .font_12')
        subtitle_text = self._card_text(card, '.font_12.color_disable em')
        location_text = self._card_text(card, '.mt10.font_12')
        deadline_text = self._card_text(card, '.left.width50 .color4')

        start_date, end_date = self._parse_period(period_text, year)
        if detail.get('period'):
            parsed_start, parsed_end = self._parse_detail_period(detail['period'])
            start_date = parsed_start or start_date
            end_date = parsed_end or end_date

        entry_close = self._parse_deadline(deadline_text, year)
        if detail.get('deadline'):
            entry_close = self._parse_detail_deadline(detail['deadline']) or entry_close

        venue_name, city, state = self._parse_location(location_text)
        venue_name = detail.get('venue_name') or venue_name
        city = detail.get('city') or city
        state = detail.get('state') or state

        modality = 'beach_tennis' if 'BEACH' in badge.upper() or 'BEACH' in title.upper() else 'tennis'
        circuit = self._infer_circuit(badge, subtitle_text)
        status = self._infer_status(detail.get('status_text') or deadline_text, start_date, end_date, entry_close)
        registration_link = self._extract_registration_link(card)
        base_price = self._extract_base_price(detail.get('price_text'))
        surface = self._normalize_surface(detail.get('surface'))

        return {
            'external_id': f'fpt:{external_id}',
            'canonical_name': title,
            'canonical_slug': self.slugify(f'fpt-{external_id}-{title}'),
            'circuit': circuit,
            'modality': modality,
            'season_year': year,
            'title': title,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'entry_open_at': None,
            'entry_close_at': entry_close.isoformat() if entry_close else None,
            'status': status,
            'surface': surface,
            'venue': {
                'name': venue_name,
                'city': city,
                'state': state,
                'address': detail.get('address', ''),
            } if venue_name or city or state else None,
            'base_price_brl': base_price,
            'official_source_url': full_info_url,
            'categories': [],
            'links': self._build_links(full_info_url, registration_link),
        }

    def _fetch_detail(self, url: str):
        response = self.fetch(url)
        if response.status_code >= 400:
            return {}
        soup = BeautifulSoup(response.text, 'html.parser')
        text = ' '.join(soup.get_text(' ', strip=True).split())

        return {
            'status_text': self._find_text(text, [r'\b(Finalizado|Iniciado|Confirmado|Planejado)\b']),
            'period': self._find_text(text, [r'(\d{2}-\d{2}\s+[^\s]+\s+\d{4}|\d{2}-\d{2}\s+[^\s]+\s+\d{2}-\d{2})']),
            'deadline': self._find_text(text, [r'Inscreva-se at[eé] \d{2}-\d{2}', r'Inscric(?:oes|ões) abertas at[eé] \d{2}/\d{2}/\d{4}']),
            'price_text': self._find_text(text, [r'Federados R\$ [\d\.,]+ N[aã]o Federados R\$ [\d\.,]+', r'R\$ [\d\.,]+']),
            'surface': self._find_text(text, [r'Piso:\s*[A-Za-zÀ-ÿ /]+']),
            'venue_name': self._find_text(text, [r'[A-Z0-9Á-ÚÃÕÇ \-]+ - [A-Z][a-zçãõáéíóú]+$']),
            'city': self._find_text(text, [r'([A-Za-zÀ-ÿ ]+) - PR']),
            'state': 'PR',
            'address': self._find_text(text, [r'AV\.[^\.]+PR', r'RUA [^\.]+PR']),
        }

    def _build_links(self, info_url: str, registration_link: str | None):
        links = [{'link_type': 'other', 'url': info_url, 'label': 'Pagina oficial FPT'}]
        if registration_link:
            links.insert(0, {
                'link_type': 'registration',
                'url': registration_link,
                'label': 'Inscricao oficial FPT',
            })
        return links

    def _extract_registration_link(self, card):
        anchor = card.select_one('a[href*="/Inscricao/"]')
        if not anchor:
            return None
        return urljoin('https://fpt.com.br', anchor.get('href') or '')

    def _parse_period(self, text: str, year: int):
        match = re.search(r'(\d{2})-(\d{2})\s+[A-Za-zÀ-ÿ]+\s+(\d{2})-(\d{2})', text)
        if not match:
            return None, None
        start_day, start_month, end_day, end_month = [int(part) for part in match.groups()]
        return date(year, start_month, start_day), date(year, end_month, end_day)

    def _parse_detail_period(self, text: str):
        if not text:
            return None, None
        match = re.search(r'(\d{2})-(\d{2}).*?(\d{2})-(\d{2})', text)
        if not match:
            return None, None
        start_day, start_month, end_day, end_month = [int(part) for part in match.groups()]
        year = date.today().year
        return date(year, start_month, start_day), date(year, end_month, end_day)

    def _parse_deadline(self, text: str, year: int):
        match = re.search(r'(\d{2})-(\d{2})$', text)
        if not match:
            return None
        day, month = [int(part) for part in match.groups()]
        return datetime(year, month, day, 23, 59)

    def _parse_detail_deadline(self, text: str):
        match = re.search(r'(\d{2})/(\d{2})/(\d{4})', text)
        if match:
            day, month, year = [int(part) for part in match.groups()]
            return datetime(year, month, day, 23, 59)
        return None

    def _parse_location(self, text: str):
        cleaned = text.replace('Pesquisar endereço', '').strip()
        parts = [part.strip() for part in cleaned.split(' - ') if part.strip()]
        if len(parts) >= 2:
            return parts[0][:200], parts[-1][:120], 'PR'
        return cleaned[:200], '', 'PR'

    def _infer_circuit(self, badge: str, subtitle: str):
        upper_badge = badge.upper()
        upper_subtitle = subtitle.upper()
        if 'BEACH' in upper_badge or 'BEACH' in upper_subtitle:
            return 'Beach Tennis'
        if 'INFANTO' in upper_subtitle or 'JUNIOR' in upper_badge:
            return 'Infantojuvenil'
        if 'CLASS' in upper_badge or 'CLASSES' in upper_badge:
            return 'Classes'
        if 'INTERCLUBES' in upper_badge:
            return 'Interclubes'
        return badge[:100] or 'FPT'

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

    def _extract_base_price(self, text: str | None):
        if not text:
            return None
        prices = re.findall(r'R\$\s*([\d\.,]+)', text)
        if not prices:
            return None
        parsed = [self.parse_price_brl(f'R$ {price}') for price in prices]
        parsed = [price for price in parsed if price is not None]
        return min(parsed) if parsed else None

    def _normalize_surface(self, text: str | None):
        if not text:
            return 'unknown'
        lowered = text.lower().replace('piso:', '').strip()
        return self.SURFACE_MAP.get(lowered, self.SURFACE_MAP.get(lowered.split(' quadras')[0].strip(), 'unknown'))

    @staticmethod
    def _card_text(card, selector: str):
        node = card.select_one(selector)
        return ' '.join(node.get_text(' ', strip=True).split()) if node else ''

    @staticmethod
    def _find_text(text: str, patterns: list[str]):
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return ''
