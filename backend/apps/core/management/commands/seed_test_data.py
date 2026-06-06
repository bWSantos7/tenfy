"""
Seed de dados para testes E2E do Tenfy.

Cria usuários, perfis esportivos, torneios e itens de watchlist
suficientes para executar toda a bateria de testes Playwright.

Uso:
    python manage.py seed_test_data           # cria/atualiza
    python manage.py seed_test_data --reset   # limpa tudo e recria
    python manage.py seed_test_data --show    # mostra credenciais

NÃO usar em produção. Os e-mails usam o domínio @tenfy-test.invalid.
"""
from datetime import date, timedelta, datetime
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()

# ─── Credenciais fixas de teste ──────────────────────────────────────────────
TEST_PLAYER_EMAIL    = 'player@tenfy-test.invalid'
TEST_PLAYER_PASSWORD = 'TestPlayer2026!'

TEST_PARENT_EMAIL    = 'parent@tenfy-test.invalid'
TEST_PARENT_PASSWORD = 'TestParent2026!'

TEST_CHILD1_EMAIL    = 'child1@tenfy-test.invalid'
TEST_CHILD1_PASSWORD = 'TestChild12026!'

TEST_CHILD2_EMAIL    = 'child2@tenfy-test.invalid'
TEST_CHILD2_PASSWORD = 'TestChild22026!'

TODAY = date.today()


class Command(BaseCommand):
    help = 'Cria massa de dados para testes E2E (não usar em produção).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Remove usuários/torneios de teste antes de recriar')
        parser.add_argument('--show', action='store_true',
                            help='Apenas exibe as credenciais de teste')

    def handle(self, *args, **options):
        if options['show']:
            self._show_credentials()
            return

        with transaction.atomic():
            if options['reset']:
                self._reset()

            player   = self._create_player()
            parent   = self._create_parent()
            child1   = self._create_child(TEST_CHILD1_EMAIL, TEST_CHILD1_PASSWORD, 'Ana Silva', 'player')
            child2   = self._create_child(TEST_CHILD2_EMAIL, TEST_CHILD2_PASSWORD, 'Bruno Lima', 'player')

            self._link_parent_child(parent, child1)
            self._link_parent_child(parent, child2)

            profile_player = self._create_profile_tennis(player, 'Jogador Teste', birth_year=2008, state='SP', city='São Paulo')
            profile_child1 = self._create_profile_tennis(child1, 'Ana Silva', birth_year=2012, state='SP', city='Campinas')
            profile_child2 = self._create_profile_beach(child2, 'Bruno Lima', birth_year=2010, state='RJ', city='Rio de Janeiro')

            editions = self._create_tournaments()
            self._create_watchlist_items(player, profile_player, editions)

        self.stdout.write(self.style.SUCCESS('\n✅  Seed de teste concluído.'))
        self._show_credentials()

    # ─── Reset ────────────────────────────────────────────────────────────────
    def _reset(self):
        self.stdout.write('  → limpando dados de teste anteriores...')
        emails = [TEST_PLAYER_EMAIL, TEST_PARENT_EMAIL, TEST_CHILD1_EMAIL, TEST_CHILD2_EMAIL]
        User.objects.filter(email__in=emails).delete()
        from apps.tournaments.models import Tournament
        Tournament.objects.filter(canonical_slug__startswith='test-').delete()
        self.stdout.write('  → limpo.')

    # ─── Usuários ─────────────────────────────────────────────────────────────
    def _create_player(self):
        user, created = User.objects.get_or_create(
            email=TEST_PLAYER_EMAIL,
            defaults=dict(
                full_name='Carlos Jogador',
                role='player',
                email_verified=True,
                is_active=True,
                consent_version='1.0.0',
                consented_at=timezone.now(),
            ),
        )
        user.set_password(TEST_PLAYER_PASSWORD)
        user.save(update_fields=['password'])
        self.stdout.write(f'  player: {user.email} ({"created" if created else "updated"})')
        return user

    def _create_parent(self):
        user, created = User.objects.get_or_create(
            email=TEST_PARENT_EMAIL,
            defaults=dict(
                full_name='Maria Responsável',
                role='parent',
                email_verified=True,
                is_active=True,
                consent_version='1.0.0',
                consented_at=timezone.now(),
            ),
        )
        user.set_password(TEST_PARENT_PASSWORD)
        user.save(update_fields=['password'])
        self.stdout.write(f'  parent: {user.email} ({"created" if created else "updated"})')
        return user

    def _create_child(self, email, password, full_name, role):
        user, created = User.objects.get_or_create(
            email=email,
            defaults=dict(
                full_name=full_name,
                role=role,
                email_verified=True,
                is_active=True,
                consent_version='1.0.0',
                consented_at=timezone.now(),
            ),
        )
        user.set_password(password)
        user.save(update_fields=['password'])
        self.stdout.write(f'  child: {user.email} ({"created" if created else "updated"})')
        return user

    def _link_parent_child(self, parent, child):
        from apps.accounts.models import ParentChild
        link, created = ParentChild.objects.get_or_create(
            parent=parent, child=child,
            defaults={'is_active': True},
        )
        if not link.is_active:
            link.is_active = True
            link.save(update_fields=['is_active'])
        return link

    # ─── Perfis esportivos ────────────────────────────────────────────────────
    def _create_profile_tennis(self, user, display_name, birth_year, state, city):
        from apps.players.models import PlayerProfile
        profile, _ = PlayerProfile.objects.get_or_create(
            user=user, display_name=display_name,
            defaults=dict(
                birth_year=birth_year,
                gender='M',
                home_state=state,
                home_city=city,
                travel_states=[state, 'RJ', 'MG'],
                competitive_level='pro',
                preferred_modality='tennis',
                is_primary=True,
            ),
        )
        self.stdout.write(f'  profile (tennis): {profile.display_name}')
        return profile

    def _create_profile_beach(self, user, display_name, birth_year, state, city):
        from apps.players.models import PlayerProfile
        profile, _ = PlayerProfile.objects.get_or_create(
            user=user, display_name=display_name,
            defaults=dict(
                birth_year=birth_year,
                gender='M',
                home_state=state,
                home_city=city,
                travel_states=[state, 'SP', 'ES'],
                competitive_level='pro',
                preferred_modality='beach_tennis',
                is_primary=True,
            ),
        )
        self.stdout.write(f'  profile (beach): {profile.display_name}')
        return profile

    # ─── Torneios ─────────────────────────────────────────────────────────────
    def _create_tournaments(self):
        from apps.tournaments.models import Tournament, TournamentEdition, Venue
        from apps.sources.models import Organization

        fpt = Organization.objects.filter(short_name='FPT').first()
        cbt = Organization.objects.filter(short_name='CBT').first()

        # Se não existirem orgs, cria minimais
        if not fpt:
            fpt, _ = Organization.objects.get_or_create(
                name='Federação Paulista de Tênis',
                defaults={'short_name': 'FPT', 'type': 'federation', 'state': 'SP'},
            )
        if not cbt:
            cbt, _ = Organization.objects.get_or_create(
                name='Confederação Brasileira de Tênis',
                defaults={'short_name': 'CBT', 'type': 'confederation'},
            )

        specs = [
            # (slug, name, modality, org, state, city, status, start_delta, close_delta, youth)
            ('test-tennis-sp-open',      'Torneio de Tênis SP — Inscrições Abertas',     'tennis',       fpt, 'SP', 'São Paulo',       'open',         30,  7, True),
            ('test-tennis-sp-closing',   'Copa FPT SP — Encerrando em Breve',            'tennis',       fpt, 'SP', 'Campinas',        'closing_soon', 20,  2, True),
            ('test-tennis-rj-open',      'Torneio de Tênis RJ — Aberto',                 'tennis',       cbt, 'RJ', 'Rio de Janeiro',  'open',         25,  5, True),
            ('test-tennis-mg-closed',    'Circuito MG — Inscrições Encerradas',          'tennis',       fpt, 'MG', 'Belo Horizonte',  'closed',       10, -2, True),
            ('test-tennis-sp-finished',  'Copa SP 2025 — Finalizado',                    'tennis',       fpt, 'SP', 'São Paulo',       'finished',   -60,-90, True),
            ('test-beach-rj-open',       'Torneio de Beach Tennis RJ — Aberto',          'beach_tennis', cbt, 'RJ', 'Niterói',         'open',         30,  5, False),
            ('test-beach-sp-open',       'Open de Beach Tennis SP',                      'beach_tennis', cbt, 'SP', 'Santos',          'open',         40, 10, False),
            ('test-beach-es-announced',  'Beach Tennis ES — Anunciado',                  'beach_tennis', cbt, 'ES', 'Vitória',         'announced',    60, 30, False),
            ('test-padel-sp-open',       'Circuito Padel SP — Aberto',                   'padel',        fpt, 'SP', 'São Paulo',       'open',         20,  3, False),
            ('test-tennis-sp-future',    'Copa SP Julho 2026 — Anunciado',               'tennis',       fpt, 'SP', 'Ribeirão Preto',  'announced',    90, 60, True),
        ]

        editions = []
        for slug, name, modality, org, state, city, status_val, start_d, close_d, youth in specs:
            venue, _ = Venue.objects.get_or_create(
                name=f'Clube Teste {city}',
                city=city,
                state=state,
                defaults={'address': f'Rua dos Testes, 100 — {city}/{state}'},
            )
            tournament, _ = Tournament.objects.get_or_create(
                canonical_slug=slug,
                defaults=dict(
                    canonical_name=name,
                    organization=org,
                    modality=modality,
                    circuit='Teste E2E',
                    description=f'Torneio de teste E2E — {modality} — {state}',
                ),
            )
            start = TODAY + timedelta(days=start_d)
            close_dt = timezone.now() + timedelta(days=close_d)
            edition, _ = TournamentEdition.objects.get_or_create(
                tournament=tournament,
                season_year=2026,
                defaults=dict(
                    title=name,
                    start_date=start,
                    end_date=start + timedelta(days=3),
                    entry_open_at=timezone.now() - timedelta(days=30),
                    entry_close_at=close_dt,
                    status=status_val,
                    venue=venue,
                    source_name='Seed E2E',
                    official_source_url='https://www.tennis.app.br',
                    is_published=True,
                    is_youth=youth,
                    base_price_brl=150 if status_val != 'finished' else None,
                    data_confidence='high',
                ),
            )
            editions.append(edition)
            self.stdout.write(f'  edition: [{status_val}] {name[:50]}')

        return editions

    # ─── Watchlist / Resultados ───────────────────────────────────────────────
    def _create_watchlist_items(self, user, profile, editions):
        from apps.watchlist.models import WatchlistItem, TournamentResult

        # Item 1: inscrito declarado (sem resultado)
        item1, _ = WatchlistItem.objects.get_or_create(
            user=user, edition=editions[0],
            defaults=dict(profile=profile, user_status='registered_declared'),
        )
        # Item 2: na agenda (pretendo)
        item2, _ = WatchlistItem.objects.get_or_create(
            user=user, edition=editions[1],
            defaults=dict(profile=profile, user_status='intended'),
        )
        # Item 3: concluído com resultado
        item3, _ = WatchlistItem.objects.get_or_create(
            user=user, edition=editions[4],
            defaults=dict(profile=profile, user_status='registered_declared'),
        )
        TournamentResult.objects.get_or_create(
            watchlist_item=item3,
            defaults=dict(category_played='Sub-14 Masculino', position=2, wins=4, losses=1, notes='Ótima competição!'),
        )
        self.stdout.write(f'  watchlist: 3 itens criados para {user.email}')

    # ─── Mostrar credenciais ──────────────────────────────────────────────────
    def _show_credentials(self):
        self.stdout.write('\n' + '─' * 60)
        self.stdout.write(self.style.SUCCESS('  CREDENCIAIS DE TESTE E2E'))
        self.stdout.write('─' * 60)
        self.stdout.write(f'  Jogador:      {TEST_PLAYER_EMAIL}')
        self.stdout.write(f'  Senha:        {TEST_PLAYER_PASSWORD}')
        self.stdout.write('')
        self.stdout.write(f'  Responsável:  {TEST_PARENT_EMAIL}')
        self.stdout.write(f'  Senha:        {TEST_PARENT_PASSWORD}')
        self.stdout.write('')
        self.stdout.write(f'  Dependente 1: {TEST_CHILD1_EMAIL}')
        self.stdout.write(f'  Senha:        {TEST_CHILD1_PASSWORD}')
        self.stdout.write('')
        self.stdout.write(f'  Dependente 2: {TEST_CHILD2_EMAIL}')
        self.stdout.write(f'  Senha:        {TEST_CHILD2_PASSWORD}')
        self.stdout.write('─' * 60)
