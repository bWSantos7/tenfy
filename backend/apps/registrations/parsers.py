"""
Federation entry parsers — extract athlete entries from HTML/text.

Each parser returns:
  {
    'entries': [...],          # list of dicts matching bulk-import schema
    'parser_warning': bool,    # True when source is unreliable or blocked
    'warning_message': str,    # human-readable explanation
    'confidence': str,         # 'high'|'medium'|'low'
    'source': str,             # 'cosat'|'cbt'|'fpt'|'manual'
  }

Parsers NEVER invent data. If extraction fails, return empty entries + warning.
"""
import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger('apps.registrations.parsers')

# ── Shared helpers ─────────────────────────────────────────────────────────────

# Words that confirm payment when NO negation precedes them
_PAID_STEMS = {'pag', 'paid', 'confirm', 'efetuad', 'aprovad', 'quitad', 'sim', 'yes', 'pg', 'ok'}
PAYMENT_WORDS_PAID = {
    'pago', 'paid', 'confirmado', 'confirmed', 'sim', 'yes', 'pg',
    'quitado', 'efetuado', 'aprovado', 'ok', 'paga',
}
PAYMENT_WORDS_PENDING = {
    'pendente', 'pending', 'aguardando', 'awaiting',
    'a pagar', 'em aberto', 'aberto', 'devido',
    'não pago', 'nao pago', 'não confirmado', 'nao confirmado',
    'pagamento não', 'pagamento nao',
}

# Negation prefixes — if any of these immediately precede a paid stem, result is pending
_NEGATION_RE = re.compile(
    r'\b(não|nao|not|no|sem|without)\s+\w*(pag|confirm|efetuad|aprovad|quitad|paid)\w*',
    re.IGNORECASE,
)

REMOVED_WORDS = {
    'substituído', 'substituida', 'substituido', 'removed', 'removido',
    'cortado', 'excluído', 'excluido', 'eliminado', 'out',
    'retirado', 'desistiu', 'desistência', 'cancelado',
    'waitlist', 'alternates', 'alternate', 'lista de espera',
    'withdrawn', 'withdraw',
}


def _classify_payment(text: str) -> str:
    """
    Classify payment status from raw text.
    Priority order:
      1. Negation pattern ("não pago", "nao pago", "not confirmed") → pending
      2. Explicit pending keywords → pending
      3. Explicit paid keywords (whole-word boundary) → paid
      4. Unknown
    This order prevents "não pago" from matching 'pago' and returning paid.
    """
    t = text.lower().strip()
    if not t:
        return 'unknown'

    # Priority 1: negation before a paid stem → pending
    if _NEGATION_RE.search(t):
        return 'pending'

    # Priority 2: pending multi-word phrases and keywords first
    for w in PAYMENT_WORDS_PENDING:
        if w in t:
            return 'pending'

    # Priority 3: paid keywords (word-boundary to avoid "não pago" → paid)
    for w in PAYMENT_WORDS_PAID:
        if re.search(r'\b' + re.escape(w) + r'\b', t):
            return 'paid'

    return 'unknown'


def _classify_removed(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in REMOVED_WORDS)


def _slugify_simple(text: str) -> str:
    """ASCII slug for deterministic dedup key — no external deps."""
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]


def _safe_int(value) -> Optional[int]:
    """Extract first integer from value, ignoring non-numeric suffixes like 'º'."""
    s = str(value or '').strip()
    m = re.search(r'\d+', s)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            pass
    return None


def _clean(value) -> str:
    return str(value or '').strip()


# ── Generic HTML table extractor ──────────────────────────────────────────────

def _extract_html_table(html: str, source_url: str = '') -> list:
    """
    Generic HTML <table> parser. Uses BeautifulSoup if available.
    Returns list of raw row dicts with lowercased keys.
    Picks the table most likely to contain entries (most rows, or with name-like headers).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning('BeautifulSoup not available')
        return []

    try:
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return []

        # Score tables: prefer ones with headers suggesting player/category content
        NAME_SIGNALS = {'nome', 'name', 'atleta', 'jogador', 'player', 'atletas', 'participante'}

        def table_score(t):
            rows = t.find_all('tr')
            if len(rows) < 2:
                return -1
            header_text = t.find('tr').get_text(' ', strip=True).lower()
            signal_bonus = 5 if any(s in header_text for s in NAME_SIGNALS) else 0
            return len(rows) + signal_bonus

        table = max(tables, key=table_score)
        rows = table.find_all('tr')
        if len(rows) < 2:
            return []

        # Build headers from first row (th or td)
        header_row = rows[0].find_all(['th', 'td'])
        if not header_row:
            return []
        headers = [
            re.sub(r'\s+', '_', th.get_text(' ', strip=True).lower().strip())
            for th in header_row
        ]
        # Remove empty headers
        if not any(headers):
            return []

        result = []
        for row in rows[1:]:
            cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
            if not any(c.strip() for c in cells):
                continue
            while len(cells) < len(headers):
                cells.append('')
            result.append(dict(zip(headers, cells[:len(headers)])))
        return result

    except Exception as exc:
        logger.warning('HTML table extraction failed: %s', exc)
        return []


def _extract_text_table(text: str) -> list:
    """
    Parse tab/semicolon/pipe/comma separated text copied from a browser table.
    Detects delimiter and header row automatically.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []

    # Detect delimiter: prefer tab, then semicolon, then pipe, then comma
    delimiters = ['\t', ';', '|', ',']
    delimiter = max(delimiters, key=lambda d: lines[0].count(d))
    if lines[0].count(delimiter) == 0:
        # Try space-separated if nothing else — last resort
        if '  ' in lines[0]:
            delimiter = None
        else:
            return []

    def split_line(line):
        if delimiter:
            return [c.strip() for c in line.split(delimiter)]
        # multi-space split
        return [c.strip() for c in re.split(r'\s{2,}', line)]

    headers = [
        re.sub(r'\s+', '_', h.lower().strip())
        for h in split_line(lines[0])
    ]
    result = []
    for line in lines[1:]:
        cells = split_line(line)
        if not any(c.strip() for c in cells):
            continue
        while len(cells) < len(headers):
            cells.append('')
        result.append(dict(zip(headers, cells[:len(headers)])))
    return result


# ── Column name normalisers ────────────────────────────────────────────────────

_NAME_ALIASES = {
    'nome', 'name', 'atleta', 'athlete', 'jogador', 'player', 'player_name',
    'nome_completo', 'full_name', 'participants', 'participante',
    'atletas', 'jogadores', 'players',
}
_CAT_ALIASES = {
    'categoria', 'category', 'cat', 'division', 'divisao', 'chave', 'draw',
    'category_text', 'categoria_text', 'classe', 'class', 'naipe', 'evento',
    'modalidade', 'event',
}
_RANK_ALIASES = {
    'ranking', 'rank', 'posicao', 'posição', 'pos', 'ranking_position',
    'colocacao', 'colocação', 'classificacao', 'classificação', 'ranked',
    'seed', 'cabeça_de_chave', 'cabeca',
}
_PAYMENT_ALIASES = {
    'pagamento', 'payment', 'pago', 'paid', 'payment_status', 'situacao_pagamento',
    'situação_pagamento', 'status_pagamento', 'financeiro', 'taxa', 'inscricao_paga',
}
_ID_ALIASES = {
    'id', 'player_id', 'external_id', 'cod', 'codigo', 'código',
    'player_external_id', 'numero', 'número', 'num', 'matricula', 'matrícula',
}
_STATUS_ALIASES = {
    'status', 'situacao', 'situação', 'state', 'inscricao', 'inscrição', 'situação',
    'status_inscricao', 'situacao_inscricao',
}


def _find_column(row: dict, aliases: set) -> str:
    """Find column value from row dict, using exact match first, then substring."""
    # Exact match
    for key in row:
        if key in aliases:
            return row[key]
    # Substring match (any alias appears in column name)
    for key in row:
        key_clean = key.replace('_', ' ').strip()
        for alias in aliases:
            if alias in key or alias in key_clean:
                return row[key]
    return ''


def _row_to_entry(row: dict, source: str, source_url: str, ranking_source: str) -> Optional[dict]:
    """
    Convert a raw row dict into a bulk-import entry dict.
    Returns None (row rejected) if:
      - player_name missing or is a header word
      - category_text missing (never substitute with generic string)
    """
    player_name = _clean(_find_column(row, _NAME_ALIASES))
    if not player_name or len(player_name) < 2:
        return None

    # Skip header-like rows that crept through
    if player_name.lower() in {
        'nome', 'name', 'atleta', 'jogador', 'player', 'participante', '-', '—',
    }:
        return None

    category_text = _clean(_find_column(row, _CAT_ALIASES))
    # RULE: reject rows without a real category — never invent "Categoria não identificada"
    if not category_text:
        logger.debug('Row rejected — no category found for player "%s"', player_name)
        return None

    rank_raw = _find_column(row, _RANK_ALIASES)
    ranking_position = _safe_int(rank_raw)

    payment_raw = _find_column(row, _PAYMENT_ALIASES)
    payment_status = _classify_payment(payment_raw) if payment_raw else 'unknown'

    status_raw = _find_column(row, _STATUS_ALIASES)
    removed = _classify_removed(status_raw) or _classify_removed(payment_raw)
    replacement_reason = ''
    if removed:
        detail = _clean(status_raw) or _clean(payment_raw)
        replacement_reason = detail if detail.lower() not in {'pago', 'paid'} else 'Substituído por critério de ranking.'

    raw_external_id = _clean(_find_column(row, _ID_ALIASES))

    # DEDUP SAFETY: generate deterministic external_id when none provided.
    # Prevents multiple athletes without an id in the same category/source from
    # overwriting each other on upsert.
    if raw_external_id:
        external_id = raw_external_id
    else:
        external_id = f'{source}:{_slugify_simple(player_name)}:{_slugify_simple(category_text)}'

    return {
        'player_name': player_name,
        'category_text': category_text,
        'player_external_id': external_id,
        'ranking_position': ranking_position,
        'ranking_source': ranking_source,
        'payment_status': payment_status,
        'removed_or_replaced': removed,
        'replacement_reason': replacement_reason,
        'source_url': source_url,
    }


def _parse_generic(html_or_text: str, source: str, source_url: str,
                   ranking_source: str) -> list:
    """Try HTML table then text table; return list of entry dicts. Never invents data."""
    rows = _extract_html_table(html_or_text, source_url)
    if not rows:
        rows = _extract_text_table(html_or_text)

    entries = []
    for row in rows:
        entry = _row_to_entry(row, source, source_url, ranking_source)
        if entry:
            entries.append(entry)
    return entries


# ── Source-specific parsers ────────────────────────────────────────────────────

def parse_cosat_entries(html_or_text: str, source_url: str = '') -> dict:
    """
    COSAT/Tournament Software entry parser.

    STATUS: LIMITED.
    - robots.txt disallows /sport/ /tournament/ /ranking/ for all crawlers.
    - Auto-scraping not supported. Use case: admin pastes HTML/text from COSAT page.
    """
    source = 'cosat'
    ranking_source = 'COSAT'

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'COSAT: sem dados de entrada. '
                'Cole HTML/texto da página de inscritos COSAT como input. '
                'Auto-scraping bloqueado por robots.txt (/sport/ /tournament/ /ranking/ são Disallow).'
            ),
            'confidence': 'low',
            'source': source,
        }

    entries = _parse_generic(html_or_text, source, source_url, ranking_source)

    if not entries:
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'COSAT: nenhum inscrito extraído. '
                'Verifique se o conteúdo copiado contém tabela com colunas nome/categoria. '
                'Use docs/examples/cosat_bulk_import_example.csv como referência de formato.'
            ),
            'confidence': 'low',
            'source': source,
        }

    return {
        'entries': entries,
        'parser_warning': False,
        'warning_message': '',
        'confidence': 'medium',
        'source': source,
    }


_TENISINTEGRADO_INSC_URL = 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/{tid}'
_TENISINTEGRADO_UA = 'TenfyDataSync/1.0 (contato@tennis.app.br; data-research; no-automation)'
_TENISINTEGRADO_RATE = 1.2  # seconds between category requests


def _parse_tenisintegrado_table(html: str, category_text: str,
                                source: str, insc_url: str) -> list:
    """
    Parse one tenisintegrado inscription page (POST response for a given id_categoria).

    Table structure:
      <th>Participantes</th><th>WTN</th><th>Posição</th><th>Sit. Financeira</th>

    Player cell contains:
      - <a href="perfil2/index/{id}">Name</a>
      - City text node
      - "UF:XX, ID:NNNNNN, Idade:NN" text
    """
    import time as _time  # avoid shadowing at module level

    entries = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row_html in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)

        # Seção de cancelados/não confirmados: 3 colunas (nome+info, posição, status badge)
        if len(cells) == 3:
            badge_text = re.sub(r'<[^>]+>', '', cells[2]).strip().lower()
            if _classify_removed(badge_text):
                player_cell = cells[0]
                id_m = re.search(r'perfil2/index/(\d+)', player_cell, re.IGNORECASE)
                player_external_id = f'tenisintegrado:{id_m.group(1)}' if id_m else ''
                player_name = ''
                for name_m in re.finditer(
                    r'<a[^>]+perfil2/index/\d+[^>]*>(.*?)</a>',
                    player_cell, re.IGNORECASE | re.DOTALL,
                ):
                    text = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
                    if text and len(text) >= 2:
                        player_name = text
                        break
                if not player_name:
                    continue
                ext_id = player_external_id or f'{source}:{_slugify_simple(player_name)}:{_slugify_simple(category_text)}'
                entries.append({
                    'player_name': player_name,
                    'category_text': category_text,
                    'player_external_id': ext_id,
                    'ranking_position': _safe_int(re.sub(r'<[^>]+>', '', cells[1]).strip()),
                    'ranking_source': source.upper(),
                    'payment_status': 'unknown',
                    'removed_or_replaced': True,
                    'replacement_reason': f'Status na fonte: {badge_text[:80]}',
                    'source_url': insc_url,
                    'confidence': 'high',
                })
            continue

        if len(cells) < 4:
            continue

        player_cell = cells[0]

        # Player external ID from profile URL
        id_m = re.search(r'perfil2/index/(\d+)', player_cell, re.IGNORECASE)
        player_external_id = f'tenisintegrado:{id_m.group(1)}' if id_m else ''

        # Player name from anchor text — skip anchors that only contain an image (avatar link)
        player_name = ''
        for name_m in re.finditer(
            r'<a[^>]+perfil2/index/\d+[^>]*>(.*?)</a>',
            player_cell, re.IGNORECASE | re.DOTALL,
        ):
            text = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
            if text and len(text) >= 2:
                player_name = text
                break
        if not player_name:
            continue

        # UF / state from "UF:XX, ID:..."
        uf_m = re.search(r'UF:([A-Z]{2})', player_cell)

        # WTN: "31,28" → float string, strip img tags
        wtn_cell = re.sub(r'<[^>]+>', '', cells[1]).strip()
        wtn_str = wtn_cell.replace(',', '.') if wtn_cell else ''

        # Ranking position: "367º" → 367
        pos_cell = re.sub(r'<[^>]+>', '', cells[2]).strip()
        ranking_position = _safe_int(pos_cell) if pos_cell else None

        # Payment status + removed detection — check all cells for cancellation
        fin_text = re.sub(r'<[^>]+>', '', cells[3]).strip().lower()
        payment_status = _classify_payment(fin_text)
        # Check every cell for removal keywords (TI may put "Cancelado" in any column)
        all_cells_text = ' '.join(re.sub(r'<[^>]+>', '', c).strip().lower() for c in cells)
        removed = _classify_removed(fin_text) or _classify_removed(all_cells_text)
        replacement_reason = ''
        if removed:
            replacement_reason = f'Status: {all_cells_text[:120]}'

        # Dedup: if tenisintegrado ID available, use it; otherwise deterministic slug
        if player_external_id:
            ext_id = player_external_id
        else:
            ext_id = f'{source}:{_slugify_simple(player_name)}:{_slugify_simple(category_text)}'

        entries.append({
            'player_name': player_name,
            'category_text': category_text,
            'player_external_id': ext_id,
            'ranking_position': ranking_position,
            'ranking_source': source.upper(),
            'payment_status': payment_status,
            'removed_or_replaced': removed,
            'replacement_reason': replacement_reason,
            'source_url': insc_url,
            'confidence': 'high',
        })

    return entries


def fetch_tenisintegrado_entries(tournament_url: str, source: str = 'cbt') -> dict:
    """
    Auto-fetch all inscription entries from a tenisintegrado tournament URL.

    Steps:
      1. GET /torneio_painel_insc/index/{id} → extract id_categoria options
      2. POST with each id_categoria → parse table rows
      3. Return combined entries

    Returns standard parser result dict.
    """
    import time as _time

    try:
        import requests as _requests
    except ImportError:
        return {
            'entries': [], 'parser_warning': True,
            'warning_message': 'requests not installed — cannot auto-fetch TenisIntegrado.',
            'confidence': 'low', 'source': source,
        }

    tid_m = re.search(r'/(\d+)/?$', tournament_url.rstrip('/'))
    if not tid_m:
        return {
            'entries': [], 'parser_warning': True,
            'warning_message': f'CBT: não foi possível extrair ID do torneio de: {tournament_url}',
            'confidence': 'low', 'source': source,
        }

    tid = tid_m.group(1)
    insc_url = _TENISINTEGRADO_INSC_URL.format(tid=tid)

    session = _requests.Session()
    session.headers.update({
        'User-Agent': _TENISINTEGRADO_UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    })

    # Step 1: fetch category list
    try:
        r0 = session.get(insc_url, timeout=10)
        r0.raise_for_status()
    except Exception as exc:
        return {
            'entries': [], 'parser_warning': True,
            'warning_message': f'CBT: falha ao buscar {insc_url}: {exc}',
            'confidence': 'low', 'source': source,
        }

    categories = {}
    for m in re.finditer(
        r'<option[^>]+value=["\'](\d+)["\'][^>]*>(.*?)</option>',
        r0.text, re.IGNORECASE,
    ):
        categories[m.group(1)] = m.group(2).strip()

    if not categories:
        return {
            'entries': [], 'parser_warning': True,
            'warning_message': (
                f'CBT: nenhuma categoria encontrada em {insc_url}. '
                'Torneio pode não ter inscrições abertas ainda.'
            ),
            'confidence': 'low', 'source': source,
        }

    # Step 1b: extract cancelled players from the GET response using flexible regex.
    # The "Cancelado" section may use any HTML structure (divs, lists, or non-standard tables).
    # Strategy: find player profile links near "Cancelado" text within a 2000-char window.
    all_entries: list = []
    html0 = r0.text
    for cancel_m in re.finditer(r'cancelado', html0, re.IGNORECASE):
        window_start = max(0, cancel_m.start() - 2000)
        window = html0[window_start:cancel_m.end() + 200]
        # Look for TI profile link within window
        id_m = re.search(r'perfil2/index/(\d+)', window, re.IGNORECASE)
        if not id_m:
            continue
        ext_id = f'tenisintegrado:{id_m.group(1)}'
        # Find name near the profile link
        name_m = re.search(
            r'<a[^>]+perfil2/index/\d+[^>]*>(.*?)</a>',
            window, re.IGNORECASE | re.DOTALL,
        )
        player_name = re.sub(r'<[^>]+>', '', name_m.group(1)).strip() if name_m else ''
        if not player_name or len(player_name) < 2:
            continue
        all_entries.append({
            'player_name': player_name,
            'category_text': 'Cancelado',
            'player_external_id': ext_id,
            'ranking_position': None,
            'ranking_source': source.upper(),
            'payment_status': 'unknown',
            'removed_or_replaced': True,
            'replacement_reason': 'Cancelado na página de inscrições',
            'source_url': insc_url,
            'confidence': 'high',
        })
        logger.debug('TI cancelled player found: %s ext_id=%s', player_name, ext_id)

    warnings: list = []

    for cat_id, cat_text in categories.items():
        _time.sleep(_TENISINTEGRADO_RATE)
        try:
            r1 = session.post(
                insc_url,
                data={'id_categoria': cat_id},
                headers={'Referer': insc_url},
                timeout=10,
            )
            r1.raise_for_status()
        except Exception as exc:
            warnings.append(f'Categoria "{cat_text}" falhou: {exc}')
            continue

        cat_entries = _parse_tenisintegrado_table(r1.text, cat_text, source, insc_url)
        all_entries.extend(cat_entries)

    if not all_entries:
        return {
            'entries': [], 'parser_warning': True,
            'warning_message': (
                f'CBT: {len(categories)} categorias processadas, nenhum inscrito extraído. '
                + (' Avisos: ' + '; '.join(warnings) if warnings else '')
            ),
            'confidence': 'low', 'source': source,
        }

    return {
        'entries': all_entries,
        'parser_warning': bool(warnings),
        'warning_message': '; '.join(warnings) if warnings else '',
        'confidence': 'high',
        'source': source,
    }


def parse_cbt_entries(html_or_text: str, source_url: str = '') -> dict:
    """
    CBT/Tênis Integrado entry parser.

    Auto-fetch mode (preferred):
      When html_or_text is empty and source_url is a tenisintegrado URL,
      the parser fetches all categories automatically via POST /torneio_painel_insc.

    Manual mode:
      When html_or_text is provided, falls back to generic HTML/text table parser.
    """
    source = 'cbt'
    ranking_source = 'CBT'

    # Auto-fetch: no raw content but a tenisintegrado URL provided
    if not (html_or_text or '').strip() and 'tenisintegrado' in (source_url or '').lower():
        return fetch_tenisintegrado_entries(source_url, source=source)

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'CBT: sem dados de entrada. '
                'Forneça source_url de um torneio TenisIntegrado para busca automática, '
                'ou cole HTML/CSV da página de inscritos como input.'
            ),
            'confidence': 'low',
            'source': source,
        }

    entries = _parse_generic(html_or_text, source, source_url, ranking_source)

    if not entries:
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'CBT: nenhum inscrito extraído do HTML fornecido. '
                'Forneça source_url TenisIntegrado para busca automática, '
                'ou use CSV com colunas nome/categoria.'
            ),
            'confidence': 'low',
            'source': source,
        }

    return {
        'entries': entries,
        'parser_warning': False,
        'warning_message': '',
        'confidence': 'medium',
        'source': source,
    }


def parse_fpt_entries(html_or_text: str, source_url: str = '') -> dict:
    """
    FPT (SP / Paulista) entry parser.

    Uses fpt.tenisintegrado.com.br (same platform as CBT).
    Auto-fetch via POST /torneio_painel_insc/index/{id} — no html_or_text needed.
    """
    source = 'fpt'
    ranking_source = 'FPT'

    is_tenisintegrado = 'tenisintegrado' in (source_url or '').lower()
    if is_tenisintegrado and not (html_or_text or '').strip():
        return fetch_tenisintegrado_entries(source_url, source=source)

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'FPT (SP): forneça source_url do torneio TenisIntegrado '
                'ou cole HTML da página de inscritos como input.'
            ),
            'confidence': 'low',
            'source': source,
        }

    entries = _parse_generic(html_or_text, source, source_url, ranking_source)

    if not entries:
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'FPT: nenhum inscrito extraído. '
                'Use importação manual CSV ou cole HTML da página de inscritos.'
            ),
            'confidence': 'low',
            'source': source,
        }

    return {
        'entries': entries,
        'parser_warning': False,
        'warning_message': '',
        'confidence': 'medium',
        'source': source,
    }


def parse_fbt_entries(html_or_text: str, source_url: str = '') -> dict:
    """
    FBT entry parser.

    FBT/BA uses TenisIntegrado for many tournament pages. Prefer the same
    category-by-category auto-fetch used by CBT when a TenisIntegrado URL is
    available; otherwise fall back to generic HTML/CSV extraction.
    """
    source = 'fbt'
    ranking_source = 'FBT'

    is_tenisintegrado = 'tenisintegrado' in (source_url or '').lower()

    if is_tenisintegrado and not (html_or_text or '').strip():
        return fetch_tenisintegrado_entries(source_url, source=source)

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'FBT: sem dados de entrada. '
                'Cole HTML/texto da página de inscritos FBT como input.'
            ),
            'confidence': 'low',
            'source': source,
        }

    entries = _parse_generic(html_or_text, source, source_url, ranking_source)

    # n8n often fetches /torneio_painel_insc/index/{id} before calling this
    # endpoint. That first page usually contains only the category selector; the
    # real entries require POSTing each id_categoria. If generic parsing found
    # nothing, delegate to the TenisIntegrado auto-fetcher.
    if not entries and is_tenisintegrado:
        return fetch_tenisintegrado_entries(source_url, source=source)

    if not entries:
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'FBT: nenhum inscrito extraído. '
                'Use importação manual CSV ou cole HTML da página de inscritos.'
            ),
            'confidence': 'low',
            'source': source,
        }

    return {
        'entries': entries,
        'parser_warning': False,
        'warning_message': '',
        'confidence': 'medium',
        'source': source,
    }


def parse_fct_entries(html_or_text: str, source_url: str = '') -> dict:
    """FCT uses same TenisIntegrado platform as CBT — same limitations apply."""
    result = parse_cbt_entries(html_or_text, source_url)
    result['source'] = 'fct'
    return result


def parse_manual_entries(html_or_text: str, source_url: str = '',
                         source: str = 'manual') -> dict:
    """
    Generic parser for manually pasted HTML/CSV/text from any source.
    Highest confidence when data is provided — admin is responsible for accuracy.
    """
    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': 'Nenhum conteúdo fornecido.',
            'confidence': 'high',
            'source': source,
        }

    entries = _parse_generic(html_or_text, source, source_url, source.upper())

    return {
        'entries': entries,
        'parser_warning': len(entries) == 0,
        'warning_message': 'Nenhum inscrito encontrado no conteúdo.' if not entries else '',
        'confidence': 'high' if entries else 'low',
        'source': source,
    }


# ── Parser registry ────────────────────────────────────────────────────────────

PARSERS = {
    'cosat':  parse_cosat_entries,
    'cbt':    parse_cbt_entries,
    'fbt':    parse_fbt_entries,
    'fpt':    parse_fpt_entries,
    'fct':    parse_fct_entries,
    'manual': parse_manual_entries,
}

PARSER_LIMITATIONS = {
    'cosat': (
        'robots.txt disabilita /sport/ /tournament/ /ranking/ para todos crawlers. '
        'Sem API pública. Import manual ou n8n com HTML colado.'
    ),
    'cbt': (
        'TenisIntegrado: lista de inscritos pública via POST /torneio_painel_insc/index/{id}. '
        'Forneça source_url do torneio para busca automática por categoria.'
    ),
    'fpt': (
        'FPT (SP / Paulista): usa TenisIntegrado — auto-fetch via POST /torneio_painel_insc/. '
        'FPT (PR / Paranaense): /Inscricao/Lista/ retorna 404 — import manual.'
    ),
    'fbt': (
        'Sem endpoint público de inscritos conhecido. '
        'Import manual ou n8n com HTML/CSV colado.'
    ),
    'fct': (
        'FCT usa TenisIntegrado — mesmas limitações do CBT. '
        'Sem endpoint público de inscritos.'
    ),
    'itf':  'ITF API requer autenticação. Verificar parceria oficial.',
    'utr':  'UTR API requer chave. Sem acesso público a inscritos.',
}


# Sources that can fetch their own data from source_url without html_or_text input.
# Used by quality_gate in parse-entries: empty html_or_text is valid for these sources
# when source_url is provided and the parser returned entries successfully.
SOURCES_AUTO_FETCH = {'cbt', 'fct', 'fbt', 'fpt'}


def get_parser(source: str):
    """Return parser function for source, or None if unsupported."""
    return PARSERS.get(source.lower())


def supports_auto_fetch(source: str) -> bool:
    """True when the parser can self-fetch from source_url without html_or_text."""
    return source.lower() in SOURCES_AUTO_FETCH


def get_limitation(source: str) -> str:
    return PARSER_LIMITATIONS.get(source.lower(), 'Fonte não reconhecida.')
