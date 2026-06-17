"""Tests for admin panel endpoints."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AdminPanelAuthTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Master (superusuário): enxerga todas as abas/endpoints do painel.
        self.admin = User.objects.create_user(
            email='admin@example.com', password='pass', role='admin',
            is_staff=True, is_superuser=True,
        )
        # Admin comum (staff, sem superuser): só Estatísticas, Usuários e Leads.
        self.staff = User.objects.create_user(
            email='staff@example.com', password='pass', role='admin', is_staff=True,
        )
        self.regular = User.objects.create_user(
            email='user@example.com', password='pass', role='player'
        )

    def test_dashboard_requires_admin(self):
        self.client.force_authenticate(user=self.regular)
        res = self.client.get('/api/admin-panel/dashboard/')
        self.assertEqual(res.status_code, 403)

    def test_dashboard_accessible_by_master(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/dashboard/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('counts', res.data)

    def test_master_only_endpoints_blocked_for_staff_admin(self):
        """Admin comum (staff não-superuser) não acessa abas master-only."""
        self.client.force_authenticate(user=self.staff)
        for url in (
            '/api/admin-panel/dashboard/',
            '/api/admin-panel/sources/',
            '/api/admin-panel/review-queue/',
            '/api/admin-panel/connector-status/',
            '/api/admin-panel/editions-list/',
        ):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 403, url)

    def test_staff_admin_sees_stats_users_leads(self):
        """Admin comum (staff) mantém acesso às abas permitidas."""
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get('/api/admin-panel/stats/').status_code, 200)
        self.assertEqual(self.client.get('/api/admin-panel/users/').status_code, 200)

    def test_sources_list_requires_admin(self):
        self.client.force_authenticate(user=self.regular)
        res = self.client.get('/api/admin-panel/sources/')
        self.assertEqual(res.status_code, 403)

    def test_sources_list_accessible_by_master(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/sources/')
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)

    def test_user_list_search(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/users/?q=user')
        self.assertEqual(res.status_code, 200)
        emails = [u['email'] for u in res.data]
        self.assertIn('user@example.com', emails)

    def test_cannot_delete_own_account(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/admin-panel/users/{self.admin.id}/')
        self.assertEqual(res.status_code, 400)

    def test_delete_user_with_payment(self):
        """Payment.user é PROTECT — deletar usuário com pagamento deve funcionar
        (remove pagamentos antes), não estourar 500."""
        from decimal import Decimal
        from apps.billing.models import Plan, Subscription, Payment
        plan = Plan.objects.create(slug='individual', name='Individual', price_monthly=Decimal('49.90'))
        sub = Subscription.objects.create(user=self.regular, plan=plan, status='active')
        Payment.objects.create(user=self.regular, subscription=sub, amount=Decimal('49.90'))
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f'/api/admin-panel/users/{self.regular.id}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(User.objects.filter(id=self.regular.id).exists())
        self.assertFalse(Payment.objects.filter(subscription_id=sub.id).exists())

    def test_review_queue_returns_sections(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/review-queue/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('low_confidence', res.data)
        self.assertIn('missing_official_url', res.data)

    def test_connector_status_does_not_raise(self):
        """Regression: registered_connectors import was broken; this guards it."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/connector-status/')
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)
        # Each entry must have expected keys
        if res.data:
            row = res.data[0]
            self.assertIn('connector_key', row)
            self.assertIn('enabled', row)
            self.assertIn('is_blocked', row)


class AdminEditionsListingTestCase(TestCase):
    """Tests for /api/admin-panel/editions-list/ (admin sees unpublished)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin2@example.com', password='pass', role='admin',
            is_staff=True, is_superuser=True,
        )
        self.player = User.objects.create_user(
            email='player2@example.com', password='pass', role='player'
        )

        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition

        org = Organization.objects.create(name='Org', short_name='ORG', type='federation')
        t = Tournament.objects.create(canonical_name='T1', canonical_slug='t1', organization=org)
        self.published = TournamentEdition.objects.create(
            tournament=t, season_year=2026, title='Published Edition', is_published=True,
        )
        self.hidden = TournamentEdition.objects.create(
            tournament=t, season_year=2026, external_id='hidden',
            title='Hidden Edition', is_published=False,
        )

    def test_public_endpoint_hides_unpublished(self):
        self.client.force_authenticate(user=self.player)
        res = self.client.get('/api/tournaments/editions/?youth_only=false')
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in res.data.get('results', res.data)]
        self.assertIn(self.published.id, ids)
        self.assertNotIn(self.hidden.id, ids)

    def test_admin_endpoint_lists_all(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/editions-list/')
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in res.data['results']]
        self.assertIn(self.published.id, ids)
        self.assertIn(self.hidden.id, ids)

    def test_admin_endpoint_filter_unpublished_only(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/admin-panel/editions-list/?published=false')
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in res.data['results']]
        self.assertNotIn(self.published.id, ids)
        self.assertIn(self.hidden.id, ids)

    def test_admin_endpoint_requires_admin(self):
        self.client.force_authenticate(user=self.player)
        res = self.client.get('/api/admin-panel/editions-list/')
        self.assertEqual(res.status_code, 403)

    def test_publish_toggle_via_patch(self):
        self.client.force_authenticate(user=self.admin)
        # Hide a published one
        res = self.client.patch(f'/api/admin-panel/editions/{self.published.id}/', {'is_published': False}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['is_published'])
        # Republish
        res = self.client.patch(f'/api/admin-panel/editions/{self.published.id}/', {'is_published': True}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['is_published'])
