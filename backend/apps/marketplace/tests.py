from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Merchant, Offer

User = get_user_model()


class MarketplaceModelTests(APITestCase):
    def test_merchant_and_offer_str(self):
        m = Merchant.objects.create(name='Loja X', slug='loja-x')
        o = Offer.objects.create(merchant=m, title='Raquete', link_url='https://ex.com')
        self.assertEqual(str(m), 'Loja X')
        self.assertEqual(str(o), 'Loja X - Raquete')


class MarketplaceEndpointTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com', password='pass', role='admin',
            is_staff=True, is_superuser=True)
        self.player = User.objects.create_user(
            email='player@example.com', password='pass', role='player')
        self.merchant = Merchant.objects.create(name='Loja X', slug='loja-x')

    def test_public_can_read_offers(self):
        # IsAdminOrReadOnly: leitura é pública.
        Offer.objects.create(
            merchant=self.merchant, title='Raquete', link_url='https://ex.com')
        self.assertEqual(self.client.get('/api/marketplace/offers/').status_code, 200)

    def test_player_cannot_create_merchant(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(
            '/api/marketplace/merchants/', {'name': 'Nova', 'slug': 'nova'})
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_create_merchant(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            '/api/marketplace/merchants/', {'name': 'Nova', 'slug': 'nova'})
        self.assertEqual(resp.status_code, 201)

    def test_offer_filter_active(self):
        Offer.objects.create(
            merchant=self.merchant, title='A', link_url='https://ex.com', active=True)
        Offer.objects.create(
            merchant=self.merchant, title='B', link_url='https://ex.com', active=False)
        resp = self.client.get('/api/marketplace/offers/?active=true')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        self.assertEqual(len(results), 1)
