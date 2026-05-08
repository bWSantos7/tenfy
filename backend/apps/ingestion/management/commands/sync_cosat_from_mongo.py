"""
Management command — sync COSAT data from MongoDB crawler into PostgreSQL.

The COSAT crawler (bWSantos7/crawler.git) runs as a separate Railway service
and writes tournament/player/ranking data to a dedicated MongoDB. This command
reads that MongoDB and normalizes the data into Tenfy PostgreSQL using the
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
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ingestion.connectors.cosat_mongo import _PLAYER_CATEGORY_FIELDS

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
        parser.add_argument(
            '--debug-sample', action='store_true', default=False,
            help=(
                'Print raw field inventory of 3 player docs (no personal data). '
                'Use to discover which fields contain category. '
                'Implies --dry-run.'
            ),
        )

    def handle(self, *args, **options):
        dry_run: bool = options['dry_run']
        limit: int = options['limit']
        tournament_id: str = options['tournament_id'].strip()
        import_entries: bool = options['import_entries']
        debug_sample: bool = options['debug_sample']

        # --debug-sample always implies dry-run
        if debug_sample:
            dry_run = True

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
            if debug_sample:
                self._run_debug_sample(conn, tournament_id)
            else:
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
                raw = t_data.get('_raw', {})
                venue = t_data.get('venue') or {}
                city_val = venue.get('city', '')
                org_val = raw.get('organization', '')
                logger.error(
                    'sync_cosat: tournament %s (%s) failed: %s | '
                    'venue.city=%d chars, venue.name=%d chars',
                    cosat_id, title[:60], str(exc)[:300],
                    len(city_val), len(org_val),
                )
                self.stdout.write(
                    self.style.ERROR(
                        f'  ERROR [{cosat_id}] {title[:60]}: {str(exc)[:200]}'
                        f' [city={len(city_val)}ch org={len(org_val)}ch]'
                    )
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
                # Track which category field was used (for transparency)
                category_field_hits: dict[str, int] = {}

                for player in conn.iter_players(tournament_id=tid):
                    player_name = (player.get('player_name') or '').strip()
                    category_text = (player.get('category_text') or '').strip()
                    category_field = player.get('_category_field', '')

                    # COSAT fallback: when no category in any field, use "Geral do torneio"
                    # This is an explicit architectural decision, not invented data.
                    # The notes field records the warning for audit transparency.
                    if not category_text:
                        player['category_text'] = 'Geral do torneio'
                        player['_category_field'] = '_fallback'
                        player['confidence'] = 'medium'
                        player['_cosat_category_fallback'] = True
                        category_text = 'Geral do torneio'

                    if category_field:
                        category_field_hits[category_field] = (
                            category_field_hits.get(category_field, 0) + 1
                        )

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

                if dry_run:
                    self.stdout.write(
                        f'  [DRY-RUN] [{tid}] edition_id={edition_id}: '
                        f'would sync {player_count} players, rejected {rejected}'
                    )
                else:
                    self.stdout.write(
                        f'  [{tid}]: created={player_count} '
                        f'rejected={rejected} errors={errors}'
                    )
                if rejected:
                    self.stdout.write(
                        f'    {rejected} using "Geral do torneio" fallback '
                        f'(no category found in any of: '
                        + ', '.join(_PLAYER_CATEGORY_FIELDS[:6]) + '… '
                        + '— run --debug-sample to inspect raw fields)'
                    )
                if category_field_hits:
                    self.stdout.write(
                        f'    category extracted from: '
                        + ', '.join(f'{f}({n})' for f, n in category_field_hits.items())
                    )

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

        # Build notes: record fallback warning when category was not in source
        notes = player.get('notes', '')
        if player.get('_cosat_category_fallback'):
            notes = (
                'COSAT não expõe categoria na listagem de players; '
                'atleta importado em "Geral do torneio".'
            )

        defaults = {
            'player_name': player_name,
            'ranking_position': player.get('ranking_position'),
            'payment_status': player.get('payment_status', 'unknown'),
            'removed_or_replaced': player.get('removed_or_replaced', False),
            'replacement_reason': player.get('replacement_reason', ''),
            'source_url': player.get('source_url', ''),
            'confidence': player.get('confidence', 'medium'),
            'player_country_name': player.get('player_country_name', ''),
            'player_country_code': player.get('player_country_code', ''),
            'notes': notes,
            'raw_data': player.get('_raw', {}),
        }

        return FederationEntry.objects.update_or_create(
            edition_id=edition_id,
            category_text=category_text,
            player_external_id=player_external_id,
            source=FederationEntry.SOURCE_COSAT,
            defaults=defaults,
        )

    def _run_debug_sample(self, conn, tournament_id: str):
        """
        Print safe field inventory of 3 player docs + tournament events.
        Does NOT print player names, DOB, or personal data.
        Used to discover which MongoDB field contains the category.
        Always dry-run — no DB writes.
        """
        from apps.ingestion.connectors.cosat_mongo import player_field_inventory

        if not conn.is_available():
            self.stdout.write(self.style.ERROR('MongoDB unreachable.'))
            return

        self.stdout.write(self.style.SUCCESS('\n=== DEBUG SAMPLE (dry-run, no writes) ==='))

        # ── Tournament events (categories) ───────────────────────────────────
        if tournament_id:
            self.stdout.write(f'\n--- Tournament raw doc [{tournament_id}] ---')
            t_doc = conn.sample_tournament_raw(tournament_id)
            if t_doc:
                events = t_doc.get('events') or []
                self.stdout.write(f'  name: {t_doc.get("name", "?")}')
                self.stdout.write(f'  events ({len(events)}):')
                for ev in events[:10]:
                    self.stdout.write(f'    {ev}')
                self.stdout.write(f'  top-level keys: {sorted(t_doc.keys())}')
            else:
                self.stdout.write(f'  Tournament not found in MongoDB.')

        # ── Player field inventory ────────────────────────────────────────────
        self.stdout.write(f'\n--- Player field inventory (3 samples, no personal data) ---')
        samples = conn.sample_players_raw(tournament_id=tournament_id, n=5)

        if not samples:
            self.stdout.write('  No player documents found for this tournament.')
            self.stdout.write(
                '  Check tournamentId field in Mongo matches the cosatId exactly.'
            )
            return

        self.stdout.write(f'  Found {len(samples)} sample(s):')
        all_keys: Counter = Counter()
        all_category_values: dict[str, set] = {}

        for i, doc in enumerate(samples):
            inventory = player_field_inventory(doc)
            self.stdout.write(f'\n  Sample [{i+1}]:')
            for key, val in sorted(inventory.items()):
                self.stdout.write(f'    {key}: {val}')
            # Track which category-candidate fields have values
            for field in _PLAYER_CATEGORY_FIELDS:
                val = doc.get(field)
                if val:
                    all_category_values.setdefault(field, set()).add(str(val)[:60])
            all_keys.update(inventory.keys())

        # ── Category field analysis ───────────────────────────────────────────
        self.stdout.write('\n--- Category field analysis ---')
        self.stdout.write(f'  Checked fields (in priority order): {_PLAYER_CATEGORY_FIELDS}')
        self.stdout.write('\n  Fields with values in samples:')
        found_any = False
        for field in _PLAYER_CATEGORY_FIELDS:
            if field in all_category_values:
                vals = list(all_category_values[field])[:3]
                self.stdout.write(f'    ✓ {field}: {vals}')
                found_any = True
        if not found_any:
            self.stdout.write(
                '  NONE of the candidate fields have values in these samples.\n'
                '  The category might be:\n'
                '    - in the Tournament.events[] and NOT stored on the player doc\n'
                '    - under a different field name (check "top-level keys" above)\n'
                '    - absent from the crawler schema\n'
                '  → Consider enriching the crawler to store event/category on each player.'
            )

        # ── All unique keys found across samples ─────────────────────────────
        self.stdout.write('\n--- All keys present in player samples ---')
        self.stdout.write(f'  {sorted(all_keys.keys())}')

        self.stdout.write(self.style.WARNING(
            '\nDEBUG SAMPLE complete — no data written.'
        ))
