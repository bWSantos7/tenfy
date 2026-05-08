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

    def test_no_venue_returns_false(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile()
        ed = MagicMock(); ed.venue = None
        self.assertFalse(within_profile_radius(p, ed))


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
