"""
Parser for Tênis Integrado public ranking *listing* pages.

This complements parsers.py (which scrapes a single athlete's profile by id).
Here we read the public ranking tables that enumerate many athletes at once, so
we can build a local catalogue of athletes (name + TI profile id + federation +
category + position + points) and use it to auto-link Tenfy profiles.

Reverse-engineered public flow (no authentication required):

  GET  /ranking_painel_classif/index/{ranking_id}
        → renders the filter UI: <select id="id_categoria">, <select id="id_corte">
          (cut-off dates) and <select id="id_uf">.

  POST /ranking_painel_classif/index   data={busca,id_corte,id_categoria,id_uf}
        → server-rendered athlete table. Each row's first cell carries:
            "{position}º - {name} ID. {ti_id}, UF: {uf}, Idade: {age} {club}"
          and links to /perfil2/index/{ti_id} — the same numeric id used by the
          per-profile parser, which is what makes auto-linking possible.

Notes / source limitations:
  * A GET on the ranking index must precede the POST (it seats a session cookie);
    otherwise the POST returns the empty filter shell.
  * Federation-scoped rankings on TI are localised by the logged-in user. The set
    of ranking_ids per source is therefore configured explicitly in
    ti_ranking_sources.py rather than crawled blindly.

All functions raise TenisScrapeError on non-recoverable failures. Callers are
responsible for persistence and overall rate-limiting between rankings; this
module only throttles its own consecutive requests.
"""
from __future__ import annotations

import logging
import re
import time

from .parsers import TenisScrapeError, _get_soup

logger = logging.getLogger('apps.players.ti_rankings')

_BASE_URL = 'https://www.tenisintegrado.com.br'
INDEX_URL = f'{_BASE_URL}/ranking_painel_classif/index'
# Federation ranking listing: GET seats the cookie, POST returns the table.
FED_INDEX_URL = f'{_BASE_URL}/new_ranking/index_ranking'
FED_LIST_URL = f'{_BASE_URL}/new_ranking/index3'

# A realistic browser UA — the ranking endpoint returns the empty shell for the
# generic data-sync UA used by parsers.py.
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
}
_TIMEOUT = 25  # seconds
# Politeness delay between consecutive HTTP requests to the same host.
REQUEST_DELAY_SECONDS = 2.0


def _session():
    try:
        import requests
    except ImportError:
        raise TenisScrapeError('requests library not available')
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


# ── athlete-row parsing ─────────────────────────────────────────────────────────

# "1º - Anna Faminova  ID. 243039, UF: RS, Idade: 14"
_NAME_ID_RE = re.compile(
    r'(?:(?P<pos>\d+)\s*[º°ºo]?\s*-\s*)?'
    r'(?P<name>.+?)\s+ID\.\s*(?P<tid>\d+)'
    r'(?:\s*,\s*UF:\s*(?P<uf>[A-Za-zÀ-ÿ]{0,3}))?'
    r'(?:\s*,\s*Idade:\s*(?P<age>\d+))?',
    re.I,
)
_PERFIL_RE = re.compile(r'perfil2/index/(\d+)')


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _header_index(headers: list[str]) -> dict[str, int]:
    """Map normalised header label → column index."""
    out: dict[str, int] = {}
    for i, h in enumerate(headers):
        key = _clean(h).lower()
        out[key] = i
    return out


def _cell_for(cells: list, hidx: dict[str, int], *labels: str) -> str:
    for label in labels:
        for key, i in hidx.items():
            if label in key and i < len(cells):
                return _clean(cells[i].get_text(' ', strip=True))
    return ''


def parse_ranking_entries(html: str) -> list[dict]:
    """
    Parse the athlete table from a ranking_painel_classif POST response.

    Returns a list of dicts:
      {position, player_name, ti_player_id, uf, age, club, wtn, points,
       points_combined, total, valid_tournaments}
    Rows without a resolvable TI profile id are skipped.
    """
    soup = _get_soup(html)
    table = soup.find('table')
    if not table:
        return []

    rows = table.find_all('tr')
    if not rows:
        return []

    header_cells = rows[0].find_all(['th', 'td'])
    headers = [c.get_text(' ', strip=True) for c in header_cells]
    hidx = _header_index(headers)

    entries: list[dict] = []
    for tr in rows[1:]:
        cells = tr.find_all('td')
        if not cells:
            continue

        link = tr.find('a', href=_PERFIL_RE)
        if not link:
            continue
        m_id = _PERFIL_RE.search(link.get('href', ''))
        if not m_id:
            continue
        ti_player_id = m_id.group(1)

        # First cell holds name/id/uf/age; the club sits in an extra div.
        first_cell = cells[0]
        name_info = first_cell.find(class_='name-info')
        # Combine the link text (name-info + the ID/UF/Idade sibling).
        text_block = _clean(link.get_text(' ', strip=True)) or _clean(first_cell.get_text(' ', strip=True))

        position = None
        player_name = ''
        uf = ''
        age = None
        m = _NAME_ID_RE.search(text_block)
        if m:
            position = int(m.group('pos')) if m.group('pos') else None
            player_name = _clean(m.group('name'))
            uf = _clean(m.group('uf') or '').upper()[:2]
            age = int(m.group('age')) if m.group('age') else None
        else:
            # Fallback: name from name-info div, strip leading "N -"
            raw = _clean(name_info.get_text(' ', strip=True)) if name_info else text_block
            raw = re.sub(r'^\s*\d+\s*[º°ºo]?\s*-\s*', '', raw)
            player_name = raw

        if not player_name:
            continue

        # Club: text-success div inside the info container (avoid the WTN/movement cells).
        club = ''
        info_container = first_cell.find(class_='info-container') or first_cell
        club_div = info_container.find(class_='text-success')
        if club_div:
            club = _clean(club_div.get_text(' ', strip=True))

        entries.append({
            'position': position,
            'player_name': player_name,
            'ti_player_id': ti_player_id,
            'uf': uf,
            'age': age,
            'club': club,
            'wtn': _cell_for(cells, hidx, 'wtn'),
            'points': _cell_for(cells, hidx, 'pontos') or _cell_for(cells, hidx, 'total'),
            'points_combined': _cell_for(cells, hidx, 'combinad'),
            'total': _cell_for(cells, hidx, 'total'),
            'valid_tournaments': _cell_for(cells, hidx, 'torneios'),
        })

    logger.info('Parsed %d ranking entries', len(entries))
    return entries


# ── filter discovery ─────────────────────────────────────────────────────────

def _parse_select(soup, select_id: str) -> list[tuple[str, str]]:
    sel = soup.find('select', id=select_id)
    if not sel:
        return []
    opts = []
    for o in sel.find_all('option'):
        val = (o.get('value') or '').strip()
        label = _clean(o.get_text(' ', strip=True))
        opts.append((val, label))
    return opts


def fetch_ranking_index(ranking_id: str | int, session=None) -> dict:
    """
    GET the ranking index page and return its available filters.

    Returns {categories, cortes, ufs} where each is a list of (value, label).
    Also seats the session cookie required by fetch_ranking_entries.
    """
    sess = session or _session()
    url = f'{INDEX_URL}/{ranking_id}'
    logger.info('Fetching TI ranking index: %s', url)
    try:
        resp = sess.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception as exc:
        raise TenisScrapeError(f'HTTP error fetching {url}: {exc}') from exc

    soup = _get_soup(resp.text)
    return {
        'categories': [(v, l) for v, l in _parse_select(soup, 'id_categoria') if v],
        'cortes': [(v, l) for v, l in _parse_select(soup, 'id_corte') if v],
        'ufs': _parse_select(soup, 'id_uf'),
    }


# ── federation ranking discovery & category filtering ───────────────────────────

# Ranking names that qualify as youth/junior rankings.
_YOUTH_RANKING_RE = re.compile(r'infanto\s*[- ]?\s*juvenil|juvenil|junior', re.I)
# A standalone age token in the 12–18 range (matches "12 anos", "Sub-14", "16M"…
# but not "112" or "10 anos").
_AGE_12_18_RE = re.compile(r'(?<!\d)(1[2-8])(?!\d)')


def is_youth_ranking_name(name: str) -> bool:
    """True when a ranking title denotes an infantojuvenil/juvenil/junior ranking."""
    return bool(_YOUTH_RANKING_RE.search(name or ''))


def is_age_12_18_category(label: str) -> bool:
    """True when a category label refers to a single age in the 12–18 range."""
    m = _AGE_12_18_RE.search(label or '')
    return bool(m)


def discover_federation_rankings(year, session=None, federacao: str = '0') -> list[dict]:
    """
    List federation rankings for a season via the public federations panel.

    POSTs the federations filter (id_federacao='0' = all, ano=year) and parses
    each row into {ranking_external_id, ranking_name, federation}. De-duplicated
    by ranking id.
    """
    sess = session or _session()
    try:
        sess.get(FED_INDEX_URL, timeout=_TIMEOUT)
    except Exception:  # cookie seating is best-effort
        pass

    try:
        resp = sess.post(
            FED_LIST_URL,
            data={'id_federacao': str(federacao), 'ano': str(year)},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception as exc:
        raise TenisScrapeError(f'HTTP error listing federation rankings: {exc}') from exc

    soup = _get_soup(resp.text)
    rid_re = re.compile(r'ranking_painel_classif/index/(\d+)')
    out: dict[str, dict] = {}
    for a in soup.find_all('a', class_='link-tournament'):
        href = a.get('href', '')
        m = rid_re.search(href)
        if not m:
            continue
        rid = m.group(1)
        if rid in out:
            continue
        name_div = a.find(class_='name-info')
        name = _clean(name_div.get_text(' ', strip=True)) if name_div else _clean(a.get_text(' ', strip=True))
        # "Criado por <a>FED</a>" sits in the sibling info container.
        federation = ''
        info = a.find_parent(class_='info-container')
        if info:
            for div in info.find_all('div'):
                if 'Criado por' in div.get_text():
                    fed_a = div.find('a')
                    federation = _clean(fed_a.get_text()) if fed_a else _clean(div.get_text().replace('Criado por', ''))
                    break
        out[rid] = {
            'ranking_external_id': rid,
            'ranking_name': name,
            'federation': federation,
        }
    logger.info('Discovered %d federation rankings for %s', len(out), year)
    return list(out.values())


def fetch_ranking_entries(
    ranking_id: str | int,
    id_categoria: str,
    id_corte: str = '',
    id_uf: str = '',
    session=None,
) -> list[dict]:
    """
    POST the ranking filter and return the parsed athlete rows for one category.

    A prior fetch_ranking_index() call on the same session is required to seat
    the session cookie. When no session is supplied we run the GET first.
    """
    sess = session
    if sess is None:
        sess = _session()
        fetch_ranking_index(ranking_id, session=sess)
        time.sleep(REQUEST_DELAY_SECONDS)

    data = {
        'busca': '',
        'id_corte': id_corte or '',
        'id_categoria': str(id_categoria),
        'id_uf': id_uf or '',
    }
    logger.info('POST TI ranking %s categoria=%s corte=%s uf=%s',
                ranking_id, id_categoria, id_corte or '-', id_uf or '-')
    try:
        resp = sess.post(INDEX_URL, data=data, timeout=_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception as exc:
        raise TenisScrapeError(f'HTTP error posting ranking {ranking_id}: {exc}') from exc

    return parse_ranking_entries(resp.text)
