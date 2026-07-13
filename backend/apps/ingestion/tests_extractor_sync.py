"""
Testes do sync_from_extractor: lê o schema "extractor" (tournament-extractor) e
faz upsert em TournamentEdition / FederationEntry.
"""
import io

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from apps.registrations.models import FederationEntry
from apps.tournaments.models import TournamentEdition
from apps.ingestion.management.commands.sync_from_extractor import (
    _map_payment, _slug, _country_code, STATUS_MAP,
)


def _create_extractor_schema():
    """Cria o schema extractor com um torneio juvenil + 1 categoria + 1 inscrito."""
    with connection.cursor() as cur:
        cur.execute('CREATE SCHEMA IF NOT EXISTS extractor')
        cur.execute('''
            CREATE TABLE extractor.sources (
                id serial PRIMARY KEY, name varchar(64), base_url varchar(512), type varchar(32))
        ''')
        cur.execute('''
            CREATE TABLE extractor.tournaments (
                id serial PRIMARY KEY, source_id int, external_id varchar(128),
                name varchar(512), original_name varchar(512), normalized_name varchar(512),
                federation varchar(255), organization varchar(255), modality varchar(64),
                country varchar(64), state varchar(64), city varchar(128), venue varchar(255),
                address text, start_date date, end_date date, registration_start_date date,
                registration_end_date date, registration_fee numeric(12,2), status varchar(64),
                original_url varchar(1024), is_youth boolean, is_kids boolean default false,
                possible_duplicate_of int,
                raw_data jsonb, created_at timestamptz default now(), updated_at timestamptz default now())
        ''')
        cur.execute('''
            CREATE TABLE extractor.tournament_categories (
                id serial PRIMARY KEY, tournament_id int, name varchar(255),
                normalized_name varchar(255), age_group int, gender varchar(16),
                category_type varchar(32))
        ''')
        cur.execute('''
            CREATE TABLE extractor.entrants (
                id serial PRIMARY KEY, tournament_id int, category_id int, external_id varchar(128),
                name varchar(255), country varchar(64), state varchar(64), city varchar(128),
                ranking varchar(64), position int, rating varchar(64),
                payment_status varchar(32), registration_status varchar(32), raw_data jsonb)
        ''')
        cur.execute("INSERT INTO extractor.sources (id, name, type) VALUES (1, 'cbt', 'html')")
        cur.execute('''
            INSERT INTO extractor.tournaments
                (id, source_id, external_id, name, federation, modality, country, state, city,
                 start_date, end_date, registration_end_date, registration_fee,
                 status, original_url, is_youth, raw_data)
            VALUES (10, 1, '22697', 'Aberto Infantojuvenil de Teste', 'CBT', 'tennis',
                    'Brasil', 'RJ', 'Niteroi', '2026-06-20', '2026-06-22', '2026-06-15', 150.00,
                    'inscricoes_abertas', 'https://x/22697', TRUE, '{}'::jsonb)
        ''')
        cur.execute('''
            INSERT INTO extractor.tournament_categories (id, tournament_id, name, age_group, gender, category_type)
            VALUES (100, 10, '14 Anos Masculino Simples', 14, 'M', 'singles')
        ''')
        cur.execute('''
            INSERT INTO extractor.entrants
                (id, tournament_id, category_id, external_id, name, country, state, city,
                 ranking, position, rating, payment_status, registration_status, raw_data)
            VALUES (1000, 10, 100, '240896', 'Fulano de Tal', 'Brasil', 'RJ', 'Rio de Janeiro',
                    '21', 1, '30,05', 'pago', 'confirmado', '{}'::jsonb)
        ''')
        # Torneio 100% Kids (sem categoria 12-18): is_youth=FALSE, is_kids=TRUE.
        # Regressão do bug em extractor_reader.iter_tournaments (WHERE só olhava
        # is_youth, excluía torneios assim do sync) e do filtro de nível de
        # jogador (que mostrava esses torneios pra perfil Profissional/Idosos).
        cur.execute('''
            INSERT INTO extractor.tournaments
                (id, source_id, external_id, name, federation, modality, country, state, city,
                 start_date, end_date, registration_end_date, registration_fee,
                 status, original_url, is_youth, is_kids, raw_data)
            VALUES (11, 1, '22876', 'Circuito KidsTour de Teste', 'CBT', 'tennis',
                    'Brasil', 'RJ', 'Niteroi', '2026-06-20', '2026-06-22', '2026-06-15', 80.00,
                    'inscricoes_abertas', 'https://x/22876', FALSE, TRUE, '{}'::jsonb)
        ''')
        cur.execute('''
            INSERT INTO extractor.tournament_categories (id, tournament_id, name, age_group, gender, category_type)
            VALUES (101, 11, '9 Anos Masculino Simples', 9, 'M', 'singles')
        ''')


class SyncFromExtractorTest(TestCase):
    def test_sync_creates_edition_and_entry(self):
        _create_extractor_schema()
        out = io.StringIO()
        call_command('sync_from_extractor', '--no-dry-run', '--import-entries', stdout=out)

        self.assertEqual(TournamentEdition.objects.count(), 2)
        ed = TournamentEdition.objects.get(external_id='cbt:22697')
        self.assertEqual(ed.title, 'Aberto Infantojuvenil de Teste')
        self.assertEqual(ed.external_id, 'cbt:22697')
        self.assertEqual(ed.season_year, 2026)
        self.assertEqual(ed.status, TournamentEdition.STATUS_OPEN)
        self.assertTrue(ed.is_youth)
        self.assertEqual(ed.categories.count(), 1)
        # Bandeira do torneio: Venue.country_code resolvido a partir de "Brasil".
        self.assertEqual(ed.venue.country_code, 'BRA')
        # Taxa: Decimal da fonte vira float (raw_payload é JSON; Decimal quebraria).
        self.assertEqual(float(ed.base_price_brl), 150.0)

        self.assertEqual(FederationEntry.objects.count(), 1)
        fe = FederationEntry.objects.first()
        self.assertEqual(fe.player_name, 'Fulano de Tal')
        self.assertEqual(fe.category_text, '14 Anos Masculino Simples')
        self.assertEqual(fe.payment_status, FederationEntry.PAYMENT_PAID)
        self.assertEqual(fe.ranking_position, 1)
        self.assertEqual(fe.source, 'cbt')
        # Bandeira do inscrito: player_country_code resolvido de "Brasil".
        self.assertEqual(fe.player_country_code, 'BRA')

    def test_sync_kids_only_tournament_is_not_excluded_and_flagged(self):
        """Torneio 100% Kids (is_youth=FALSE, is_kids=TRUE no extractor) precisa
        chegar no sync (não ser filtrado por engano) e virar is_kids=True /
        is_youth=False na TournamentEdition."""
        _create_extractor_schema()
        out = io.StringIO()
        call_command('sync_from_extractor', '--no-dry-run', stdout=out)

        self.assertEqual(TournamentEdition.objects.count(), 2)
        kids_ed = TournamentEdition.objects.get(external_id='cbt:22876')
        self.assertTrue(kids_ed.is_kids)
        self.assertFalse(kids_ed.is_youth)

    def test_country_code_passthrough_and_itf_hint(self):
        # inscrito ITF/COSAT já vem com código 3 letras -> passthrough
        self.assertEqual(_country_code('BRA'), 'BRA')
        self.assertEqual(_country_code('ECU'), 'ECU')
        # torneio ITF usa hostNationCode como hint
        self.assertEqual(_country_code('France', hint='FRA'), 'FRA')
        # nome sul-americano (COSAT) -> código
        self.assertEqual(_country_code('Ecuador'), 'ECU')
        self.assertEqual(_country_code('Brasil'), 'BRA')

    def test_dry_run_writes_nothing(self):
        _create_extractor_schema()
        out = io.StringIO()
        call_command('sync_from_extractor', '--import-entries', stdout=out)  # dry-run default
        self.assertEqual(TournamentEdition.objects.count(), 0)
        self.assertEqual(FederationEntry.objects.count(), 0)
        self.assertIn('DRY-RUN', out.getvalue())

    def test_idempotent_resync(self):
        _create_extractor_schema()
        call_command('sync_from_extractor', '--no-dry-run', '--import-entries', stdout=io.StringIO())
        call_command('sync_from_extractor', '--no-dry-run', '--import-entries', stdout=io.StringIO())
        self.assertEqual(TournamentEdition.objects.count(), 2)
        self.assertEqual(FederationEntry.objects.count(), 1)

    def test_refresh_replaces_old_entries(self):
        """Refresh por torneio: inscritos antigos da edição (de meios anteriores)
        são substituídos pelos do extractor, sem duplicar."""
        _create_extractor_schema()
        call_command('sync_from_extractor', '--no-dry-run', '--import-entries', stdout=io.StringIO())
        ed = TournamentEdition.objects.get(external_id='cbt:22697')
        self.assertEqual(FederationEntry.objects.filter(edition=ed).count(), 1)
        # Inscrito antigo (meio anterior) na MESMA edição, fonte/id diferentes.
        FederationEntry.objects.create(
            edition=ed, category_text='Chave Antiga', player_name='Velho Inscrito',
            player_external_id='old:1', source='cbt_legado',
        )
        self.assertEqual(FederationEntry.objects.filter(edition=ed).count(), 2)
        # Re-sync: o antigo é removido (refresh), fica só o do extractor.
        call_command('sync_from_extractor', '--no-dry-run', '--import-entries', stdout=io.StringIO())
        self.assertEqual(FederationEntry.objects.filter(edition=ed).count(), 1)
        self.assertFalse(FederationEntry.objects.filter(player_external_id='old:1').exists())

    def test_itf_acceptance_list_entries(self):
        """ITF (acceptance list): categoria por gênero×seção, desistência vira
        removed_or_replaced, bandeira pelo código e nome cheio do país via raw."""
        _create_extractor_schema()  # cria as tabelas; adiciona uma fonte 'itf'
        with connection.cursor() as cur:
            cur.execute("INSERT INTO extractor.sources (id, name, type) VALUES (2, 'itf', 'api')")
            cur.execute('''
                INSERT INTO extractor.tournaments
                    (id, source_id, external_id, name, federation, modality, country,
                     city, start_date, end_date, status, original_url, is_youth, raw_data)
                VALUES (20, 2, 'j-j100-usa-2026-002', 'J100 Bloomington', 'ITF', 'tennis',
                        'United States', 'Bloomington', '2026-06-20', '2026-06-26',
                        'inscricoes_abertas', 'https://itf/x', TRUE,
                        '{"hostNationCode": "USA"}'::jsonb)
            ''')
            cur.execute('''
                INSERT INTO extractor.tournament_categories (id, tournament_id, name, gender, category_type)
                VALUES (200, 20, 'Masculino - Chave Principal', 'M', 'singles'),
                       (201, 20, 'Masculino - Desistências',  'M', 'singles')
            ''')
            cur.execute('''
                INSERT INTO extractor.entrants
                    (id, tournament_id, category_id, external_id, name, country,
                     ranking, position, registration_status, raw_data)
                VALUES
                  (2000, 20, 200, 'itf:chave_principal:joshua-adamson:usa:1', 'Joshua Adamson',
                   'USA', '121', NULL, 'aceito_direto',
                   '{"country_name": "United States", "country_code": "USA", "wtn": 18.69}'::jsonb),
                  (2001, 20, 201, 'itf:desistencias:fulano-silva:bra:5', 'Fulano Silva',
                   'BRA', '300', NULL, 'cancelado',
                   '{"country_name": "Brazil", "country_code": "BRA"}'::jsonb)
            ''')

        call_command('sync_from_extractor', '--source', 'itf', '--no-dry-run',
                     '--import-entries', stdout=io.StringIO())

        itf_entries = FederationEntry.objects.filter(source='itf')
        self.assertEqual(itf_entries.count(), 2)

        main = itf_entries.get(category_text='Masculino - Chave Principal')
        self.assertEqual(main.player_name, 'Joshua Adamson')
        self.assertEqual(main.ranking_position, 121)
        self.assertFalse(main.removed_or_replaced)
        self.assertEqual(main.payment_status, FederationEntry.PAYMENT_UNKNOWN)
        self.assertEqual(main.player_country_code, 'USA')        # bandeira
        self.assertEqual(main.player_country_name, 'United States')  # nome cheio via raw

        withdrawn = itf_entries.get(category_text='Masculino - Desistências')
        self.assertTrue(withdrawn.removed_or_replaced)            # desistência
        self.assertEqual(withdrawn.player_country_code, 'BRA')

    def test_federations_entry_source_per_federation(self):
        """'federations' agrupa várias federações; o inscrito leva o source da
        federação específica (ex.: 'fct-sc'), não 'federations'. E o torneio é
        atribuído à Organization canônica pela UF (filtro por federação no site)."""
        from apps.sources.models import Organization
        # Usa a federação de SC já seedada (pela migração 0012) — a UF é a chave
        # canônica; não criamos uma org duplicada.
        org_sc = Organization.objects.get(
            state='SC', type=Organization.TYPE_FEDERATION)
        _create_extractor_schema()
        with connection.cursor() as cur:
            cur.execute("INSERT INTO extractor.sources (id, name, type) VALUES (3, 'federations', 'html')")
            cur.execute('''
                INSERT INTO extractor.tournaments
                    (id, source_id, external_id, name, federation, modality, country,
                     state, city, start_date, end_date, status, original_url, is_youth, raw_data)
                VALUES (30, 3, '22999', 'Estadual Infantojuvenil SC', 'FCT (SC)', 'tennis',
                        'Brasil', 'SC', 'Florianópolis', '2026-07-10', '2026-07-12',
                        'inscricoes_abertas', 'https://x/22999', TRUE, '{}'::jsonb)
            ''')
            cur.execute('''
                INSERT INTO extractor.tournament_categories (id, tournament_id, name, age_group, gender, category_type)
                VALUES (300, 30, '14 Anos Masculino Simples', 14, 'M', 'singles')
            ''')
            cur.execute('''
                INSERT INTO extractor.entrants
                    (id, tournament_id, category_id, external_id, name, country, payment_status, raw_data)
                VALUES (3000, 30, 300, '99001', 'Atleta SC', 'Brasil', 'pago', '{}'::jsonb)
            ''')
        call_command('sync_from_extractor', '--source', 'federations', '--no-dry-run',
                     '--import-entries', stdout=io.StringIO())
        fe = FederationEntry.objects.get(player_name='Atleta SC')
        self.assertEqual(fe.source, 'fct-sc')  # separado por federação, não 'federations'
        # Torneio atribuído à Organization canônica da UF (SC), não a uma nova.
        self.assertEqual(fe.edition.tournament.organization_id, org_sc.id)
        self.assertEqual(Organization.objects.filter(state='SC').count(), 1)

    def test_entrant_ti_id_uf_age_populated(self):
        """TASK 6: id_tenista/uf/idade do raw_data.part viram
        player_ti_id/player_uf/player_age na FederationEntry."""
        from apps.registrations.models import FederationEntry
        _create_extractor_schema()
        with connection.cursor() as cur:
            cur.execute("INSERT INTO extractor.sources (id, name, type) VALUES (4, 'cbt', 'html')")
            cur.execute('''
                INSERT INTO extractor.tournaments
                    (id, source_id, external_id, name, federation, modality, country,
                     state, city, start_date, end_date, status, original_url, is_youth, raw_data)
                VALUES (40, 4, '21000', 'CBT Teste', 'CBT', 'tennis', 'Brasil', 'SP',
                        'São Paulo', '2026-07-10', '2026-07-12', 'inscricoes_abertas',
                        'https://x/21000', TRUE, '{}'::jsonb)
            ''')
            cur.execute('''
                INSERT INTO extractor.tournament_categories (id, tournament_id, name, age_group, gender, category_type)
                VALUES (400, 40, '12 Anos Masculino Simples', 12, 'M', 'singles')
            ''')
            cur.execute('''
                INSERT INTO extractor.entrants
                    (id, tournament_id, category_id, external_id, name, country, payment_status, raw_data)
                VALUES (4000, 40, 400, '88-257249', 'Eduardo Pozzi', 'Brasil', 'pago',
                        '{"part": {"id_tenista": "257249", "uf": "SP", "idade": "12"}}'::jsonb)
            ''')
        call_command('sync_from_extractor', '--source', 'cbt', '--no-dry-run',
                     '--import-entries', stdout=io.StringIO())
        fe = FederationEntry.objects.get(player_name='Eduardo Pozzi')
        self.assertEqual(fe.player_ti_id, '257249')  # id_tenista puro, não o composto
        self.assertEqual(fe.player_uf, 'SP')
        self.assertEqual(fe.player_age, 12)


class ExtractorSchemaWithoutIsKidsColumnTest(TestCase):
    """Dependência de ordem de deploy: o Tenfy e o tournament-extractor são
    deployados de repos/serviços separados. Se este código for ao ar ANTES da
    migration 002_add_kids.sql rodar no banco do extractor, a coluna is_kids
    ainda não existe — o sync inteiro (não só o suporte a Kids) não pode
    quebrar por causa disso."""

    def _create_extractor_schema_pre_kids(self):
        """Schema do extractor no formato ANTERIOR ao suporte a Kids (sem a
        coluna tournaments.is_kids) — replica o estado do banco de produção
        antes do deploy da migration correspondente no repo sync."""
        with connection.cursor() as cur:
            cur.execute('CREATE SCHEMA IF NOT EXISTS extractor')
            cur.execute('''
                CREATE TABLE extractor.sources (
                    id serial PRIMARY KEY, name varchar(64), base_url varchar(512), type varchar(32))
            ''')
            cur.execute('''
                CREATE TABLE extractor.tournaments (
                    id serial PRIMARY KEY, source_id int, external_id varchar(128),
                    name varchar(512), original_name varchar(512), normalized_name varchar(512),
                    federation varchar(255), organization varchar(255), modality varchar(64),
                    country varchar(64), state varchar(64), city varchar(128), venue varchar(255),
                    address text, start_date date, end_date date, registration_start_date date,
                    registration_end_date date, registration_fee numeric(12,2), status varchar(64),
                    original_url varchar(1024), is_youth boolean, possible_duplicate_of int,
                    raw_data jsonb, created_at timestamptz default now(), updated_at timestamptz default now())
            ''')
            cur.execute('''
                CREATE TABLE extractor.tournament_categories (
                    id serial PRIMARY KEY, tournament_id int, name varchar(255),
                    normalized_name varchar(255), age_group int, gender varchar(16),
                    category_type varchar(32))
            ''')
            cur.execute('''
                CREATE TABLE extractor.entrants (
                    id serial PRIMARY KEY, tournament_id int, category_id int, external_id varchar(128),
                    name varchar(255), country varchar(64), state varchar(64), city varchar(128),
                    ranking varchar(64), position int, rating varchar(64),
                    payment_status varchar(32), registration_status varchar(32), raw_data jsonb)
            ''')
            cur.execute("INSERT INTO extractor.sources (id, name, type) VALUES (1, 'cbt', 'html')")
            cur.execute('''
                INSERT INTO extractor.tournaments
                    (id, source_id, external_id, name, federation, modality, country, state, city,
                     start_date, end_date, registration_end_date, registration_fee,
                     status, original_url, is_youth, raw_data)
                VALUES (10, 1, '22697', 'Aberto Infantojuvenil de Teste', 'CBT', 'tennis',
                        'Brasil', 'RJ', 'Niteroi', '2026-06-20', '2026-06-22', '2026-06-15', 150.00,
                        'inscricoes_abertas', 'https://x/22697', TRUE, '{}'::jsonb)
            ''')

    def test_sync_does_not_crash_without_is_kids_column(self):
        self._create_extractor_schema_pre_kids()
        out = io.StringIO()
        call_command('sync_from_extractor', '--no-dry-run', stdout=out)  # não deve levantar UndefinedColumn

        self.assertEqual(TournamentEdition.objects.count(), 1)
        ed = TournamentEdition.objects.get(external_id='cbt:22697')
        self.assertTrue(ed.is_youth)
        self.assertFalse(ed.is_kids)  # default do model, sem dado do extractor pra sobrepor


class MappingHelpersTest(TestCase):
    def test_payment_mapping(self):
        self.assertEqual(_map_payment({'payment_status': 'pago'})[0], FederationEntry.PAYMENT_PAID)
        self.assertEqual(_map_payment({'payment_status': 'pendente'})[0], FederationEntry.PAYMENT_PENDING)
        # cancelado -> removed_or_replaced=True
        pay, removed, _ = _map_payment({'payment_status': 'cancelado'})
        self.assertTrue(removed)
        self.assertEqual(pay, FederationEntry.PAYMENT_UNKNOWN)
        # ITF: só situação de entrada, sem pagamento
        self.assertEqual(_map_payment({'registration_status': 'aceito_direto'})[0],
                         FederationEntry.PAYMENT_UNKNOWN)

    def test_status_mapping(self):
        self.assertEqual(STATUS_MAP['inscricoes_abertas'], TournamentEdition.STATUS_OPEN)
        self.assertEqual(STATUS_MAP['finalizado'], TournamentEdition.STATUS_FINISHED)

    def test_slug(self):
        self.assertEqual(_slug('Aberto Infantojuvenil de Teste'), 'aberto-infantojuvenil-de-teste')
