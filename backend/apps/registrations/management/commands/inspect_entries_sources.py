"""
Management command — deep inspection of real federation inscription URLs.

Fetches actual HTML from preferred_entries_url for each target, saves optional
snapshots, and analyses the structure (tables, forms, login walls, JSON APIs,
XHR patterns) to determine what is publicly accessible without authentication.

Usage:
    python manage.py inspect_entries_sources
    python manage.py inspect_entries_sources --source fpt --limit 5
    python manage.py inspect_entries_sources --source cbt --limit 3 --save-snapshots
    python manage.py inspect_entries_sources --no-fetch   # DB-only summary

Safe: read-only, no DB writes, polite rate limiting, short timeout.
Snapshots saved to .tmp/source_snapshots/ (gitignored).
"""
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.registrations.integration_views import (
    _edition_source,
    derive_entries_source_url,
    infer_source_from_url,
)
from apps.registrations.models import FederationEntry
from apps.registrations.parsers import get_limitation
from apps.tournaments.models import TournamentEdition

USER_AGENT = 'TenfyDataSync/1.0 (contato@tennis.app.br; research-only; no-automation)'
TIMEOUT = 10
RATE_LIMIT = 2.0  # seconds between requests

# Terms that strongly indicate a login wall / auth requirement
AUTH_WALL_TERMS = [
    'login', 'entrar', 'fazer login', 'sign in', 'log in',
    'password', 'senha', 'autenti', 'acesso restrito',
    'you must be logged', 'precisa estar logado', 'area restrita',
    'sessão expirou', 'session expired',
]

# Terms that indicate a CAPTCHA
CAPTCHA_TERMS = [
    'recaptcha', 'g-recaptcha', 'hcaptcha', 'turnstile', 'captcha',
    'cloudflare', 'cf-challenge', 'ray id', 'checking your browser',
]

# Terms that indicate inscription/entry list content
INSCRIPTION_SIGNALS = [
    'inscrito', 'inscritos', 'inscrição', 'inscrições',
    'lista de inscritos', 'atletas inscritos', 'entry list',
    'jogadores', 'participantes', 'acceptance list',
    'draw', 'chaves', 'tabela de inscrições',
]

# URL patterns that may link to entry lists
ENTRY_LINK_PATTERNS = [
    '/inscrit', '/inscricao', '/inscrição', '/inscrições', 'inscrito',
    'entry', 'draw', 'players', 'participant', 'atleta',
    'acceptance', 'chave', 'tabela', 'ranking',
]

# JSON/XHR API patterns in JS
XHR_PATTERNS = [
    r'fetch\s*\(["\']([^"\']+)["\']',
    r'axios\.[a-z]+\s*\(["\']([^"\']+)["\']',
    r'XMLHttpRequest.*open.*["\']([^"\']+)["\']',
    r'url\s*[:=]\s*["\']([^"\']+/api[^"\']*)["\']',
    r'\$\.ajax\s*\(\s*["\']([^"\']+)["\']',
    r'\$\.get\s*\(\s*["\']([^"\']+)["\']',
    r'\$\.post\s*\(\s*["\']([^"\']+)["\']',
]

# HTML table header patterns suggesting entry data
TABLE_HEADER_PATTERNS = [
    r'<th[^>]*>(.*?)</th>',
    r'<td[^>]*>\s*<b>(.*?)</b>\s*</td>',
]


def _detect_auth_wall(html_lower: str) -> list[str]:
    return [t for t in AUTH_WALL_TERMS if t in html_lower]


def _detect_captcha(html_lower: str) -> list[str]:
    return [t for t in CAPTCHA_TERMS if t in html_lower]


def _detect_inscription_signals(html_lower: str) -> list[str]:
    return [s for s in INSCRIPTION_SIGNALS if s in html_lower]


def _extract_tables(html: str) -> list[dict]:
    """Extract HTML tables and their headers + sample rows."""
    tables = []
    for table_html in re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE):
        headers = re.findall(r'<th[^>]*>(.*?)</th>', table_html, re.DOTALL | re.IGNORECASE)
        headers = [re.sub(r'<[^>]+>', '', h).strip() for h in headers[:10]]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        sample_row = ''
        if rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[0], re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r'<[^>]+>', '', c).strip()[:40] for c in cells[:6]]
            sample_row = ' | '.join(cells)
        tables.append({
            'headers': headers,
            'row_count_estimate': len(rows),
            'sample_row': sample_row,
        })
    return tables


def _extract_xhr_endpoints(html: str) -> list[str]:
    """Scan JS for XHR/fetch/axios API calls."""
    endpoints = []
    for pattern in XHR_PATTERNS:
        for m in re.findall(pattern, html, re.IGNORECASE):
            if m and len(m) > 3 and len(m) < 200:
                endpoints.append(m)
    return list(dict.fromkeys(endpoints))[:15]


def _extract_entry_links(html: str, base_url: str) -> list[str]:
    """Find href links that match entry/inscription patterns."""
    links = []
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', html):
        href_lower = href.lower()
        if any(p in href_lower for p in ENTRY_LINK_PATTERNS):
            if href.startswith('http'):
                links.append(href[:150])
            elif href.startswith('/'):
                domain = re.match(r'(https?://[^/]+)', base_url)
                if domain:
                    links.append(domain.group(1) + href[:150])
    return list(dict.fromkeys(links))[:10]


def _detect_json_data(html: str) -> list[str]:
    """Find embedded JSON blobs (common in SPA/turbolinks apps)."""
    patterns = [
        r'var\s+\w+\s*=\s*(\{[^;]{50,2000}?\});',
        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        r'data-json=["\'](\{[^"\']{10,500}\})["\']',
        r'application/json[^>]*>(\{[^<]{10,500}\})',
    ]
    found = []
    for p in patterns:
        for m in re.findall(p, html, re.DOTALL | re.IGNORECASE):
            try:
                json.loads(m)
                found.append(m[:200])
            except (ValueError, TypeError):
                pass
    return found[:3]


def _assess_accessibility(analysis: dict) -> str:
    """Return a one-line verdict on public accessibility."""
    if analysis['auth_wall']:
        return 'BLOCKED — login wall detected'
    if analysis['captcha']:
        return 'BLOCKED — CAPTCHA detected'
    if analysis['http_status'] != 200:
        return f'BLOCKED — HTTP {analysis["http_status"]}'
    if analysis['is_js_only']:
        return 'UNCERTAIN — JS-rendered, static HTML empty (needs headless browser)'
    if analysis['inscription_signals'] and analysis['tables']:
        return 'ACCESSIBLE — inscription data found in static HTML'
    if analysis['inscription_signals']:
        return 'PARTIAL — inscription signals but no clear table structure'
    if analysis['xhr_endpoints']:
        return 'UNCERTAIN — API endpoints found in JS, data may be dynamic'
    if analysis['entry_links']:
        return 'POSSIBLE — entry-related links found, deeper crawl needed'
    return 'UNKNOWN — no clear inscription data found'


class Command(BaseCommand):
    help = 'Deep inspection of real federation inscription URLs — accessibility analysis'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10,
                            help='Max targets per source (default: 10)')
        parser.add_argument('--source', type=str, default='',
                            help='Filter: fpt|cbt|cosat|manual (empty = all)')
        parser.add_argument('--no-fetch', action='store_true',
                            help='Skip HTTP; show DB summary only')
        parser.add_argument('--save-snapshots', action='store_true',
                            help='Save raw HTML to .tmp/source_snapshots/')

    def handle(self, *args, **options):
        limit = min(options['limit'], 50)
        source_filter = options['source'].lower().strip()
        no_fetch = options['no_fetch']
        save_snapshots = options['save_snapshots']

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Inspect Entries Sources '
            f'(limit={limit}, source={source_filter or "all"}, '
            f'fetch={not no_fetch}, snapshots={save_snapshots}) ==='
        ))

        if save_snapshots:
            snap_dir = Path('.tmp/source_snapshots')
            snap_dir.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f'Snapshots → {snap_dir.resolve()}')

        qs = (
            TournamentEdition.objects
            .select_related('tournament', 'data_source')
            .prefetch_related('links')
            .filter(official_source_url__gt='')
            .exclude(status__in=['finished', 'canceled'])
        )

        targets = []
        for edition in qs.iterator(chunk_size=100):
            source = _edition_source(edition)
            if source_filter and source != source_filter:
                continue
            entries_url, ranking_url, candidates = derive_entries_source_url(edition)
            preferred = entries_url or edition.official_source_url
            targets.append({
                'edition': edition,
                'source': source,
                'preferred_url': preferred,
                'entries_url': entries_url,
                'ranking_url': ranking_url,
                'candidates': candidates,
            })
            if len(targets) >= limit:
                break

        by_source = defaultdict(list)
        for t in targets:
            by_source[t['source']].append(t)

        self.stdout.write(f'\nTotal targets: {len(targets)}')
        for src, items in sorted(by_source.items()):
            limitation = get_limitation(src)
            self.stdout.write(f'  {src}: {len(items)} targets — {limitation[:80]}')

        if not targets:
            self._explain_zero_targets(source_filter)
            return

        if no_fetch:
            self._print_db_summary(targets)
            return

        try:
            import requests
        except ImportError:
            self.stdout.write(self.style.ERROR('requests not installed'))
            return

        session = requests.Session()
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5',
        })

        results = {}
        self.stdout.write('\n--- Fetching (rate limited) ---')

        for i, t in enumerate(targets):
            url = t['preferred_url']
            eid = t['edition'].id
            name = (t['edition'].title or t['edition'].tournament.canonical_name or '')[:50]
            self.stdout.write(f'\n[{i+1}/{len(targets)}] {name} | {t["source"]}')
            self.stdout.write(f'  URL: {url[:100]}')

            try:
                resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
                html = resp.text[:80000]
                html_lower = html.lower()
                content_type = resp.headers.get('content-type', '')

                # Detect JS-only: HTML < 2KB and has script tags but no body text
                body_text = re.sub(r'<[^>]+>', '', html).strip()
                is_js_only = (
                    len(body_text) < 500
                    and '<script' in html_lower
                    and resp.status_code == 200
                )

                analysis = {
                    'url': url,
                    'final_url': resp.url,
                    'http_status': resp.status_code,
                    'content_type': content_type[:80],
                    'size_bytes': len(resp.content),
                    'auth_wall': _detect_auth_wall(html_lower),
                    'captcha': _detect_captcha(html_lower),
                    'inscription_signals': _detect_inscription_signals(html_lower),
                    'tables': _extract_tables(html),
                    'xhr_endpoints': _extract_xhr_endpoints(html),
                    'entry_links': _extract_entry_links(html, url),
                    'json_data': _detect_json_data(html),
                    'is_js_only': is_js_only,
                }
                analysis['verdict'] = _assess_accessibility(analysis)
                results[eid] = analysis

                self._print_result(analysis)

                if save_snapshots:
                    snap_path = snap_dir / f'{t["source"]}_{eid}.html'
                    snap_path.write_text(resp.text[:200000], encoding='utf-8', errors='replace')
                    self.stdout.write(f'  Snapshot: {snap_path}')

            except Exception as exc:
                results[eid] = {
                    'url': url, 'http_status': 'ERROR', 'error': str(exc)[:100],
                    'verdict': f'ERROR — {exc}',
                    'auth_wall': [], 'captcha': [], 'inscription_signals': [],
                    'tables': [], 'xhr_endpoints': [], 'entry_links': [],
                    'json_data': [], 'is_js_only': False,
                }
                self.stdout.write(f'  ERROR: {exc}')

            time.sleep(RATE_LIMIT)

        self._print_final_report(targets, by_source, results)

    def _print_result(self, a: dict):
        self.stdout.write(f'  HTTP={a["http_status"]} size={a["size_bytes"]}B '
                          f'type={a["content_type"][:40]}')
        self.stdout.write(f'  Verdict: {a["verdict"]}')
        if a['auth_wall']:
            self.stdout.write(f'  Auth wall: {a["auth_wall"][:3]}')
        if a['captcha']:
            self.stdout.write(f'  CAPTCHA: {a["captcha"][:3]}')
        if a['inscription_signals']:
            self.stdout.write(f'  Inscription signals: {a["inscription_signals"][:5]}')
        if a['tables']:
            for j, tbl in enumerate(a['tables'][:3]):
                self.stdout.write(f'  Table[{j}] headers={tbl["headers"][:6]} '
                                  f'rows≈{tbl["row_count_estimate"]}')
                if tbl['sample_row']:
                    self.stdout.write(f'    sample: {tbl["sample_row"][:100]}')
        if a['xhr_endpoints']:
            self.stdout.write(f'  XHR/API: {a["xhr_endpoints"][:3]}')
        if a['entry_links']:
            self.stdout.write(f'  Entry links: {a["entry_links"][:3]}')
        if a['json_data']:
            self.stdout.write(f'  JSON blobs: {len(a["json_data"])} found')

    def _print_db_summary(self, targets: list):
        self.stdout.write('\n--- DB Summary (no fetch) ---')
        for t in targets:
            eid = t['edition'].id
            name = (t['edition'].title or t['edition'].tournament.canonical_name or '')[:50]
            self.stdout.write(
                f'  [{eid}] {name} | src={t["source"]} | url={t["preferred_url"][:80]}'
            )
            if t['candidates']:
                self.stdout.write(f'    candidates: {t["candidates"][:2]}')

    def _print_final_report(self, targets, by_source, results):
        self.stdout.write('\n' + '='*60)
        self.stdout.write('=== FINAL ACCESSIBILITY REPORT ===')
        self.stdout.write('='*60)

        for src, items in sorted(by_source.items()):
            self.stdout.write(f'\n[{src.upper()}]')
            limitation = get_limitation(src)
            self.stdout.write(f'  Parser limitation: {limitation}')

            verdicts = defaultdict(int)
            for t in items:
                r = results.get(t['edition'].id, {})
                verdict = r.get('verdict', 'NOT FETCHED')
                verdicts[verdict] += 1

            for verdict, count in sorted(verdicts.items()):
                self.stdout.write(f'  {count}x {verdict}')

            # Collect all XHR endpoints and promising table headers for this source
            all_xhr = []
            all_tables = []
            all_entry_links = []
            for t in items:
                r = results.get(t['edition'].id, {})
                all_xhr.extend(r.get('xhr_endpoints', []))
                all_tables.extend(r.get('tables', []))
                all_entry_links.extend(r.get('entry_links', []))

            if all_xhr:
                unique_xhr = list(dict.fromkeys(all_xhr))[:5]
                self.stdout.write(f'  API patterns found: {unique_xhr}')
            if all_entry_links:
                unique_links = list(dict.fromkeys(all_entry_links))[:5]
                self.stdout.write(f'  Entry links found: {unique_links}')
            if all_tables:
                # Find tables with player-like headers
                for tbl in all_tables[:5]:
                    hdrs = [h.lower() for h in tbl['headers']]
                    player_terms = {'nome', 'name', 'atleta', 'jogador', 'player', 'cpf', 'ranking'}
                    if any(t in hdrs for t in player_terms):
                        self.stdout.write(
                            f'  Player table: headers={tbl["headers"][:6]}'
                        )

        self.stdout.write('\n--- Parser Implementation Recommendation ---')
        for src, items in sorted(by_source.items()):
            accessible = [
                t for t in items
                if 'ACCESSIBLE' in results.get(t['edition'].id, {}).get('verdict', '')
            ]
            partial = [
                t for t in items
                if 'PARTIAL' in results.get(t['edition'].id, {}).get('verdict', '')
                or 'POSSIBLE' in results.get(t['edition'].id, {}).get('verdict', '')
            ]
            uncertain = [
                t for t in items
                if 'UNCERTAIN' in results.get(t['edition'].id, {}).get('verdict', '')
            ]
            blocked = [
                t for t in items
                if 'BLOCKED' in results.get(t['edition'].id, {}).get('verdict', '')
            ]

            if accessible:
                rec = f'IMPLEMENT parser — {len(accessible)} URLs return public HTML tables'
            elif partial:
                rec = f'INVESTIGATE further — {len(partial)} URLs have partial signals'
            elif uncertain:
                rec = f'NEEDS HEADLESS BROWSER — {len(uncertain)} URLs are JS-rendered'
            elif blocked:
                rec = f'NOT FEASIBLE — {len(blocked)} URLs require login/CAPTCHA'
            else:
                rec = 'INSUFFICIENT DATA — increase --limit or check targets exist'

            self.stdout.write(f'  {src}: {rec}')

    def _explain_zero_targets(self, source_filter: str):
        self.stdout.write('\n--- Why zero targets? ---')
        if source_filter == 'cosat':
            self.stdout.write(
                'COSAT connector is DISABLED (enabled=False in seed_sources).\n'
                'Reason: COSAT robots.txt explicitly blocks all automated access:\n'
                '  Disallow: /sport/\n'
                '  Disallow: /tournament/\n'
                '  Disallow: /ranking/\n'
                'Additionally, the COSAT API endpoint returns HTTP 404.\n'
                'No TournamentEdition rows exist with source=cosat.\n'
                'To add COSAT support: data must be provided manually or via\n'
                'official COSAT data sharing agreement.'
            )
        else:
            self.stdout.write(
                f'No active TournamentEdition with source={source_filter!r} found.\n'
                'Possible reasons:\n'
                '  - No tournaments imported for this federation yet\n'
                '  - All editions have status=finished/canceled\n'
                '  - official_source_url is empty for this source\n'
                'Try: python manage.py inspect_entries_sources --no-fetch --source '
                + (source_filter or 'fpt')
            )
