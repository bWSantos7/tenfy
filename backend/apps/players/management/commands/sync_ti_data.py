"""
Management command to force re-sync Tênis Integrado data for player profiles.

Usage:
  python manage.py sync_ti_data                   # sync all profiles with a TI ID
  python manage.py sync_ti_data --profile-id 5    # sync a specific profile
  python manage.py sync_ti_data --reset-empty     # only sync profiles with empty cache
  python manage.py sync_ti_data --dry-run         # list targets without syncing
"""
import logging

from django.core.management.base import BaseCommand

from apps.players.models import PlayerProfile
from apps.players.parsers import extract_ti_id, TenisScrapeError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Force re-sync Tênis Integrado results and rankings for player profiles.'

    def add_arguments(self, parser):
        parser.add_argument('--profile-id', type=int, help='Sync a single profile by ID.')
        parser.add_argument('--reset-empty', action='store_true', help='Only sync profiles with empty cache.')
        parser.add_argument('--dry-run', action='store_true', help='List targets without syncing.')

    def handle(self, *args, **options):
        from django.utils import timezone

        profile_id = options.get('profile_id')
        reset_empty = options.get('reset_empty')
        dry_run = options.get('dry_run')

        qs = PlayerProfile.objects.all()
        if profile_id:
            qs = qs.filter(pk=profile_id)

        targets = []
        for profile in qs:
            ti_id, source = extract_ti_id(profile.external_ids or {})
            if not ti_id:
                continue
            if reset_empty and (profile.ti_results_cache or profile.ti_rankings_cache):
                continue
            targets.append((profile, ti_id, source))

        self.stdout.write(f'Found {len(targets)} profile(s) to sync.')

        if dry_run:
            for profile, ti_id, source in targets:
                self.stdout.write(
                    f'  Profile #{profile.pk} {profile.display_name!r} '
                    f'ti_id={ti_id} source={source} '
                    f'results={len(profile.ti_results_cache or [])} '
                    f'rankings={len(profile.ti_rankings_cache or [])}'
                )
            return

        from apps.players.views import _sync_ti_data_inline

        ok = 0
        errors = 0
        for profile, ti_id, source in targets:
            try:
                _sync_ti_data_inline(profile, ti_id)
                profile.refresh_from_db(fields=['ti_results_cache', 'ti_rankings_cache', 'ti_sync_error'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Profile #{profile.pk} {profile.display_name!r}: '
                        f'{len(profile.ti_results_cache or [])} results, '
                        f'{len(profile.ti_rankings_cache or [])} rankings'
                    )
                )
                if profile.ti_sync_error:
                    self.stdout.write(self.style.WARNING(f'    Warning: {profile.ti_sync_error}'))
                ok += 1
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f'  ✗ Profile #{profile.pk}: {exc}')
                )
                errors += 1

        self.stdout.write(f'\nDone. OK={ok} Errors={errors}')
