"""
Management command — sync ITF tournaments from MongoDB scraper into PostgreSQL.

The ITF scraper runs as a separate Railway service and writes tournament +
acceptance-list data to a MongoDB collection ('itftournaments'). This command
reads that collection and normalizes the data into Tenfy PostgreSQL using the
existing persistence layer (TournamentPersister) and FederationEntry model.

Usage:
    python manage.py sync_itf_from_mongo                     # dry-run (safe default)
    python manage.py sync_itf_from_mongo --no-dry-run        # commit changes
    python manage.py sync_itf_from_mongo --limit 20
    python manage.py sync_itf_from_mongo --slug itf-12345-x
    python manage.py sync_itf_from_mongo --no-dry-run --import-entries

Rules:
  - Default is dry-run. Pass --no-dry-run to commit changes.
  - Idempotent: upserts by external_id / unique_together constraint.
  - Never deletes data (withdrawn players marked removed_or_replaced=True).
  - Aborts cleanly if ITF_MONGO_ENABLED=False or MongoDB unreachable.
  - No secrets in logs (URIs sanitized).
  - conn.close() always called in finally.
"""
import logging
import unicodedata
import re as _re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('apps.ingestion.itf_mongo')

_ITF_BASE_URL = 'https://www.itftennis.com'
_CONNECTOR_KEY = 'itf_mongo'


def _slug(text: str) -> str:
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:40]


class Command(BaseCommand):
    help = 'Sync ITF tournaments and acceptance lists from MongoDB scraper into PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true', default=True,
            help='Preview changes without saving to DB (default: True)',
        )
        parser.add_argument(
            '--no-dry-run', dest='dry_run', action='store_false',
            help='Commit changes to PostgreSQL',
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Max tournaments to process (0 = all)',
        )
        parser.add_argument(
            '--slug', type=str, default='',
            help='Sync only this tournament (slug_externo field in MongoDB)',
        )
        parser.add_argument(
            '--import-entries', action='store_true', default=False,
            help='Also sync player acceptance lists as FederationEntry records',
        )

    def handle(self, *args, **options):
        dry_run: bool = options['dry_run']
        limit: int = options['limit']
        slug: str = options['slug'].strip()
        import_entries: bool = options['import_entries']

        if limit < 0:
            raise CommandError('--limit must be >= 0 (0 = all)')
        limit = min(limit, 1000) if limit else 0

        if not getattr(settings, 'ITF_MONGO_ENABLED', False):
            self.stdout.write(self.style.WARNING(
                'ITF_MONGO_ENABLED is False or not set. '
                'Set ITF_MONGO_ENABLED=true in Railway backend variables. '
                'No changes made.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\n=== sync_itf_from_mongo '
            f'dry_run={dry_run} limit={limit or "all"} '
            f'slug={slug or "all"} '
            f'import_entries={import_entries} ==='
        ))

        from apps.ingestion.connectors.itf_mongo import ItfMongoConnector
        conn = ItfMongoConnector()

        try:
            self._run(conn, dry_run, limit, slug, import_entries)
        finally:
            conn.close()

    def _run(self, conn, dry_run, limit, slug, import_entries):
        from apps.tournaments.models import TournamentEdition

        if not conn.is_available():
            self.stdout.write(self.style.ERROR(
                'MongoDB is not reachable. '
                'Check ITF_MONGO_URL / COSAT_MONGO_URL and Railway connectivity. '
                'No changes made.'
            ))
            return

        stats = {
            'tournaments_created': 0,
            'tournaments_updated': 0,
            'tournaments_skipped': 0,
            'tournaments_error': 0,
            'entries_created': 0,
            'entries_updated': 0,
            'entries_skipped': 0,
            'entries_error': 0,
            'acceptance_list_updated': 0,
        }

        # slug_externo → TournamentEdition.id (built during tournament sync)
        edition_map: dict[str, int] = {}
        # slug_externo → raw inscritos dict (for entries step)
        inscritos_map: dict[str, dict] = {}

        # ── Step 1: Tournaments ──────────────────────────────────────────────
        self.stdout.write('\n--- Tournaments ---')
        data_source = self._get_or_create_datasource(dry_run)

        # Single IngestionRun for the entire sync batch — one per execution, not one per tournament
        batch_run = None if dry_run else self._create_batch_run(data_source)

        for t_data in conn.iter_tournaments(limit=limit, slug_externo=slug):
            raw = t_data.get('_raw', {})
            slug_ext = raw.get('slug_externo', '') or raw.get('key', '')
            title = t_data.get('title', '')[:60]
            ext_id = t_data.get('external_id', '')
            inscritos = t_data.get('_inscritos') or {}

            if dry_run:
                self.stdout.write(f'  [DRY-RUN] would upsert: [{slug_ext}] {title}')
                existing = TournamentEdition.objects.filter(external_id=ext_id).first()
                if existing:
                    edition_map[slug_ext] = existing.id
                    self.stdout.write(
                        f'    → exists in PostgreSQL as edition_id={existing.id}'
                    )
                inscritos_map[slug_ext] = inscritos
                stats['tournaments_skipped'] += 1
                continue

            try:
                edition, created = self._upsert_tournament(t_data, data_source, batch_run)
                if edition:
                    edition_map[slug_ext] = edition.id
                    inscritos_map[slug_ext] = inscritos
                    self._update_acceptance_list(edition, inscritos)
                    stats['acceptance_list_updated'] += 1
                verb = 'created' if created else 'updated'
                self.stdout.write(f'  {verb}: [{slug_ext}] {title}')
                if created:
                    stats['tournaments_created'] += 1
                else:
                    stats['tournaments_updated'] += 1
            except Exception as exc:
                logger.error('sync_itf: tournament %s failed: %s', slug_ext, exc)
                self.stdout.write(self.style.ERROR(
                    f'  ERROR [{slug_ext}] {title}: {str(exc)[:200]}'
                ))
                stats['tournaments_error'] += 1

        if batch_run:
            from apps.ingestion.models import IngestionRun
            from django.utils import timezone as _tz
            batch_run.status = IngestionRun.STATUS_SUCCESS if not stats['tournaments_error'] else IngestionRun.STATUS_PARTIAL
            batch_run.items_fetched = stats['tournaments_created'] + stats['tournaments_updated'] + stats['tournaments_error']
            batch_run.items_created = stats['tournaments_created']
            batch_run.items_updated = stats['tournaments_updated']
            batch_run.finished_at = _tz.now()
            batch_run.save(update_fields=['status', 'items_fetched', 'items_created', 'items_updated', 'finished_at', 'updated_at'])

        # ── Step 2: Player entries (FederationEntry) ─────────────────────────
        if import_entries:
            self.stdout.write('\n--- Player Entries ---')

            # Extend edition_map with existing ITF editions not in this run
            target_map = self._resolve_entry_targets(slug, edition_map)

            for slug_ext, edition_id in target_map.items():
                raw_inscritos = inscritos_map.get(slug_ext)

                # If inscritos not in this run, skip (can't re-read from Mongo here)
                if raw_inscritos is None:
                    if dry_run:
                        stats['entries_skipped'] += 1
                    continue

                from apps.ingestion.connectors.itf_mongo import iter_player_entries
                created_n = updated_n = error_n = skipped_n = 0

                for entry in iter_player_entries(raw_inscritos, slug_ext):
                    if dry_run:
                        skipped_n += 1
                        continue
                    try:
                        _, was_created = self._upsert_entry(entry, edition_id)
                        if was_created:
                            created_n += 1
                        else:
                            updated_n += 1
                    except Exception as exc:
                        logger.error('sync_itf: entry %s/%s failed: %s',
                                     entry.get('player_name'), slug_ext, exc)
                        error_n += 1

                if dry_run:
                    self.stdout.write(
                        f'  [DRY-RUN] [{slug_ext}] edition_id={edition_id}: '
                        f'would sync entries from inscritos'
                    )
                    stats['entries_skipped'] += skipped_n
                else:
                    self.stdout.write(
                        f'  [{slug_ext}]: created={created_n} '
                        f'updated={updated_n} errors={error_n}'
                    )
                    stats['entries_created'] += created_n
                    stats['entries_updated'] += updated_n
                    stats['entries_error'] += error_n

        # ── Report ───────────────────────────────────────────────────────────
        self.stdout.write('\n=== Result ===')
        for key, val in stats.items():
            if val:
                self.stdout.write(f'  {key}: {val}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nDRY-RUN — no data saved. Add --no-dry-run to commit.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nSync complete.'))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_entry_targets(self, slug: str, edition_map: dict) -> dict:
        """Return {slug_externo: edition_id} combining this run + existing ITF editions."""
        from apps.tournaments.models import TournamentEdition

        result = dict(edition_map)

        if slug and slug not in result:
            ext_id = f'itf:{slug}'
            existing = TournamentEdition.objects.filter(external_id=ext_id).first()
            if existing:
                result[slug] = existing.id
            else:
                self.stdout.write(self.style.WARNING(
                    f'  SKIP entries for [{slug}]: no matching edition in PostgreSQL.'
                ))

        if not slug:
            for ed in TournamentEdition.objects.filter(
                external_id__startswith='itf:'
            ).exclude(id__in=result.values()):
                s = ed.external_id.removeprefix('itf:')
                if s not in result:
                    result[s] = ed.id

        return result

    def _get_or_create_datasource(self, dry_run: bool):
        if dry_run:
            return None

        from apps.sources.models import DataSource, Organization

        org, _ = Organization.objects.get_or_create(
            name='International Tennis Federation',
            defaults={
                'short_name': 'ITF',
                'type': Organization.TYPE_CONFEDERATION,
                'website_url': _ITF_BASE_URL,
                'description': (
                    'International Tennis Federation. '
                    'Dados sincronizados via scraper MongoDB interno.'
                ),
                'is_active': True,
            },
        )

        data_source, _ = DataSource.objects.get_or_create(
            connector_key=_CONNECTOR_KEY,
            defaults={
                'organization': org,
                'source_name': 'ITF MongoDB',
                'slug': 'itf-mongo',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': _ITF_BASE_URL,
                'enabled': True,
                'priority': 'P1',
                'legal_notes': (
                    'Dados lidos de MongoDB do serviço scraper ITF (Railway). '
                    'O scraper coleta apenas dados públicos de itftennis.com. '
                    'Nenhum scraping ocorre no backend principal.'
                ),
                'config_json': {
                    'mongo_collection_setting': 'ITF_MONGO_COLLECTION_TOURNAMENTS',
                    'default_collection': 'itftournaments',
                },
            },
        )
        return data_source

    def _create_batch_run(self, data_source):
        """Create a single IngestionRun for the entire sync batch."""
        from apps.ingestion.models import IngestionRun
        from django.utils import timezone
        return IngestionRun.objects.create(
            data_source=data_source,
            triggered_by='sync_itf_from_mongo',
            status=IngestionRun.STATUS_RUNNING,
            started_at=timezone.now(),
        )

    def _upsert_tournament(self, data: dict, data_source, batch_run=None):
        """Upsert TournamentEdition via TournamentPersister using the shared batch run."""
        from apps.ingestion.persistence import TournamentPersister
        from apps.ingestion.models import IngestionRun
        from apps.tournaments.models import TournamentEdition

        clean_data = {k: v for k, v in data.items() if k not in ('_raw', '_inscritos')}

        try:
            ext_id = data['external_id']
            before_ids = set(
                TournamentEdition.objects.filter(external_id=ext_id)
                .values_list('id', flat=True)
            )
            persister = TournamentPersister(data_source, batch_run)
            persister.upsert(clean_data)

            edition = TournamentEdition.objects.filter(external_id=ext_id).first()
            after_ids = set(
                TournamentEdition.objects.filter(external_id=ext_id)
                .values_list('id', flat=True)
            )
            created = bool(after_ids - before_ids)
            return edition, created

        except Exception:
            raise

    def _update_acceptance_list(self, edition, inscritos: dict):
        """Update TournamentEdition.acceptance_list from raw inscritos dict."""
        from apps.ingestion.connectors.itf_mongo import normalize_acceptance_list

        acceptance_list = normalize_acceptance_list(inscritos)
        edition.acceptance_list = acceptance_list
        edition.needs_sync = False
        from django.utils import timezone
        edition.last_synced_at = timezone.now()
        edition.save(update_fields=['acceptance_list', 'needs_sync', 'last_synced_at', 'updated_at'])

    def _upsert_entry(self, entry: dict, edition_id: int):
        """Upsert a FederationEntry. Returns (FederationEntry, created)."""
        from apps.registrations.models import FederationEntry

        player_name = (entry.get('player_name') or '').strip()
        category_text = (entry.get('category_text') or '').strip()
        player_external_id = (entry.get('player_external_id') or '').strip()

        if not player_name:
            raise ValueError('player_name is required')
        if not category_text:
            raise ValueError(f'player "{player_name}" has no category_text — entry rejected')

        defaults = {
            'player_name': player_name,
            'ranking_position': entry.get('ranking_position'),
            'payment_status': entry.get('payment_status', 'unknown'),
            'removed_or_replaced': entry.get('removed_or_replaced', False),
            'replacement_reason': entry.get('replacement_reason', ''),
            'source_url': entry.get('source_url', ''),
            'confidence': entry.get('confidence', 'high'),
            'player_country_name': entry.get('player_country_name', ''),
            'player_country_code': entry.get('player_country_code', ''),
            'raw_data': entry.get('_raw', {}),
        }

        return FederationEntry.objects.update_or_create(
            edition_id=edition_id,
            category_text=category_text,
            player_external_id=player_external_id,
            source=entry.get('source', 'itf'),
            defaults=defaults,
        )
