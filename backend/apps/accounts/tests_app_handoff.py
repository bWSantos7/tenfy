"""Testes do handoff de sessão app <-> web (retorno automático logado)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AppHandoffTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='handoff@example.com', password='Str0ngPass!', full_name='Handoff User',
        )

    def _mint(self):
        self.client.force_authenticate(self.user)
        res = self.client.post('/api/auth/app-handoff/', {}, format='json')
        self.client.force_authenticate(None)
        return res

    def test_mint_requires_authentication(self):
        res = self.client.post('/api/auth/app-handoff/', {}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_mint_returns_token(self):
        res = self._mint()
        self.assertEqual(res.status_code, 200)
        self.assertIn('token', res.data)
        self.assertTrue(res.data['token'])
        self.assertEqual(res.data['expires_in'], 300)

    def test_exchange_returns_jwt_for_minted_token(self):
        token = self._mint().data['token']
        res = self.client.post('/api/auth/app-handoff/exchange/', {'token': token}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        self.assertEqual(res.data['user']['email'], 'handoff@example.com')

    def test_exchanged_access_token_authenticates(self):
        token = self._mint().data['token']
        access = self.client.post(
            '/api/auth/app-handoff/exchange/', {'token': token}, format='json',
        ).data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['email'], 'handoff@example.com')

    def test_token_is_single_use(self):
        token = self._mint().data['token']
        first = self.client.post('/api/auth/app-handoff/exchange/', {'token': token}, format='json')
        self.assertEqual(first.status_code, 200)
        second = self.client.post('/api/auth/app-handoff/exchange/', {'token': token}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_invalid_token_rejected(self):
        res = self.client.post(
            '/api/auth/app-handoff/exchange/', {'token': 'nope-not-real'}, format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_missing_token_rejected(self):
        res = self.client.post('/api/auth/app-handoff/exchange/', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_inactive_user_cannot_exchange(self):
        token = self._mint().data['token']
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        res = self.client.post('/api/auth/app-handoff/exchange/', {'token': token}, format='json')
        self.assertEqual(res.status_code, 400)
