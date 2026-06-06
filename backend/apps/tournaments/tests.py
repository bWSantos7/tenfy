"""
Tests for tournament filters, views, modality isolation and UF validation.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.players.models import PlayerCategory, PlayerProfile, PlayerProfileCategory
from apps.sources.models import Organization, DataSource
from apps.tournaments.models import Tournament, TournamentCategory, TournamentEdition, Venue

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

class YouthCategoryPromotionCompatibilityTestCase(TestCase):
    """Business rules for youth category promotion by tournament circuit."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='youth_rules@test.com', password='pass', full_name='Youth Rules'
        )
        self.client.force_authenticate(user=self.user)
        self.categories = {
            age: PlayerCategory.objects.get_or_create(
                taxonomy=PlayerCategory.TAXONOMY_CBT_AGE,
                code=f'{age}M',
                gender_scope='M',
                defaults={
                    'label_ptbr': f'Sub-{age} Masculino',
                    'min_age': age,
                    'max_age': age,
                },
            )[0]
            for age in (12, 14, 16, 18)
        }
        self.orgs = {
            'FPT': self._org('Youth Rules FPT', 'FPT', Organization.TYPE_FEDERATION, 'SP'),
            'CBT': self._org('Youth Rules CBT', 'CBT', Organization.TYPE_CONFEDERATION, ''),
            'COSAT': self._org('Youth Rules COSAT', 'COSAT', Organization.TYPE_CONFEDERATION, ''),
            'ITF': self._org('Youth Rules ITF', 'ITF', Organization.TYPE_CONFEDERATION, ''),
        }

    def _org(self, name, short_name, org_type, state):
        return Organization.objects.create(
            name=name,
            short_name=short_name,
            type=org_type,
            state=state,
        )

    def _profile(self, age):
        return PlayerProfile.objects.create(
            user=self.user,
            display_name=f'Atleta {age}',
            birth_year=timezone.now().year - age,
            gender='M',
            preferred_modality='tennis',
            competitive_level=PlayerProfile.LEVEL_YOUTH,
        )

    def _edition(self, org_key, slug, title, category_text, normalized_age=None, start_date='2026-07-10'):
        org = self.orgs[org_key]
        tournament = Tournament.objects.create(
            canonical_name=title,
            canonical_slug=slug,
            organization=org,
            circuit=org_key,
            modality='tennis',
        )
        edition = TournamentEdition.objects.create(
            tournament=tournament,
            external_id=f'{org_key.lower()}:{slug}',
            title=title,
            season_year=2026,
            status=TournamentEdition.STATUS_OPEN,
            start_date=start_date,
            is_youth=True,
            is_published=True,
        )
        TournamentCategory.objects.create(
            edition=edition,
            source_category_text=category_text,
            normalized_category=self.categories.get(normalized_age) if normalized_age else None,
        )
        return edition

    def _compatible_ids(self, profile, **params):
        response = self.client.get(
            '/api/tournaments/editions/compatible/',
            {'profile_id': profile.id, 'page_size': 100, **params},
        )
        self.assertEqual(response.status_code, 200, response.data)
        return [item['id'] for item in response.data.get('results', [])]

    def test_default_listing_shows_only_official_category(self):
        profile = self._profile(14)
        official = self._edition('CBT', 'default-14', 'CBT Sub-14', '14M', 14)
        superior = self._edition('CBT', 'default-16', 'CBT Sub-16', '16M', 16)

        ids = self._compatible_ids(profile)

        self.assertIn(official.id, ids)
        self.assertNotIn(superior.id, ids)

    def test_default_listing_uses_home_state_when_travel_states_empty(self):
        profile = self._profile(14)
        profile.home_city = 'Sao Jose do Rio Preto'
        profile.home_state = 'SP'
        profile.travel_radius_km = 100
        profile.travel_states = []
        profile.save(update_fields=['home_city', 'home_state', 'travel_radius_km', 'travel_states'])
        venue = Venue.objects.create(name='Arena Ribeirao', city='Ribeirao Preto', state='SP')
        official = self._edition('FPT', 'same-state-14', 'FPT Sub-14 SP', '14M', 14)
        official.venue = venue
        official.save(update_fields=['venue'])

        ids = self._compatible_ids(profile)

        self.assertIn(official.id, ids)

    def test_default_listing_accepts_raw_embedded_age_gender_code(self):
        profile = self._profile(14)
        raw_rank = self._edition(
            'FPT',
            'raw-ranking-14m',
            'FPT Ranking Raw Sub-14',
            'Ranking Infantojuvenil 2026 - 14M',
        )
        raw_superior = self._edition(
            'FPT',
            'raw-ranking-16m',
            'FPT Ranking Raw Sub-16',
            'Ranking Infantojuvenil 2026 - 16M',
        )

        ids = self._compatible_ids(profile)

        self.assertIn(raw_rank.id, ids)
        self.assertNotIn(raw_superior.id, ids)

    def test_advanced_filter_allows_paulista_up_to_two_categories(self):
        profile = self._profile(12)
        sub16 = self._edition('FPT', 'fpt-16', 'Paulista Sub-16', '16M', 16)
        sub18 = self._edition('FPT', 'fpt-18', 'Paulista Sub-18', '18M', 18)

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(sub16.id, ids)
        self.assertNotIn(sub18.id, ids)

    def test_advanced_filter_allows_brasileiro_only_one_category(self):
        profile = self._profile(14)
        sub16 = self._edition('CBT', 'cbt-16', 'Brasileiro Sub-16', '16M', 16)
        sub18 = self._edition('CBT', 'cbt-18', 'Brasileiro Sub-18', '18M', 18)

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(sub16.id, ids)
        self.assertNotIn(sub18.id, ids)

    def test_category_filter_blocks_brasileiro_above_limit(self):
        profile = self._profile(14)
        sub18 = self._edition('CBT', 'cbt-filter-18', 'Brasileiro Filtrado Sub-18', '18M', 18)

        ids = self._compatible_ids(profile, category='18')

        self.assertNotIn(sub18.id, ids)

    def test_cosat_only_uses_14_and_16_categories(self):
        profile = self._profile(14)
        sub14 = self._edition('COSAT', 'cosat-14', 'COSAT U14', 'BS U14')
        sub16 = self._edition('COSAT', 'cosat-16', 'COSAT U16', 'BS U16')
        sub18 = self._edition('COSAT', 'cosat-18', 'COSAT U18', 'BS U18')

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(sub14.id, ids)
        self.assertIn(sub16.id, ids)
        self.assertNotIn(sub18.id, ids)

    def test_itf_junior_is_treated_as_18_only_in_advanced_listing(self):
        profile = self._profile(14)
        itf = self._edition('ITF', 'itf-junior', 'ITF Junior J30', 'Boys Singles')

        default_ids = self._compatible_ids(profile)
        advanced_ids = self._compatible_ids(profile, include_category_up='true')

        self.assertNotIn(itf.id, default_ids)
        self.assertIn(itf.id, advanced_ids)

    def test_cosat_and_itf_can_coexist_on_same_calendar_date(self):
        profile = self._profile(16)
        cosat = self._edition(
            'COSAT',
            'same-date-cosat',
            'COSAT Same Date',
            'BS U16',
            start_date='2026-08-01',
        )
        itf = self._edition(
            'ITF',
            'same-date-itf',
            'ITF Junior Same Date',
            'Boys Singles',
            start_date='2026-08-01',
        )

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(cosat.id, ids)
        self.assertIn(itf.id, ids)

    # ── Sub-12 explicit tests ──────────────────────────────────────────────────

    def test_sub12_default_listing_shows_only_sub12(self):
        """Sub-12 player sees only Sub-12 in default listing — never Sub-14/16/18."""
        profile = self._profile(12)
        sub12 = self._edition('CBT', 'cbt-12-12', 'CBT Sub-12', '12M', 12)
        sub14 = self._edition('CBT', 'cbt-12-14', 'CBT Sub-14', '14M', 14)
        sub16 = self._edition('CBT', 'cbt-12-16', 'CBT Sub-16', '16M', 16)
        sub18 = self._edition('CBT', 'cbt-12-18', 'CBT Sub-18', '18M', 18)

        ids = self._compatible_ids(profile)

        self.assertIn(sub12.id, ids)
        self.assertNotIn(sub14.id, ids)
        self.assertNotIn(sub16.id, ids)
        self.assertNotIn(sub18.id, ids)

    def test_sub12_brasileiro_advanced_only_one_above(self):
        """Sub-12 via Brasileiro advanced filter: sees Sub-12 and Sub-14 only."""
        profile = self._profile(12)
        sub12 = self._edition('CBT', 'bra-12-12', 'Brasileiro Sub-12', '12M', 12)
        sub14 = self._edition('CBT', 'bra-12-14', 'Brasileiro Sub-14', '14M', 14)
        sub16 = self._edition('CBT', 'bra-12-16', 'Brasileiro Sub-16', '16M', 16)

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(sub12.id, ids)
        self.assertIn(sub14.id, ids)
        self.assertNotIn(sub16.id, ids)

    def test_sub12_paulista_advanced_up_to_two_above(self):
        """Sub-12 via Paulista advanced filter: sees Sub-12, Sub-14 and Sub-16 only."""
        profile = self._profile(12)
        sub14 = self._edition('FPT', 'pau-12-14', 'Paulista Sub-14', '14M', 14)
        sub16 = self._edition('FPT', 'pau-12-16', 'Paulista Sub-16', '16M', 16)
        sub18 = self._edition('FPT', 'pau-12-18', 'Paulista Sub-18', '18M', 18)

        ids = self._compatible_ids(profile, include_category_up='true')

        self.assertIn(sub14.id, ids)
        self.assertIn(sub16.id, ids)
        self.assertNotIn(sub18.id, ids)

    # ── Gender filter tests ────────────────────────────────────────────────────

    def _profile_gendered(self, age, gender, modality='tennis'):
        return PlayerProfile.objects.create(
            user=self.user,
            display_name=f'Atleta {age} {gender}',
            birth_year=timezone.now().year - age,
            gender=gender,
            preferred_modality=modality,
            competitive_level=PlayerProfile.LEVEL_YOUTH,
        )

    def _edition_gendered(self, org_key, slug, title, category_text, normalized_age=None, gender_scope='M'):
        org = self.orgs[org_key]
        normalized_cat = None
        if normalized_age is not None:
            normalized_cat, _ = PlayerCategory.objects.get_or_create(
                taxonomy=PlayerCategory.TAXONOMY_CBT_AGE,
                code=f'{normalized_age}{gender_scope}',
                gender_scope=gender_scope,
                defaults={
                    'label_ptbr': f'Sub-{normalized_age} {gender_scope}',
                    'min_age': normalized_age,
                    'max_age': normalized_age,
                },
            )
        tournament = Tournament.objects.create(
            canonical_name=title,
            canonical_slug=slug,
            organization=org,
            circuit=org_key,
            modality='tennis',
        )
        edition = TournamentEdition.objects.create(
            tournament=tournament,
            external_id=f'{org_key.lower()}:{slug}',
            title=title,
            season_year=2026,
            status=TournamentEdition.STATUS_OPEN,
            start_date='2026-07-10',
            is_youth=True,
            is_published=True,
        )
        TournamentCategory.objects.create(
            edition=edition,
            source_category_text=category_text,
            normalized_category=normalized_cat,
        )
        return edition

    def test_male_profile_does_not_see_female_categories(self):
        """Male athlete must not receive female-only tournament categories."""
        profile = self._profile_gendered(14, 'M')
        female_ed = self._edition_gendered('CBT', 'gender-14f', 'CBT Sub-14 Fem', '14F', 14, 'F')
        male_ed = self._edition_gendered('CBT', 'gender-14m', 'CBT Sub-14 Masc', '14M', 14, 'M')

        ids = self._compatible_ids(profile)

        self.assertIn(male_ed.id, ids)
        self.assertNotIn(female_ed.id, ids)

    def test_female_profile_does_not_see_male_categories(self):
        """Female athlete must not receive male-only tournament categories."""
        profile = self._profile_gendered(14, 'F')
        female_ed = self._edition_gendered('CBT', 'gender-f14', 'CBT Sub-14 Fem-v2', '14F', 14, 'F')
        male_ed = self._edition_gendered('CBT', 'gender-m14', 'CBT Sub-14 Masc-v2', '14M', 14, 'M')

        ids = self._compatible_ids(profile)

        self.assertIn(female_ed.id, ids)
        self.assertNotIn(male_ed.id, ids)

    def test_mixed_category_visible_to_both_genders(self):
        """Mixed-gender category (gender_scope='X') must appear for both M and F."""
        male_profile = self._profile_gendered(14, 'M')
        female_profile = self._profile_gendered(14, 'F')
        mixed_cat, _ = PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_CBT_AGE,
            code='14X',
            gender_scope='X',
            defaults={'label_ptbr': 'Sub-14 Misto', 'min_age': 14, 'max_age': 14},
        )
        org = self.orgs['CBT']
        tournament = Tournament.objects.create(
            canonical_name='CBT Sub-14 Misto',
            canonical_slug='cbt-sub14-misto-x',
            organization=org,
            circuit='CBT',
            modality='tennis',
        )
        edition = TournamentEdition.objects.create(
            tournament=tournament,
            external_id='cbt:sub14-misto-x',
            title='CBT Sub-14 Misto',
            season_year=2026,
            status=TournamentEdition.STATUS_OPEN,
            start_date='2026-07-10',
            is_youth=True,
            is_published=True,
        )
        TournamentCategory.objects.create(
            edition=edition,
            source_category_text='14X',
            normalized_category=mixed_cat,
        )

        male_ids = self._compatible_ids(male_profile)
        female_ids = self._compatible_ids(female_profile)

        self.assertIn(edition.id, male_ids, 'Mixed category must appear for male profile')
        self.assertIn(edition.id, female_ids, 'Mixed category must appear for female profile')

    # ── State / location filter tests ──────────────────────────────────────────

    def test_tournament_outside_accepted_states_not_shown(self):
        """If athlete only plays in SP, tournaments in other states must not appear."""
        profile = self._profile(14)
        profile.travel_states = ['SP']
        profile.home_state = 'SP'
        profile.save(update_fields=['travel_states', 'home_state'])

        sp_venue = Venue.objects.create(name='Arena SP Loc', city='Sao Paulo', state='SP')
        rj_venue = Venue.objects.create(name='Arena RJ Loc', city='Rio de Janeiro', state='RJ')

        sp_edition = self._edition('CBT', 'state-sp-14', 'CBT SP', '14M', 14)
        sp_edition.venue = sp_venue
        sp_edition.save(update_fields=['venue'])

        rj_edition = self._edition('CBT', 'state-rj-14', 'CBT RJ', '14M', 14)
        rj_edition.venue = rj_venue
        rj_edition.save(update_fields=['venue'])

        ids = self._compatible_ids(profile)

        self.assertIn(sp_edition.id, ids, 'SP tournament must appear for SP-only athlete')
        self.assertNotIn(rj_edition.id, ids, 'RJ tournament must not appear for SP-only athlete')

    def test_tournament_in_accepted_state_shown_when_multiple_states(self):
        """Athlete accepting SP and SC must see tournaments in both states."""
        profile = self._profile(14)
        profile.travel_states = ['SP', 'SC']
        profile.save(update_fields=['travel_states'])

        sc_venue = Venue.objects.create(name='Arena SC Loc', city='Florianopolis', state='SC')
        sc_edition = self._edition('CBT', 'state-sc-14', 'CBT SC', '14M', 14)
        sc_edition.venue = sc_venue
        sc_edition.save(update_fields=['venue'])

        ids = self._compatible_ids(profile)
        self.assertIn(sc_edition.id, ids, 'SC tournament must appear when SC is in travel_states')

    # ── Profile switching test ─────────────────────────────────────────────────

    def test_different_profiles_return_different_results(self):
        """Switching to a different profile immediately changes compatible results."""
        sub12_profile = self._profile(12)
        sub16_profile = self._profile(16)

        sub12_ed = self._edition('CBT', 'switch-12', 'CBT Switch Sub-12', '12M', 12)
        sub16_ed = self._edition('CBT', 'switch-16', 'CBT Switch Sub-16', '16M', 16)

        ids_sub12 = self._compatible_ids(sub12_profile)
        ids_sub16 = self._compatible_ids(sub16_profile)

        self.assertIn(sub12_ed.id, ids_sub12)
        self.assertNotIn(sub16_ed.id, ids_sub12,
                         'Sub-16 tournament must not appear for Sub-12 profile')
        self.assertIn(sub16_ed.id, ids_sub16)
        self.assertNotIn(sub12_ed.id, ids_sub16,
                         'Sub-12 tournament must not appear for Sub-16 profile')

    def test_cache_is_profile_specific(self):
        """Compatible results are cached per profile — switching profiles bypasses wrong cache."""
        cache.clear()
        sub12_profile = self._profile(12)
        sub16_profile = self._profile(16)

        sub12_ed = self._edition('CBT', 'cache-12', 'CBT Cache Sub-12', '12M', 12)
        sub16_ed = self._edition('CBT', 'cache-16', 'CBT Cache Sub-16', '16M', 16)

        # Warm cache for Sub-12
        ids_sub12_first = self._compatible_ids(sub12_profile)
        # Warm cache for Sub-16
        ids_sub16_first = self._compatible_ids(sub16_profile)

        # Second call must return same profile-specific results (not bleed between caches)
        ids_sub12_second = self._compatible_ids(sub12_profile)
        ids_sub16_second = self._compatible_ids(sub16_profile)

        self.assertEqual(set(ids_sub12_first), set(ids_sub12_second))
        self.assertEqual(set(ids_sub16_first), set(ids_sub16_second))
        self.assertNotIn(sub16_ed.id, ids_sub12_second,
                         'Sub-16 tournament must never appear in Sub-12 profile results')
        self.assertNotIn(sub12_ed.id, ids_sub16_second,
                         'Sub-12 tournament must never appear in Sub-16 profile results')

    def test_clearing_filters_does_not_break_modality_isolation(self):
        """Even after clearing all filters, modality must remain mandatory."""
        tennis_profile = self._profile(14)

        org = self.orgs['CBT']
        bt_tournament = Tournament.objects.create(
            canonical_name='Beach Tennis CBT',
            canonical_slug='beach-tennis-cbt-clear',
            organization=org,
            circuit='CBT',
            modality='beach_tennis',
        )
        bt_edition = TournamentEdition.objects.create(
            tournament=bt_tournament,
            external_id='cbt:beach-tennis-clear',
            title='Beach Tennis CBT',
            season_year=2026,
            status=TournamentEdition.STATUS_OPEN,
            start_date='2026-07-10',
            is_youth=True,
            is_published=True,
        )
        TournamentCategory.objects.create(
            edition=bt_edition,
            source_category_text='14M',
            normalized_category=self.categories[14],
        )

        ids = self._compatible_ids(tennis_profile)
        self.assertNotIn(bt_edition.id, ids,
                         'Beach tennis edition must never appear for tennis profile even with cleared filters')


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


class CompatibleStatusOrderingTestCase(TestCase):
    """
    Regression: the "torneios compatíveis" endpoint must return ONLY editions whose
    live (dynamic) status is acionável — Inscrições abertas / Encerrando em breve /
    Anunciado — and must not let old finished/in-progress/closed editions crowd the
    first page (which the clients then strip, leaving the user with an empty list).

    Root cause that this guards against: candidate ordering was `start_date ASC`, so the
    oldest (already finished) editions filled the paginated page even though plenty of
    compatible OPEN editions existed further down the list.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='compat_status@test.com', password='pass', full_name='Compat Status'
        )
        self.client.force_authenticate(user=self.user)
        self.now = timezone.now()
        self.cat14 = PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_CBT_AGE, code='14M', gender_scope='M',
            defaults={'label_ptbr': 'Sub-14 Masculino', 'min_age': 14, 'max_age': 14},
        )[0]
        self.org = Organization.objects.create(
            name='Compat Status CBT', short_name='CBT',
            type=Organization.TYPE_CONFEDERATION, state='',
        )
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name='Atleta 14', birth_year=self.now.year - 14,
            gender='M', preferred_modality='tennis',
            competitive_level=PlayerProfile.LEVEL_YOUTH, travel_states=['SP'],
        )
        self.venue = Venue.objects.create(name='Arena SP', city='Sao Paulo', state='SP')

    def _edition(self, slug, *, stored_status='unknown', start_date=None,
                 end_date=None, entry_open_at=None, entry_close_at=None):
        tournament = Tournament.objects.create(
            canonical_name=slug, canonical_slug=slug, organization=self.org,
            circuit='CBT', modality='tennis',
        )
        edition = TournamentEdition.objects.create(
            tournament=tournament, external_id=f'cbt:{slug}', title=slug,
            season_year=self.now.year, status=stored_status,
            start_date=start_date, end_date=end_date,
            entry_open_at=entry_open_at, entry_close_at=entry_close_at,
            venue=self.venue, is_youth=True, is_published=True,
        )
        TournamentCategory.objects.create(
            edition=edition, source_category_text='14M', normalized_category=self.cat14,
        )
        return edition

    def _compatible(self, **params):
        response = self.client.get(
            '/api/tournaments/editions/compatible/',
            {'profile_id': self.profile.id, 'page_size': 100, **params},
        )
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data.get('results', [])

    def test_only_active_status_editions_are_returned(self):
        from datetime import timedelta
        day = timedelta(days=1)
        active_open = self._edition(
            'active-open', start_date=(self.now + 20 * day).date(),
            entry_close_at=self.now + 10 * day,
        )
        active_closing = self._edition(
            'active-closing', start_date=(self.now + 5 * day).date(),
            entry_close_at=self.now + 2 * day,
        )
        active_announced = self._edition(
            'active-announced', start_date=(self.now + 40 * day).date(),
        )
        # Inactive ones — must never appear.
        self._edition('finished', start_date=(self.now - 30 * day).date(),
                      end_date=(self.now - 25 * day).date())
        self._edition('in-progress', start_date=(self.now - 2 * day).date(),
                      end_date=(self.now + 2 * day).date())
        self._edition('closed', start_date=(self.now + 10 * day).date(),
                      entry_close_at=self.now - day)
        self._edition('canceled', stored_status=TournamentEdition.STATUS_CANCELED,
                      start_date=(self.now + 10 * day).date())

        ids = {item['id'] for item in self._compatible()}
        self.assertIn(active_open.id, ids)
        self.assertIn(active_closing.id, ids)
        self.assertIn(active_announced.id, ids)
        self.assertEqual(len(ids), 3, 'Only the three active editions must be returned.')
        statuses = {item['dynamic_status'] for item in self._compatible()}
        self.assertTrue(statuses <= {'open', 'closing_soon', 'announced'}, statuses)

    def test_old_finished_editions_do_not_crowd_out_active_on_first_page(self):
        """The regression itself: many old finished editions + one future OPEN one."""
        from datetime import timedelta
        day = timedelta(days=1)
        for i in range(25):
            self._edition(
                f'old-finished-{i}', start_date=(self.now - (60 - i) * day).date(),
                end_date=(self.now - (59 - i) * day).date(),
            )
        active = self._edition(
            'the-open-one', start_date=(self.now + 30 * day).date(),
            entry_close_at=self.now + 15 * day,
        )

        # Even with a small page, the active edition must be present (it is not buried
        # behind 25 finished editions, because finished ones are excluded server-side).
        response = self.client.get(
            '/api/tournaments/editions/compatible/',
            {'profile_id': self.profile.id, 'page_size': 10},
        )
        self.assertEqual(response.status_code, 200, response.data)
        ids = [item['id'] for item in response.data.get('results', [])]
        self.assertIn(active.id, ids)
        self.assertEqual(response.data.get('count'), 1)

    def test_messy_stored_status_is_normalized_by_dynamic_status(self):
        """A messy/legacy stored status string must not break the allowlist: the
        dynamic status (from dates) decides. Future entry_close_at => open => shown."""
        from datetime import timedelta
        day = timedelta(days=1)
        ed = self._edition(
            'messy-status', stored_status='Inscrições Abertas',
            start_date=(self.now + 12 * day).date(), entry_close_at=self.now + 6 * day,
        )
        ids = {item['id'] for item in self._compatible()}
        self.assertIn(ed.id, ids)


class CountryFilterTestCase(TestCase):
    """Task 7: country filter + countries endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='country@test.com', password='pass', full_name='C')
        self.client.force_authenticate(user=self.user)
        self.cbt = Organization.objects.create(
            name='CBT País', short_name='CBT', type=Organization.TYPE_CONFEDERATION, state='',
        )
        self.cosat = Organization.objects.create(
            name='COSAT País', short_name='COSAT', type=Organization.TYPE_CONFEDERATION, state='',
        )

    def _edition(self, org, slug, *, city, state='', country='', country_code=''):
        venue = Venue.objects.create(name=f'V {slug}', city=city, state=state,
                                     country=country, country_code=country_code)
        t = Tournament.objects.create(canonical_name=slug, canonical_slug=slug, organization=org, modality='tennis')
        return TournamentEdition.objects.create(
            tournament=t, season_year=2026, title=slug, venue=venue, is_published=True,
        )

    def test_country_filter_argentina(self):
        arg = self._edition(self.cosat, 'cosat-arg', city='Rosario', state='AR', country='Argentina', country_code='ARG')
        self._edition(self.cosat, 'cosat-chl', city='Santiago', state='CH', country='Chile', country_code='CHL')
        self._edition(self.cbt, 'cbt-sp', city='São Paulo', state='SP')  # Brazilian federation, no code
        res = self.client.get('/api/tournaments/editions/?country=ARG')
        ids = {r['id'] for r in res.data['results']}
        self.assertEqual(ids, {arg.id})

    def test_country_filter_brazil_includes_empty_code(self):
        br_fed = self._edition(self.cbt, 'cbt-rj', city='Rio', state='RJ')          # country_code=''
        br_intl = self._edition(self.cosat, 'cosat-br', city='Porto Alegre', state='BR', country='Brasil', country_code='BRA')
        self._edition(self.cosat, 'cosat-uy', city='Montevideo', state='UR', country='Uruguai', country_code='URY')
        res = self.client.get('/api/tournaments/editions/?country=BRA')
        ids = {r['id'] for r in res.data['results']}
        self.assertEqual(ids, {br_fed.id, br_intl.id})

    def test_countries_endpoint(self):
        self._edition(self.cosat, 'cosat-arg2', city='Rosario', state='AR', country='Argentina', country_code='ARG')
        self._edition(self.cbt, 'cbt-sp2', city='São Paulo', state='SP')  # empty code → Brazil surfaced as BRA
        res = self.client.get('/api/tournaments/editions/countries/')
        self.assertIn('ARG', res.data)
        self.assertIn('BRA', res.data)

    def test_country_filter_multi_code(self):
        # ITF (IOC 'CHI') and COSAT (ISO 'CHL') both mean Chile; a comma-separated
        # value must match both.
        chi = self._edition(self.cosat, 'itf-chi', city='Santiago', country='Chile', country_code='CHI')
        chl = self._edition(self.cosat, 'cosat-chl2', city='Viña', state='CH', country='Chile', country_code='CHL')
        self._edition(self.cosat, 'cosat-arg3', city='Rosario', country_code='ARG')
        res = self.client.get('/api/tournaments/editions/?country=CHI,CHL')
        ids = {r['id'] for r in res.data['results']}
        self.assertEqual(ids, {chi.id, chl.id})
