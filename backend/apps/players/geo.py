"""
Validação de cidade x UF usando a lista de municípios do IBGE (Card 8 tasks2).

Estratégia segura:
  - lista por UF é cacheada (7 dias) — uma chamada por UF por período;
  - degradação graciosa: se o IBGE estiver indisponível, NÃO bloqueia o save
    (retorna None = "não foi possível verificar"), evitando travar o usuário por
    uma falha externa.
"""
import logging
import unicodedata

from django.core.cache import cache

logger = logging.getLogger('apps.players.geo')

_CACHE_TTL = 60 * 60 * 24 * 7  # 7 dias
_IBGE_URL = 'https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios'


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', (s or '').strip().lower()).encode('ascii', 'ignore').decode()


def cities_for_uf(uf: str):
    """Conjunto de nomes de municípios (normalizados) da UF, ou None se indisponível."""
    uf = (uf or '').upper().strip()
    if len(uf) != 2:
        return None
    key = f'ibge:cities:{uf}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        import requests
        resp = requests.get(_IBGE_URL.format(uf=uf), timeout=5)
        resp.raise_for_status()
        names = {_norm(m['nome']) for m in resp.json() if m.get('nome')}
        if names:
            cache.set(key, names, _CACHE_TTL)
        return names or None
    except Exception as exc:  # noqa: BLE001 — falha externa não deve travar o save
        logger.warning('IBGE city list fetch failed for UF=%s: %s', uf, exc)
        return None


def city_belongs_to_uf(city: str, uf: str):
    """True se a cidade pertence à UF; False se claramente não pertence;
    None quando não foi possível verificar (IBGE indisponível)."""
    names = cities_for_uf(uf)
    if not names:
        return None
    return _norm(city) in names
