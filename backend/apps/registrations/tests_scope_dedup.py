"""
Regressão para GET /api/registrations/my/ — scope, dedup e flag is_past.

Item 1 — 'Inscrições ativas' não pode exibir torneios já passados.
Item 2 — Histórico não pode repetir o mesmo torneio (edições duplicadas).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone as tz
from rest_framework.test import APIClient

User = get_user_model()


class MyRegistrationsScopeDedupTestCase(TestCase):
    def setUp(self):
        from apps.sources.models import Organization
        from apps.players.models import PlayerProfile

        self.today = tz.now().date()
        self.user = User.objects.create_user(email='reg-scope@test.com', password='x')
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name='Atleta Scope', is_primary=True,
        )
        self.org, _ = Organization.objects.get_or_create(
            name='SCOPE_ORG', defaults={'short_name': 'SCO', 'type': 'confederation'},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self._counter = 0

    def _edition(self, title, start, end, status='open', slug=None):
        from apps.tournaments.models import Tournament, TournamentEdition
        self._counter += 1
        slug = slug or f'scope-t-{self._counter}'
        t = Tournament.objects.create(
            canonical_name=title, canonical_slug=slug, circuit='CBT',
            modality='tennis', organization=self.org,
        )
        return TournamentEdition.objects.create(
            tournament=t, title=title, external_id=f'scope:{self._counter}',
            season_year=2026, status=status, start_date=start, end_date=end,
        )

    def _reg(self, edition, withdrawn=False, registered_at=None):
        from apps.registrations.models import TournamentRegistration
        return TournamentRegistration.objects.create(
            profile=self.profile, edition=edition,
            registered_at=registered_at or tz.now(),
            is_withdrawn=withdrawn,
            withdrawn_at=tz.now() if withdrawn else None,
        )

    # ── Item 1: flag is_past ────────────────────────────────────────────────
    def test_is_past_false_for_future_edition(self):
        ed = self._edition('Futuro', self.today + timedelta(days=10), self.today + timedelta(days=12))
        self._reg(ed)
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data[0]['is_past'])

    def test_is_past_true_for_finished_edition(self):
        ed = self._edition('Passado', self.today - timedelta(days=10), self.today - timedelta(days=8))
        self._reg(ed)
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data[0]['is_past'])

    # ── Item 1: scope=active exclui passados ────────────────────────────────
    def test_scope_active_excludes_past_tournaments(self):
        fut = self._edition('Futuro', self.today + timedelta(days=10), self.today + timedelta(days=12))
        past = self._edition('Passado', self.today - timedelta(days=10), self.today - timedelta(days=8))
        self._reg(fut)
        self._reg(past)
        res = self.client.get('/api/registrations/my/?scope=active')
        self.assertEqual(res.status_code, 200)
        titles = {r['edition_title'] for r in res.data}
        self.assertIn('Futuro', titles)
        self.assertNotIn('Passado', titles)

    def test_scope_active_keeps_in_progress(self):
        """Torneio em andamento (começou, não terminou) continua ativo."""
        ip = self._edition('EmAndamento', self.today - timedelta(days=1), self.today + timedelta(days=2))
        self._reg(ip)
        res = self.client.get('/api/registrations/my/?scope=active')
        titles = {r['edition_title'] for r in res.data}
        self.assertIn('EmAndamento', titles)

    def test_scope_history_includes_past_and_withdrawn(self):
        fut = self._edition('FuturoH', self.today + timedelta(days=10), self.today + timedelta(days=12))
        past = self._edition('PassadoH', self.today - timedelta(days=10), self.today - timedelta(days=8))
        self._reg(fut)
        self._reg(past)
        wd = self._edition('CanceladoH', self.today + timedelta(days=20), self.today + timedelta(days=22))
        self._reg(wd, withdrawn=True)
        res = self.client.get('/api/registrations/my/?scope=history')
        titles = {r['edition_title'] for r in res.data}
        self.assertIn('PassadoH', titles)
        self.assertIn('CanceladoH', titles)
        self.assertNotIn('FuturoH', titles)

    # ── Item 2: dedup de edições duplicadas ─────────────────────────────────
    def test_history_does_not_repeat_same_cancelled_event(self):
        start = self.today + timedelta(days=30)
        end = self.today + timedelta(days=34)
        for i in range(3):
            ed = self._edition(
                'G2 - Campeonato Nacional Clube De Campo De Sao Paulo',
                start, end, slug=f'dup-g2-{i}',
            )
            self._reg(ed, withdrawn=True, registered_at=tz.now() - timedelta(hours=i))
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1, res.data)

    def test_dedup_normalizes_case_and_accents(self):
        start = self.today + timedelta(days=30)
        end = self.today + timedelta(days=34)
        ed1 = self._edition('G1 - Circuito Brasiliense de Tênis', start, end, slug='dup-a')
        ed2 = self._edition('G1 - CIRCUITO BRASILIENSE DE TENIS', start, end, slug='dup-b')
        self._reg(ed1, withdrawn=True, registered_at=tz.now() - timedelta(hours=2))
        self._reg(ed2, withdrawn=True, registered_at=tz.now() - timedelta(hours=1))
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(len(res.data), 1, res.data)

    def test_dedup_prefers_active_over_withdrawn(self):
        start = self.today + timedelta(days=30)
        end = self.today + timedelta(days=34)
        ed_wd = self._edition('Copa Duplicada', start, end, slug='pref-a')
        ed_active = self._edition('Copa Duplicada', start, end, slug='pref-b')
        self._reg(ed_wd, withdrawn=True, registered_at=tz.now() - timedelta(hours=2))
        self._reg(ed_active, withdrawn=False, registered_at=tz.now() - timedelta(hours=1))
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(len(res.data), 1, res.data)
        self.assertFalse(res.data[0]['is_withdrawn'])

    def test_different_events_are_not_merged(self):
        a = self._edition('Copa X', self.today + timedelta(days=5), self.today + timedelta(days=7))
        b = self._edition('Copa X', self.today + timedelta(days=40), self.today + timedelta(days=42))
        self._reg(a)
        self._reg(b)
        res = self.client.get('/api/registrations/my/')
        self.assertEqual(len(res.data), 2, res.data)


class SyncTargetsWindowRegressionTestCase(TestCase):
    """
    Item 4 — federation_sync_targets não pode retornar count:0 quando existem
    torneios sincronizáveis da fonte pedida.

    Regressão do bug do slice: a query é ordenada por -start_date e o loop só
    varria os primeiros (limit*3) registros ANTES de filtrar por ?source. Uma
    edição da fonte alvo posicionada fora dessa janela ficava invisível
    (count:0 mesmo com total_with_source_url alto).
    """

    def setUp(self):
        from apps.sources.models import Organization
        self.today = tz.now().date()
        self.staff = User.objects.create_user(
            email='sync-window@test.com', password='x', is_staff=True,
        )
        self.org, _ = Organization.objects.get_or_create(
            name='WINDOW_ORG', defaults={'short_name': 'WIN', 'type': 'confederation'},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self._n = 0

    def _edition(self, circuit, source_url, start, end=None, status='open'):
        from apps.tournaments.models import Tournament, TournamentEdition
        self._n += 1
        t = Tournament.objects.create(
            canonical_name=f'{circuit} {self._n}', canonical_slug=f'win-{self._n}',
            circuit=circuit, modality='tennis', organization=self.org,
        )
        return TournamentEdition.objects.create(
            tournament=t, title=f'{circuit} Tour {self._n}', external_id=f'win:{self._n}',
            season_year=2026, status=status, start_date=start, end_date=end,
            official_source_url=source_url,
        )

    def test_target_source_found_outside_first_window(self):
        # 20 edições FPT com start no futuro (sobem ao topo sob -start_date)
        for i in range(20):
            self._edition('FPT', f'https://fpt.com.br/t{i}', self.today + timedelta(days=30 + i))
        # 1 edição CBT com start no passado (afunda para o fim da ordenação)
        cbt = self._edition(
            'CBT', 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/9001',
            self.today - timedelta(days=2),
        )
        # limit pequeno: janela antiga = limit*3 = 15 → CBT ficava de fora.
        res = self.client.get('/api/integrations/federation-sync-targets/?source=cbt&limit=5')
        self.assertEqual(res.status_code, 200)
        ids = [r['edition_id'] for r in res.data['results']]
        self.assertIn(cbt.id, ids, f"CBT fora da janela não foi encontrado: {res.data}")
        self.assertGreaterEqual(res.data['count'], 1)

    def test_count_zero_only_when_no_syncable_source(self):
        # Só FPT existe; pedir CBT deve dar 0 (legítimo), sem erro.
        self._edition('FPT', 'https://fpt.com.br/only', self.today + timedelta(days=10))
        res = self.client.get('/api/integrations/federation-sync-targets/?source=cbt')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 0)
        self.assertIn('scanned', res.data)


class DeduplicateEditionsTestCase(TestCase):
    """
    Item 3 — detecção de duplicados por título normalizado + datas, mesmo em
    tournaments/organizações distintos (caso real: edições duplicadas criadas
    sob tournament_ids diferentes). dry_run não altera nada.
    """

    def setUp(self):
        from apps.sources.models import Organization
        self.today = tz.now().date()
        self.staff = User.objects.create_user(email='dedup@test.com', password='x', is_staff=True)
        self.org, _ = Organization.objects.get_or_create(
            name='DEDUP_ORG', defaults={'short_name': 'DDP', 'type': 'confederation'},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self._n = 0

    def _edition(self, title, start, end):
        from apps.tournaments.models import Tournament, TournamentEdition
        self._n += 1
        t = Tournament.objects.create(
            canonical_name=title, canonical_slug=f'dedup-{self._n}',
            circuit='CBT', modality='tennis', organization=self.org,
        )
        return TournamentEdition.objects.create(
            tournament=t, title=title, external_id=f'dedup:{self._n}',
            season_year=2026, status='open', start_date=start, end_date=end,
        )

    def test_norm_title_dates_groups_cross_tournament(self):
        start = self.today + timedelta(days=20)
        end = self.today + timedelta(days=22)
        # Mesmo evento, caixa/acentos diferentes, tournaments distintos
        a = self._edition('COPA SÃO JOÃO TÊNIS CLUBE - IJ 600', start, end)
        b = self._edition('Copa Sao Joao Tenis Clube - IJ 600', start, end)
        res = self.client.post('/api/integrations/deduplicate-editions/',
                               {'dry_run': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        reasons = [g['reason'] for g in res.data['report']]
        self.assertIn('norm_title+dates', reasons)
        # nenhum registro removido em dry_run
        self.assertEqual(res.data['removed'], 0)
        # o grupo contém as duas editions
        grp = next(g for g in res.data['report'] if g['reason'] == 'norm_title+dates')
        ids = [grp['keep']['id']] + [r['id'] for r in grp['remove']]
        self.assertEqual(set(ids), {a.id, b.id})

    def test_different_dates_not_grouped(self):
        a = self._edition('Copa Igual', self.today + timedelta(days=5), self.today + timedelta(days=7))
        b = self._edition('Copa Igual', self.today + timedelta(days=40), self.today + timedelta(days=42))
        res = self.client.post('/api/integrations/deduplicate-editions/',
                               {'dry_run': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        for g in res.data['report']:
            ids = {g['keep']['id']} | {r['id'] for r in g['remove']}
            self.assertNotEqual(ids, {a.id, b.id})

    def test_merge_migrates_inscritos_not_lost(self):
        """No merge real, inscritos que só existem na duplicata são migrados
        para a edição mantida — nunca perdidos."""
        from apps.registrations.models import FederationEntry
        start = self.today + timedelta(days=15)
        end = self.today + timedelta(days=17)
        keep = self._edition('Copa Merge', start, end)   # menor id -> keep
        dup = self._edition('COPA MERGE', start, end)     # duplicata -> remove
        # inscrito existe SÓ na duplicata
        FederationEntry.objects.create(
            edition=dup, category_text='Sub-16 M', player_name='Atleta Único',
            player_external_id='ext-unico-1', source='cbt',
        )
        res = self.client.post('/api/integrations/deduplicate-editions/',
                               {'dry_run': False}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        # duplicata removida
        from apps.tournaments.models import TournamentEdition
        self.assertFalse(TournamentEdition.objects.filter(id=dup.id).exists())
        # inscrito preservado, agora na edição mantida
        self.assertEqual(FederationEntry.objects.filter(edition=keep, player_external_id='ext-unico-1').count(), 1)
        self.assertEqual(FederationEntry.objects.count(), 1)
