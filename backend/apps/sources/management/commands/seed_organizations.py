"""
Seed core organizations (CBT, FPT, COSAT, ITF, UTR, FMT) and their data source stubs.

Usage:
    python manage.py seed_organizations
"""
from django.core.management.base import BaseCommand
from apps.sources.models import Organization, DataSource

ORGANIZATIONS = [
    {
        'name': 'Confederação Brasileira de Tênis',
        'short_name': 'CBT',
        'type': Organization.TYPE_CONFEDERATION,
        'website_url': 'https://www.cbt.org.br',
        'state': '',
        'description': 'Confederação nacional que organiza o circuito brasileiro, incluindo o circuito infantojuvenil e kids.',
    },
    {
        'name': 'Federação Paulista de Tênis',
        'short_name': 'FPT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://www.tenispaulista.com.br',
        'state': 'SP',
        'description': 'Federação estadual de São Paulo, com maior densidade de torneios abertos no país.',
    },
    {
        'name': 'Confederação Sulamericana de Tênis',
        'short_name': 'COSAT',
        'type': Organization.TYPE_CONFEDERATION,
        'website_url': 'https://cosat.tournamentsoftware.com',
        'state': '',
        'description': 'Organização sulamericana de tênis, responsável pelo circuito juvenil sul-americano (14–18 anos). Elegibilidade: COSAT Member Nation + ranking COSAT/ITF.',
    },
    {
        'name': 'International Tennis Federation',
        'short_name': 'ITF',
        'type': Organization.TYPE_CONFEDERATION,
        'website_url': 'https://www.itftennis.com',
        'state': '',
        'description': 'Federação internacional de tênis. Organiza o circuito juvenil ITF Juniors (14+ anos) e o World Tennis Tour adulto.',
    },
    {
        'name': 'Universal Tennis Rating',
        'short_name': 'UTR',
        'type': Organization.TYPE_PLATFORM,
        'website_url': 'https://www.utrsports.net',
        'state': '',
        'description': 'Plataforma de rating universal para tênis. Organiza torneios baseados em UTR rating.',
    },
    {
        'name': 'Federação Mineira de Tênis',
        'short_name': 'FMT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://www.fmtenis.com.br',
        'state': 'MG',
        'description': 'Federação estadual de Minas Gerais.',
    },
    {
        'name': 'Federação Carioca de Tênis',
        'short_name': 'FCT',
        'type': Organization.TYPE_FEDERATION,
        'website_url': 'https://fct.com.br',
        'state': 'RJ',
        'description': 'Federação estadual do Rio de Janeiro.',
    },
]

DATA_SOURCES = [
    {
        'org_short': 'FPT',
        'source_name': 'FPT – Área pública de torneios abertos',
        'slug': 'fpt-public-tournaments',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://sisfpt.com.br/area-publica/torneios/abertos',
        'connector_key': 'fpt_public',
        'fetch_schedule_cron': '0 */4 * * *',
        'priority': 'P0',
        'legal_notes': 'Área pública do sistema FPT. Dados acessíveis sem autenticação.',
    },
    {
        'org_short': 'FPT',
        'source_name': 'FPT – Regulamento Torneios Abertos 2026 (PDF)',
        'slug': 'fpt-regulamento-2026',
        'source_type': DataSource.SOURCE_TYPE_PDF,
        'base_url': 'https://www.tenispaulista.com.br/wp-content/uploads/2026/02/FPT_-_Regulamento-Torneios-Abertos-2026.pdf',
        'connector_key': 'fpt_regulation_pdf',
        'fetch_schedule_cron': '0 8 * * 1',
        'priority': 'P0',
        'legal_notes': 'Regulamento oficial público da FPT 2026. Define regras de categoria, classe, elegibilidade.',
    },
    {
        'org_short': 'CBT',
        'source_name': 'CBT – Regulamento Infantojuvenil 2026 (PDF)',
        'slug': 'cbt-infantojuvenil-regulamento-2026',
        'source_type': DataSource.SOURCE_TYPE_PDF,
        'base_url': 'https://tenis-integrado-prod.s3.amazonaws.com/sync-prod/id22798/anexos/anexo_1773928563.pdf',
        'connector_key': 'cbt_youth_regulation_pdf',
        'fetch_schedule_cron': '0 8 * * 1',
        'priority': 'P0',
        'legal_notes': 'Regulamento oficial público CBT Infantojuvenil 2026. Define elegibilidade formal (CPF/federação), regra de idade por ano civil.',
    },
    {
        'org_short': 'CBT',
        'source_name': 'CBT – Tênis Integrado (torneios)',
        'slug': 'cbt-tenis-integrado',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://www.tenisintegrado.com.br/new_torneio/index_tournament/2',
        'connector_key': 'cbt_tenis_integrado',
        'fetch_schedule_cron': '0 */6 * * *',
        'priority': 'P1',
        'legal_notes': 'Plataforma operacional CBT. Risco de bloqueio; usar com moderação. Buscar parceria.',
        'enabled': False,
    },
    {
        'org_short': 'COSAT',
        'source_name': 'COSAT – Tournament Software (calendário)',
        'slug': 'cosat-tournament-software',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://cosat.tournamentsoftware.com',
        'connector_key': 'cosat_tournament_software',
        'fetch_schedule_cron': '0 */12 * * *',
        'priority': 'P1',
        'legal_notes': 'Calendário público COSAT. Juvenil sulamericano (14-18 anos).',
        'enabled': False,
    },
    {
        'org_short': 'ITF',
        'source_name': 'ITF – Juniors Calendar',
        'slug': 'itf-juniors-calendar',
        'source_type': DataSource.SOURCE_TYPE_JSON,
        'base_url': 'https://www.itftennis.com/en/tournament-calendar/juniors-calendar/',
        'connector_key': 'itf_juniors',
        'fetch_schedule_cron': '0 */12 * * *',
        'priority': 'P1',
        'legal_notes': 'Calendário público ITF Juniors. Elegibilidade: mínimo 14 anos.',
        'enabled': False,
    },
    {
        'org_short': 'UTR',
        'source_name': 'UTR Sports – Calendário de eventos',
        'slug': 'utr-sports-events',
        'source_type': DataSource.SOURCE_TYPE_HTML,
        'base_url': 'https://www.utrsports.net',
        'connector_key': 'utr_sports',
        'fetch_schedule_cron': '0 */12 * * *',
        'priority': 'P2',
        'legal_notes': 'Plataforma UTR. Verificar política de scraping.',
        'enabled': False,
    },
]


class Command(BaseCommand):
    help = 'Seed core organizations (CBT, FPT, COSAT, ITF, UTR, FMT) and data source stubs'

    def handle(self, *args, **options):
        org_map: dict[str, Organization] = {}

        for data in ORGANIZATIONS:
            obj, created = Organization.objects.get_or_create(
                name=data['name'],
                defaults={k: v for k, v in data.items() if k != 'name'},
            )
            if not created:
                for k, v in data.items():
                    if k != 'name':
                        setattr(obj, k, v)
                obj.save()
            org_map[obj.short_name] = obj
            label = 'criada' if created else 'atualizada'
            self.stdout.write(f'  {label}: {obj}')

        self.stdout.write(self.style.SUCCESS(f'\n{len(ORGANIZATIONS)} organizações processadas.'))

        created_sources = 0
        for ds_data in DATA_SOURCES:
            org = org_map.get(ds_data['org_short'])
            if not org:
                self.stdout.write(self.style.WARNING(f'  Org não encontrada: {ds_data["org_short"]}'))
                continue
            defaults = {
                'organization': org,
                'source_name': ds_data['source_name'],
                'source_type': ds_data['source_type'],
                'base_url': ds_data['base_url'],
                'connector_key': ds_data['connector_key'],
                'fetch_schedule_cron': ds_data.get('fetch_schedule_cron', '0 * * * *'),
                'priority': ds_data.get('priority', 'P2'),
                'legal_notes': ds_data.get('legal_notes', ''),
                'enabled': ds_data.get('enabled', True),
            }
            _, created = DataSource.objects.get_or_create(
                slug=ds_data['slug'],
                defaults=defaults,
            )
            if created:
                created_sources += 1
                self.stdout.write(f'  fonte criada: {ds_data["source_name"]}')

        self.stdout.write(self.style.SUCCESS(f'{created_sources} fonte(s) criada(s).'))
