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

    def test_create_duplicate_display_name_returns_400(self):
        # DRF returns 400 for UniqueConstraint violations via serializer validation
        PlayerProfile.objects.create(user=self.user, display_name='Dup')
        res = self.client.post('/api/players/profiles/', {
            'display_name': 'Dup',
            'competitive_level': 'amateur',
        }, format='json')
        self.assertEqual(res.status_code, 400)


class PlayerProfileChildRestrictionTestCase(TestCase):
    """Managed child accounts cannot create/delete profiles."""

    def setUp(self):
        self.client = APIClient()
        self.parent = make_user(email='parent@example.com', role='parent')
        self.child = make_user(email='child@example.com', role='player')
        from apps.accounts.models import ParentChild
        ParentChild.objects.create(parent=self.parent, child=self.child, is_active=True)
        self.client.force_authenticate(user=self.child)

    def test_child_cannot_create_profile(self):
        res = self.client.post('/api/players/profiles/', {
            'display_name': 'Child Profile',
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
