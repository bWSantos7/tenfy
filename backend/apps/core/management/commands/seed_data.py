"""
Seed initial data:
- Organizations (CBT, FPT, FMT, etc.)
- DataSources (connector keys wired)
- PlayerCategories (fpt_class, fpt_age, cbt_age, seniors, kids, open)
- RuleSets / RuleVersions with basic active versions

Usage: python manage.py seed_data
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import Organization, DataSource
from apps.players.models import PlayerCategory
from apps.eligibility.models import RuleSet, RuleVersion


class Command(BaseCommand):
    help = 'Seed baseline data (organizations, sources, categories, rulesets).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing seed rows first')

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get('reset'):
            self.stdout.write('Resetting seed tables...')
            DataSource.objects.all().delete()
            Organization.objects.all().delete()
            PlayerCategory.objects.all().delete()
            RuleSet.objects.all().delete()

        self._seed_organizations()
        self._seed_data_sources()
        self._seed_categories()
        self._seed_rulesets()
        self.stdout.write(self.style.SUCCESS('Seed concluído.'))

    # ---------- Organizations ----------
    def _seed_organizations(self):
        orgs = [
            dict(
                name='Confederação Brasileira de Tênis',
                short_name='CBT', type=Organization.TYPE_CONFEDERATION,
                website_url='https://cbt-tenis.com.br',
                description='Entidade máxima do tênis no Brasil.',
            ),
            dict(
                name='Federação Paulista de Tênis',
                short_name='FPT', type=Organization.TYPE_FEDERATION, state='SP',
                website_url='https://www.tenispaulista.com.br',
                description='Federação estadual de São Paulo.',
            ),
            dict(
                name='Federação Mineira de Tênis',
                short_name='FMT', type=Organization.TYPE_FEDERATION, state='MG',
                website_url='https://www.fmtenis.com.br',
            ),
            dict(
                name='Federação Gaúcha de Tênis',
                short_name='FGT', type=Organization.TYPE_FEDERATION, state='RS',
                website_url='https://fgt.com.br',
            ),
            dict(
                name='Tênis Integrado',
                short_name='TenisIntegrado', type=Organization.TYPE_PLATFORM,
                website_url='https://www.tenisintegrado.com.br',
            ),
            dict(
                name='LetzPlay',
                short_name='LetzPlay', type=Organization.TYPE_PLATFORM,
                website_url='https://letzplay.me',
            ),
        ]
        for o in orgs:
            Organization.objects.update_or_create(name=o['name'], defaults=o)
        self.stdout.write(f'  organizations: {Organization.objects.count()}')

    # ---------- Data sources ----------
    def _seed_data_sources(self):
        cbt = Organization.objects.get(short_name='CBT')
        fpt = Organization.objects.get(short_name='FPT')

        sources = [
            dict(
                organization=cbt,
                source_name='CBT - Público',
                slug='cbt-public',
                source_type=DataSource.SOURCE_TYPE_HTML,
                base_url='https://cbt-tenis.com.br',
                connector_key='cbt_public',
                fetch_schedule_cron='0 */2 * * *',
                priority='P0',
                enabled=True,
                legal_notes='Dados factuais de torneios; link oficial preservado em todas as fichas.',
            ),
            dict(
                organization=fpt,
                source_name='FPT - Área Pública',
                slug='fpt-public',
                source_type=DataSource.SOURCE_TYPE_HTML,
                base_url='https://sisfpt.com.br/area-publica/torneios/abertos',
                connector_key='fpt_public',
                fetch_schedule_cron='0 */2 * * *',
                priority='P0',
                enabled=True,
            ),
        ]
        for s in sources:
            DataSource.objects.update_or_create(slug=s['slug'], defaults=s)
        self.stdout.write(f'  data sources: {DataSource.objects.count()}')

    # ---------- Player categories ----------
    def _seed_categories(self):
        rows = []

        # FPT classes 1..5, M and F
        for lvl in [1, 2, 3, 4, 5]:
            for gender in ['M', 'F']:
                code = f'{lvl}{gender}'
                rows.append(dict(
                    taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
                    code=code, label_ptbr=f'{lvl}ª Classe {"Masculino" if gender == "M" else "Feminino"}',
                    gender_scope=gender,
                    class_level=lvl,
                ))

        # CBT / FPT youth ages: 10, 12, 14, 16, 18
        for age in [10, 12, 14, 16, 18]:
            for gender in ['M', 'F']:
                code = f'{age}{gender}'
                rows.append(dict(
                    taxonomy=PlayerCategory.TAXONOMY_CBT_AGE,
                    code=code, label_ptbr=f'Sub-{age} {"Masculino" if gender == "M" else "Feminino"}',
                    gender_scope=gender, min_age=age, max_age=age,
                ))

        # Kids tiers (red / orange / green / yellow)
        for tier, (mn, mx) in [('Kids 8', (6, 8)), ('Kids 10', (8, 10))]:
            rows.append(dict(
                taxonomy=PlayerCategory.TAXONOMY_KIDS,
                code=tier.replace(' ', ''), label_ptbr=tier,
                gender_scope='*', min_age=mn, max_age=mx,
            ))

        # Seniors 30+ .. 85+
        for mn in [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]:
            for gender in ['M', 'F']:
                code = f'{mn}+{gender}'
                rows.append(dict(
                    taxonomy=PlayerCategory.TAXONOMY_SENIORS,
                    code=code, label_ptbr=f'{mn}+ {"Masculino" if gender == "M" else "Feminino"}',
                    gender_scope=gender, min_age=mn,
                ))

        # Open
        for gender in ['M', 'F']:
            rows.append(dict(
                taxonomy=PlayerCategory.TAXONOMY_OPEN,
                code=f'Open{gender}', label_ptbr=f'Open {"Masculino" if gender == "M" else "Feminino"}',
                gender_scope=gender,
            ))

        for r in rows:
            PlayerCategory.objects.update_or_create(
                taxonomy=r['taxonomy'], code=r['code'], gender_scope=r.get('gender_scope', '*'),
                defaults=r,
            )
        self.stdout.write(f'  player categories: {PlayerCategory.objects.count()}')

    # ---------- Rulesets ----------
    def _seed_rulesets(self):
        cbt = Organization.objects.get(short_name='CBT')
        fpt = Organization.objects.get(short_name='FPT')

        rs_fpt, _ = RuleSet.objects.update_or_create(
            organization=fpt, scope='fpt_abertos',
            defaults={'name': 'FPT Torneios Abertos', 'description': 'Regras de classes e idades FPT'}
        )
        RuleVersion.objects.update_or_create(
            ruleset=rs_fpt, version='2026.1',
            defaults={
                'effective_from': date(2026, 1, 1),
                'status': RuleVersion.STATUS_ACTIVE,
                'source_url': 'https://www.tenispaulista.com.br/wp-content/uploads/2026/02/FPT_-_Regulamento-Torneios-Abertos-2026.pdf',
                'notes': 'Classes 1..5; pode inscrever-se na própria classe ou uma acima. Seniors ascensão unidirecional permitida.',
            },
        )

        rs_cbt, _ = RuleSet.objects.update_or_create(
            organization=cbt, scope='cbt_juvenil',
            defaults={'name': 'CBT Circuito Infantojuvenil', 'description': 'Idade por ano civil.'}
        )
        RuleVersion.objects.update_or_create(
            ruleset=rs_cbt, version='2026.1',
            defaults={
                'effective_from': date(2026, 1, 1),
                'status': RuleVersion.STATUS_ACTIVE,
                'source_url': 'https://tenis-integrado-prod.s3.amazonaws.com/sync-prod/id22798/anexos/anexo_1773928563.pdf',
                'notes': 'Idade = ano_atual - ano_nascimento (regra do ano civil).',
            },
        )
        self.stdout.write(f'  rulesets: {RuleSet.objects.count()}')
