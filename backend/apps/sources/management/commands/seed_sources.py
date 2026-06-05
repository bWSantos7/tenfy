"""Seeds Organizations and DataSources for piloto integrations."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import Organization, DataSource


ORGANIZATIONS = [
    {
        'name': 'Confederacao Brasileira de Tenis',
        'short_name': 'CBT',
        'type': Organization.TYPE_CONFEDERATION,
        'website_url': 'https://cbt-tenis.com.br',
        'state': '',
        'description': 'Confederacao Brasileira de Tenis - entidade nacional.',
    },
    {
        # Accented canonical name — must match apps.sources.federations so the
        # profile picker and ingestion converge on a single org per UF (no dup).
        'name': 'Federação Paulista de Tênis',
        'short_name': 'FPT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://fpt.tenisintegrado.com.br',
        'state': 'SP',
    },
    {
        'name': 'Federação Mineira de Tênis',
        'short_name': 'FMT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://www.fmtenis.com.br',
        'state': 'MG',
    },
    {
        'name': 'Federação Catarinense de Tênis',
        'short_name': 'FCT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://fct.org.br',
        'state': 'SC',
    },
    {
        'name': 'Tenis Integrado',
        'short_name': 'TI',
        'type': Organization.TYPE_PLATFORM,
        'website_url': 'https://www.tenisintegrado.com.br',
    },
    {
        'name': 'LetzPlay',
        'short_name': 'LZP',
        'type': Organization.TYPE_PLATFORM,
        'website_url': 'https://letzplay.me',
    },
    {
        'name': 'Universal Tennis Rating',
        'short_name': 'UTR',
        'type': Organization.TYPE_PLATFORM,
        'website_url': 'https://app.utrsports.net',
        'description': 'Plataforma UTR. Torneios infantojuvenis do Brasil via API v2 (conta autenticada).',
    },
    {
        'name': 'Federação Baiana de Tênis',
        'short_name': 'FBT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://fbt.com.br',
        'state': 'BA',
        'description': (
            'Federacao Baiana de Tenis. '
            'Listas de inscritos acessadas via workflow n8n (importacao assistida). '
            'Sem conector automatico de calendario — torneios importados manualmente ou via admin.'
        ),
    },
]


DATA_SOURCES = [
    {
        'org_short': 'CBT',
        'source_name': 'CBT - Tournaments Central',
        'slug': 'cbt-public',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://cbt-tenis.com.br',
        'connector_key': 'cbt_public',
        'fetch_schedule_cron': '0 */2 * * *',
        'priority': 'P0',
        'config_json': {
            'sections': ['youth', 'professional', 'beachtennis', 'wheelchair', 'seniors', 'kids'],
        },
    },
    {
        'org_short': 'FPT',
        'source_name': 'FPT (SP) - Tennis Tool API',
        'slug': 'fpt-sp-tennistool',
        'source_type': DataSource.SOURCE_TYPE_JSON,
        'base_url': 'https://api.tennistool.tenisintegrado.com/tournaments/tournament/getTournamentDepartmentList',
        'connector_key': 'fpt_sp_public',
        'fetch_schedule_cron': '15 */2 * * *',
        'priority': 'P0',
        'config_json': {},
    },
    {
        'org_short': 'FCT',
        'source_name': 'FCT - Torneios publicos via Tenis Integrado',
        'slug': 'fct-public',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://www.tenisintegrado.com.br',
        'connector_key': 'fct_public',
        'fetch_schedule_cron': '30 */2 * * *',
        'priority': 'P1',
        'config_json': {
            'site_id': 4183,
            'entity_type': 2,
            'state_id': 24,
            'months_ahead': 5,
        },
    },
    {
        'org_short': 'UTR',
        'source_name': 'UTR Sports – Torneios infantojuvenis (Brasil)',
        'slug': 'utr-public',
        'source_type': DataSource.SOURCE_TYPE_JSON,
        'base_url': 'https://api.utrsports.net/v2/search/events',
        'connector_key': 'utr_public',
        'fetch_schedule_cron': '0 */12 * * *',
        'priority': 'P2',
        # Kept out of the hourly run_all_active_sources sweep; driven by the
        # dedicated sync_utr_task (every 12h) — paging the UTR API is heavy.
        'enabled': False,
        'config_json': {
            'country_code3': 'BRA',
            'youth_only': True,
            'youth_min': 12,
            'youth_max': 18,
            'page_size': 100,
            'max_pages': 60,
        },
        'legal_notes': (
            'API pública de busca de eventos da UTR (v2). Acesso autenticado por conta '
            'própria (env UTR_EMAIL/UTR_PASSWORD) apenas para leitura de torneios e '
            'lista de inscritos públicos do evento. Sem burlar paywall/captcha.'
        ),
    },
    {
        'org_short': 'FBT',
        'source_name': 'FBT - Federacao Baiana de Tenis (importacao assistida)',
        'slug': 'fbt-public',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://fbt.com.br',
        'connector_key': 'fbt_public',
        'fetch_schedule_cron': '',
        'priority': 'P2',
        'enabled': False,  # no public calendar connector yet
        'config_json': {
            'status': 'no_public_calendar',
            'notes': (
                'FBT nao expoe calendario publico de torneios via HTML/API estruturada. '
                'Torneios devem ser cadastrados manualmente via admin ou importados pelo operador. '
                'Listas de inscritos sao obtidas via workflow n8n FBT (importacao assistida). '
                'Habilitado automaticamente quando conector de calendario for implementado.'
            ),
            'parser_available': True,
            'parser_note': 'parse_fbt_entries() disponivel em parsers.py para paginas de inscritos.',
        },
        'legal_notes': (
            'Dados publicos de https://fbt.com.br. '
            'Coleta apenas paginas abertas ao publico. '
            'Sem scraping de areas protegidas, login ou paywall.'
        ),
    },
]


class Command(BaseCommand):
    help = 'Seeds Organizations and DataSources for the MVP pilot.'

    @transaction.atomic
    def handle(self, *args, **options):
        org_by_short = {}
        for entry in ORGANIZATIONS:
            obj, _ = Organization.objects.update_or_create(
                name=entry['name'],
                defaults={k: v for k, v in entry.items() if k != 'name'},
            )
            org_by_short[entry['short_name']] = obj

        for entry in DATA_SOURCES:
            org = org_by_short.get(entry['org_short'])
            if not org:
                self.stderr.write(f'Org {entry["org_short"]} not found, skipping')
                continue
            defaults: dict = {
                'organization': org,
                'source_name': entry['source_name'],
                'source_type': entry['source_type'],
                'base_url': entry['base_url'],
                'connector_key': entry['connector_key'],
                'fetch_schedule_cron': entry.get('fetch_schedule_cron', ''),
                'priority': entry['priority'],
                'config_json': entry['config_json'],
                'enabled': entry.get('enabled', True),
            }
            if entry.get('legal_notes'):
                defaults['legal_notes'] = entry['legal_notes']
            DataSource.objects.update_or_create(slug=entry['slug'], defaults=defaults)

        self.stdout.write(self.style.SUCCESS(
            f'Organizations: {len(ORGANIZATIONS)} | DataSources: {len(DATA_SOURCES)}'
        ))
