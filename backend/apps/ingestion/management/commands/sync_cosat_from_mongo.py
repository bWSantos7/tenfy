"""
Management command — sync COSAT data from MongoDB crawler into PostgreSQL.

The COSAT crawler (bWSantos7/crawler.git) runs as a separate Railway service
and writes tournament/player/ranking data to a dedicated MongoDB. This command
reads that MongoDB and normalizes the data into Tennis Hub PostgreSQL using the
existing persistence layer.

Usage:
    python manage.py sync_cosat_from_mongo              # dry-run (safe default)
    python manage.py sync_cosat_from_mongo --no-dry-run # commit changes
    python manage.py sync_cosat_from_mongo --limit 20
    python manage.py sync_cosat_from_mongo --tournament-id <cosatId>
    python manage.py sync_cosat_from_mongo --no-dry-run --import-entries
    python manage.py sync_cosat_from_mongo --import-entries  # dry-run entries

NOTES on rankings:
  Rankings from the 'rankingentries' MongoDB collection are NOT imported in
  this command. They represent standalone COSAT rankings (not per-tournament
  inscriptions) and lack a reliable tournament FK to link to TournamentEdition.
  Tracking issue: import rankings when COSAT provides a tournament linkage.

Rules:
  - Default is dry-run. Pass --no-dry-run to commit changes.
  - Idempotent: upserts by external_id / unique_together constraint.
  - Never deletes data.
  - Aborts cleanly if COSAT_MONGO_ENABLED=False or MongoDB unreachable.
  - No secrets in logs or stdout (URIs sanitized).
  - conn.close() always called in finally.
"""
import logging
import unicodedata
import re as _re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger('apps.ingestion.cosat_mongo')

_COSAT_BASE_URL = 'https://cosat.tournamentsoftware.com'
_CONNECTOR_KEY = 'cosat_mongo'


def _slug(text: str) -> str:
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:40]


class Command(BaseCommand):
    help = 'Sync COSAT tournaments and player entries from MongoDB crawler into PostgreSQL'

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
            '--tournament-id', type=str, default='',
            help='Sync only this COSAT tournament ID (cosatId field in MongoDB)',
        )
        parser.add_argument(
            '--import-entries', action='store_true', default=False,
            help='Also sync player entries for each tournament',
        )

    def handle(self, *args, **options):
        dry_run: bool = options['dry_run']
        limit: int = options['limit']
        tournament_id: str = options['tournament_id'].strip()
        import_entries: bool = options['import_entries']

        # Validate limit
        if limit < 0:
            raise CommandError('--limit must be >= 0 (0 = all)')
        limit = min(limit, 1000) if limit else 0

        if not getattr(settings, 'COSAT_MONGO_ENABLED', False):
            self.stdout.write(self.style.WARNING(
                'COSAT_MONGO_ENABLED is False or not set. '
                'Set COSAT_MONGO_ENABLED=true in Railway backend variables. '
                'No changes made.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\n=== sync_cosat_from_mongo '
            f'dry_run={dry_run} limit={limit or "all"} '
            f'tournament_id={tournament_id or "all"} '
            f'import_entries={import_entries} ==='
        ))

        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()

        try:
            self._run(conn, dry_run, limit, tournament_id, import_entries)
        finally:
            conn.close()

    def _run(self, conn, dry_run, limit, tournament_id, import_entries):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        from apps.tournaments.models import TournamentEdition

        if not conn.is_available():
            self.stdout.write(self.style.ERROR(
                'MongoDB is not reachable. '
                'Check COSAT_MONGO_URL and Railway private networking. '
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
            'entries_rejected': 0,  # bad category / missing player_name
            'entries_error': 0,
        }

        # edition_map: cosatId → TournamentEdition.id (built during tournament sync)
        edition_map: dict[str, int] = {}

        # ── Step 1: Tournaments ──────────────────────────────────────────────
        self.stdout.write('\n--- Tournaments ---')
        data_source = self._get_or_create_datasource(dry_run)

        for t_data in conn.iter_tournaments(limit=limit, cosat_id=tournament_id):
            raw = t_data.get('_raw', {})
            cosat_id = raw.get('cosatId', '')
            title = t_data.get('title', '')[:60]
            ext_id = t_data.get('external_id', '')

            if dry_run:
                self.stdout.write(
                    f'  [DRY-RUN] would upsert: [{cosat_id}] {title}'
                )
                # Pre-populate edition_map from existing editions for entries dry-run
                existing = TournamentEdition.objects.filter(
                    external_id=ext_id
                ).first()
                if existing:
                    edition_map[cosat_id] = existing.id
                    self.stdout.write(
                        f'    → exists in PostgreSQL as edition_id={existing.id}'
                    )
                stats['tournaments_skipped'] += 1
                continue

            try:
                edition, created = self._upsert_tournament(t_data, data_source)
                if edition:
                    edition_map[cosat_id] = edition.id
                verb = 'created' if created else 'updated'
                self.stdout.write(f'  {verb}: [{cosat_id}] {title}')
                if created:
                    stats['tournaments_created'] += 1
                else:
                    stats['tournaments_updated'] += 1
            except Exception as exc:
                logger.error('sync_cosat: tournament %s failed: %s', cosat_id, exc)
                self.stdout.write(
                    self.style.ERROR(f'  ERROR [{cosat_id}]: {exc}')
                )
                stats['tournaments_error'] += 1

        # ── Step 2: Entries ──────────────────────────────────────────────────
        if import_entries:
            self.stdout.write('\n--- Player Entries ---')
            self.stdout.write(
                '  NOTE: rankings from rankingentries collection are NOT imported '
                '(no reliable tournament FK — see command docstring).'
            )

            # Build target list: cosatIds from this run's edition_map
            # PLUS any existing PostgreSQL COSAT editions matching the filter
            target_ids = self._resolve_entry_targets(
                tournament_id, edition_map, conn, dry_run
            )

            for tid, edition_id in target_ids.items():
                player_count = 0
                rejected = 0
                errors = 0

                for player in conn.iter_players(tournament_id=tid):
                    player_name = (player.get('player_name') or '').strip()
                    category_text = (player.get('category_text') or '').strip()

                    # Reject entries without category — never invent "Não informado"
                    if not category_text:
                        logger.debug(
                            'sync_cosat: skipping player "%s" for tournament %s — '
                            'no category_text in MongoDB document',
                            player_name, tid,
                        )
                        stats['entries_rejected'] += 1
                        rejected += 1
                        continue

                    if dry_run:
                        stats['entries_skipped'] += 1
                        player_count += 1
                        continue

                    try:
                        _, created = self._upsert_entry(player, edition_id)
                        if created:
                            stats['entries_created'] += 1
                        else:
                            stats['entries_updated'] += 1
                    except Exception as exc:
                        logger.error(
                            'sync_cosat: entry %s/%s failed: %s',
                            player_name, tid, exc,
                        )
                        stats['entries_error'] += 1
                        errors += 1

                msg = (
                    f'  [DRY-RUN] [{tid}] edition_id={edition_id}: '
                    f'would sync {player_count} players'
                    if dry_run
                    else f'  [{tid}]: created={player_count} rejected={rejected} errors={errors}'
                )
                if rejected:
                    msg += f' ({rejected} rejected — no category)'
                self.stdout.write(msg)

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

    def _resolve_entry_targets(
        self, tournament_id: str, edition_map: dict, conn, dry_run: bool
    ) -> dict[str, int]:
        """
        Build a {cosatId: edition_id} map for entry sync.

        Combines:
        1. Editions created/updated in this run (already in edition_map).
        2. Pre-existing PostgreSQL editions with source=cosat matching the filter.
           Looks up by external_id='cosat:{cosatId}' — the format used by
           _normalize_tournament() and TournamentPersister.upsert().
        """
        from apps.tournaments.models import TournamentEdition

        result = dict(edition_map)  # start with this-run editions

        # For --tournament-id: also look up existing editions not in this run
        if tournament_id and tournament_id not in result:
            ext_id = f'cosat:{tournament_id}'
            existing = TournamentEdition.objects.filter(external_id=ext_id).first()
            if existing:
                result[tournament_id] = existing.id
                self.stdout.write(
                    f'  Found existing edition for [{tournament_id}]: '
                    f'edition_id={existing.id}'
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'  SKIP entries for [{tournament_id}]: '
                        'no matching edition in PostgreSQL. '
                        'Run without --import-entries first to sync the tournament.'
                    )
                )

        # Without --tournament-id: also include existing COSAT editions not in this run
        if not tournament_id:
            existing_cosat = TournamentEdition.objects.filter(
                external_id__startswith='cosat:'
            ).exclude(id__in=result.values())
            for ed in existing_cosat:
                cosat_id = ed.external_id.removeprefix('cosat:')
                if cosat_id not in result:
                    result[cosat_id] = ed.id

        return result

    def _get_or_create_datasource(self, dry_run: bool):
        """Return the COSAT MongoDB DataSource, creating it with all required fields."""
        if dry_run:
            return None

        from apps.sources.models import DataSource, Organization

        org, _ = Organization.objects.get_or_create(
            name='COSAT',
            defaults={
                'short_name': 'COSAT',
                'type': Organization.TYPE_CONFEDERATION,
                'website_url': _COSAT_BASE_URL,
                'description': (
                    'Confederación Sudamericana de Tenis. '
                    'Dados sincronizados via crawler MongoDB interno.'
                ),
                'is_active': True,
            },
        )

        data_source, _ = DataSource.objects.get_or_create(
            connector_key=_CONNECTOR_KEY,
            defaults={
                'organization': org,
                'source_name': 'COSAT MongoDB',
                'slug': 'cosat-mongo',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': _COSAT_BASE_URL,
                'enabled': True,
                'priority': 'P1',
                'legal_notes': (
                    'Dados lidos de MongoDB exclusivo do serviço crawler COSAT '
                    '(bWSantos7/crawler.git, Railway). '
                    'O crawler coleta apenas dados públicos de '
                    'https://cosat.tournamentsoftware.com. '
                    'Nenhum scraping ocorre no backend principal.'
                ),
                'config_json': {
                    'mongo_db_setting': 'COSAT_MONGO_DB',
                    'collections': {
                        'tournaments': 'COSAT_MONGO_COLLECTION_TOURNAMENTS',
                        'players': 'COSAT_MONGO_COLLECTION_ENTRIES',
                        'rankings': 'COSAT_MONGO_COLLECTION_RANKINGS',
                    },
                },
            },
        )
        return data_source

    def _upsert_tournament(self, data: dict, data_source):
        """
        Upsert a TournamentEdition via TournamentPersister.
        Returns (TournamentEdition | None, created: bool).
        """
        from apps.ingestion.persistence import TournamentPersister
        from apps.ingestion.models import IngestionRun
        from apps.tournaments.models import TournamentEdition

        run = IngestionRun.objects.create(
            data_source=data_source,
            triggered_by='sync_cosat_from_mongo',
            status=IngestionRun.STATUS_RUNNING,
        )

        clean_data = {k: v for k, v in data.items() if k != '_raw'}

        try:
            ext_id = data['external_id']
            before_ids = set(
                TournamentEdition.objects.filter(external_id=ext_id)
                .values_list('id', flat=True)
            )
            persister = TournamentPersister(data_source, run)
            persister.upsert(clean_data)

            run.status = IngestionRun.STATUS_SUCCESS
            run.save(update_fields=['status', 'updated_at'])

            edition = TournamentEdition.objects.filter(external_id=ext_id).first()
            after_ids = set(
                TournamentEdition.objects.filter(external_id=ext_id)
                .values_list('id', flat=True)
            )
            created = bool(after_ids - before_ids)
            return edition, created

        except Exception:
            run.status = IngestionRun.STATUS_FAILED
            run.save(update_fields=['status', 'updated_at'])
            raise

    def _upsert_entry(self, player: dict, edition_id: int):
        """
        Upsert a FederationEntry. Rejects entries with empty category_text.
        unique_together: (edition, category_text, player_external_id, source)
        Returns (FederationEntry, created: bool).
        """
        from apps.registrations.models import FederationEntry

        player_name = (player.get('player_name') or '').strip()
        category_text = (player.get('category_text') or '').strip()
        player_external_id = (player.get('player_external_id') or '').strip()

        if not player_name:
            raise ValueError('player_name is required')

        # RULE: never invent category. Callers must pre-filter empty categories.
        if not category_text:
            raise ValueError(
                f'player "{player_name}" has no category_text — '
                'entry rejected to avoid inventing data'
            )

        if not player_external_id:
            player_external_id = (
                f'cosat:{_slug(player_name)}:{_slug(category_text)}'
            )

        defaults = {
            'player_name': player_name,
            'ranking_position': player.get('ranking_position'),
            'payment_status': player.get('payment_status', 'unknown'),
            'removed_or_replaced': player.get('removed_or_replaced', False),
            'replacement_reason': player.get('replacement_reason', ''),
            'source_url': player.get('source_url', ''),
            'confidence': player.get('confidence', 'medium'),
            'raw_data': player.get('_raw', {}),
        }

        return FederationEntry.objects.update_or_create(
            edition_id=edition_id,
            category_text=category_text,
            player_external_id=player_external_id,
            source=FederationEntry.SOURCE_COSAT,
            defaults=defaults,
        )
