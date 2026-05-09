"""
Seed DataSource records for all supported circuits.

Usage:
    python manage.py seed_sources
    python manage.py seed_sources --reset   # drop and recreate all
"""
from datetime import date
from django.core.management.base import BaseCommand
from apps.sources.models import Organization, DataSource


CURRENT_YEAR = date.today().year

ORGS = [
    {'name': 'Federação Paulista de Tênis', 'short_name': 'FPT', 'type': 'federation'},
    {'name': 'Confederação Brasileira de Tênis', 'short_name': 'CBT', 'type': 'confederation'},
    {'name': 'Federação Catarinense de Tênis', 'short_name': 'FCT', 'type': 'federation'},
    {'name': 'Federação Baiana de Tênis', 'short_name': 'FBT', 'type': 'federation'},
    {'name': 'Confederación Sudamericana de Tenis', 'short_name': 'COSAT', 'type': 'confederation'},
    {'name': 'International Tennis Federation', 'short_name': 'ITF', 'type': 'confederation'},
    {'name': 'Universal Tennis Rating', 'short_name': 'UTR', 'type': 'platform'},
]

SOURCES = [
    {
        'org_short': 'FPT',
        'source_name': 'FPT Calendário Público',
        'connector_key': 'fpt_public',
        'source_type': 'html',
        'base_url': 'https://fpt.com.br/Torneio/Calendario/',
        'fetch_schedule_cron': '0 */2 * * *',  # every 2 hours
        'priority': 'P0',
        'enabled': True,
        'config_json': {'years': [CURRENT_YEAR]},
        'legal_notes': 'Public calendar page. Scraping respects rate limits.',
    },
    {
        'org_short': 'CBT',
        'source_name': 'CBT / Tênis Integrado API',
        'connector_key': 'cbt_public',
        'source_type': 'json',
        'base_url': 'https://api.tennistool.tenisintegrado.com',
        'fetch_schedule_cron': '30 */2 * * *',  # every 2 hours, offset 30m
        'priority': 'P0',
        'enabled': True,
        'config_json': {'year': CURRENT_YEAR},
        'legal_notes': 'Public JSON API used by official CBT website.',
    },
    {
        'org_short': 'CBT',
        'source_name': 'CBT Juvenil / Tênis Integrado API',
        'connector_key': 'cbt_youth',
        'source_type': 'json',
        'base_url': 'https://api.tennistool.tenisintegrado.com',
        'fetch_schedule_cron': '45 */2 * * *',  # every 2 hours, offset 45m
        'priority': 'P0',
        'enabled': True,
        'config_json': {},
        'legal_notes': 'Public JSON API — CBT youth/junior circuit (system=3). Same API as cbt_public.',
    },
    {
        'org_short': 'FCT',
        'source_name': 'FCT / Tênis Integrado',
        'connector_key': 'fct_public',
        'source_type': 'html',
        'base_url': 'https://www.tenisintegrado.com.br',
        'fetch_schedule_cron': '0 */8 * * *',  # every 8 hours
        'priority': 'P1',
        'enabled': True,
        'config_json': {},
        'legal_notes': 'Public HTML pages. Scraping respects robots.txt and rate limits.',
    },
    {
        'org_short': 'FBT',
        'source_name': 'FBT Calendário Público',
        'connector_key': 'fbt_public',
        'source_type': 'html',
        'base_url': 'https://www.fbt.com.br',
        'fetch_schedule_cron': '0 */12 * * *',  # every 12 hours
        'priority': 'P2',
        'enabled': False,  # DISABLED: no public calendar API confirmed. Enable after n8n workflow + targets identified.
        'config_json': {},
        'legal_notes': 'DISABLED — no confirmed public API/calendar endpoint. Pending n8n assisted import workflow.',
    },
    {
        'org_short': 'COSAT',
        'source_name': 'COSAT TournamentSoftware',
        'connector_key': 'cosat_public',
        'source_type': 'json',
        'base_url': 'https://cosat.tournamentsoftware.com',
        'fetch_schedule_cron': '0 2 * * *',  # daily at 2am
        'priority': 'P1',
        'enabled': False,  # DISABLED: robots.txt disallows /sport/ /tournament/ /ranking/ for all crawlers.
        # API endpoint /api/tournament/search returns 404 (unavailable as of 2026-04-28).
        # Re-enable only after obtaining official API partnership with COSAT/TournamentSoftware.
        # Manual import available via /api/registrations/federation/bulk-import/
        'config_json': {'year': CURRENT_YEAR},
        'legal_notes': (
            'DISABLED — robots.txt (User-agent:*) disallows /sport/ /tournament/ /ranking/ /player/. '
            'Search API returns 404. Requires official API partnership with COSAT/TournamentSoftware '
            'for re-activation. Manual admin import is available as an alternative.'
        ),
    },
    {
        'org_short': 'ITF',
        'source_name': 'ITF Junior Circuit',
        'connector_key': 'itf_junior',
        'source_type': 'json',
        'base_url': 'https://www.itftennis.com',
        'fetch_schedule_cron': '0 3 * * *',  # daily at 3am
        'priority': 'P1',
        'enabled': True,
        'config_json': {'year': CURRENT_YEAR, 'circuit': 'JT', 'zone': 'SAM'},
        'legal_notes': 'ITF public calendar API. Official API partnership recommended for production.',
    },
    {
        'org_short': 'UTR',
        'source_name': 'UTR Sports Brazil',
        'connector_key': 'utr_public',
        'source_type': 'json',
        'base_url': 'https://api.utrsports.net',
        'fetch_schedule_cron': '0 4 * * *',  # daily at 4am
        'priority': 'P2',
        'enabled': True,
        'config_json': {'year': CURRENT_YEAR, 'country': 'BRA'},
        'legal_notes': 'UTR public events API. API key required for full access.',
    },
]


class Command(BaseCommand):
    help = 'Seed DataSource records for all supported circuits (idempotent)'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete and recreate all sources')

    def handle(self, *args, **options):
        if options['reset']:
            DataSource.objects.all().delete()
            Organization.objects.all().delete()
            self.stdout.write(self.style.WARNING('Existing sources and orgs deleted.'))

        # Upsert organizations
        org_map = {}
        for org_data in ORGS:
            org, created = Organization.objects.update_or_create(
                short_name=org_data['short_name'],
                defaults={
                    'name': org_data['name'],
                    'type': org_data['type'],
                },
            )
            org_map[org_data['short_name']] = org
            action = 'Created' if created else 'Updated'
            self.stdout.write(f'  {action} organization: {org_data["short_name"]}')

        # Upsert data sources
        for src_data in SOURCES:
            org = org_map.get(src_data['org_short'])
            if not org:
                self.stdout.write(self.style.WARNING(f'  Org {src_data["org_short"]} not found — skipping.'))
                continue

            import re, unicodedata
            def _slug(text):
                s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
                return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:200]

            ds, created = DataSource.objects.update_or_create(
                connector_key=src_data['connector_key'],
                defaults={
                    'organization': org,
                    'slug': _slug(src_data['connector_key']),
                    'source_name': src_data['source_name'],
                    'source_type': src_data['source_type'],
                    'base_url': src_data['base_url'],
                    'fetch_schedule_cron': src_data['fetch_schedule_cron'],
                    'priority': src_data['priority'],
                    'enabled': src_data['enabled'],
                    'config_json': src_data['config_json'],
                    'legal_notes': src_data['legal_notes'],
                },
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(f'  {action} source: {src_data["source_name"]} ({src_data["connector_key"]})')

        total = DataSource.objects.count()
        self.stdout.write(self.style.SUCCESS(f'Done. {total} data source(s) in database.'))
