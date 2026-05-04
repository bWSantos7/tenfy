"""
Management command — audit federation sync targets.

Usage:
    python manage.py audit_federation_sync_targets
    python manage.py audit_federation_sync_targets --limit 20
    python manage.py audit_federation_sync_targets --source fpt
    python manage.py audit_federation_sync_targets --no-fetch  # skip HTTP, show DB only

Safe: read-only, no DB writes, polite rate limiting, short timeout.
"""
import time
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.registrations.integration_views import (
    _edition_source, _sync_priority, derive_entries_source_url,
)
from apps.registrations.models import FederationEntry
from apps.registrations.parsers import get_limitation
from apps.tournaments.models import TournamentEdition

INSCRIPTION_SIGNALS = [
    'inscrito', 'inscritos', 'inscrição', 'inscrições', 'lista de inscritos',
    'atletas', 'jogadores', 'participantes', 'ranking', 'pagamento',
    'entry list', 'players', 'acceptance list', 'draw', 'tournament',
    'entry', 'chaves', 'tabela',
]

CANDIDATE_LINK_PATTERNS = [
    '/inscrit', '/inscricao', '/inscrição', '/inscrições',
    'players', 'entry', 'draw', 'ranking', 'chaves',
    'acceptance', 'participant', 'atleta',
]

USER_AGENT = 'TennisHubDataSync/1.0 (contato@tennis.app.br; audit-only; no-save)'
TIMEOUT = 8
RATE_LIMIT = 1.5  # seconds between requests


class Command(BaseCommand):
    help = 'Audit federation sync targets — read-only analysis of source URLs'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50,
                            help='Max targets to analyse (default: 50)')
        parser.add_argument('--source', type=str, default='',
                            help='Filter by source: fpt|cbt|cosat|manual')
        parser.add_argument('--no-fetch', action='store_true',
                            help='Skip HTTP fetching; show DB data only')

    def handle(self, *args, **options):
        limit = min(options['limit'], 200)
        source_filter = options['source'].lower().strip()
        no_fetch = options['no_fetch']

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Federation Sync Target Audit (limit={limit}, source={source_filter or "all"}, fetch={not no_fetch}) ==='
        ))

        now = timezone.now()
        stale_threshold = now - timedelta(hours=12)

        qs = (
            TournamentEdition.objects
            .select_related('tournament')
            .prefetch_related('links')
            .filter(official_source_url__gt='')
            .exclude(status__in=['finished', 'canceled'])
        )

        synced_map = dict(
            FederationEntry.objects
            .filter(edition__in=qs)
            .values('edition_id')
            .annotate(last=Max('synced_at'))
            .values_list('edition_id', 'last')
        )

        targets = []
        for edition in qs.select_related('tournament')[:limit * 3]:
            source = _edition_source(edition)
            if source_filter and source != source_filter:
                continue
            dyn_status = edition.compute_dynamic_status()
            last_synced = synced_map.get(edition.id)
            needs_sync = last_synced is None or last_synced < stale_threshold
            priority = _sync_priority(edition, dyn_status, last_synced)
            entries_url, ranking_url, candidates = derive_entries_source_url(edition)

            targets.append({
                'edition': edition,
                'source': source,
                'dynamic_status': dyn_status,
                'last_synced': last_synced,
                'needs_sync': needs_sync,
                'priority': priority,
                'entries_source_url': entries_url,
                'ranking_source_url': ranking_url,
                'candidate_links': candidates,
            })
            if len(targets) >= limit:
                break

        self.stdout.write(f'Targets found: {len(targets)}')
        if not targets:
            self.stdout.write('No targets match filters.')
            return

        # Group stats
        by_source = defaultdict(list)
        for t in targets:
            by_source[t['source']].append(t)

        self.stdout.write('\n--- By Source ---')
        for src, items in sorted(by_source.items()):
            self.stdout.write(f'  {src}: {len(items)} targets')

        if no_fetch:
            self._print_summary(targets, by_source, fetch_results={})
            return

        # HTTP fetch analysis
        try:
            import requests
            session = requests.Session()
            session.headers.update({'User-Agent': USER_AGENT})
        except ImportError:
            self.stdout.write(self.style.WARNING('requests not available — skipping HTTP fetch'))
            self._print_summary(targets, by_source, fetch_results={})
            return

        self.stdout.write('\n--- Fetching source URLs (rate limited) ---')
        fetch_results = {}

        for i, t in enumerate(targets):
            url = t['entries_source_url'] or t['edition'].official_source_url
            edition_id = t['edition'].id
            self.stdout.write(f'  [{i+1}/{len(targets)}] edition={edition_id} url={url[:80]}')

            try:
                resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
                html = resp.text[:50000]
                html_lower = html.lower()
                content_type = resp.headers.get('content-type', '')
                size = len(resp.content)

                signals = [s for s in INSCRIPTION_SIGNALS if s in html_lower]

                # Find candidate links
                import re
                links_found = []
                for href in re.findall(r'href=["\']([^"\']+)["\']', html):
                    href_lower = href.lower()
                    if any(p in href_lower for p in CANDIDATE_LINK_PATTERNS):
                        links_found.append(href[:120])

                fetch_results[edition_id] = {
                    'url': url,
                    'http_status': resp.status_code,
                    'content_type': content_type[:80],
                    'size_bytes': size,
                    'signals': signals,
                    'candidate_links': links_found[:10],
                    'has_inscription_signal': bool(signals),
                    'has_candidate_links': bool(links_found),
                }

                signal_str = ', '.join(signals[:5]) if signals else 'none'
                self.stdout.write(
                    f'    HTTP={resp.status_code} size={size}B signals=[{signal_str}] '
                    f'links={len(links_found)}'
                )

            except Exception as exc:
                fetch_results[edition_id] = {
                    'url': url, 'http_status': 'ERROR', 'error': str(exc)[:80],
                    'signals': [], 'candidate_links': [], 'has_inscription_signal': False,
                    'has_candidate_links': False,
                }
                self.stdout.write(f'    ERROR: {exc}')

            time.sleep(RATE_LIMIT)

        self._print_summary(targets, by_source, fetch_results)
        self._print_promising_patterns(fetch_results)

    def _print_summary(self, targets, by_source, fetch_results):
        self.stdout.write('\n=== SUMMARY ===')
        self.stdout.write(f'Total analysed: {len(targets)}')

        total_200 = sum(1 for r in fetch_results.values() if r.get('http_status') == 200)
        total_signals = sum(1 for r in fetch_results.values() if r.get('has_inscription_signal'))
        total_links = sum(1 for r in fetch_results.values() if r.get('has_candidate_links'))

        if fetch_results:
            self.stdout.write(f'HTTP 200: {total_200}/{len(fetch_results)}')
            self.stdout.write(f'Has inscription signals: {total_signals}')
            self.stdout.write(f'Has candidate links: {total_links}')

        self.stdout.write('\n--- By source ---')
        for src, items in sorted(by_source.items()):
            edition_ids = {t['edition'].id for t in items}
            src_200 = sum(1 for eid, r in fetch_results.items()
                          if eid in edition_ids and r.get('http_status') == 200)
            src_sig = sum(1 for eid, r in fetch_results.items()
                          if eid in edition_ids and r.get('has_inscription_signal'))
            src_links = sum(1 for eid, r in fetch_results.items()
                            if eid in edition_ids and r.get('has_candidate_links'))
            has_entries = sum(1 for t in items if t['entries_source_url'])
            limitation = get_limitation(src)

            self.stdout.write(
                f'  {src}: targets={len(items)} HTTP200={src_200} '
                f'signals={src_sig} links={src_links} entries_url={has_entries}'
            )
            self.stdout.write(f'    limitation: {limitation[:100]}')

    def _print_promising_patterns(self, fetch_results):
        self.stdout.write('\n--- Promising URL patterns ---')
        all_links = []
        for r in fetch_results.values():
            if r.get('has_candidate_links'):
                all_links.extend(r.get('candidate_links', []))

        from collections import Counter
        # Show most common patterns
        prefixes = Counter()
        for link in all_links:
            import re
            m = re.match(r'(https?://[^/]+/[^/]+)', link)
            if m:
                prefixes[m.group(1)] += 1

        for pattern, count in prefixes.most_common(10):
            self.stdout.write(f'  {count}x {pattern}')

        if not all_links:
            self.stdout.write('  None found — sources likely do not expose public entry lists.')
