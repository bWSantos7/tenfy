"""
Fetches public player data from tenisintegrado.com.br using the numeric player ID.

Pages scraped:
  /perfil2/jogos/{ti_id}    → match results / games
  /perfil2/rankings/{ti_id} → federation rankings

All functions raise TenisScrapeError on non-recoverable failures.
The caller is responsible for caching and rate-limiting.
"""
import logging
import re

logger = logging.getLogger('apps.players.parsers')

_HEADERS = {
    'User-Agent': 'TenfyDataSync/1.0 (contato@tennis.app.br; data-research; no-automation)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
    'Connection': 'keep-alive',
}
_TIMEOUT = 15  # seconds
_BASE_URL = 'https://www.tenisintegrado.com.br'


class TenisScrapeError(Exception):
    """Raised when a page cannot be fetched or parsed."""


def _get_session():
    try:
        import requests
        s = requests.Session()
        s.headers.update(_HEADERS)
        return s
    except ImportError:
        raise TenisScrapeError('requests library not available')


def _fetch(url: str) -> str:
    """Fetch a URL and return the HTML text. Raises TenisScrapeError on failure."""
    session = _get_session()
    try:
        resp = session.get(url, timeout=_TIMEOUT)
        if resp.status_code == 404:
            raise TenisScrapeError(f'Profile not found (404): {url}')
        resp.raise_for_status()
        return resp.text
    except TenisScrapeError:
        raise
    except Exception as exc:
        raise TenisScrapeError(f'HTTP error fetching {url}: {exc}') from exc


def _parse_tables(html: str) -> list[dict]:
    """
    Extract all tables from HTML using BeautifulSoup.
    Returns list of {'headers': [...], 'rows': [[...], ...]} dicts.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
    except ImportError:
        # Fallback to html.parser if lxml not available
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
        except ImportError:
            logger.warning('BeautifulSoup not available — falling back to regex parser')
            return _parse_tables_regex(html)

    tables = []
    for table in soup.find_all('table'):
        # Extract headers from <th> in first row or <thead>
        headers = []
        thead = table.find('thead')
        if thead:
            headers = [th.get_text(separator=' ', strip=True) for th in thead.find_all(['th', 'td'])]
        if not headers:
            first_row = table.find('tr')
            if first_row:
                ths = first_row.find_all('th')
                if ths:
                    headers = [th.get_text(separator=' ', strip=True) for th in ths]

        # Extract data rows (skip header rows)
        rows = []
        body = table.find('tbody') or table
        for tr in body.find_all('tr'):
            cells = tr.find_all('td')
            if not cells:
                continue
            row = [td.get_text(separator=' ', strip=True) for td in cells]
            if any(c.strip() for c in row):
                rows.append(row)

        if rows:
            tables.append({'headers': headers, 'rows': rows})

    return tables


def _parse_tables_regex(html: str) -> list[dict]:
    """Minimal regex-based fallback table parser."""
    tables_html = re.findall(r'<table[^>]*>(.*?)</table>', html, re.S | re.I)
    result = []
    for tbl in tables_html:
        headers = re.findall(r'<th[^>]*>(.*?)</th>', tbl, re.S | re.I)
        headers = [re.sub(r'<[^>]+>', '', h).strip() for h in headers]
        row_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.S | re.I)
        rows = []
        for row in row_matches:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S | re.I)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if cells and any(c for c in cells):
                rows.append(cells)
        if rows:
            result.append({'headers': headers, 'rows': rows})
    return result


def _normalise_result_row(headers: list[str], row: list[str]) -> dict:
    """
    Map a raw table row to a normalised result dict.
    Handles varying column orderings gracefully.
    """
    # Build raw mapping from available columns
    raw = {}
    for i, val in enumerate(row):
        key = headers[i].strip() if i < len(headers) else f'col_{i}'
        raw[key] = val.strip()

    # Portuguese column name synonyms → normalised keys
    COL_MAP = {
        # tournament
        'torneio': 'tournament', 'tournament': 'tournament', 'competição': 'tournament',
        # date
        'data': 'date', 'date': 'date', 'período': 'date',
        # category
        'categoria': 'category', 'category': 'category', 'chave': 'category',
        # round/phase
        'fase': 'round', 'round': 'round', 'rodada': 'round', 'etapa': 'round',
        # opponent
        'adversário': 'opponent', 'oponente': 'opponent', 'adversario': 'opponent',
        'jogador': 'opponent',
        # outcome
        'resultado': 'outcome', 'result': 'outcome', 'situação': 'outcome',
        'win': 'outcome', 'vitória': 'outcome',
        # score
        'placar': 'score', 'score': 'score', 'sets': 'score',
        # position
        'posição': 'position', 'classificação': 'position', 'colocação': 'position',
        'place': 'position',
    }

    out: dict = {'_raw': raw}
    used = set()

    for raw_key, val in raw.items():
        norm_key = COL_MAP.get(raw_key.lower().strip())
        if norm_key and norm_key not in out:
            out[norm_key] = val
            used.add(raw_key)

    # Fallback: if specific fields not yet mapped, try positional heuristics for
    # the most common Tênis Integrado layout:
    # [Torneio, Categoria, Fase, Adversário, Resultado/Placar, ...]
    if 'tournament' not in out and row:
        out.setdefault('tournament', row[0])
    if len(row) >= 2 and 'category' not in out:
        out.setdefault('category', row[1])
    if len(row) >= 3 and 'round' not in out:
        out.setdefault('round', row[2])
    if len(row) >= 4 and 'opponent' not in out:
        out.setdefault('opponent', row[3])
    if len(row) >= 5 and 'outcome' not in out:
        out.setdefault('outcome', row[4])
    if len(row) >= 6 and 'score' not in out:
        out.setdefault('score', row[5])

    return out


def _normalise_ranking_row(headers: list[str], row: list[str]) -> dict:
    """Map a raw ranking table row to a normalised ranking dict."""
    raw = {}
    for i, val in enumerate(row):
        key = headers[i].strip() if i < len(headers) else f'col_{i}'
        raw[key] = val.strip()

    COL_MAP = {
        'categoria': 'category', 'category': 'category',
        'modalidade': 'modality', 'modality': 'modality', 'esporte': 'modality',
        'federação': 'federation', 'federacao': 'federation', 'circuito': 'federation',
        'circuit': 'federation', 'entidade': 'federation',
        'posição': 'position', 'pos': 'position', 'colocação': 'position',
        'pontos': 'points', 'points': 'points', 'pts': 'points', 'pontuação': 'points',
        'classe': 'class_label', 'class': 'class_label', 'nível': 'class_label',
        'ranking': 'ranking_name', 'nome': 'ranking_name',
    }

    out: dict = {'_raw': raw}
    for raw_key, val in raw.items():
        norm_key = COL_MAP.get(raw_key.lower().strip())
        if norm_key and norm_key not in out:
            out[norm_key] = val

    # Positional fallbacks for common layout:
    # [Categoria, Federação/Circuito, Posição, Pontos, Classe]
    if 'category' not in out and row:
        out.setdefault('category', row[0])
    if len(row) >= 2 and 'federation' not in out:
        out.setdefault('federation', row[1])
    if len(row) >= 3 and 'position' not in out:
        out.setdefault('position', row[2])
    if len(row) >= 4 and 'points' not in out:
        out.setdefault('points', row[3])
    if len(row) >= 5 and 'class_label' not in out:
        out.setdefault('class_label', row[4])

    return out


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_ti_id(external_ids: dict) -> tuple[str | None, str | None]:
    """
    Given a PlayerProfile.external_ids dict, return (ti_id, source) for the
    first TenisIntegrado-linked entry, or (None, None) if none found.

    TI IDs are stored as:
      - "tenisintegrado:275619"  → numeric id = "275619"
      - "275619"                 → already numeric, treated as TI id
    """
    if not external_ids:
        return None, None

    TI_SOURCES = ('cbt', 'fpt', 'fbt', 'fct')  # sources that use TenisIntegrado

    for source in TI_SOURCES:
        val = external_ids.get(source)
        if not val:
            continue
        s = str(val).strip()
        m = re.match(r'^tenisintegrado:(\d+)$', s) or (re.match(r'^(\d+)$', s) and s)
        if m:
            ti_id = m.group(1) if hasattr(m, 'group') else s
            return ti_id, source

    return None, None


def _get_soup(html: str):
    """Return a BeautifulSoup object, preferring lxml then html.parser."""
    try:
        from bs4 import BeautifulSoup
        try:
            return BeautifulSoup(html, 'lxml')
        except Exception:
            return BeautifulSoup(html, 'html.parser')
    except ImportError:
        raise TenisScrapeError('BeautifulSoup not available')


def _extract_category_from_title(title: str) -> str:
    """Try to extract category code from tournament title (e.g. '14M', '12F')."""
    m = re.search(r'\b(\d{2}[MF](?:D|MD)?)\b', title)
    return m.group(1) if m else ''


def fetch_ti_results(ti_id: str) -> list[dict]:
    """
    Fetch match results from /perfil2/jogos/{ti_id}.

    The page uses <div class="panel last-results"> containing alternating:
      - <div class="innerpanel-header"> — tournament name, location/date, organizer
      - <ul class="list-group tournmt-results"> — list of <li> match rows

    Each <li class="list-group-item"> has:
      - <div class="round"> — phase (R16, Q, S, F …)
      - <a class="avatar-name"> — opponent name
      - <div class="result pull-right"> — "<span>V|D</span> score"

    Returns a list of normalised result dicts.
    Raises TenisScrapeError on failure.
    """
    url = f'{_BASE_URL}/perfil2/jogos/{ti_id}'
    logger.info('Fetching TI results: %s', url)
    html = _fetch(url)
    soup = _get_soup(html)

    last_results = soup.find('div', class_='panel last-results')
    if not last_results:
        logger.info('No last-results panel on TI results page for id=%s', ti_id)
        return []

    results = []
    current_tournament: dict = {}

    for child in last_results.children:
        if not hasattr(child, 'name') or not child.name:
            continue
        cls = child.get('class', [])

        if 'innerpanel-header' in cls:
            # Tournament header — extract name, date, organizer
            title_a = child.find('a')
            parts = [t.strip() for t in child.get_text(separator='|').split('|') if t.strip()]
            title = title_a.get_text(strip=True) if title_a else (parts[0] if parts else '')
            # parts[1] is usually "City - State, date range"
            date_str = parts[1] if len(parts) > 1 else ''
            federation = ''
            for i, p in enumerate(parts):
                if 'Criado' in p and i + 1 < len(parts):
                    federation = parts[i + 1]
                    break
            current_tournament = {
                'tournament': title,
                'date': date_str,
                'category': _extract_category_from_title(title),
                'federation': federation,
            }

        elif 'tournmt-results' in cls:
            # Game list for the current tournament
            for li in child.find_all('li', class_='list-group-item'):
                round_div = li.find(class_='round')
                round_text = round_div.get_text(strip=True) if round_div else ''

                opp_a = li.find('a', class_='avatar-name')
                opponent = opp_a.get_text(strip=True) if opp_a else ''

                result_div = li.find(class_='result')
                outcome, score = '', ''
                if result_div:
                    full = result_div.get_text(separator=' ', strip=True)
                    span = result_div.find('span')
                    if span:
                        outcome = span.get_text(strip=True)
                        score = full.replace(outcome, '').strip()
                    else:
                        outcome = full[:1] if full else ''
                        score = full[1:].strip()

                results.append({
                    'tournament': current_tournament.get('tournament', ''),
                    'date': current_tournament.get('date', ''),
                    'category': current_tournament.get('category', ''),
                    'federation': current_tournament.get('federation', ''),
                    'round': round_text,
                    'opponent': opponent,
                    'outcome': outcome,
                    'score': score,
                })

    logger.info('TI results fetched for id=%s: %d entries', ti_id, len(results))
    return results


def fetch_ti_rankings(ti_id: str) -> list[dict]:
    """
    Fetch rankings from /perfil2/rankings/{ti_id}.

    The page contains two data sources:
    1. <table> elements in the sidebar — WTN (World Tennis Number) for Simples/Duplas.
    2. <div class="ranking"> blocks — historical federation rankings, each with an
       <div class="innerpanel-header"> containing name, date, organizer, and
       position/points in the form "300.00 - 1º Colocado".

    Returns a list of normalised ranking dicts.
    Raises TenisScrapeError on failure.
    """
    url = f'{_BASE_URL}/perfil2/rankings/{ti_id}'
    logger.info('Fetching TI rankings: %s', url)
    html = _fetch(url)
    soup = _get_soup(html)

    rankings: list[dict] = []

    # 1. WTN from sidebar tables — cells like ['', '31,33Simples'] or ['', '31,88 Duplas']
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            if not cells:
                continue
            full = ' '.join(cells).strip()
            m = re.search(r'([\d]+[.,][\d]+)\s*(Simples|Duplas|Misto)', full, re.I)
            if m:
                wtn_value = m.group(1).replace(',', '.')
                modality = m.group(2).capitalize()
                rankings.append({
                    'ranking_name': f'WTN - {modality}',
                    'category': f'WTN {modality}',
                    'modality': modality,
                    'federation': 'World Tennis Number',
                    'points': wtn_value,
                    'position': '',
                    'class_label': '',
                })

    # 2. Historical federation rankings from div.ranking blocks
    for rd in soup.find_all('div', class_='ranking'):
        header = rd.find(class_='innerpanel-header')
        if not header:
            continue

        title_a = header.find('a')
        name = title_a.get_text(strip=True) if title_a else ''
        if not name:
            parts = [t.strip() for t in header.get_text(separator='|').split('|') if t.strip()]
            name = parts[0] if parts else ''
        if not name:
            continue

        parts = [t.strip() for t in header.get_text(separator='|').split('|') if t.strip()]

        # Federation/organizer: part after "Criado por"
        organizer = ''
        for i, p in enumerate(parts):
            if 'Criado' in p and i + 1 < len(parts):
                organizer = parts[i + 1]
                break

        # Position & points: "300.00 - 1º Colocado" pattern
        position, points = '', ''
        for p in parts:
            m = re.search(r'([\d.,]+)\s*-\s*(\d+)\s*[ºo°]?\s*Colocado', p, re.I)
            if m:
                points = m.group(1).replace(',', '.')
                position = m.group(2)
                break

        # Date
        date_str = ''
        for p in parts:
            if re.search(r'\d{2}/\d{2}/\d{4}', p):
                date_str = re.search(r'\d{2}/\d{2}/\d{4}', p).group(0)
                break

        rankings.append({
            'ranking_name': name,
            'category': name,
            'federation': organizer,
            'position': position,
            'points': points,
            'modality': '',
            'class_label': '',
            'date': date_str,
        })

    logger.info('TI rankings fetched for id=%s: %d entries', ti_id, len(rankings))
    return rankings
