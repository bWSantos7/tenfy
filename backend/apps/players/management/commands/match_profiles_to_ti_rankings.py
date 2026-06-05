"""
Backfill: try to link existing Tenfy profiles (and dependents) to a Tênis
Integrado profile id using the imported ranking catalogue + federation entries.

Usage:
  python manage.py match_profiles_to_ti_rankings --dry-run
  python manage.py match_profiles_to_ti_rankings              # link + queue sync
  python manage.py match_profiles_to_ti_rankings --no-sync    # link only

Rules (mirroring the zero-click bootstrap):
  * Only links when a *unique* high-confidence name match is found.
  * Ambiguous names (more than one candidate TI id) are reported, never linked.
  * Profiles that already carry a TI id are skipped.
"""
import logging

from django.core.management.base import BaseCommand

from apps.players.models import PlayerProfile
from apps.players.parsers import extract_ti_id
from apps.players.tasks import _find_ti_external_id_for_profile

logger = logging.getLogger('apps.players')


class Command(BaseCommand):
    help = 'Link existing profiles to Tênis Integrado ids using imported rankings.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report matches without writing.')
        parser.add_argument('--no-sync', action='store_true', help='Link without queueing data sync.')
        parser.add_argument('--profile-id', type=int, help='Restrict to a single profile.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        no_sync = options['no_sync']

        qs = PlayerProfile.objects.all()
        if options.get('profile_id'):
            qs = qs.filter(pk=options['profile_id'])

        linked = skipped = ambiguous = no_match = 0

        for profile in qs.iterator():
            existing, _ = extract_ti_id(profile.external_ids or {})
            if existing:
                skipped += 1
                continue

            source, external_id = _find_ti_external_id_for_profile(profile)
            if not external_id:
                no_match += 1
                continue

            self.stdout.write(
                f'  Profile #{profile.pk} {profile.display_name!r} → {source}={external_id}'
            )
            linked += 1

            if dry_run:
                continue

            ext_ids = dict(profile.external_ids or {})
            ext_ids[source] = external_id
            profile.external_ids = ext_ids
            profile.save(update_fields=['external_ids', 'updated_at'])

            if not no_sync:
                try:
                    from apps.players.tasks import sync_ti_data_task
                    sync_ti_data_task.apply_async(args=[profile.pk], countdown=5)
                except Exception as exc:
                    logger.warning('Could not queue sync for profile %s: %s', profile.pk, exc)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. linked={linked} skipped(existing)={skipped} '
            f'no_match={no_match} dry_run={dry_run}'
        ))
