# -*- coding: utf-8 -*-
"""
Busca de jogadores para convite de dependente — tolerante a acento e caixa.
GET /api/auth/children/search-players/?q=...
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class SearchPlayersFlexibleTestCase(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            email='parent-search@test.com', password='x',
            role=User.ROLE_PARENT, full_name='Pai Responsavel',
        )
        self.player = User.objects.create_user(
            email='joao.silva@test.com', password='x',
            role=User.ROLE_PLAYER, full_name='João Silva',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def _search(self, q):
        return self.client.get('/api/auth/children/search-players/', {'q': q})

    def test_finds_without_accent(self):
        res = self._search('joao')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 1, res.data)

    def test_finds_with_accent(self):
        res = self._search('joão')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 1, res.data)

    def test_finds_uppercase(self):
        res = self._search('JOAO')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 1, res.data)

    def test_finds_by_email(self):
        res = self._search('joao.silva')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 1, res.data)

    def test_no_false_positive(self):
        res = self._search('zzzznotfound')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 0, res.data)
