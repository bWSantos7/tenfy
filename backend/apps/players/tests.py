"""Tests for players app: PlayerProfile CRUD, permissions, categories, sporting_age, actions."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.players.models import PlayerCategory, PlayerProfile, PlayerProfileCategory

User = get_user_model()


def make_user(email='player@example.com', password='pass123', role='player'):
    return User.objects.create_user(email=email, password=password, full_name='Test Player', role=role)


# ── PlayerProfile model ────────────────────────────────────────────────────────

class PlayerProfileModelTestCase(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_create_profile(self):
        p = PlayerProfile.objects.create(user=self.user, display_name='Test Profile')
        self.assertEqual(str(p), f'Test Profile ({self.user.email})')

    def test_sporting_age_from_birth_year(self):
        from django.utils import timezone
        current_year = timezone.now().year
        p = PlayerProfile(birth_year=current_year - 16)
        self.assertEqual(p.sporting_age, 16)

    def test_sporting_age_none_when_no_birth_year(self):
        p = PlayerProfile(birth_year=None)
        self.assertIsNone(p.sporting_age)

    def test_unique_display_name_per_user(self):
        PlayerProfile.objects.create(user=self.user, display_name='Dup Name')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PlayerProfile.objects.create(user=self.user, display_name='Dup Name')

    def test_default_competitive_level_is_amateur(self):
        p = PlayerProfile.objects.create(user=self.user, display_name='Level Test')
        self.assertEqual(p.competitive_level, PlayerProfile.LEVEL_AMATEUR)

    def test_default_travel_radius_is_100(self):
        p = PlayerProfile.objects.create(user=self.user, display_name='Radius Test')
        self.assertEqual(p.travel_radius_km, 100)


# ── PlayerCategory model ───────────────────────────────────────────────────────

class PlayerCategoryModelTestCase(TestCase):
    def test_create_category(self):
        cat = PlayerCategory.objects.create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
            code='3M',
            gender_scope=PlayerCategory.GENDER_M,
            label_ptbr='Classe 3 Masculino',
            class_level=3,
        )
        self.assertIn('3M', str(cat))

    def test_unique_taxonomy_code_gender(self):
        PlayerCategory.objects.create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_AGE,
            code='14M',
            gender_scope=PlayerCategory.GENDER_M,
            label_ptbr='14 Anos Masc',
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PlayerCategory.objects.create(
                taxonomy=PlayerCategory.TAXONOMY_FPT_AGE,
                code='14M',
                gender_scope=PlayerCategory.GENDER_M,
                label_ptbr='Duplicate',
            )


# ── PlayerProfile API ─────────────────────────────────────────────────────────

class PlayerProfileAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.other = make_user(email='other@example.com')
        self.client.force_authenticate(user=self.user)

    def test_list_requires_auth(self):
        anon = APIClient()
        res = anon.get('/api/players/profiles/')
        self.assertEqual(res.status_code, 401)

    def test_create_profile(self):
        res = self.client.post('/api/players/profiles/', {
            'display_name': 'New Profile',
            'competitive_level': 'amateur',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['display_name'], 'New Profile')
        self.assertEqual(PlayerProfile.objects.filter(user=self.user).count(), 1)

    def test_list_returns_own_profiles_only(self):
        PlayerProfile.objects.create(user=self.user, display_name='Mine')
        PlayerProfile.objects.create(user=self.other, display_name='Not Mine')
        res = self.client.get('/api/players/profiles/')
        self.assertEqual(res.status_code, 200)
        data = res.data
        if isinstance(data, dict) and 'results' in data:
            items = data['results']
        elif isinstance(data, list):
            items = data
        else:
            self.fail(f'Unexpected response shape: {type(data)}')

        names = [p['display_name'] for p in items]
        self.assertIn('Mine', names)
        self.assertNotIn('Not Mine', names)

    def test_update_own_profile(self):
        p = PlayerProfile.objects.create(user=self.user, display_name='To Update')
        res = self.client.patch(f'/api/players/profiles/{p.id}/', {
            'home_state': 'SP',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['home_state'], 'SP')

    def test_cannot_access_other_user_profile(self):
        p = PlayerProfile.objects.create(user=self.other, display_name='Other Profile')
        res = self.client.get(f'/api/players/profiles/{p.id}/')
        self.assertEqual(res.status_code, 404)

    def test_player_role_cannot_delete_own_profile(self):
        p = PlayerProfile.objects.create(user=self.user, display_name='No Delete')
        res = self.client.delete(f'/api/players/profiles/{p.id}/')
        self.assertEqual(res.status_code, 400)

    def test_player_cannot_create_second_profile_returns_403(self):
        # Player accounts may keep only one sporting profile. A second create is
        # blocked by the single-profile rule (403) before any other validation —
        # so a duplicate display_name never reaches the unique-constraint path.
        PlayerProfile.objects.create(user=self.user, display_name='Existing')
        res = self.client.post('/api/players/profiles/', {
            'display_name': 'Another',
            'competitive_level': 'amateur',
        }, format='json')
        self.assertEqual(res.status_code, 403)


class PlayerProfileChildRestrictionTestCase(TestCase):
    """Managed child accounts cannot add extra profiles or delete profiles —
    their responsável manages them. (A child's own first profile is created
    before they are linked to a parent.)"""

    def setUp(self):
        self.client = APIClient()
        self.parent = make_user(email='parent@example.com', role='parent')
        self.child = make_user(email='child@example.com', role='player')
        from apps.accounts.models import ParentChild
        ParentChild.objects.create(parent=self.parent, child=self.child, is_active=True)
        self.client.force_authenticate(user=self.child)

    def test_managed_child_cannot_create_additional_profile(self):
        # The child already has their own profile; once managed, they cannot add more.
        PlayerProfile.objects.create(user=self.child, display_name='Existing Child Profile')
        res = self.client.post('/api/players/profiles/', {
            'display_name': 'Child Profile 2',
        }, format='json')
        self.assertEqual(res.status_code, 403)


# ── PlayerProfile actions ─────────────────────────────────────────────────────

class PlayerProfileActionsTestCase(TestCase):
    """Tests for set_primary, add_category, remove_category actions."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email='actions@example.com')
        self.client.force_authenticate(user=self.user)
        self.profile = PlayerProfile.objects.create(user=self.user, display_name='Primary')
        self.profile2 = PlayerProfile.objects.create(user=self.user, display_name='Secondary')
        self.category = PlayerCategory.objects.create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
            code='2F',
            gender_scope=PlayerCategory.GENDER_F,
            label_ptbr='Classe 2 Feminino',
            class_level=2,
        )

    def test_set_primary_marks_profile(self):
        res = self.client.post(f'/api/players/profiles/{self.profile2.id}/set_primary/')
        self.assertEqual(res.status_code, 200)
        self.profile2.refresh_from_db()
        self.assertTrue(self.profile2.is_primary)

    def test_set_primary_unsets_previous_primary(self):
        self.profile.is_primary = True
        self.profile.save()
        self.client.post(f'/api/players/profiles/{self.profile2.id}/set_primary/')
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_primary)

    def test_add_category_to_profile(self):
        res = self.client.post(
            f'/api/players/profiles/{self.profile.id}/categories/',
            {'category_id': self.category.id},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(
            PlayerProfileCategory.objects.filter(profile=self.profile, category=self.category).exists()
        )

    def test_add_category_missing_id_returns_400(self):
        res = self.client.post(
            f'/api/players/profiles/{self.profile.id}/categories/',
            {},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_remove_category_from_profile(self):
        PlayerProfileCategory.objects.create(profile=self.profile, category=self.category)
        res = self.client.delete(
            f'/api/players/profiles/{self.profile.id}/categories/{self.category.id}/'
        )
        self.assertEqual(res.status_code, 204)
        self.assertFalse(
            PlayerProfileCategory.objects.filter(profile=self.profile, category=self.category).exists()
        )

    def test_child_cannot_set_primary(self):
        child = make_user(email='child2@example.com', role='player')
        from apps.accounts.models import ParentChild
        parent = make_user(email='parent2@example.com', role='parent')
        ParentChild.objects.create(parent=parent, child=child, is_active=True)
        child_profile = PlayerProfile.objects.create(user=child, display_name='Child P')
        child_client = APIClient()
        child_client.force_authenticate(user=child)
        res = child_client.post(f'/api/players/profiles/{child_profile.id}/set_primary/')
        self.assertEqual(res.status_code, 403)


# ── PlayerCategory API ────────────────────────────────────────────────────────

class PlayerCategoryAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)
        PlayerCategory.objects.create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS,
            code='2M',
            gender_scope=PlayerCategory.GENDER_M,
            label_ptbr='Classe 2 Masculino',
            class_level=2,
        )

    def test_categories_list_authenticated(self):
        res = self.client.get('/api/players/categories/')
        self.assertEqual(res.status_code, 200)
        self.assertGreater(len(res.data), 0)

    def test_categories_require_auth(self):
        # PlayerCategoryViewSet uses IsAuthenticated — anonymous must receive 401
        anon = APIClient()
        res = anon.get('/api/players/categories/')
        self.assertEqual(res.status_code, 401)


class UtrUnlinkTestCase(TestCase):
    """utr-unlink clears every UTR field (backs the 'Confirmar exclusão' modal)."""

    def setUp(self):
        self.user = make_user(email='utr_unlink@example.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        from django.utils import timezone
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name='UTR Player',
            utr_player_id='12345', utr_display_name='UTR Player',
            utr_singles='8.50', utr_doubles='8.00',
            utr_profile_url='https://app.utrsports.net/profiles/12345',
            utr_synced_at=timezone.now(), utr_sync_error='',
        )

    def test_unlink_clears_all_utr_fields(self):
        res = self.client.post(f'/api/players/profiles/{self.profile.id}/utr-unlink/')
        self.assertEqual(res.status_code, 200, res.data)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.utr_player_id, '')
        self.assertEqual(self.profile.utr_singles, '')
        self.assertEqual(self.profile.utr_doubles, '')
        self.assertEqual(self.profile.utr_display_name, '')
        self.assertEqual(self.profile.utr_profile_url, '')
        self.assertIsNone(self.profile.utr_synced_at)

    def test_unlink_is_idempotent(self):
        self.client.post(f'/api/players/profiles/{self.profile.id}/utr-unlink/')
        res = self.client.post(f'/api/players/profiles/{self.profile.id}/utr-unlink/')
        self.assertEqual(res.status_code, 200)

    def test_unlink_requires_owner(self):
        other = make_user(email='utr_other@example.com')
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        res = other_client.post(f'/api/players/profiles/{self.profile.id}/utr-unlink/')
        self.assertIn(res.status_code, (403, 404))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.utr_player_id, '12345')  # untouched


class HourlySyncTasksTestCase(TestCase):
    """
    Atualização automática de hora em hora: as tasks periódicas enfileiram um
    sync por perfil relevante, sem duplicar e sem chamadas externas desnecessárias.
    """

    def _profile(self, email, **kw):
        user = make_user(email=email)
        return PlayerProfile.objects.create(user=user, display_name=email, **kw)

    def test_ti_sync_dispatches_once_per_linked_profile(self):
        from unittest.mock import patch
        from apps.players.tasks import sync_all_ti_profiles_task

        self._profile('ti_a@test.com', external_ids={'cbt': 'tenisintegrado:111'})
        self._profile('ti_b@test.com', external_ids={'fpt': '222'})
        self._profile('ti_none@test.com', external_ids={})  # no TI id → skipped

        with patch('apps.players.tasks.sync_ti_data_task.apply_async') as mock_apply:
            sync_all_ti_profiles_task()

        self.assertEqual(mock_apply.call_count, 2)  # only the two TI-linked profiles

    def test_utr_sync_only_dispatches_stale_linked_profiles(self):
        from unittest.mock import patch
        from datetime import timedelta
        from django.utils import timezone
        from apps.players.tasks import sync_all_utr_profiles_task

        now = timezone.now()
        # Stale (old sync) → dispatched
        self._profile('utr_stale@test.com', utr_player_id='1', utr_synced_at=now - timedelta(hours=3))
        # Never synced → dispatched
        self._profile('utr_new@test.com', utr_player_id='2', utr_synced_at=None)
        # Fresh (synced 5 min ago) → skipped (avoid unnecessary external call)
        self._profile('utr_fresh@test.com', utr_player_id='3', utr_synced_at=now - timedelta(minutes=5))
        # No UTR id → skipped
        self._profile('utr_unlinked@test.com', utr_player_id='')

        with patch('apps.players.tasks.extract_utr_rating_task.apply_async') as mock_apply:
            dispatched = sync_all_utr_profiles_task()

        self.assertEqual(dispatched, 2)
        self.assertEqual(mock_apply.call_count, 2)

    def test_setup_periodic_tasks_registers_hourly_and_prunes_obsolete(self):
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        from django.core.management import call_command

        # Simulate a leftover obsolete task from a previous deploy.
        old_cron, _ = CrontabSchedule.objects.get_or_create(
            minute='50', hour='*/2', day_of_week='*', day_of_month='*', month_of_year='*',
        )
        PeriodicTask.objects.create(
            name='sync-all-ti-profiles-every-2h',
            task='apps.players.tasks.sync_all_ti_profiles_task', crontab=old_cron,
        )

        call_command('setup_periodic_tasks', verbosity=0)

        names = set(PeriodicTask.objects.values_list('name', flat=True))
        self.assertIn('sync-all-ti-profiles-hourly', names)
        self.assertIn('sync-all-utr-profiles-hourly', names)
        self.assertNotIn('sync-all-ti-profiles-every-2h', names)  # pruned

        ti = PeriodicTask.objects.get(name='sync-all-ti-profiles-hourly')
        self.assertEqual(ti.crontab.hour, '*')  # hourly, not */2


class TenisIntegradoBootstrapTestCase(TestCase):
    def _profile(self, email, **kw):
        user = make_user(email=email)
        return PlayerProfile.objects.create(user=user, display_name=email, **kw)

    def _edition(self):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition

        org = Organization.objects.create(
            name='Federação Paulista de Tênis',
            short_name='FPT',
            type=Organization.TYPE_FEDERATION,
            state='SP',
        )
        tournament = Tournament.objects.create(
            canonical_name='Ranking Infantojuvenil',
            canonical_slug='ranking-infantojuvenil',
            organization=org,
        )
        return TournamentEdition.objects.create(
            tournament=tournament,
            season_year=2026,
            title='Ranking Infantojuvenil 2026',
        )

    def test_bootstrap_resolves_ti_id_from_imported_entry_and_queues_sync(self):
        from unittest.mock import patch
        from apps.players.tasks import bootstrap_ti_profile_task
        from apps.registrations.models import FederationEntry

        profile = self._profile('laura@example.com')
        profile.display_name = 'Laura Saviole'
        profile.external_ids = {}
        profile.save(update_fields=['display_name', 'external_ids'])

        FederationEntry.objects.create(
            edition=self._edition(),
            category_text='14F',
            player_name='Laura Saviole',
            player_external_id='tenisintegrado:375605',
            source=FederationEntry.SOURCE_FPT,
        )

        with patch('apps.players.tasks.sync_ti_data_task.apply_async') as mock_apply:
            result = bootstrap_ti_profile_task.run(profile.pk)

        profile.refresh_from_db()
        self.assertEqual(profile.external_ids['fpt'], 'tenisintegrado:375605')
        self.assertEqual(result['status'], 'queued_sync')
        mock_apply.assert_called_once()

    def test_new_profile_enqueues_ti_bootstrap_after_commit(self):
        from unittest.mock import patch

        with patch('apps.players.tasks.bootstrap_ti_profile_task.delay') as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                profile = self._profile('new_ti_bootstrap@example.com')

        mock_delay.assert_called_once_with(profile.pk)


# ── Task 1: Tênis Integrado ranking import (ExternalPlayerRanking) ───────────────

# Trimmed but structurally-faithful sample of a ranking_painel_classif POST
# response: one header row + three athlete rows (incl. one missing UF/age).
TI_RANKING_HTML = """
<table>
  <tr><th>Tenista</th><th>WTN</th><th>Movimentos</th><th>Pontos</th><th>Total</th><th>Torneios válidos</th><th>Ação</th></tr>
  <tr>
    <td>
      <div class="avatar-container"><a href="perfil2/index/243039"><img class="avatar"/></a></div>
      <div class="info-container">
        <a class="link-tournament" href="perfil2/index/243039">
          <div class="name-info">1º - Anna Faminova </div>
          <div> ID. 243039, UF: RS, Idade: 14 </div>
        </a>
        <div class="text-success">Avenida Tênis Clube</div>
      </div>
    </td>
    <td><div title="WTN"><span class="text-bold text-danger">29,88</span></div></td>
    <td><span><i class="text-success fa fa-arrow-circle-up"></i> 2</span></td>
    <td>500,00</td><td>612,50</td><td>2 de 2</td><td>Detalhes</td>
  </tr>
  <tr>
    <td>
      <div class="info-container">
        <a class="link-tournament" href="perfil2/index/380089">
          <div class="name-info">2º - Manuela Tavares de Souza </div>
          <div> ID. 380089, UF: PR, Idade: 14 </div>
        </a>
        <div class="text-success">Clube Curitibano</div>
      </div>
    </td>
    <td><span>30,68</span></td><td><span>0</span></td>
    <td>400,00</td><td>575,00</td><td>3 de 3</td><td>Detalhes</td>
  </tr>
  <tr>
    <td>
      <div class="info-container">
        <a class="link-tournament" href="perfil2/index/999111">
          <div class="name-info">3º - João Sem Dados </div>
          <div> ID. 999111 </div>
        </a>
      </div>
    </td>
    <td><span>40,00</span></td><td><span>1</span></td>
    <td>351,00</td><td>351,00</td><td>1 de 1</td><td>Detalhes</td>
  </tr>
</table>
"""


class TIRankingParserTestCase(TestCase):
    def test_parse_ranking_entries_extracts_fields(self):
        from apps.players.ti_rankings import parse_ranking_entries
        entries = parse_ranking_entries(TI_RANKING_HTML)
        self.assertEqual(len(entries), 3)

        first = entries[0]
        self.assertEqual(first['position'], 1)
        self.assertEqual(first['player_name'], 'Anna Faminova')
        self.assertEqual(first['ti_player_id'], '243039')
        self.assertEqual(first['uf'], 'RS')
        self.assertEqual(first['age'], 14)
        self.assertEqual(first['points'], '500,00')
        self.assertEqual(first['wtn'], '29,88')
        self.assertIn('Avenida', first['club'])

    def test_parse_handles_missing_uf_and_age(self):
        from apps.players.ti_rankings import parse_ranking_entries
        entries = parse_ranking_entries(TI_RANKING_HTML)
        last = entries[-1]
        self.assertEqual(last['ti_player_id'], '999111')
        self.assertEqual(last['player_name'], 'João Sem Dados')
        self.assertEqual(last['uf'], '')
        self.assertIsNone(last['age'])

    def test_parse_empty_table_returns_empty(self):
        from apps.players.ti_rankings import parse_ranking_entries
        self.assertEqual(parse_ranking_entries('<html><body>no table</body></html>'), [])


class ExternalPlayerRankingModelTestCase(TestCase):
    def test_unique_constraint_prevents_duplicates(self):
        from django.db import IntegrityError, transaction
        from apps.players.models import ExternalPlayerRanking
        base = dict(
            source='cbt', ranking_external_id='1419', category_code='10',
            ti_player_id='243039', season=2026, player_name='Anna Faminova',
        )
        ExternalPlayerRanking.objects.create(**base)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExternalPlayerRanking.objects.create(**base)


class TIRankingMatchingTestCase(TestCase):
    def _ranking(self, name, ti_id, source='cbt', normalized=None):
        from apps.players.models import ExternalPlayerRanking
        import unicodedata
        norm = normalized if normalized is not None else (
            unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().strip()
        )
        return ExternalPlayerRanking.objects.create(
            source=source, ranking_external_id='1419', category_code='10',
            ti_player_id=ti_id, season=2026, player_name=name,
            player_name_normalized=norm,
        )

    def test_unique_name_resolves_ti_id(self):
        from apps.players.tasks import _find_ti_id_in_rankings
        self._ranking('Anna Faminova', '243039')
        source, ext = _find_ti_id_in_rankings('anna faminova')
        self.assertEqual(source, 'cbt')
        self.assertEqual(ext, 'tenisintegrado:243039')

    def test_ambiguous_name_is_not_linked(self):
        from apps.players.tasks import _find_ti_id_in_rankings
        self._ranking('Bruno Santos', '111')
        self._ranking('Bruno Santos', '222')
        source, ext = _find_ti_id_in_rankings('bruno santos')
        self.assertIsNone(ext)
        self.assertIsNone(source)

    def test_accent_and_case_insensitive_match(self):
        from apps.players.tasks import _find_ti_external_id_for_profile
        self._ranking('João Pereira', '375605')
        user = make_user('joaomatch@example.com')
        profile = PlayerProfile.objects.create(user=user, display_name='JOAO PEREIRA', external_ids={})
        source, ext = _find_ti_external_id_for_profile(profile)
        self.assertEqual(ext, 'tenisintegrado:375605')

    def test_backfill_command_links_profile(self):
        from django.core.management import call_command
        from io import StringIO
        self._ranking('Carla Souza', '654321')
        user = make_user('carlamatch@example.com')
        profile = PlayerProfile.objects.create(user=user, display_name='Carla Souza', external_ids={})
        out = StringIO()
        call_command('match_profiles_to_ti_rankings', '--no-sync', stdout=out)
        profile.refresh_from_db()
        self.assertEqual(profile.external_ids.get('cbt'), 'tenisintegrado:654321')


class TIRankingSyncCommandTestCase(TestCase):
    def test_sync_command_imports_entries(self):
        from unittest.mock import patch
        from django.core.management import call_command
        from io import StringIO
        from apps.players.models import ExternalPlayerRanking

        fake_index = {
            'categories': [('10', '14 Anos Feminino Simples')],
            'cortes': [('8299', '25/05/2026')],
            'ufs': [],
        }
        fake_entries = [{
            'position': 1, 'player_name': 'Anna Faminova', 'ti_player_id': '243039',
            'uf': 'RS', 'age': 14, 'club': 'Avenida', 'wtn': '29,88',
            'points': '500,00', 'points_combined': '', 'total': '612,50',
            'valid_tournaments': '2 de 2',
        }]

        with patch('apps.players.ti_rankings.fetch_ranking_index', return_value=fake_index), \
             patch('apps.players.ti_rankings.fetch_ranking_entries', return_value=fake_entries), \
             patch('time.sleep'):
            call_command('sync_ti_rankings', '--ranking-id', '1419', '--source', 'cbt',
                         '--year', '2026', stdout=StringIO())

        row = ExternalPlayerRanking.objects.get(ti_player_id='243039')
        self.assertEqual(row.position, 1)
        self.assertEqual(row.source, 'cbt')
        self.assertEqual(row.season, 2026)
        self.assertEqual(row.player_name_normalized, 'anna faminova')
        self.assertEqual(str(row.classified_at), '2026-05-25')

    def test_sync_command_dry_run_writes_nothing(self):
        from unittest.mock import patch
        from django.core.management import call_command
        from io import StringIO
        from apps.players.models import ExternalPlayerRanking

        with patch('apps.players.ti_rankings.fetch_ranking_index', return_value={'categories': [('10', 'x')], 'cortes': [], 'ufs': []}), \
             patch('apps.players.ti_rankings.fetch_ranking_entries', return_value=[{'position': 1, 'player_name': 'X', 'ti_player_id': '1', 'uf': '', 'age': None, 'club': '', 'wtn': '', 'points': '', 'points_combined': '', 'total': '', 'valid_tournaments': ''}]), \
             patch('time.sleep'):
            call_command('sync_ti_rankings', '--ranking-id', '1419', '--source', 'cbt', '--dry-run', stdout=StringIO())

        self.assertEqual(ExternalPlayerRanking.objects.count(), 0)


class ProfileCatalogRankingsTestCase(TestCase):
    """Task 3: the profile ti-data endpoint surfaces catalogue rankings for the athlete."""

    def setUp(self):
        self.user = make_user('catalog@example.com')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        from django.utils import timezone
        now = timezone.now()
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name='Anna Faminova',
            external_ids={'cbt': 'tenisintegrado:243039'},
            ti_results_synced_at=now,
            ti_rankings_synced_at=now,
        )

    def _make_ranking(self, **over):
        from apps.players.models import ExternalPlayerRanking
        data = dict(
            source='fed', ranking_external_id='1385', category_code='10',
            ti_player_id='243039', season=2026, player_name='Anna Faminova',
            federation='FPT (SP)', ranking_name='Ranking Infantojuvenil 2026',
            category_label='14 Anos Feminino Simples', position=1, points='500,00',
            source_url='https://www.tenisintegrado.com.br/ranking_painel_classif/index/1385',
        )
        data.update(over)
        return ExternalPlayerRanking.objects.create(**data)

    def test_ti_data_includes_catalog_rankings(self):
        from unittest.mock import patch
        self._make_ranking()
        self._make_ranking(category_code='11', category_label='16 Anos Feminino Simples', position=3)
        # cache is "fresh" (synced_at set in setUp) so no scraping path is taken
        with patch('apps.players.views._sync_ti_data_inline') as mocked:
            resp = self.client.get(f'/api/players/profiles/{self.profile.id}/ti-data/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('catalog_rankings', body)
        self.assertEqual(len(body['catalog_rankings']), 2)
        first = body['catalog_rankings'][0]
        self.assertEqual(first['federation'], 'FPT (SP)')
        self.assertEqual(first['category'], '14 Anos Feminino Simples')
        self.assertEqual(first['position'], 1)
        self.assertEqual(first['source_label'], 'Federação (via Tênis Integrado)')

    def test_catalog_rankings_empty_when_no_classification(self):
        from unittest.mock import patch
        with patch('apps.players.views._sync_ti_data_inline'):
            resp = self.client.get(f'/api/players/profiles/{self.profile.id}/ti-data/')
        self.assertEqual(resp.json()['catalog_rankings'], [])


class TIYouthRankingHelpersTestCase(TestCase):
    def test_youth_ranking_name_matches(self):
        from apps.players.ti_rankings import is_youth_ranking_name
        for name in ['Ranking Infanto Juvenil 2026', 'Ranking Infantojuvenil 2026',
                     'Ranking Nacional Juvenil', 'Ranking de Juniors 2026']:
            self.assertTrue(is_youth_ranking_name(name), name)
        for name in ['Ranking Nacional de Profissionais 2026', 'Ranking Classes 2026',
                     'Ranking Beach Tennis 2026', 'Ranking Masters 2026']:
            self.assertFalse(is_youth_ranking_name(name), name)

    def test_age_12_18_category_filter(self):
        from apps.players.ti_rankings import is_age_12_18_category
        for label in ['12 Anos Masculino Simples', '14 Anos Feminino Simples',
                      '16 Anos Masculino Simples', '18 Anos Masculino Simples',
                      'Sub-15 Masculino', '12 Anos Masculino Simples (G1)']:
            self.assertTrue(is_age_12_18_category(label), label)
        for label in ['10 anos Masculino', 'Adulto', 'Profissional', '112 anos', 'Classe 1']:
            self.assertFalse(is_age_12_18_category(label), label)


class TIFederationDiscoveryTestCase(TestCase):
    FED_HTML = """
    <table><tbody>
      <tr><td>
        <div class="avatar-container"><a href="https://www.tenisintegrado.com.br/ranking_painel_classif/index/1385"><img/></a></div>
        <div class="info-container">
          <a class="link-tournament" href="https://www.tenisintegrado.com.br/ranking_painel_classif/index/1385">
            <div class="name-info">Ranking Infantojuvenil 2026</div>
          </a>
          <div class="">Criado por <a href="/perfil2/index/1">FPT (SP)</a></div>
        </div>
      </td></tr>
      <tr><td>
        <div class="info-container">
          <a class="link-tournament" href="https://www.tenisintegrado.com.br/ranking_painel_classif/index/1365">
            <div class="name-info">Ranking Nacional de Profissionais 2026</div>
          </a>
          <div class="">Criado por <a href="/perfil2/index/2">CBT</a></div>
        </div>
      </td></tr>
    </tbody></table>
    """

    def test_discover_parses_name_and_federation(self):
        from unittest.mock import patch, MagicMock
        from apps.players.ti_rankings import discover_federation_rankings
        resp = MagicMock(text=self.FED_HTML, encoding='utf-8')
        resp.raise_for_status = MagicMock()
        with patch('apps.players.ti_rankings._session') as mk:
            sess = MagicMock()
            sess.post.return_value = resp
            mk.return_value = sess
            rankings = discover_federation_rankings(2026)
        by_id = {r['ranking_external_id']: r for r in rankings}
        self.assertEqual(by_id['1385']['ranking_name'], 'Ranking Infantojuvenil 2026')
        self.assertEqual(by_id['1385']['federation'], 'FPT (SP)')
        self.assertEqual(len(rankings), 2)

    def test_federations_juvenil_command_imports_only_youth_12_18(self):
        from unittest.mock import patch
        from django.core.management import call_command
        from io import StringIO
        from apps.players.models import ExternalPlayerRanking

        discovered = [
            {'ranking_external_id': '1385', 'ranking_name': 'Ranking Infantojuvenil 2026', 'federation': 'FPT (SP)'},
            {'ranking_external_id': '1365', 'ranking_name': 'Ranking de Profissionais 2026', 'federation': 'CBT'},
        ]
        index = {'categories': [('5', '12 Anos Masculino Simples'), ('99', 'Adulto')], 'cortes': [('1', '01/06/2026')], 'ufs': []}
        entry = [{'position': 1, 'player_name': 'Y', 'ti_player_id': '77', 'uf': 'SP', 'age': 12, 'club': '', 'wtn': '', 'points': '10', 'points_combined': '', 'total': '10', 'valid_tournaments': ''}]

        with patch('apps.players.ti_rankings.discover_federation_rankings', return_value=discovered), \
             patch('apps.players.ti_rankings.fetch_ranking_index', return_value=index), \
             patch('apps.players.ti_rankings.fetch_ranking_entries', return_value=entry), \
             patch('time.sleep'):
            call_command('sync_ti_rankings', '--federations-juvenil', '--year', '2026', stdout=StringIO())

        # Only the youth ranking (1385) imported, and only the 12-anos category (not "Adulto").
        self.assertEqual(ExternalPlayerRanking.objects.filter(ranking_external_id='1365').count(), 0)
        rows = ExternalPlayerRanking.objects.filter(ranking_external_id='1385')
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.source, ExternalPlayerRanking.SOURCE_FED)
        self.assertEqual(row.federation, 'FPT (SP)')
        self.assertEqual(row.category_label, '12 Anos Masculino Simples')
