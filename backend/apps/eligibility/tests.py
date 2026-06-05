"""Tests for eligibility: location utilities, rule engine, API endpoint."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from unittest.mock import MagicMock, patch

User = get_user_model()


# ─── Location tests ────────────────────────────────────────────────────────────

class HaversineTestCase(TestCase):
    def test_same_point_is_zero(self):
        from apps.eligibility.location import haversine_km
        self.assertAlmostEqual(haversine_km(-23.5, -46.6, -23.5, -46.6), 0.0, places=2)

    def test_sp_to_campinas_approx_100km(self):
        from apps.eligibility.location import haversine_km
        dist = haversine_km(-23.5505, -46.6333, -22.9056, -47.0608)
        self.assertGreater(dist, 80)
        self.assertLess(dist, 120)

    def test_sp_to_rio_approx_350km(self):
        from apps.eligibility.location import haversine_km
        dist = haversine_km(-23.5505, -46.6333, -22.9068, -43.1729)
        self.assertGreater(dist, 300)
        self.assertLess(dist, 400)


class WithinProfileRadiusTestCase(TestCase):
    def _make_profile(self, city='São Paulo', state='SP', radius=100, lat=None, lng=None):
        p = MagicMock()
        p.home_city = city; p.home_state = state
        p.travel_radius_km = radius; p.home_lat = lat; p.home_lng = lng
        return p

    def _make_edition(self, city='São Paulo', state='SP', lat=None, lng=None):
        venue = MagicMock()
        venue.city = city; venue.state = state
        venue.address = ''; venue.latitude = lat; venue.longitude = lng
        ed = MagicMock(); ed.venue = venue
        return ed

    def test_same_city_returns_true(self):
        from apps.eligibility.location import within_profile_radius
        self.assertTrue(within_profile_radius(self._make_profile(), self._make_edition()))

    def test_within_radius_with_coords(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile(radius=200, lat=-23.5505, lng=-46.6333)
        ed = self._make_edition(city='Campinas', state='SP', lat=-22.9056, lng=-47.0608)
        self.assertTrue(within_profile_radius(p, ed))

    def test_outside_radius_returns_false(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile(radius=100, lat=-23.5505, lng=-46.6333)
        ed = self._make_edition(city='Rio de Janeiro', state='RJ', lat=-22.9068, lng=-43.1729)
        self.assertFalse(within_profile_radius(p, ed))

    def test_no_home_city_returns_true(self):
        from apps.eligibility.location import within_profile_radius
        self.assertTrue(within_profile_radius(self._make_profile(city='', state=''), self._make_edition()))

    def test_no_venue_includes_optimistically(self):
        # When venue data is missing, we include the tournament optimistically
        # rather than silently hiding it. Geocoding failure = uncertain, not excluded.
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile()
        ed = MagicMock(); ed.venue = None
        self.assertTrue(within_profile_radius(p, ed))


# ─── Category normalization tests ──────────────────────────────────────────────

class CategoryNormalizationTestCase(TestCase):
    """
    normalize_category_text() returns a PlayerCategory ORM object (from DB)
    or None when no match found. Tests verify regex matching logic by checking
    what DB rows are created/retrieved, not the internal dict format.
    """
    def setUp(self):
        from apps.players.models import PlayerCategory
        # Use the correct lowercase taxonomy constants from the model
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS, code='1M', gender_scope='M',
            defaults={'label_ptbr': 'Classe 1 Masculino', 'class_level': 1}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_CLASS, code='2F', gender_scope='F',
            defaults={'label_ptbr': 'Classe 2 Feminino', 'class_level': 2}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_AGE, code='14M', gender_scope='M',
            defaults={'label_ptbr': '14 Anos Masc', 'min_age': 14, 'max_age': 14}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_AGE, code='18F', gender_scope='F',
            defaults={'label_ptbr': '18 Anos Fem', 'min_age': 18, 'max_age': 18}
        )
        # Clear lru_cache to force fresh DB lookups in each test
        from apps.eligibility.services_normalize import normalize_category_text
        normalize_category_text.cache_clear()

    def tearDown(self):
        from apps.eligibility.services_normalize import normalize_category_text
        normalize_category_text.cache_clear()

    def _normalize(self, text):
        from apps.eligibility.services_normalize import normalize_category_text
        return normalize_category_text(text)

    def test_fpt_class_male_found_in_db(self):
        result = self._normalize('1M')
        self.assertIsNotNone(result)
        self.assertEqual(result.gender_scope, 'M')

    def test_fpt_class_female_found_in_db(self):
        result = self._normalize('2F')
        self.assertIsNotNone(result)
        self.assertEqual(result.gender_scope, 'F')

    def test_age_category_14_male(self):
        result = self._normalize('14M')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 14)

    def test_age_category_18_female(self):
        result = self._normalize('18F')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 18)

    def test_unknown_category_returns_none(self):
        result = self._normalize('XYZABC_RANDOM_999')
        self.assertIsNone(result)


# ─── Eligibility API tests ─────────────────────────────────────────────────────

class EligibilityAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='elig@example.com', password='pass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_eligibility_endpoint_requires_auth(self):
        anon = APIClient()
        res = anon.get('/api/eligibility/evaluate/1/')
        self.assertIn(res.status_code, [401, 403, 404])

    def test_ruleset_list_accessible(self):
        # RuleSet list may be public or require auth — accept any non-500 response
        anon = APIClient()
        res = anon.get('/api/eligibility/rulesets/')
        self.assertNotIn(res.status_code, [500, 502, 503])

    def test_ruleset_list_authenticated(self):
        res = self.client.get('/api/eligibility/rulesets/')
        self.assertIn(res.status_code, [200, 403])

    def test_evaluate_nonexistent_edition_returns_error(self):
        res = self.client.get('/api/eligibility/evaluate/99999999/')
        # Returns 404 or 400 depending on implementation — both indicate "not found/invalid"
        self.assertIn(res.status_code, [400, 404])


# ─── EligibilityEngine default behaviour ──────────────────────────────────────

class EligibilityEngineDefaultsTestCase(TestCase):
    """EligibilityEngine must default to include_category_up=False (official category only)."""

    def _profile(self, age):
        from apps.players.models import PlayerProfile
        from django.utils import timezone
        p = MagicMock(spec=PlayerProfile)
        p.birth_year = timezone.now().year - age
        p.gender = 'M'
        p.tennis_class = ''
        p.external_ids = {}
        p.sporting_age = age
        return p

    def test_default_is_include_category_up_false(self):
        from apps.eligibility.services import EligibilityEngine
        engine = EligibilityEngine.__new__(EligibilityEngine)
        engine.__init__(self._profile(14))
        self.assertFalse(engine.include_category_up)

    def test_explicit_true_overrides_default(self):
        from apps.eligibility.services import EligibilityEngine
        engine = EligibilityEngine(self._profile(14), include_category_up=True)
        self.assertTrue(engine.include_category_up)


# ─── _apply_tournament_youth_policy: default listing ─────────────────────────

class TournamentYouthPolicyDefaultTestCase(TestCase):
    """
    _apply_tournament_youth_policy must block superior categories in default mode
    and allow them only in advanced mode within circuit-specific limits.
    """

    def _profile(self, age):
        from apps.players.models import PlayerProfile
        from django.utils import timezone
        p = MagicMock(spec=PlayerProfile)
        p.birth_year = timezone.now().year - age
        # sporting_age is a real @property on PlayerProfile; the mock must provide it
        # or official_youth_category_age() compares a MagicMock against an int.
        p.sporting_age = age
        p.gender = 'M'
        p.tennis_class = ''
        p.external_ids = {}
        return p

    def _make_tc(self, source_text, max_age, circuit_org_short):
        """Build a TournamentCategory mock with normalized_category and circuit info."""
        from apps.players.models import PlayerCategory
        norm = MagicMock(spec=PlayerCategory)
        norm.taxonomy = PlayerCategory.TAXONOMY_CBT_AGE
        norm.max_age = max_age
        norm.min_age = max_age
        norm.class_level = None
        norm.gender_scope = 'M'
        norm.code = f'{max_age}M'
        norm.label_ptbr = f'Sub-{max_age} M'

        org = MagicMock()
        org.short_name = circuit_org_short
        org.name = ''

        tournament = MagicMock()
        tournament.organization = org
        tournament.circuit = circuit_org_short
        tournament.modality = 'tennis'

        edition = MagicMock()
        edition.tournament = tournament
        edition.title = ''
        edition.external_id = ''

        tc = MagicMock()
        tc.normalized_category = norm
        tc.source_category_text = source_text
        tc.edition = edition
        tc.max_participants = None
        tc.edition_id = 1
        return tc

    def test_sub14_default_sees_own_category(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_COMPATIBLE
        engine = EligibilityEngine(self._profile(14), include_category_up=False)
        tc = self._make_tc('14M', 14, 'CBT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_sub14_default_blocks_sub16(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_INCOMPATIBLE
        engine = EligibilityEngine(self._profile(14), include_category_up=False)
        tc = self._make_tc('16M', 16, 'CBT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_sub12_default_blocks_sub18(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_INCOMPATIBLE
        engine = EligibilityEngine(self._profile(12), include_category_up=False)
        tc = self._make_tc('18M', 18, 'CBT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_sub12_paulista_advanced_allows_sub16(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_COMPATIBLE
        engine = EligibilityEngine(self._profile(12), include_category_up=True)
        tc = self._make_tc('16M', 16, 'FPT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_sub12_paulista_advanced_blocks_sub18(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_INCOMPATIBLE
        engine = EligibilityEngine(self._profile(12), include_category_up=True)
        tc = self._make_tc('18M', 18, 'FPT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_sub12_brasileiro_advanced_allows_sub14(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_COMPATIBLE
        engine = EligibilityEngine(self._profile(12), include_category_up=True)
        tc = self._make_tc('14M', 14, 'CBT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_sub12_brasileiro_advanced_blocks_sub16(self):
        from apps.eligibility.services import EligibilityEngine, STATUS_INCOMPATIBLE
        engine = EligibilityEngine(self._profile(12), include_category_up=True)
        tc = self._make_tc('16M', 16, 'CBT')
        result = engine.evaluate_category(tc)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)


# ─── Travel states tests ──────────────────────────────────────────────────────

class TravelStatesTestCase(TestCase):
    """within_profile_states: state-based location check."""

    def _make_profile(self, states, federation_state=''):
        p = MagicMock()
        p.travel_states = states
        # No federation by default — exercise the legacy travel_states path.
        # (A bare MagicMock attribute would be truthy and wrongly trigger the
        # federation branch, so set it explicitly.)
        p.federation_state = federation_state
        # Radius fallback fields — None causes within_profile_radius() to return
        # True optimistically (no home city → include), which is the expected
        # behaviour when travel_states is empty.
        p.travel_radius_km = None
        p.home_city = None
        p.home_state = None
        p.home_lat = None
        p.home_lng = None
        return p

    def _make_edition(self, state='SP'):
        venue = MagicMock(); venue.state = state
        ed = MagicMock(); ed.venue = venue
        return ed

    def setUp(self):
        from apps.eligibility.services_normalize import normalize_category_text
        normalize_category_text.cache_clear()

    def test_state_match_returns_true(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile(['SP', 'RJ', 'MG'])
        self.assertTrue(within_profile_states(p, self._make_edition('SP')))
        self.assertTrue(within_profile_states(p, self._make_edition('RJ')))
        self.assertTrue(within_profile_states(p, self._make_edition('MG')))

    def test_state_mismatch_returns_false(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile(['SP', 'RJ'])
        self.assertFalse(within_profile_states(p, self._make_edition('BA')))

    def test_empty_states_includes_optimistically(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile([])
        self.assertTrue(within_profile_states(p, self._make_edition('AM')))

    def test_empty_states_uses_home_state_when_available(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile([])
        p.home_state = 'SP'

        self.assertTrue(within_profile_states(p, self._make_edition('SP')))
        self.assertFalse(within_profile_states(p, self._make_edition('RJ')))

    def test_all_states_todo_brasil(self):
        from apps.eligibility.location import within_profile_states, ALL_BR_STATES
        p = self._make_profile(list(ALL_BR_STATES))
        self.assertTrue(within_profile_states(p, self._make_edition('AC')))
        self.assertTrue(within_profile_states(p, self._make_edition('TO')))

    def test_no_venue_state_includes_optimistically(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile(['SP'])
        venue = MagicMock(); venue.state = None
        ed = MagicMock(); ed.venue = venue
        self.assertTrue(within_profile_states(p, ed))

    def test_case_insensitive(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile(['sp', 'rj'])
        self.assertTrue(within_profile_states(p, self._make_edition('SP')))

    # ── Federation takes precedence over travel_states ──────────────────────

    def test_federation_state_matches(self):
        from apps.eligibility.location import within_profile_states
        # travel_states would include SP, but federation (RJ) is the source of truth.
        p = self._make_profile(['SP', 'MG'], federation_state='RJ')
        self.assertTrue(within_profile_states(p, self._make_edition('RJ')))

    def test_federation_state_mismatch(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile(['SP', 'MG'], federation_state='RJ')
        # SP is in travel_states but federation is RJ → SP tournament excluded.
        self.assertFalse(within_profile_states(p, self._make_edition('SP')))

    def test_federation_no_venue_state_optimistic(self):
        from apps.eligibility.location import within_profile_states
        p = self._make_profile([], federation_state='SP')
        venue = MagicMock(); venue.state = None
        ed = MagicMock(); ed.venue = venue
        self.assertTrue(within_profile_states(p, ed))

    def test_federation_result_message(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_OUTSIDE
        p = self._make_profile(['SP'], federation_state='RJ')
        res = profile_state_result(p, self._make_edition('SP'))
        self.assertFalse(res['included'])
        self.assertEqual(res['status'], DISTANCE_OUTSIDE)


# ─── COSAT / duplas eligibility tests ─────────────────────────────────────────

class CosatEligibilityTestCase(TestCase):
    """Raw text evaluation: COSAT BS/GS/BD/GD U-age, duplas por texto."""

    def _profile(self, age_birth_year_offset, gender):
        from apps.players.models import PlayerProfile
        from django.utils import timezone
        p = MagicMock(spec=PlayerProfile)
        p.birth_year = timezone.now().year - age_birth_year_offset
        p.gender = gender
        p.tennis_class = ''
        p.external_ids = {}
        return p

    def _engine(self, age, gender):
        from apps.eligibility.services import EligibilityEngine
        eng = EligibilityEngine.__new__(EligibilityEngine)
        from datetime import datetime
        eng._current_year = datetime.now().year
        eng.profile = self._profile(age, gender)
        return eng

    def _eval(self, age, gender, text):
        eng = self._engine(age, gender)
        return eng._evaluate_raw_text(text)

    # --- BS U12 – U18 ---
    def test_bs_u12_male_12_compatible(self):
        r = self._eval(12, 'M', 'BS U12')
        self.assertEqual(r.status, 'compatible')

    def test_bs_u14_male_12_compatible(self):
        r = self._eval(12, 'M', 'BS U14')
        self.assertEqual(r.status, 'compatible')

    def test_bs_u16_male_12_compatible(self):
        r = self._eval(12, 'M', 'BS U16')
        self.assertEqual(r.status, 'compatible')

    def test_bs_u18_male_12_compatible(self):
        r = self._eval(12, 'M', 'BS U18')
        self.assertEqual(r.status, 'compatible')

    def test_bs_u12_male_14_incompatible(self):
        r = self._eval(14, 'M', 'BS U12')
        self.assertEqual(r.status, 'incompatible')

    # --- GS U12 – U18 ---
    def test_gs_u12_female_12_compatible(self):
        r = self._eval(12, 'F', 'GS U12')
        self.assertEqual(r.status, 'compatible')

    def test_gs_u14_female_12_compatible(self):
        r = self._eval(12, 'F', 'GS U14')
        self.assertEqual(r.status, 'compatible')

    def test_gs_u12_female_14_incompatible(self):
        r = self._eval(14, 'F', 'GS U12')
        self.assertEqual(r.status, 'incompatible')

    # --- BD / GD ---
    def test_bd_u14_male_12_compatible(self):
        r = self._eval(12, 'M', 'BD U14')
        self.assertEqual(r.status, 'compatible')

    def test_gd_u16_female_15_compatible(self):
        r = self._eval(15, 'F', 'GD U16')
        self.assertEqual(r.status, 'compatible')

    def test_gd_u14_female_14_incompatible_age(self):
        # 14 anos em GD U12 = incompatível por idade
        r = self._eval(14, 'F', 'GD U12')
        self.assertEqual(r.status, 'incompatible')

    # --- Gender cross ---
    def test_bs_male_12_female_incompatible(self):
        r = self._eval(12, 'F', 'BS U14')
        self.assertEqual(r.status, 'incompatible')

    def test_gs_female_12_male_incompatible(self):
        r = self._eval(12, 'M', 'GS U14')
        self.assertEqual(r.status, 'incompatible')

    def test_bd_female_incompatible(self):
        r = self._eval(12, 'F', 'BD U14')
        self.assertEqual(r.status, 'incompatible')

    def test_gd_male_incompatible(self):
        r = self._eval(12, 'M', 'GD U14')
        self.assertEqual(r.status, 'incompatible')

    # --- Variants ---
    def test_cosat_nospace_bsu12(self):
        r = self._eval(12, 'M', 'BSU12')
        self.assertEqual(r.status, 'compatible')

    def test_cosat_nospace_gsu14(self):
        r = self._eval(12, 'F', 'GSU14')
        self.assertEqual(r.status, 'compatible')

    def test_bs_space_12(self):
        r = self._eval(12, 'M', 'BS 12')
        self.assertEqual(r.status, 'compatible')

    def test_gs_space_14(self):
        r = self._eval(12, 'F', 'GS 14')
        self.assertEqual(r.status, 'compatible')

    def test_boys_singles_u12(self):
        r = self._eval(12, 'M', 'Boys Singles U12')
        self.assertEqual(r.status, 'compatible')

    def test_girls_doubles_u18(self):
        r = self._eval(17, 'F', 'Girls Doubles U18')
        self.assertEqual(r.status, 'compatible')

    # --- Duplas texto ---
    def test_dupla_masc_12_male_12_compatible(self):
        r = self._eval(12, 'M', 'Dupla Masculina - 12 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_masc_14_male_12_compatible(self):
        r = self._eval(12, 'M', 'Dupla Masculina - 14 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_masc_16_male_15_compatible(self):
        r = self._eval(15, 'M', 'Dupla Masculina - 16 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_masc_18_male_17_compatible(self):
        r = self._eval(17, 'M', 'Dupla Masculina - 18 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_masc_12_male_14_incompatible(self):
        r = self._eval(14, 'M', 'Dupla Masculina - 12 anos')
        self.assertEqual(r.status, 'incompatible')

    def test_dupla_masc_14_female_incompatible(self):
        r = self._eval(12, 'F', 'Dupla Masculina - 14 anos')
        self.assertEqual(r.status, 'incompatible')

    def test_dupla_fem_12_female_compatible(self):
        r = self._eval(12, 'F', 'Dupla Feminina - 12 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_fem_16_female_14_compatible(self):
        r = self._eval(14, 'F', 'Dupla Feminina - 16 anos')
        self.assertEqual(r.status, 'compatible')

    def test_dupla_fem_12_female_14_incompatible(self):
        r = self._eval(14, 'F', 'Dupla Feminina - 12 anos')
        self.assertEqual(r.status, 'incompatible')

    def test_dupla_fem_14_male_incompatible(self):
        r = self._eval(12, 'M', 'Dupla Feminina - 14 anos')
        self.assertEqual(r.status, 'incompatible')

    # --- Global age rule ---
    def test_age_rule_12_u12(self):
        r = self._eval(12, 'M', 'BS U12')
        self.assertEqual(r.status, 'compatible')

    def test_age_rule_12_u14(self):
        r = self._eval(12, 'M', 'BS U14')
        self.assertEqual(r.status, 'compatible')

    def test_age_rule_12_u16(self):
        r = self._eval(12, 'M', 'BS U16')
        self.assertEqual(r.status, 'compatible')

    def test_age_rule_12_u18(self):
        r = self._eval(12, 'M', 'BS U18')
        self.assertEqual(r.status, 'compatible')

    def test_age_rule_14_u12_incompatible(self):
        r = self._eval(14, 'M', 'BS U12')
        self.assertEqual(r.status, 'incompatible')

    def test_age_rule_15_u16(self):
        r = self._eval(15, 'M', 'BS U16')
        self.assertEqual(r.status, 'compatible')

    def test_age_rule_17_u18(self):
        r = self._eval(17, 'M', 'BS U18')
        self.assertEqual(r.status, 'compatible')


# ─── State machine tests ───────────────────────────────────────────────────────

class SubscriptionStateMachineTestCase(TestCase):
    """Test that billing state machine rejects invalid transitions."""

    def test_valid_transitions_map_is_complete(self):
        from apps.billing.views import _VALID_TRANSITIONS
        from apps.billing.models import Subscription
        all_statuses = {
            Subscription.STATUS_PENDING, Subscription.STATUS_ACTIVE,
            Subscription.STATUS_UNPAID, Subscription.STATUS_EXPIRED,
            Subscription.STATUS_TRIAL, Subscription.STATUS_CANCELED,
        }
        for status in all_statuses:
            self.assertIn(status, _VALID_TRANSITIONS, f'Missing status in transitions: {status}')

    def test_canceled_is_terminal(self):
        from apps.billing.views import _VALID_TRANSITIONS
        self.assertEqual(len(_VALID_TRANSITIONS['canceled']), 0)

    def test_active_can_become_unpaid(self):
        from apps.billing.views import _VALID_TRANSITIONS
        self.assertIn('unpaid', _VALID_TRANSITIONS['active'])

    def test_transition_function_rejects_invalid(self):
        from apps.billing.views import _transition_subscription
        from apps.billing.models import Subscription, Plan
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(email='sm@example.com', password='pass')
        plan = Plan.objects.create(name='Free2', slug='free2', price_monthly='0', price_yearly='0', display_order=99, is_active=True)
        sub = Subscription(user=user, plan=plan, status='canceled')
        # canceled → active is invalid
        result = _transition_subscription(sub, 'active', 'test')
        self.assertFalse(result)


# ─── Federation-scope compatibility (real models) ───────────────────────────────

class FederationScopeTestCase(TestCase):
    """profile_state_result: federation-aware rules using the tournament's org."""

    def setUp(self):
        from apps.sources.models import Organization
        from apps.players.models import PlayerProfile
        # Federations seeded by players.0012; CBT seeded by seed_organizations is
        # absent in the test DB, so create the confederation explicitly.
        self.cbt, _ = Organization.objects.get_or_create(
            name='Confederação Brasileira de Tênis',
            defaults={'short_name': 'CBT', 'type': Organization.TYPE_CONFEDERATION},
        )
        self.fpt = Organization.objects.get(type='federation', state='SP')
        self.fct = Organization.objects.get(name='Federação Carioca de Tênis')  # RJ
        self.utr, _ = Organization.objects.get_or_create(
            name='Universal Tennis Rating',
            defaults={'short_name': 'UTR', 'type': Organization.TYPE_PLATFORM},
        )
        self.user = User.objects.create_user(email='fed@example.com', password='pass', full_name='Fed')
        # Athlete competes for FPT (SP).
        self.profile = PlayerProfile.objects.create(
            user=self.user, display_name='FPT Athlete', federation=self.fpt,
        )

    def _edition(self, org, circuit='', name='Torneio', state='SP'):
        from apps.tournaments.models import Tournament, TournamentEdition, Venue
        import uuid
        slug = f'{org.short_name}-{circuit}-{uuid.uuid4().hex[:8]}'.lower()
        tournament = Tournament.objects.create(
            canonical_name=name, canonical_slug=slug, organization=org, circuit=circuit,
        )
        venue = Venue.objects.create(name=f'Clube {state}', city='Cidade', state=state)
        return TournamentEdition.objects.create(
            tournament=tournament, season_year=2026, title=name, venue=venue,
        )

    def test_national_cbt_included_for_any_federation(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_NATIONAL
        # CBT tournament held in BA — FPT athlete must still see it.
        ed = self._edition(self.cbt, circuit='Infantojuvenil', name='Nacional CBT', state='BA')
        res = profile_state_result(self.profile, ed)
        self.assertTrue(res['included'])
        self.assertEqual(res['status'], DISTANCE_NATIONAL)

    def test_own_federation_state_included(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_OWN_FEDERATION
        ed = self._edition(self.fpt, circuit='Infantojuvenil', name='Estadual FPT', state='SP')
        res = profile_state_result(self.profile, ed)
        self.assertTrue(res['included'])
        self.assertEqual(res['status'], DISTANCE_OWN_FEDERATION)

    def test_other_federation_state_excluded(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_OTHER_FEDERATION
        ed = self._edition(self.fct, circuit='Infantojuvenil', name='Estadual FCT', state='RJ')
        res = profile_state_result(self.profile, ed)
        self.assertFalse(res['included'])
        self.assertEqual(res['status'], DISTANCE_OTHER_FEDERATION)

    def test_other_federation_open_included(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_OPEN
        # FCT "Torneios Abertos" — open to other federations.
        ed = self._edition(self.fct, circuit='Abertos', name='Aberto FCT', state='RJ')
        res = profile_state_result(self.profile, ed)
        self.assertTrue(res['included'])
        self.assertEqual(res['status'], DISTANCE_OPEN)

    def test_utr_platform_included(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_NATIONAL
        ed = self._edition(self.utr, circuit='', name='UTR Event', state='RJ')
        res = profile_state_result(self.profile, ed)
        self.assertTrue(res['included'])
        self.assertEqual(res['status'], DISTANCE_NATIONAL)

    def test_national_keyword_overrides_state_org(self):
        from apps.eligibility.location import profile_state_result, DISTANCE_NATIONAL
        # Even if linked to a state federation, a clearly national title is open.
        ed = self._edition(self.fct, circuit='', name='Campeonato Brasileiro Juvenil', state='RJ')
        res = profile_state_result(self.profile, ed)
        self.assertTrue(res['included'])
        self.assertEqual(res['status'], DISTANCE_NATIONAL)
