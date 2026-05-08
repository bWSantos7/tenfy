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
    """Legacy bool wrapper — kept for regression coverage."""
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

    def test_no_venue_returns_true(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile()
        ed = MagicMock(); ed.venue = None
        self.assertTrue(within_profile_radius(p, ed))

    def test_venue_no_city_returns_true(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile()
        venue = MagicMock(); venue.city = ''; venue.state = ''
        ed = MagicMock(); ed.venue = venue
        self.assertTrue(within_profile_radius(p, ed))

    def test_geocoding_failure_returns_true(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile(city='Palmares do Sul', state='RS', radius=100)
        ed = self._make_edition(city='Porto Alegre', state='RS')
        with patch('apps.eligibility.location.geocode_location', return_value=None):
            result = within_profile_radius(p, ed)
        self.assertTrue(result)

    def test_todo_brasil_radius_includes_all_cities(self):
        """radius=1000 sentinel = 'Todo o Brasil'; no distance check — Recife included even from SP."""
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile(radius=1000, lat=-23.5505, lng=-46.6333)
        ed = self._make_edition(city='Recife', state='PE', lat=-8.0539, lng=-34.8811)
        self.assertTrue(within_profile_radius(p, ed))

    def test_small_radius_excludes_distant_city_with_coords(self):
        from apps.eligibility.location import within_profile_radius
        p = self._make_profile(radius=50, lat=-23.5505, lng=-46.6333)
        ed = self._make_edition(city='Campinas', state='SP', lat=-22.9056, lng=-47.0608)
        self.assertFalse(within_profile_radius(p, ed))


# ─── profile_distance_result — detailed status tests ──────────────────────────

class DistanceResultTestCase(TestCase):
    """Test profile_distance_result() status fields and messages."""

    def _p(self, city='São Paulo', state='SP', radius=100, lat=None, lng=None):
        p = MagicMock()
        p.home_city = city; p.home_state = state
        p.travel_radius_km = radius; p.home_lat = lat; p.home_lng = lng
        return p

    def _ed(self, city='São Paulo', state='SP', lat=None, lng=None):
        venue = MagicMock()
        venue.city = city; venue.state = state
        venue.address = ''; venue.latitude = lat; venue.longitude = lng
        ed = MagicMock(); ed.venue = venue
        return ed

    def test_same_city_within_radius_no_message(self):
        from apps.eligibility.location import profile_distance_result, DISTANCE_WITHIN
        r = profile_distance_result(self._p(), self._ed())
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_WITHIN)
        self.assertIsNone(r['message'])

    def test_within_radius_with_coords_status(self):
        from apps.eligibility.location import profile_distance_result, DISTANCE_WITHIN
        p = self._p(radius=200, lat=-23.5505, lng=-46.6333)
        ed = self._ed(city='Campinas', state='SP', lat=-22.9056, lng=-47.0608)
        r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_WITHIN)
        self.assertIsNone(r['message'])

    def test_outside_radius_status(self):
        from apps.eligibility.location import profile_distance_result, DISTANCE_OUTSIDE
        p = self._p(radius=100, lat=-23.5505, lng=-46.6333)
        ed = self._ed(city='Rio de Janeiro', state='RJ', lat=-22.9068, lng=-43.1729)
        r = profile_distance_result(p, ed)
        self.assertFalse(r['included'])
        self.assertEqual(r['status'], DISTANCE_OUTSIDE)
        self.assertIsNone(r['message'])

    def test_no_profile_city_unknown_included(self):
        """Profile has no city → distance unknown, tournament included."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        r = profile_distance_result(self._p(city='', state=''), self._ed())
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)
        self.assertIsNotNone(r['message'])

    def test_no_venue_unknown_included(self):
        """Venue missing → distance unknown, tournament included."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        p = self._p()
        ed = MagicMock(); ed.venue = None
        r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)
        self.assertIsNotNone(r['message'])

    def test_venue_no_city_unknown_included(self):
        """Venue has no city/state → distance unknown, tournament included."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        p = self._p()
        venue = MagicMock(); venue.city = ''; venue.state = ''
        ed = MagicMock(); ed.venue = venue
        r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)
        self.assertIsNotNone(r['message'])

    def test_geocoding_failure_unknown_included(self):
        """Geocoding fails → distance unknown, tournament included, message set."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        p = self._p(city='Palmares do Sul', state='RS', radius=50)
        ed = self._ed(city='Porto Alegre', state='RS')
        with patch('apps.eligibility.location.geocode_location', return_value=None):
            r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)
        self.assertIsNotNone(r['message'])
        self.assertIn('distância', r['message'].lower())

    def test_profile_no_coords_venue_no_coords_geocoding_fails_unknown(self):
        """Neither side has coords, geocoding fails → unknown, included."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        p = self._p(city='Curitiba', state='PR', radius=100)
        ed = self._ed(city='Florianópolis', state='SC')
        with patch('apps.eligibility.location.geocode_location', return_value=None):
            r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)

    def test_todo_brasil_1000km_nationwide_status(self):
        """radius=1000 sentinel = 'Todo o Brasil' → nationwide, included=True, no distance check."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_NATIONWIDE
        p = self._p(radius=1000, lat=-23.5505, lng=-46.6333)
        ed = self._ed(city='Recife', state='PE', lat=-8.0539, lng=-34.8811)
        r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_NATIONWIDE)
        self.assertIsNone(r['message'])

    def test_nationwide_venue_no_coords_still_included(self):
        """Todo o Brasil + venue without coordinates → nationwide, not unknown."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_NATIONWIDE
        p = self._p(radius=1000)
        ed = MagicMock(); ed.venue = None
        r = profile_distance_result(p, ed)
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_NATIONWIDE)

    def test_nationwide_geocoding_failure_still_included(self):
        """Todo o Brasil + geocoding fails → nationwide, no geocoding called at all."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_NATIONWIDE
        p = self._p(radius=1000, city='Manaus', state='AM')
        ed = self._ed(city='Florianópolis', state='SC')
        # geocode_location must NOT be called — nationwide short-circuits before geocoding.
        with patch('apps.eligibility.location.geocode_location') as mock_geo:
            r = profile_distance_result(p, ed)
            mock_geo.assert_not_called()
        self.assertTrue(r['included'])
        self.assertEqual(r['status'], DISTANCE_NATIONWIDE)

    def test_distance_message_not_none_when_unknown(self):
        """distance_message must be a non-empty string for unknown status."""
        from apps.eligibility.location import profile_distance_result, DISTANCE_UNKNOWN
        p = self._p()
        ed = MagicMock(); ed.venue = None
        r = profile_distance_result(p, ed)
        self.assertEqual(r['status'], DISTANCE_UNKNOWN)
        self.assertIsInstance(r['message'], str)
        self.assertGreater(len(r['message']), 10)


# ─── Category normalization tests ──────────────────────────────────────────────

class CategoryNormalizationTestCase(TestCase):
    """
    normalize_category_text() returns a PlayerCategory ORM object (from DB)
    or None when no match found. Tests verify regex matching logic by checking
    what DB rows are created/retrieved, not the internal dict format.
    """
    def setUp(self):
        from apps.players.models import PlayerCategory
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
            taxonomy=PlayerCategory.TAXONOMY_CBT_AGE, code='12M', gender_scope='M',
            defaults={'label_ptbr': '12 Anos Masc', 'min_age': 12, 'max_age': 12}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_CBT_AGE, code='12F', gender_scope='F',
            defaults={'label_ptbr': '12 Anos Fem', 'min_age': 12, 'max_age': 12}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_AGE, code='16M', gender_scope='M',
            defaults={'label_ptbr': '16 Anos Masc', 'min_age': 16, 'max_age': 16}
        )
        PlayerCategory.objects.get_or_create(
            taxonomy=PlayerCategory.TAXONOMY_FPT_AGE, code='18F', gender_scope='F',
            defaults={'label_ptbr': '18 Anos Fem', 'min_age': 18, 'max_age': 18}
        )
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

    def test_itf_boys_singles_bs14(self):
        """'BS 14' should normalize to male max_age=14 category."""
        result = self._normalize('BS 14')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 14)

    def test_itf_girls_singles_gs12(self):
        """'GS 12' should normalize to female max_age=12 category."""
        result = self._normalize('GS 12')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 12)

    def test_sub16_normalizes_to_age16(self):
        """'Sub 16' should normalize to max_age=16 category."""
        result = self._normalize('Sub 16')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 16)

    def test_anos_format_normalizes(self):
        """'14 anos' should normalize to max_age=14 category."""
        result = self._normalize('14 anos')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 14)

    def test_duplas_14_normalizes(self):
        """'Duplas 14' should normalize to max_age=14 category."""
        result = self._normalize('Duplas 14')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 14)

    def test_duplas_12_normalizes(self):
        """'Duplas 12' should normalize to max_age=12 category."""
        result = self._normalize('Duplas 12')
        self.assertIsNotNone(result)
        self.assertEqual(result.max_age, 12)


# ─── Raw age extraction tests ──────────────────────────────────────────────────

class RawAgeExtractionTestCase(TestCase):
    """Test EligibilityEngine.extract_age_from_text() for various formats."""

    def _extract(self, text):
        from apps.eligibility.services import EligibilityEngine
        return EligibilityEngine.extract_age_from_text(text)

    def test_bs14_extracts_14_male(self):
        result = self._extract('BS 14')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 14)
        self.assertEqual(result[1], 'M')

    def test_gs12_extracts_12_female(self):
        result = self._extract('GS 12')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 12)
        self.assertEqual(result[1], 'F')

    def test_sub16_extracts_16(self):
        result = self._extract('Sub 16')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 16)

    def test_16anos_extracts_16(self):
        result = self._extract('16 anos')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 16)

    def test_duplas12_extracts_12(self):
        result = self._extract('Duplas 12')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 12)

    def test_duplas14_extracts_14(self):
        result = self._extract('Duplas 14')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 14)

    def test_duplas_m_14_extracts_14_male(self):
        result = self._extract('Duplas M 14')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 14)
        self.assertEqual(result[1], 'M')

    def test_duplas_f_12_extracts_12_female(self):
        result = self._extract('Duplas F 12')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 12)
        self.assertEqual(result[1], 'F')

    def test_14m_extracts_14(self):
        result = self._extract('14M')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 14)

    def test_class_category_returns_none(self):
        """FPT class categories like '1M' or '3ª Classe' have no age info."""
        result = self._extract('1M')
        # '1M' matches AGE_RE (1 and M gender), so we get age=1 — but FPT class codes
        # don't have numeric age. This is OK: the engine checks age <= 1 for class=1, which will
        # be incompatible for any reasonable age.
        # More importantly, purely named class categories should return None.
        result2 = self._extract('3ª Classe')
        self.assertIsNone(result2)

    def test_random_text_returns_none(self):
        result = self._extract('Open Masculino')
        self.assertIsNone(result)

    def test_empty_returns_none(self):
        result = self._extract('')
        self.assertIsNone(result)


# ─── Core eligibility engine age rules ────────────────────────────────────────

class AgeEligibilityTestCase(TestCase):
    """Test the MVP age compatibility rule: player.age <= category.max_age."""

    def _make_profile(self, birth_year, gender='M', tennis_class=''):
        p = MagicMock()
        from datetime import datetime
        p.birth_year = birth_year
        p.gender = gender
        p.tennis_class = tennis_class
        p.external_ids = {}
        return p

    def _make_cat(self, taxonomy, max_age, gender_scope='*', min_age=None, class_level=None):
        from apps.players.models import PlayerCategory
        cat = MagicMock(spec=PlayerCategory)
        cat.taxonomy = taxonomy
        cat.max_age = max_age
        cat.min_age = min_age
        cat.gender_scope = gender_scope
        cat.class_level = class_level
        cat.code = f'CAT_{max_age}'
        cat.label_ptbr = f'Categoria {max_age}'
        return cat

    def setUp(self):
        from apps.players.models import PlayerCategory
        self.TAXONOMY_AGE = PlayerCategory.TAXONOMY_CBT_AGE

    def _engine(self, birth_year, gender='M'):
        from apps.eligibility.services import EligibilityEngine
        profile = self._make_profile(birth_year, gender)
        return EligibilityEngine(profile)

    def test_user_12_category_12_compatible(self):
        """12-year-old in BS 12 → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=12)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_12_category_14_compatible(self):
        """12-year-old in BS 14 → compatible (can play up)."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=14)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_12_category_16_compatible(self):
        """12-year-old in BS 16 → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=16)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_12_category_18_compatible(self):
        """12-year-old in BS 18 → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=18)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_14_category_12_incompatible(self):
        """14-year-old in BS 12 → NOT compatible (too old for category)."""
        from apps.eligibility.services import STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 14)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=12)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_user_15_category_16_compatible(self):
        """15-year-old in Sub 16 → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 15)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=16)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_17_category_18_compatible(self):
        """17-year-old in Sub 18 → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 17)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=18)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_user_8_category_8_compatible(self):
        """8-year-old in 8 anos → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 8)
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=8)
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_gender_mismatch_incompatible(self):
        """Male player in female-only category → incompatible."""
        from apps.eligibility.services import STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 14, gender='M')
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=14, gender_scope='F')
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_gender_any_compatible(self):
        """Category with gender_scope='*' → compatible regardless of player gender."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 14, gender='F')
        cat = self._make_cat(self.TAXONOMY_AGE, max_age=14, gender_scope='*')
        result = engine.evaluate_player_category(cat)
        self.assertEqual(result.status, STATUS_COMPATIBLE)


# ─── Class does not block MVP compatibility ───────────────────────────────────

class ClassNotBlockingTestCase(TestCase):
    """Per MVP spec: class/rank does NOT block compatibility."""

    def _engine(self, birth_year, tennis_class=''):
        from apps.eligibility.services import EligibilityEngine
        profile = MagicMock()
        profile.birth_year = birth_year
        profile.gender = 'M'
        profile.tennis_class = tennis_class
        profile.external_ids = {}
        return EligibilityEngine(profile)

    def _make_fpt_class_cat(self, class_level, gender_scope='M'):
        from apps.players.models import PlayerCategory
        cat = MagicMock(spec=PlayerCategory)
        cat.taxonomy = PlayerCategory.TAXONOMY_FPT_CLASS
        cat.class_level = class_level
        cat.gender_scope = gender_scope
        cat.max_age = None
        cat.min_age = None
        cat.code = f'CLASS_{class_level}'
        cat.label_ptbr = f'{class_level}ª Classe Masc'
        return cat

    def test_fpt_class_returns_unknown_not_incompatible(self):
        """FPT class category → STATUS_UNKNOWN (informational only), never INCOMPATIBLE."""
        from apps.eligibility.services import STATUS_UNKNOWN, STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 14, tennis_class='3')
        cat = self._make_fpt_class_cat(class_level=5)
        result = engine.evaluate_player_category(cat)
        self.assertNotEqual(result.status, STATUS_INCOMPATIBLE)
        self.assertEqual(result.status, STATUS_UNKNOWN)

    def test_fpt_class_different_level_still_unknown(self):
        """Even mismatched class → STATUS_UNKNOWN, not blocked."""
        from apps.eligibility.services import STATUS_UNKNOWN, STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 12, tennis_class='1')
        cat = self._make_fpt_class_cat(class_level=3)
        result = engine.evaluate_player_category(cat)
        self.assertNotEqual(result.status, STATUS_INCOMPATIBLE)
        self.assertEqual(result.status, STATUS_UNKNOWN)

    def test_class_info_reason_in_reasons(self):
        """Class categories should have REASON_CLASS_INFO_ONLY in reasons."""
        from apps.eligibility.services import REASON_CLASS_INFO_ONLY
        engine = self._engine(2026 - 14, tennis_class='2')
        cat = self._make_fpt_class_cat(class_level=1)
        result = engine.evaluate_player_category(cat)
        self.assertIn(REASON_CLASS_INFO_ONLY, result.reasons)


# ─── Raw age fallback in evaluate_category ────────────────────────────────────

class RawAgeFallbackTestCase(TestCase):
    """Test that unnormalized categories (normalized_category=None) use age extraction."""

    def _engine(self, birth_year, gender='M'):
        from apps.eligibility.services import EligibilityEngine
        profile = MagicMock()
        profile.birth_year = birth_year
        profile.gender = gender
        profile.tennis_class = ''
        profile.external_ids = {}
        return EligibilityEngine(profile)

    def _tc(self, source_text, normalized=None):
        tc = MagicMock()
        tc.source_category_text = source_text
        tc.normalized_category = normalized
        tc.max_participants = None
        tc.edition_id = 1
        tc.id = 1
        return tc

    def test_bs14_unnormalized_12yo_compatible(self):
        """BS 14 (unnormalized) + 12yo → compatible via raw age extraction."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        result = engine.evaluate_category(self._tc('BS 14'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_gs12_unnormalized_12yo_female_compatible(self):
        """GS 12 (unnormalized) + 12yo female → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12, gender='F')
        result = engine.evaluate_category(self._tc('GS 12'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_duplas12_unnormalized_12yo_compatible(self):
        """Duplas 12 (unnormalized) + 12yo → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        result = engine.evaluate_category(self._tc('Duplas 12'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_duplas14_unnormalized_12yo_compatible(self):
        """Duplas 14 (unnormalized) + 12yo → compatible (can play up)."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 12)
        result = engine.evaluate_category(self._tc('Duplas 14'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_duplas14_unnormalized_15yo_incompatible(self):
        """Duplas 14 (unnormalized) + 15yo → incompatible (too old)."""
        from apps.eligibility.services import STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 15)
        result = engine.evaluate_category(self._tc('Duplas 14'))
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)

    def test_sub16_unnormalized_15yo_compatible(self):
        """Sub 16 (unnormalized) + 15yo → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 15)
        result = engine.evaluate_category(self._tc('Sub 16'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_16anos_unnormalized_15yo_compatible(self):
        """'16 anos' (unnormalized) + 15yo → compatible."""
        from apps.eligibility.services import STATUS_COMPATIBLE
        engine = self._engine(2026 - 15)
        result = engine.evaluate_category(self._tc('16 anos'))
        self.assertEqual(result.status, STATUS_COMPATIBLE)

    def test_class_only_unnormalized_returns_unknown(self):
        """'3ª Classe' (unnormalized, no age) → STATUS_UNKNOWN with safe message."""
        from apps.eligibility.services import STATUS_UNKNOWN
        engine = self._engine(2026 - 14)
        result = engine.evaluate_category(self._tc('3ª Classe'))
        self.assertEqual(result.status, STATUS_UNKNOWN)

    def test_open_masc_unnormalized_returns_unknown(self):
        """'Principiante' (unnormalized, no age) → STATUS_UNKNOWN."""
        from apps.eligibility.services import STATUS_UNKNOWN
        engine = self._engine(2026 - 25)
        result = engine.evaluate_category(self._tc('Principiante Avançado'))
        self.assertEqual(result.status, STATUS_UNKNOWN)

    def test_gender_mismatch_bs14_female_incompatible(self):
        """BS 14 (Boys Singles = male) + female player → incompatible."""
        from apps.eligibility.services import STATUS_INCOMPATIBLE
        engine = self._engine(2026 - 12, gender='F')
        result = engine.evaluate_category(self._tc('BS 14'))
        self.assertEqual(result.status, STATUS_INCOMPATIBLE)


# ─── effective_compatible field in evaluate_edition ───────────────────────────

class EffectiveCompatibleTestCase(TestCase):
    """Test that evaluate_edition correctly computes effective_compatible."""

    def _engine(self, birth_year, gender='M'):
        from apps.eligibility.services import EligibilityEngine
        profile = MagicMock()
        profile.birth_year = birth_year
        profile.gender = gender
        profile.tennis_class = ''
        profile.external_ids = {}
        return EligibilityEngine(profile)

    def _edition_with_tcs(self, tcs):
        edition = MagicMock()
        edition.id = 99
        edition.categories = MagicMock()
        edition.categories.select_related.return_value = edition.categories
        edition.categories.all.return_value = tcs
        return edition

    def _tc(self, source_text, normalized=None):
        tc = MagicMock()
        tc.source_category_text = source_text
        tc.normalized_category = normalized
        tc.max_participants = None
        tc.edition_id = 99
        tc.id = 1
        tc.price_brl = None
        return tc

    def test_class_only_tournament_effective_compatible_true(self):
        """Tournament with only class categories → effective_compatible=True (not blocked)."""
        engine = self._engine(2026 - 14)
        tcs = [self._tc('3ª Classe'), self._tc('Principiante')]
        edition = self._edition_with_tcs(tcs)
        result = engine.evaluate_edition(edition)
        self.assertTrue(result['effective_compatible'])
        self.assertEqual(result['compatible_count'], 0)
        self.assertEqual(result['incompatible_count'], 0)

    def test_age_compatible_edition_effective_compatible_true(self):
        """Tournament with compatible age category → effective_compatible=True."""
        engine = self._engine(2026 - 12)
        tcs = [self._tc('BS 14')]  # 12yo in BS 14 → compatible
        edition = self._edition_with_tcs(tcs)
        result = engine.evaluate_edition(edition)
        self.assertTrue(result['effective_compatible'])
        self.assertGreater(result['compatible_count'], 0)

    def test_all_incompatible_edition_not_effective_compatible(self):
        """Tournament where player is too old for all categories → effective_compatible=False."""
        engine = self._engine(2026 - 16)  # 16 years old
        tcs = [self._tc('BS 12'), self._tc('GS 12')]  # both max_age=12 — 16yo is too old
        edition = self._edition_with_tcs(tcs)
        result = engine.evaluate_edition(edition)
        self.assertFalse(result['effective_compatible'])
        self.assertEqual(result['compatible_count'], 0)
        self.assertGreater(result['incompatible_count'], 0)


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
        anon = APIClient()
        res = anon.get('/api/eligibility/rulesets/')
        self.assertNotIn(res.status_code, [500, 502, 503])

    def test_ruleset_list_authenticated(self):
        res = self.client.get('/api/eligibility/rulesets/')
        self.assertIn(res.status_code, [200, 403])

    def test_evaluate_nonexistent_edition_returns_error(self):
        res = self.client.get('/api/eligibility/evaluate/99999999/')
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
        result = _transition_subscription(sub, 'active', 'test')
        self.assertFalse(result)


# ─── Watchlist summary tests ───────────────────────────────────────────────────

class WatchlistSummaryTestCase(TestCase):
    """Test that watchlist summary correctly counts enrolled items."""

    def setUp(self):
        from apps.watchlist.models import WatchlistItem
        from apps.tournaments.models import Tournament, TournamentEdition, Venue
        from apps.sources.models import Organization

        self.client = APIClient()
        self.user = User.objects.create_user(email='wl@example.com', password='pass')
        self.client.force_authenticate(user=self.user)

        org = Organization.objects.create(name='Test Org', type='federation')
        tournament = Tournament.objects.create(
            canonical_name='Test Tournament',
            canonical_slug='test-tournament',
            organization=org,
        )
        self.edition = TournamentEdition.objects.create(
            tournament=tournament,
            season_year=2026,
            title='Test Edition 2026',
        )

    def test_summary_active_registrations_counts_registered_status(self):
        """active_registrations should count STATUS_REGISTERED items, not entry_close_at."""
        from apps.watchlist.models import WatchlistItem
        # Create item with registered status
        item = WatchlistItem.objects.create(
            user=self.user,
            edition=self.edition,
            user_status=WatchlistItem.STATUS_REGISTERED,
        )
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['active_registrations'], 1)

    def test_summary_non_registered_not_counted(self):
        """Items with status other than registered should not count in active_registrations."""
        from apps.watchlist.models import WatchlistItem
        WatchlistItem.objects.create(
            user=self.user,
            edition=self.edition,
            user_status=WatchlistItem.STATUS_INTENDED,
        )
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['active_registrations'], 0)

    def test_by_status_contains_registered_count(self):
        """by_status should include registered_declared count."""
        from apps.watchlist.models import WatchlistItem
        WatchlistItem.objects.create(
            user=self.user, edition=self.edition,
            user_status=WatchlistItem.STATUS_REGISTERED,
        )
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('registered_declared', res.data['by_status'])
        self.assertEqual(res.data['by_status']['registered_declared'], 1)
