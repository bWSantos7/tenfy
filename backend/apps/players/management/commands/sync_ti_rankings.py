"""
Import Tênis Integrado public rankings into the local ExternalPlayerRanking
catalogue.

Usage:
  python manage.py sync_ti_rankings --source=cbt --year=2026
  python manage.py sync_ti_rankings --all
  python manage.py sync_ti_rankings --ranking-id 1419 --source cbt
  python manage.py sync_ti_rankings --source=cbt --dry-run
  python manage.py sync_ti_rankings --discover            # list candidate ranking ids

Behaviour:
  * Creates or updates rows (no duplicates — keyed by source/ranking/category/
    athlete/season).
  * Respects a polite delay between HTTP requests (--delay, default 2s).
  * Registers per-ranking errors without aborting the whole run.
  * --dry-run lists what would be imported without touching the DB or persisting.

Federation rankings (FPT/SP, FCT) are localised by login on TI; configure their
ranking ids in ti_ranking_sources.py once confirmed. --discover helps list them.
"""
import logging
import time
import unicodedata
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.players.models import ExternalPlayerRanking
from apps.players.parsers import TenisScrapeError
from apps.players import ti_rankings as tir
from apps.players.ti_ranking_sources import (
    TI_RANKING_SOURCES, get_source_rankings, get_source_federation, all_sources,
)

logger = logging.getLogger('apps.players.ti_rankings')


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    return normalized.encode('ascii', 'ignore').decode('ascii').lower().strip()


def _parse_corte_date(label: str):
    """corte labels look like '25/05/2026'."""
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(label.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


class Command(BaseCommand):
    help = 'Import public Tênis Integrado rankings into the local athlete catalogue.'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, help='Source key: cbt, fpt, fct…')
        parser.add_argument('--all', action='store_true', help='Import every configured source.')
        parser.add_argument('--ranking-id', type=str, help='Import a single TI ranking id (requires --source for labelling).')
        parser.add_argument('--year', '--season', type=int, dest='year', help='Season/year tag for imported rows (default: current year).')
        parser.add_argument('--delay', type=float, default=tir.REQUEST_DELAY_SECONDS, help='Seconds between HTTP requests.')
        parser.add_argument('--limit', type=int, default=0, help='Max categories per ranking (0 = all).')
        parser.add_argument('--dry-run', action='store_true', help='List targets without writing.')
        parser.add_argument('--discover', action='store_true', help='List candidate ranking ids from TI navigation and exit.')
        parser.add_argument(
            '--federations-juvenil', action='store_true',
            help='Import every federation ranking named infantojuvenil/juvenil/juniors '
                 '(source=fed), restricted to the 12–18 age categories.',
        )
        parser.add_argument('--federacao', type=str, default='0', help='Federation id filter for --federations-juvenil (default 0 = all).')

    # ── discovery ────────────────────────────────────────────────────────────
    def handle_discover(self, delay):
        import re
        from bs4 import BeautifulSoup
        sess = tir._session()
        self.stdout.write('Discovering ranking ids from TI navigation…\n')
        for t, name in [(2, 'Confederação (CBT)'), (3, 'Federações'), (4, 'Clubes/Academias')]:
            url = f'{tir._BASE_URL}/new_ranking/index_ranking/{t}'
            try:
                r = sess.get(url, timeout=tir._TIMEOUT)
                r.encoding = 'utf-8'
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  [{name}] fetch error: {exc}'))
                continue
            soup = BeautifulSoup(r.text, 'lxml')
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n== {name} =='))
            seen = set()
            for a in soup.find_all('a', href=re.compile(r'ranking_painel_classif/index/\d+')):
                m = re.search(r'index/(\d+)', a['href'])
                rid = m.group(1)
                # The label sits in a sibling text node; grab the nearest non-empty.
                label = ''
                for sib in a.find_all_next(string=True, limit=6):
                    s = tir._clean(sib)
                    if s and 'Ranking' in s:
                        label = s
                        break
                if not label or rid in seen:
                    continue
                seen.add(rid)
                self.stdout.write(f'  ranking_id={rid:<6} {label}')
            time.sleep(delay)

    # ── main ───────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        if options['discover']:
            self.handle_discover(options['delay'])
            return

        year = options.get('year') or timezone.now().year
        delay = options['delay']
        limit = options['limit']
        dry_run = options['dry_run']

        # Build the list of (source, ranking descriptor) to process.
        jobs: list[tuple[str, dict]] = []
        if options.get('federations_juvenil'):
            sess0 = tir._session()
            try:
                discovered = tir.discover_federation_rankings(
                    year, session=sess0, federacao=options['federacao'],
                )
            except TenisScrapeError as exc:
                raise CommandError(f'Could not list federation rankings: {exc}')
            youth = [r for r in discovered if tir.is_youth_ranking_name(r['ranking_name'])]
            self.stdout.write(
                f'Federações: {len(discovered)} rankings, '
                f'{len(youth)} infantojuvenil/juvenil/juniors (categorias 12–18).'
            )
            for r in youth:
                jobs.append((ExternalPlayerRanking.SOURCE_FED, {
                    'ranking_external_id': r['ranking_external_id'],
                    'ranking_name': r['ranking_name'],
                    'federation': r['federation'],
                    'modality': 'tennis',
                    'youth_categories_only': True,
                }))
        elif options.get('ranking_id'):
            source = options.get('source')
            if not source:
                raise CommandError('--ranking-id requires --source for labelling.')
            jobs.append((source, {
                'ranking_external_id': str(options['ranking_id']),
                'ranking_name': '',
                'modality': '',
            }))
        elif options['all']:
            for src in all_sources():
                for r in get_source_rankings(src):
                    jobs.append((src, r))
        elif options.get('source'):
            src = options['source']
            if src not in TI_RANKING_SOURCES:
                raise CommandError(f'Unknown source {src!r}. Known: {", ".join(all_sources())}')
            for r in get_source_rankings(src):
                jobs.append((src, r))
        else:
            raise CommandError('Provide --source, --all, --ranking-id, --federations-juvenil or --discover.')

        if not jobs:
            self.stdout.write(self.style.WARNING(
                'No rankings configured for the requested source(s). '
                'Add confirmed ranking ids to ti_ranking_sources.py '
                '(see `--discover`).'
            ))
            return

        self.stdout.write(f'Season={year} jobs={len(jobs)} dry_run={dry_run}\n')

        totals = {'created': 0, 'updated': 0, 'rows': 0, 'errors': 0, 'rankings': 0}
        sess = tir._session()

        for source, desc in jobs:
            rid = desc['ranking_external_id']
            federation = desc.get('federation') or get_source_federation(source)
            youth_only = desc.get('youth_categories_only', False)
            try:
                idx = tir.fetch_ranking_index(rid, session=sess)
            except TenisScrapeError as exc:
                self.stderr.write(self.style.ERROR(f'  ✗ ranking {rid}: index error: {exc}'))
                totals['errors'] += 1
                continue
            time.sleep(delay)

            categories = idx['categories']
            if youth_only:
                categories = [(c, l) for c, l in categories if tir.is_age_12_18_category(l)]
            if limit:
                categories = categories[:limit]
            corte_val, corte_label = (idx['cortes'][0] if idx['cortes'] else ('', ''))
            corte_date = _parse_corte_date(corte_label)
            totals['rankings'] += 1

            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n[{source}] ranking {rid} "{desc.get("ranking_name") or "?"}" '
                f'— {len(categories)} categoria(s), corte={corte_label or "-"}'
            ))

            for cat_code, cat_label in categories:
                try:
                    entries = tir.fetch_ranking_entries(
                        rid, id_categoria=cat_code, id_corte=corte_val, session=sess,
                    )
                except TenisScrapeError as exc:
                    self.stderr.write(self.style.ERROR(f'    ✗ categoria {cat_code}: {exc}'))
                    totals['errors'] += 1
                    time.sleep(delay)
                    continue

                if dry_run:
                    self.stdout.write(f'    {cat_label}: {len(entries)} atleta(s)')
                    totals['rows'] += len(entries)
                    time.sleep(delay)
                    continue

                for e in entries:
                    defaults = {
                        'player_name': e['player_name'],
                        'player_name_normalized': _normalize_name(e['player_name']),
                        'uf': e['uf'],
                        'age': e['age'],
                        'club': e['club'],
                        'federation': federation,
                        'ranking_name': desc.get('ranking_name', ''),
                        'category_label': cat_label,
                        'modality': desc.get('modality', ''),
                        'position': e['position'],
                        'points': e['points'],
                        'wtn': e['wtn'],
                        'classified_at': corte_date,
                        'source_url': f'{tir.INDEX_URL}/{rid}',
                        'confidence': ExternalPlayerRanking.CONFIDENCE_HIGH,
                        'raw_data': e,
                    }
                    _, created = ExternalPlayerRanking.objects.update_or_create(
                        source=source,
                        ranking_external_id=str(rid),
                        category_code=str(cat_code),
                        ti_player_id=e['ti_player_id'],
                        season=year,
                        defaults=defaults,
                    )
                    totals['created' if created else 'updated'] += 1
                    totals['rows'] += 1

                self.stdout.write(f'    {cat_label}: {len(entries)} atleta(s)')
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. rankings={totals["rankings"]} rows={totals["rows"]} '
            f'created={totals["created"]} updated={totals["updated"]} errors={totals["errors"]}'
        ))
