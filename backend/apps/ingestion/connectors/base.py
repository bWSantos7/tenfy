"""
Connector framework.

Each connector extracts a normalized list of tournament dicts from one source.
Output schema (list[dict]):

{
    'external_id': str,
    'canonical_name': str,
    'canonical_slug': str,
    'circuit': str,
    'modality': str,
    'season_year': int,
    'title': str,
    'start_date': 'YYYY-MM-DD' | None,
    'end_date': 'YYYY-MM-DD' | None,
    'entry_open_at': 'YYYY-MM-DDTHH:MM:SSZ' | None,
    'entry_close_at': '...' | None,
    'status': str,  # matching TournamentEdition.STATUS_* when known
    'surface': str,
    'venue': { 'name', 'city', 'state', 'address' } | None,
    'base_price_brl': float | None,
    'official_source_url': str,
    'categories': [
        { 'source_text': str, 'price_brl': float | None, 'notes': str }, ...
    ],
    'links': [
        { 'link_type': str, 'url': str, 'label': str }, ...
    ],
}
"""
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Optional

import requests
from django.conf import settings

logger = logging.getLogger('apps.ingestion')


class ConnectorError(Exception):
    """Raised on unrecoverable connector errors."""


class BaseConnector(ABC):
    """Base class for all source connectors."""
    key: str = ''

    def __init__(self, data_source=None, config: Optional[dict] = None):
        self.data_source = data_source
        self.config = config or (data_source.config_json if data_source else {})
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': getattr(settings, 'SCRAPER_USER_AGENT', 'TennisHubBot/1.0'),
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
        })
        self._rate_limit = getattr(settings, 'SCRAPER_RATE_LIMIT_SECONDS', 2)
        self._timeout = getattr(settings, 'SCRAPER_TIMEOUT', 30)

    def fetch(self, url: str, **kwargs) -> requests.Response:
        """HTTP GET with sensible defaults and polite rate limiting."""
        time.sleep(self._rate_limit)
        try:
            response = self.session.get(url, timeout=self._timeout, **kwargs)
            logger.info('fetch url=%s status=%s', url, response.status_code)
            return response
        except requests.RequestException as exc:
            logger.warning('fetch failed url=%s exc=%s', url, exc)
            raise ConnectorError(f'Request failed: {exc}')

    @abstractmethod
    def extract(self) -> Iterable[dict]:
        """Yield normalized tournament dicts."""
        raise NotImplementedError

    @staticmethod
    def parse_date_br(s: Optional[str]):
        """Parse DD/MM/YYYY or YYYY-MM-DD."""
        if not s:
            return None
        s = s.strip()
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        m = re.match(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', s)
        if m:
            d, mo, y = m.groups()
            y = int(y)
            if y < 100:
                y += 2000
            try:
                return datetime(int(y), int(mo), int(d)).date()
            except ValueError:
                return None
        return None

    @staticmethod
    def parse_price_brl(text: Optional[str]):
        if not text:
            return None
        m = re.search(r'R?\$?\s*([\d\.]+,\d{2}|\d+)', text)
        if not m:
            return None
        raw = m.group(1).replace('.', '').replace(',', '.')
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def slugify(text: str) -> str:
        import unicodedata
        s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
        return s[:250]


_REGISTRY: dict = {}


def register_connector(cls):
    """Class decorator registering connector by its `key`."""
    if not cls.key:
        raise ValueError(f'{cls.__name__} must define `key`')
    _REGISTRY[cls.key] = cls
    return cls


def get_connector(key: str):
    return _REGISTRY.get(key)


def registered_connectors():
    return dict(_REGISTRY)
