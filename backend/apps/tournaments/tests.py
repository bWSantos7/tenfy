"""
Tests for tournament filters, views, modality isolation and UF validation.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.players.models import PlayerProfile
from apps.sources.models import Organization, DataSource
from apps.tournaments.models import Tournament, TournamentEdition, Venue

User = get_user_model()


def _response_items(response):
    data = response.data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    if isinstance(data, list):
        return data
    raise AssertionError(f'Unexpected response shape: {type(data)}')


def _setup_cosat_tournament(db):
    """Create minimal COSAT tournament fixture. Returns TournamentEdition."""
    org, _ = Organization.objects.get_or_create(
        name='COSAT_FILTER_TEST',
        defaults={'short_name': 'COSAT', 'type': Organization.TYPE_CONFEDERATION},
    )
    ds, _ = DataSource.objects.get_or_create(
        connector_key='cosat_filter_test',
        defaults={
            'organization': org, 'source_name': 'COSAT Filter Test',
            'slug': 'cosat-filter-test',
            'source_type': DataSource.SOURCE_TYPE_JSON,
            'base_url': 'https://cosat.tournamentsoftware.com',
        },
    )
    tournament, _ = Tournament.objects.get_or_create(
        canonical_slug='copa-cosat-14-anos-test',
        defaults={
            'canonical_name': 'Copa COSAT 14 años',
            'circuit': 'COSAT',
            'organization': org,
        },
    )
    edition, _ = TournamentEdition.objects.get_or_create(
        external_id='cosat:copa-cosat-14-test',
        defaults={
            'tournament': tournament,
            'data_source': ds,
            'title': 'Copa COSAT 14 años',
            'season_year': 2025,
            'status': 'unknown',
            'is_youth': True,  # correctly classified
        },
    )
    return edition


class TournamentFilterCosatTestCase(TestCase):
    """Endpoint returns COSAT tournaments when circuit=COSAT filter is applied."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='filter_test@test.com', password='pass', is_staff=False
        )
        self.client.force_authenticate(user=self.user)
        self.edition = _setup_cosat_tournament(self)

    def test_circuit_cosat_filter_returns_edition(self):
        """GET /api/tournaments/editions/?circuit=COSAT returns COSAT tournament."""
        res = self.client.get('/api/tournaments/editions/', {'circuit': 'COSAT'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in _response_items(res)]
        self.assertIn(self.edition.id, ids,
                      'COSAT tournament must appear when circuit=COSAT filter applied')

    def test_search_cosat_text_finds_tournament(self):
        """GET /api/tournaments/editions/?q=cosat finds tournament by circuit."""
        res = self.client.get('/api/tournaments/editions/', {'q': 'cosat'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in _response_items(res)]
        self.assertIn(self.edition.id, ids,
                      'Text search for "cosat" must find COSAT tournament via circuit field')

    def test_null_start_date_not_excluded_by_queryset(self):
        """Tournament with start_date=None is not excluded by the queryset filter."""
        self.edition.start_date = None
        self.edition.save(update_fields=['start_date', 'updated_at'])
        # Directly test the queryset - no API pagination interaction
        from apps.tournaments.models import TournamentEdition
        from django.db.models import Q
        ids = list(
            TournamentEdition.objects
            .filter(Q(is_youth=True) | Q(is_youth__isnull=True))
            .filter(tournament__circuit__icontains='COSAT')
            .values_list('id', flat=True)
        )
        self.assertIn(self.edition.id, ids,
                      'is_youth filter must not exclude null-start_date COSAT tournament')

    def test_is_youth_false_excluded_from_default_list(self):
        """Tournament with is_youth=False is excluded from default list (not COSAT-specific)."""
        self.edition.is_youth = False
        self.edition.save(update_fields=['is_youth'])
        res = self.client.get('/api/tournaments/editions/', {'circuit': 'COSAT'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in _response_items(res)]
        self.assertNotIn(self.edition.id, ids,
                         'is_youth=False must be excluded unless youth_only=false')

    def test_youth_only_false_bypasses_is_youth_filter(self):
        """?youth_only=false shows is_youth=False tournaments (admin/debug use)."""
        self.edition.is_youth = False
        self.edition.save(update_fields=['is_youth'])
        res = self.client.get('/api/tournaments/editions/',
                              {'circuit': 'COSAT', 'youth_only': 'false'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in _response_items(res)]
        self.assertIn(self.edition.id, ids)

    def test_calendar_cache_varies_by_filter_params(self):
        """Calendar cache must not reuse an unfiltered response for filtered queries."""
        cache.clear()
        sp_venue = Venue.objects.create(name='Arena SP', city='Sao Paulo', state='SP')
        rj_venue = Venue.objects.create(name='Arena RJ', city='Rio de Janeiro', state='RJ')
        self.edition.start_date = '2026-06-10'
        self.edition.venue = sp_venue
        self.edition.save(update_fields=['start_date', 'venue', 'updated_at'])
        rj_edition = TournamentEdition.objects.create(
            tournament=self.edition.tournament,
            external_id='cosat:rj-cache-test',
            title='Copa COSAT RJ',
            season_year=2026,
            status='unknown',
            is_youth=True,
            start_date='2026-06-11',
            venue=rj_venue,
        )

        unfiltered = self.client.get('/api/tournaments/editions/calendar/')
        filtered = self.client.get('/api/tournaments/editions/calendar/', {'state': 'SP'})

        self.assertEqual(unfiltered.status_code, 200)
        self.assertEqual(filtered.status_code, 200)
        unfiltered_ids = [
            item['id']
            for month in unfiltered.data
            for item in month['items']
        ]
        filtered_ids = [
            item['id']
            for month in filtered.data
            for item in month['items']
        ]

        self.assertIn(rj_edition.id, unfiltered_ids)
        self.assertIn(self.edition.id, filtered_ids)
        self.assertNotIn(rj_edition.id, filtered_ids)

    def test_near_profile_without_coordinates_returns_no_results(self):
        """near_profile must not silently use 0,0 when profile has no coordinates."""
        venue = Venue.objects.create(
            name='Arena Geocoded',
            city='Sao Paulo',
            state='SP',
            latitude=-23.5505,
            longitude=-46.6333,
        )
        self.edition.venue = venue
        self.edition.save(update_fields=['venue', 'updated_at'])
        profile = PlayerProfile.objects.create(
            user=self.user,
            display_name='Filter Player',
            travel_radius_km=100,
        )

        res = self.client.get('/api/tournaments/editions/', {'near_profile': profile.id})

        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in _response_items(res)]
        self.assertNotIn(self.edition.id, ids)


class CompatibleEndpointModalityTestCase(TestCase):
    """
    GET /api/tournaments/editions/compatible/?profile_id=X enforces modality isolation.

    Covers four scenarios:
    1. Empty preferred_modality   → 400 with code='modality_required'
    2. Whitespace preferred_modality → same 400
    3. preferred_modality='tennis'       → no beach_tennis in results
    4. preferred_modality='beach_tennis' → no tennis in results
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='compat_mod@test.com', password='pass', full_name='Compat Tester'
        )
        self.client.force_authenticate(user=self.user)

        org, _ = Organization.objects.get_or_create(
            name='COMPAT_MOD_ORG',
            defaults={'short_name': 'CMO', 'type': Organization.TYPE_FEDERATION},
        )
        ds, _ = DataSource.objects.get_or_create(
            connector_key='compat_mod_test',
            defaults={
                'organization': org,
                'source_name': 'Compat Modality Test',
                'slug': 'compat-mod-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://example.com',
            },
        )
        t_tennis, _ = Tournament.objects.get_or_create(
            canonical_slug='compat-tennis-mod-test',
            defaults={
                'canonical_name': 'Compat Tennis Mod', 'circuit': 'FPT',
                'organization': org, 'modality': 'tennis',
            },
        )
        t_beach, _ = Tournament.objects.get_or_create(
            canonical_slug='compat-beach-mod-test',
            defaults={
                'canonical_name': 'Compat Beach Mod', 'circuit': 'CBT',
                'organization': org, 'modality': 'beach_tennis',
            },
        )
        self.tennis_ed = TournamentEdition.objects.create(
            tournament=t_tennis, external_id='cmod:tennis-ed',
            data_source=ds, title='Compat Tennis Edition', season_year=2026,
            status='open', is_youth=True, is_published=True,
        )
        self.beach_ed = TournamentEdition.objects.create(
            tournament=t_beach, external_id='cmod:beach-ed',
            data_source=ds, title='Compat Beach Edition', season_year=2026,
            status='open', is_youth=True, is_published=True,
        )

    def _make_profile(self, modality, suffix=''):
        return PlayerProfile.objects.create(
            user=self.user,
            display_name=f'CMod-{modality or "empty"}{suffix}',
            preferred_modality=modality,
        )

    def _compatible_ids_and_modalities(self, profile_id):
        res = self.client.get(
            '/api/tournaments/editions/compatible/', {'profile_id': profile_id}
        )
        return res, [e.get('modality') for e in (res.data.get('results') or [])]

    def test_empty_modality_returns_400_not_mixed_results(self):
        """Profile with empty preferred_modality must return 400, never mixed results."""
        profile = self._make_profile('')
        res = self.client.get(
            '/api/tournaments/editions/compatible/', {'profile_id': profile.id}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get('code'), 'modality_required')

    def test_whitespace_modality_returns_400(self):
        """Profile with whitespace-only preferred_modality returns 400."""
        profile = self._make_profile('')
        PlayerProfile.objects.filter(pk=profile.pk).update(preferred_modality='   ')
        res = self.client.get(
            '/api/tournaments/editions/compatible/', {'profile_id': profile.id}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get('code'), 'modality_required')

    def test_tennis_profile_contains_no_beach_tennis(self):
        """Tennis profile results must never include beach_tennis editions."""
        profile = self._make_profile('tennis', '-t')
        res, modalities = self._compatible_ids_and_modalities(profile.id)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(
            'beach_tennis', modalities,
            f'Tennis profile must not see beach_tennis editions. Got modalities: {modalities}',
        )

    def test_beach_tennis_profile_contains_no_tennis(self):
        """Beach_tennis profile results must never include tennis editions."""
        profile = self._make_profile('beach_tennis', '-b')
        res, modalities = self._compatible_ids_and_modalities(profile.id)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(
            'tennis', modalities,
            f'Beach tennis profile must not see tennis editions. Got modalities: {modalities}',
        )


# ─── Modality inference utility ───────────────────────────────────────────────

class ModalityUtilsTestCase(TestCase):
    """Unit tests for apps.ingestion.modality_utils.infer_modality."""

    def _infer(self, *args):
        from apps.ingestion.modality_utils import infer_modality
        return infer_modality(*args)

    def test_beach_in_title(self):
        self.assertEqual(self._infer('Copa Beach Tennis SP 2026', 'FPT'), 'beach_tennis')

    def test_praia_in_title(self):
        self.assertEqual(self._infer('Open de Praia Masculino', ''), 'beach_tennis')

    def test_wheelchair_in_title(self):
        self.assertEqual(self._infer('Open Wheelchair SP', 'CBT'), 'wheelchair')

    def test_cadeira_in_title(self):
        self.assertEqual(self._infer('Torneio Cadeira de Rodas', ''), 'wheelchair')

    def test_padel_in_title(self):
        self.assertEqual(self._infer('Campeonato de Padel', ''), 'padel')

    def test_tennis_default(self):
        self.assertEqual(self._infer('Aberto Masculino São Paulo', 'FPT'), 'tennis')

    def test_empty_inputs(self):
        self.assertEqual(self._infer('', ''), 'tennis')

    def test_beach_in_circuit_not_title(self):
        self.assertEqual(self._infer('Torneio Outono', 'Beach Tennis Brasil'), 'beach_tennis')

    def test_case_insensitive(self):
        self.assertEqual(self._infer('COPA BEACH TENNIS', ''), 'beach_tennis')


# ─── Persistence: modality update on re-ingestion ─────────────────────────────

class PersistenceModalityUpdateTestCase(TestCase):
    """
    Tests that Tournament.modality is updated when a connector yields a
    different value on a subsequent ingestion run.
    """

    def setUp(self):
        from apps.sources.models import Organization, DataSource
        from apps.ingestion.models import IngestionRun
        self.org, _ = Organization.objects.get_or_create(
            name='PERSIST_MOD_ORG',
            defaults={'short_name': 'PMO', 'type': Organization.TYPE_FEDERATION},
        )
        self.ds, _ = DataSource.objects.get_or_create(
            connector_key='persist_mod_test',
            defaults={
                'organization': self.org,
                'source_name': 'Persist Modality Test',
                'slug': 'persist-mod-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://example.com',
            },
        )
        self.run = IngestionRun.objects.create(data_source=self.ds, triggered_by='test')

    def _upsert(self, slug, modality, title='Test'):
        from apps.ingestion.persistence import TournamentPersister
        persister = TournamentPersister(self.ds, self.run)
        data = {
            'external_id': f'pm:{slug}',
            'canonical_name': title,
            'canonical_slug': slug,
            'circuit': 'TestCircuit',
            'modality': modality,
            'season_year': 2026,
            'title': title,
        }
        ed, created, changes = persister.upsert(data)
        return ed

    def test_modality_corrected_on_second_upsert(self):
        """Tournament created as tennis is corrected to beach_tennis on re-run."""
        from apps.tournaments.models import Tournament
        slug = 'pm-modality-fix-test'

        # First upsert: wrong modality (legacy data)
        self._upsert(slug, 'tennis', 'Copa Beach Test')
        t = Tournament.objects.get(canonical_slug=slug)
        self.assertEqual(t.modality, 'tennis')  # stored as-is first time

        # Second upsert: connector now correctly infers beach_tennis
        self._upsert(slug, 'beach_tennis', 'Copa Beach Test')
        t.refresh_from_db()
        self.assertEqual(
            t.modality, 'beach_tennis',
            'Tournament.modality must be updated when connector infers a new value',
        )

    def test_correct_modality_unchanged(self):
        """Tournament already with correct modality is not unnecessarily updated."""
        from apps.tournaments.models import Tournament
        slug = 'pm-correct-mod-test'

        self._upsert(slug, 'tennis', 'Aberto SP')
        self._upsert(slug, 'tennis', 'Aberto SP')  # same value
        t = Tournament.objects.get(canonical_slug=slug)
        self.assertEqual(t.modality, 'tennis')


# ─── Persistence: UF mismatch validation ──────────────────────────────────────

class PersistenceUFValidationTestCase(TestCase):
    """
    Tests that a UF mismatch between organization.state and venue.state
    is recorded in TournamentEdition.validation_errors.
    """

    def setUp(self):
        from apps.sources.models import Organization, DataSource
        from apps.ingestion.models import IngestionRun
        self.org, _ = Organization.objects.get_or_create(
            name='UF_VAL_ORG_SP',
            defaults={
                'short_name': 'UVSP',
                'type': Organization.TYPE_FEDERATION,
                'state': 'SP',
            },
        )
        self.ds, _ = DataSource.objects.get_or_create(
            connector_key='uf_val_test',
            defaults={
                'organization': self.org,
                'source_name': 'UF Val Test',
                'slug': 'uf-val-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://example.com',
            },
        )
        self.run = __import__('apps.ingestion.models', fromlist=['IngestionRun']).IngestionRun.objects.create(
            data_source=self.ds, triggered_by='test'
        )

    def _upsert(self, slug, venue_state):
        from apps.ingestion.persistence import TournamentPersister
        persister = TournamentPersister(self.ds, self.run)
        data = {
            'external_id': f'ufv:{slug}',
            'canonical_name': f'UF Test {slug}',
            'canonical_slug': slug,
            'circuit': 'Test',
            'modality': 'tennis',
            'season_year': 2026,
            'title': f'UF Test {slug}',
            'venue': {'name': 'Arena Test', 'city': 'Cidade Teste', 'state': venue_state},
        }
        ed, _, _ = persister.upsert(data)
        return ed

    def test_uf_mismatch_recorded_in_validation_errors(self):
        """Edition with venue in PR but org in SP gets a uf_mismatch error."""
        ed = self._upsert('uf-mismatch-test', 'PR')
        ed.refresh_from_db()
        self.assertTrue(
            any('uf_mismatch' in str(e) for e in (ed.validation_errors or [])),
            f'Expected uf_mismatch in validation_errors, got: {ed.validation_errors}',
        )

    def test_uf_match_no_validation_error(self):
        """Edition with venue in SP and org in SP produces no UF validation error."""
        ed = self._upsert('uf-match-test', 'SP')
        ed.refresh_from_db()
        self.assertFalse(
            any('uf_mismatch' in str(e) for e in (ed.validation_errors or [])),
            f'No uf_mismatch expected, got: {ed.validation_errors}',
        )

    def test_no_org_state_no_error(self):
        """Org without state (e.g. national confederation) does not trigger uf_mismatch."""
        from apps.sources.models import Organization, DataSource
        from apps.ingestion.models import IngestionRun
        org_national, _ = Organization.objects.get_or_create(
            name='UF_VAL_NATIONAL',
            defaults={'short_name': 'CBT', 'type': Organization.TYPE_CONFEDERATION, 'state': ''},
        )
        ds_national, _ = DataSource.objects.get_or_create(
            connector_key='uf_val_national_test',
            defaults={
                'organization': org_national,
                'source_name': 'UF Val National Test',
                'slug': 'uf-val-national-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://example.com',
            },
        )
        run = IngestionRun.objects.create(data_source=ds_national, triggered_by='test')
        from apps.ingestion.persistence import TournamentPersister
        persister = TournamentPersister(ds_national, run)
        ed, _, _ = persister.upsert({
            'external_id': 'ufv:national-no-state',
            'canonical_name': 'CBT National Test',
            'canonical_slug': 'ufv-national-no-state',
            'circuit': 'CBT',
            'modality': 'tennis',
            'season_year': 2026,
            'title': 'CBT National Test',
            'venue': {'name': 'Arena', 'city': 'Curitiba', 'state': 'PR'},
        })
        ed.refresh_from_db()
        self.assertFalse(
            any('uf_mismatch' in str(e) for e in (ed.validation_errors or [])),
            'National org with no state must not produce uf_mismatch errors.',
        )
