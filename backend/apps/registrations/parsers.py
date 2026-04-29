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
from typing import Optional

logger = logging.getLogger('apps.registrations.parsers')

# ── Shared helpers ─────────────────────────────────────────────────────────────

PAYMENT_WORDS_PAID = {'pago', 'paid', 'confirmado', 'confirmed', 'sim', 'yes', 'pg'}
PAYMENT_WORDS_PENDING = {'pendente', 'pending', 'aguardando', 'awaiting', 'nao', 'não', 'no'}

REMOVED_WORDS = {
    'substituído', 'substituida', 'substituido', 'removed', 'removido',
    'cortado', 'excluído', 'excluido', 'eliminado', 'out',
}


def _classify_payment(text: str) -> str:
    t = text.lower().strip()
    if any(w in t for w in PAYMENT_WORDS_PAID):
        return 'paid'
    if any(w in t for w in PAYMENT_WORDS_PENDING):
        return 'pending'
    return 'unknown'


def _classify_removed(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in REMOVED_WORDS)


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _clean(value) -> str:
    return str(value or '').strip()


# ── Generic HTML table extractor ──────────────────────────────────────────────

def _extract_html_table(html: str, source_url: str = '') -> list:
    """
    Generic HTML <table> parser — works for any federation page pasted by admin.
    Returns list of raw row dicts with keys lowercased.
    Tries BeautifulSoup first; falls back to regex on ImportError.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return []

        # Use the largest table (most likely the entry list)
        table = max(tables, key=lambda t: len(t.find_all('tr')))
        rows = table.find_all('tr')
        if len(rows) < 2:
            return []

        headers = [
            th.get_text(' ', strip=True).lower().replace(' ', '_')
            for th in rows[0].find_all(['th', 'td'])
        ]
        if not headers:
            return []

        result = []
        for row in rows[1:]:
            cells = [td.get_text(' ', strip=True) for td in row.find_all(['td', 'th'])]
            if len(cells) < 2:
                continue
            # Pad cells to match header length
            while len(cells) < len(headers):
                cells.append('')
            result.append(dict(zip(headers, cells[:len(headers)])))
        return result

    except ImportError:
        logger.warning('BeautifulSoup not available — skipping HTML table extraction')
        return []
    except Exception as exc:
        logger.warning('HTML table extraction failed: %s', exc)
        return []


def _extract_text_table(text: str) -> list:
    """
    Parse tab/semicolon/pipe-separated text copied from a browser table.
    Tries to detect delimiter and header row automatically.
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return []

    # Detect delimiter: prefer tab, then semicolon, then pipe, then comma
    delimiters = ['\t', ';', '|', ',']
    delimiter = max(delimiters, key=lambda d: lines[0].count(d))
    if lines[0].count(delimiter) == 0:
        return []

    headers = [h.strip().lower().replace(' ', '_') for h in lines[0].split(delimiter)]
    result = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split(delimiter)]
        while len(cells) < len(headers):
            cells.append('')
        result.append(dict(zip(headers, cells[:len(headers)])))
    return result


# ── Column name normalisers ────────────────────────────────────────────────────

_NAME_ALIASES = {
    'nome', 'name', 'atleta', 'athlete', 'jogador', 'player', 'player_name',
    'nome_completo', 'full_name',
}
_CAT_ALIASES = {
    'categoria', 'category', 'cat', 'division', 'divisao', 'chave', 'draw',
    'category_text', 'categoria_text',
}
_RANK_ALIASES = {
    'ranking', 'rank', 'posicao', 'posição', 'pos', 'ranking_position',
    'colocacao', 'colocação', 'classificacao', 'classificação',
}
_PAYMENT_ALIASES = {
    'pagamento', 'payment', 'pago', 'paid', 'payment_status', 'situacao',
    'situação', 'status_pagamento',
}
_ID_ALIASES = {
    'id', 'player_id', 'external_id', 'cod', 'codigo', 'código',
    'player_external_id', 'numero', 'número', 'num',
}
_STATUS_ALIASES = {
    'status', 'situacao', 'situação', 'state', 'inscricao', 'inscrição',
}


def _find_column(row: dict, aliases: set) -> str:
    for key in row:
        if key in aliases:
            return row[key]
        # fuzzy: any alias in key
        for alias in aliases:
            if alias in key:
                return row[key]
    return ''


def _row_to_entry(row: dict, source: str, source_url: str, ranking_source: str) -> Optional[dict]:
    """Convert a raw row dict into a bulk-import entry dict. Returns None if no name found."""
    player_name = _clean(_find_column(row, _NAME_ALIASES))
    if not player_name:
        return None

    category_text = _clean(_find_column(row, _CAT_ALIASES))
    if not category_text:
        category_text = 'Categoria não identificada'

    rank_raw = _find_column(row, _RANK_ALIASES)
    ranking_position = _safe_int(rank_raw)

    payment_raw = _find_column(row, _PAYMENT_ALIASES)
    payment_status = _classify_payment(payment_raw) if payment_raw else 'unknown'

    status_raw = _find_column(row, _STATUS_ALIASES)
    removed = _classify_removed(status_raw) or _classify_removed(payment_raw)
    replacement_reason = ''
    if removed:
        replacement_reason = _clean(status_raw) or 'Substituído por critério de ranking.'

    external_id = _clean(_find_column(row, _ID_ALIASES))

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
    """Try HTML table then text table; return list of entry dicts."""
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

    STATUS: LIMITED — robots.txt disallows /sport/ /tournament/ /ranking/.
    Use case: admin pastes HTML/text from COSAT page manually.
    Auto-scraping not supported — parser_warning always True for auto mode.

    Returns entries extracted from pasted HTML/text, or empty list with warning
    if input is empty.
    """
    source = 'cosat'
    ranking_source = 'COSAT'

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'COSAT: sem dados de entrada. '
                'Copie o HTML/texto da página de inscritos COSAT e passe como input. '
                'Scraping automático não suportado — robots.txt desabilita /sport/ e /tournament/.'
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
                'COSAT: nenhum inscrito extraído do HTML/texto fornecido. '
                'Verifique se o conteúdo copiado contém uma tabela com colunas de nome e categoria. '
                'Use o CSV de exemplo em docs/examples/cosat_bulk_import_example.csv como referência.'
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


def parse_cbt_entries(html_or_text: str, source_url: str = '') -> dict:
    """
    CBT/Tênis Integrado entry parser.

    STATUS: LIMITED — TenisIntegrado API returns 404 for individual registration endpoints.
    The public site (tenisintegrado.com.br) may have HTML tables on tournament detail pages
    but structure changes frequently. Auto-fetch not reliable.

    Use case: admin pastes HTML/text from CBT tournament detail page.
    """
    source = 'cbt'
    ranking_source = 'CBT'

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'CBT: sem dados de entrada. '
                'A API TenisIntegrado não expõe lista nominal de inscritos (/getRegistrations retorna 404). '
                'Cole o HTML da página de inscritos do torneio CBT como input.'
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
                'CBT: nenhum inscrito extraído. '
                'O TenisIntegrado não retorna lista nominal via API pública. '
                'Importe manualmente usando o CSV de exemplo ou cole o HTML da página.'
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
    FPT entry parser.

    STATUS: LIMITED — FPT does not expose a public entries/inscritos endpoint.
    /Inscricao/Lista/ returns 404. Manual paste is the only reliable path.

    Use case: admin pastes HTML/text from FPT tournament page.
    """
    source = 'fpt'
    ranking_source = 'FPT'

    if not (html_or_text or '').strip():
        return {
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                'FPT: sem dados de entrada. '
                '/Inscricao/Lista/ retorna 404 — FPT não tem endpoint público de inscritos. '
                'Cole o HTML da página de inscritos FPT como input.'
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
                'FPT não expõe lista nominal via API pública. '
                'Use importação manual CSV ou cole o HTML da página de inscritos.'
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


def parse_manual_entries(html_or_text: str, source_url: str = '',
                         source: str = 'manual') -> dict:
    """
    Generic parser for manually pasted HTML/CSV/text.
    Used when admin pastes content from any source.
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
    'cosat':   parse_cosat_entries,
    'cbt':     parse_cbt_entries,
    'fpt':     parse_fpt_entries,
    'fct':     parse_fpt_entries,   # same structure as FPT
    'manual':  parse_manual_entries,
}

PARSER_LIMITATIONS = {
    'cosat': 'robots.txt disabilita /sport/ /tournament/ /ranking/. Sem API pública. Import manual ou n8n com HTML colado.',
    'cbt':   'TenisIntegrado API retorna 404 para inscritos individuais. Import manual ou n8n com HTML colado.',
    'fpt':   '/Inscricao/Lista/ retorna 404. Sem endpoint público de inscritos. Import manual.',
    'fct':   'Sem endpoint público de inscritos. Import manual.',
    'itf':   'ITF API requer autenticação. Verificar parceria oficial.',
    'utr':   'UTR API requer chave. Sem acesso público a inscritos.',
}


def get_parser(source: str):
    """Return parser function for source, or None if unsupported."""
    return PARSERS.get(source.lower())


def get_limitation(source: str) -> str:
    return PARSER_LIMITATIONS.get(source.lower(), 'Fonte não reconhecida.')
