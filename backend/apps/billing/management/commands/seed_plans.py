"""
Seed Individual / Família plans with features.

Usage:
    python manage.py seed_plans
    python manage.py seed_plans --reset          # wipe and recreate
    python manage.py seed_plans --deactivate-old # deactivate legacy free/pro/elite plans
"""
from django.core.management.base import BaseCommand
from apps.billing.models import Feature, Plan, PlanFeature

LEGACY_SLUGS = ['free', 'pro', 'elite']

FEATURES = [
    ('tournament_creation',     'Criação de torneios',            'Criar e gerenciar torneios'),
    ('profile_highlight',       'Destaque no perfil',             'Perfil destacado nos resultados de busca'),
    ('advanced_stats',          'Estatísticas avançadas',         'Acesso a estatísticas e análises detalhadas'),
    ('ranking_access',          'Acesso ao ranking',              'Visualizar rankings regionais e nacionais'),
    ('unlimited_registrations', 'Acesso completo aos torneios',   'Acesse e acompanhe todos os torneios disponíveis'),
    ('advanced_filters',        'Filtros avançados e favoritos',  'Filtros por nível, distância, tipo e lista de favoritos'),
    ('alerts_reminders',        'Alertas e lembretes',            'Receba alertas de prazo, chaves publicadas e alterações'),
    ('priority_support',        'Suporte prioritário',            'Atendimento com prioridade via e-mail e chat'),
    ('match_priority',          'Prioridade em partidas',         'Prioridade na formação de duplas e partidas'),
    ('premium_tournaments',     'Torneios premium',               'Acesso a torneios exclusivos premium'),
    ('export_data',             'Exportar dados',                 'Exportar histórico e estatísticas em CSV/PDF'),
    ('coach_module',            'Módulo de treinador',            'Ferramentas de gestão de atletas para coaches'),
    ('multi_profile',           'Múltiplos perfis',               'Gerenciar múltiplos perfis de jogo'),
    ('watchlist_unlimited',     'Watchlist ilimitada',            'Acompanhar torneios sem limite de quantidade'),
    ('family_members',          'Perfis de família',              'Adicionar dependentes ao plano Família'),
]

# Individual plan features — exactly as shown in the product image
_INDIVIDUAL_FEATURES = {
    'unlimited_registrations': None,  # Acesso completo aos torneios
    'advanced_filters':        None,  # Filtros avançados e favoritos
    'alerts_reminders':        None,  # Alertas e lembretes
    'priority_support':        None,  # Suporte prioritário
}

# Família includes all Individual features plus family member management
_FAMILIA_FEATURES = {
    **_INDIVIDUAL_FEATURES,
    'family_members': None,           # Perfis de família (até 2 responsáveis + 3 dependentes)
}

# Tester plan: all features enabled, free during beta period
_TESTER_FEATURES = {
    **_FAMILIA_FEATURES,
    'multi_profile':           None,
    'watchlist_unlimited':     None,
}

PLANS = [
    {
        'name': 'Tester',
        'slug': 'tester',
        'price_monthly': '0.00',
        'price_yearly':  '0.00',
        'description': 'Acesso completo durante o período beta. Todas as funcionalidades liberadas.',
        'highlight_label': 'Período beta',
        'display_order': 0,
        'max_members': 4,
        'features': _TESTER_FEATURES,
    },
    {
        'name': 'Individual',
        'slug': 'individual',
        'price_monthly': '49.90',
        'price_yearly':  '499.00',
        'description': 'Para o atleta que quer centralizar seus torneios e evoluir no tênis.',
        'highlight_label': '',
        'display_order': 1,
        'max_members': 1,
        'features': _INDIVIDUAL_FEATURES,
    },
    {
        'name': 'Família',
        'slug': 'familia',
        'price_monthly': '89.90',
        'price_yearly':  '899.00',
        'description': 'Até 2 responsáveis e 3 dependentes na mesma assinatura.',
        'highlight_label': 'Mais popular',
        'display_order': 2,
        'max_members': 5,
        'max_responsibles': 2,
        'features': _FAMILIA_FEATURES,
    },
]


class Command(BaseCommand):
    help = 'Seed billing plans (Individual e Família) and features'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete ALL plans and features before seeding')
        parser.add_argument('--deactivate-old', action='store_true', help='Deactivate legacy free/pro/elite plans')

    def handle(self, *args, **options):
        if options['reset']:
            PlanFeature.objects.all().delete()
            Plan.objects.all().delete()
            Feature.objects.all().delete()
            self.stdout.write(self.style.WARNING('Billing data wiped.'))

        if options['deactivate_old']:
            deactivated = Plan.objects.filter(slug__in=LEGACY_SLUGS, is_active=True).update(is_active=False)
            if deactivated:
                self.stdout.write(self.style.WARNING(f'Deactivated {deactivated} legacy plan(s): {LEGACY_SLUGS}'))

        # Upsert features
        feature_map = {}
        for code, name, description in FEATURES:
            f, created = Feature.objects.update_or_create(
                code=code,
                defaults={'name': name, 'description': description},
            )
            feature_map[code] = f
            action = 'Created' if created else 'Updated'
            self.stdout.write(f'  {action} feature: {code}')

        # Upsert plans — use a shallow copy so the module-level PLANS constant is not mutated
        for plan_data in PLANS:
            plan_data = dict(plan_data)  # copy before pop to preserve the original
            features = plan_data.pop('features')
            plan, created = Plan.objects.update_or_create(
                slug=plan_data['slug'],
                defaults=plan_data,
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(
                f'  {action} plan: {plan.slug} '
                f'(max_members={plan.max_members}, max_responsibles={plan.max_responsibles})'
            )

            desired_feature_ids = []
            for code, limit in features.items():
                pf, _ = PlanFeature.objects.update_or_create(
                    plan=plan,
                    feature=feature_map[code],
                    defaults={'limit': limit},
                )
                desired_feature_ids.append(pf.pk)

            removed, _ = PlanFeature.objects.filter(plan=plan).exclude(pk__in=desired_feature_ids).delete()
            if removed:
                self.stdout.write(f'  Removed {removed} orphaned feature(s) from plan: {plan.slug}')

        self.stdout.write(self.style.SUCCESS('Plans seeded: Tester, Individual e Família.'))
        self.stdout.write('Run with --deactivate-old to disable legacy free/pro/elite plans.')
