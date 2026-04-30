"""
Management command — sync COSAT data from MongoDB crawler into PostgreSQL.

The COSAT crawler (bWSantos7/crawler.git) runs as a separate Railway service
and writes tournament/player/ranking data to a dedicated MongoDB. This command
reads that MongoDB and normalizes the data into the Tennis Hub PostgreSQL
(TournamentEdition, FederationEntry) using the existing persistence layer.

Usage:
    python manage.py sync_cosat_from_mongo              # dry-run (safe)
    python manage.py sync_cosat_from_mongo --no-dry-run # actually save
    python manage.py sync_cosat_from_mongo --limit 20
    python manage.py sync_cosat_from_mongo --tournament-id <cosatId>
    python manage.py sync_cosat_from_mongo --import-entries
    python manage.py sync_cosat_from_mongo --no-dry-run --import-entries

Rules:
  - Default is dry-run. Pass --no-dry-run to commit changes.
  - Idempotent: upserts by external_id / unique_together constraint.
  - Never deletes data without explicit flag.
  - Aborts cleanly if COSAT_MONGO_ENABLED=False or MongoDB is unreachable.
  - No secrets in logs or stdout.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger('apps.ingestion.cosat_mongo')

_SOURCE_NAME = 'cosat_mongo'
_SOURCE_LABEL = 'COSAT'
_COSAT_BASE_URL = 'https://cosat.tournamentsoftware.com'


class Command(BaseCommand):
    help = 'Sync COSAT tournaments and entries from MongoDB crawler into PostgreSQL'

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
            help='Sync only this COSAT tournament ID (cosatId field)',
        )
        parser.add_argument(
            '--import-entries', action='store_true', default=False,
            help='Also sync player entries for each tournament',
        )

    def handle(self, *args, **options):
        dry_run: bool = options['dry_run']
        limit: int = min(options['limit'], 500) if options['limit'] else 0
        tournament_id: str = options['tournament_id'].strip()
        import_entries: bool = options['import_entries']

        if not getattr(settings, 'COSAT_MONGO_ENABLED', False):
            self.stdout.write(self.style.WARNING(
                'COSAT_MONGO_ENABLED is False or not set. '
                'Set COSAT_MONGO_ENABLED=true in Railway backend variables to enable. '
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

        if not conn.is_available():
            self.stdout.write(self.style.ERROR(
                'MongoDB is not reachable. '
                'Check COSAT_MONGO_URL and Railway private networking. '
                'No changes made.'
            ))
            return

        if not dry_run:
            total_docs = conn.count_tournaments()
            self.stdout.write(f'MongoDB: {total_docs} tournaments available.')

        stats = {
            'tournaments_created': 0,
            'tournaments_updated': 0,
            'tournaments_skipped': 0,
            'tournaments_error': 0,
            'entries_created': 0,
            'entries_updated': 0,
            'entries_skipped': 0,
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

            if dry_run:
                self.stdout.write(
                    f'  [DRY-RUN] would upsert: [{cosat_id}] {title}'
                )
                stats['tournaments_skipped'] += 1
                continue

            try:
                edition, created = self._upsert_tournament(t_data, data_source)
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

        # ── Step 2: Entries/Players ──────────────────────────────────────────
        if import_entries:
            self.stdout.write('\n--- Entries/Players ---')
            target_ids = [tournament_id] if tournament_id else list(edition_map.keys())

            for tid in target_ids:
                edition_id = edition_map.get(tid)
                if not edition_id and not dry_run:
                    self.stdout.write(
                        f'  SKIP entries for [{tid}]: no edition synced yet '
                        '(run without --import-entries first, or this tournament '
                        'was already in DB)'
                    )
                    continue

                player_count = 0
                for player in conn.iter_players(tournament_id=tid):
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
                        logger.error('sync_cosat: entry %s failed: %s',
                                     player.get('player_name', '?'), exc)
                        stats['entries_error'] += 1

                if dry_run and player_count:
                    self.stdout.write(
                        f'  [DRY-RUN] [{tid}]: would sync {player_count} players'
                    )

        conn.close()

        # ── Report ───────────────────────────────────────────────────────────
        self.stdout.write('\n=== Result ===')
        for key, val in stats.items():
            if val:
                self.stdout.write(f'  {key}: {val}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nDRY-RUN — no data saved. '
                'Add --no-dry-run to commit changes to PostgreSQL.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nSync complete.'))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_create_datasource(self, dry_run: bool):
        """Return the COSAT MongoDB DataSource, creating it if needed."""
        if dry_run:
            return None

        from apps.sources.models import DataSource, Organization

        org, _ = Organization.objects.get_or_create(
            name='COSAT',
            defaults={'short_name': 'COSAT'},
        )
        data_source, _ = DataSource.objects.get_or_create(
            connector_key=_SOURCE_NAME,
            defaults={
                'source_name': 'COSAT MongoDB',
                'base_url': _COSAT_BASE_URL,
                'enabled': True,
                'organization': org,
            },
        )
        return data_source

    def _upsert_tournament(self, data: dict, data_source):
        """
        Upsert a tournament + edition into PostgreSQL via TournamentPersister.

        Returns (TournamentEdition, created: bool).
        """
        from apps.ingestion.persistence import TournamentPersister
        from apps.ingestion.models import IngestionRun
        from apps.tournaments.models import TournamentEdition

        run = IngestionRun.objects.create(
            data_source=data_source,
            triggered_by='sync_cosat_from_mongo',
        )
        persister = TournamentPersister(data_source, run)

        # Strip _raw before passing to persister (not part of connector schema)
        clean_data = {k: v for k, v in data.items() if k != '_raw'}

        # Store raw COSAT metadata in raw_payload via persister (handled internally)
        before_count = TournamentEdition.objects.filter(
            external_id=data['external_id']
        ).count()

        persister.upsert(clean_data)

        run.status = 'completed'
        run.save(update_fields=['status', 'updated_at'])

        edition = TournamentEdition.objects.filter(
            external_id=data['external_id']
        ).first()
        created = (
            TournamentEdition.objects.filter(external_id=data['external_id']).count()
            > before_count
        ) if edition else False

        return edition, created

    def _upsert_entry(self, player: dict, edition_id: int):
        """
        Upsert a FederationEntry row.
        Returns (FederationEntry, created: bool).
        unique_together: (edition, category_text, player_external_id, source)
        """
        from apps.registrations.models import FederationEntry

        player_name = (player.get('player_name') or '').strip()
        category_text = (player.get('category_text') or '').strip()
        player_external_id = (player.get('player_external_id') or '').strip()

        if not player_name:
            raise ValueError('player_name required')

        # Deterministic fallback ID (no registry ID available)
        if not player_external_id:
            import unicodedata
            import re as _re
            def slug(s):
                s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
                return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:40]
            player_external_id = (
                f'cosat:{slug(player_name)}:{slug(category_text or "cat")}'
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
            category_text=category_text or 'Não informado',
            player_external_id=player_external_id,
            source=FederationEntry.SOURCE_COSAT,
            defaults=defaults,
        )
