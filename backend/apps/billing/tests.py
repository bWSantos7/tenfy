"""Tests for billing app: plans, subscriptions, checkout flow, webhook processing."""
from unittest.mock import patch, MagicMock
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.billing.models import Feature, FamilyMembership, Plan, PlanFeature, Subscription, Payment, WebhookEvent

User = get_user_model()


def make_user(email='test@example.com', password='testpass123'):
    return User.objects.create_user(email=email, password=password, full_name='Test User')


def make_plans():
    individual = Plan.objects.create(
        name='Individual', slug='individual', price_monthly='29.90', price_yearly='299.00',
        display_order=0, is_active=True, max_members=1,
    )
    familia = Plan.objects.create(
        name='Família', slug='familia', price_monthly='49.90', price_yearly='499.00',
        display_order=1, is_active=True, max_members=5,
    )
    feat = Feature.objects.create(code='ranking_access', name='Ranking')
    PlanFeature.objects.create(plan=individual, feature=feat, limit=None)
    PlanFeature.objects.create(plan=familia, feature=feat, limit=None)
    return individual, familia, feat


class PlansListTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        make_plans()

    def test_plans_list_public(self):
        res = self.client.get('/api/billing/plans/')
        self.assertEqual(res.status_code, 200)
        slugs = [p['slug'] for p in res.data]
        self.assertIn('individual', slugs)
        self.assertIn('familia', slugs)

    def test_plans_include_features(self):
        res = self.client.get('/api/billing/plans/')
        self.assertEqual(res.status_code, 200)
        ind = next(p for p in res.data if p['slug'] == 'individual')
        self.assertTrue(len(ind['features']) > 0)

    def test_plans_include_max_members(self):
        res = self.client.get('/api/billing/plans/')
        self.assertEqual(res.status_code, 200)
        individual = next(p for p in res.data if p['slug'] == 'individual')
        familia = next(p for p in res.data if p['slug'] == 'familia')
        self.assertEqual(individual['max_members'], 1)
        self.assertEqual(familia['max_members'], 5)


class SubscriptionCheckoutTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.individual, self.familia, _ = make_plans()
        self.client.force_authenticate(user=self.user)

    @override_settings(ASAAS_API_KEY='')
    def test_checkout_individual_creates_pending_subscription(self):
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual',
            'billing_period': 'monthly',
            'payment_method': 'pix',
        }, format='json')
        self.assertIn(res.status_code, [200, 201])
        self.assertEqual(res.data['status'], 'pending')
        self.assertEqual(res.data['pending_plan'], self.individual.id)

    @override_settings(ASAAS_API_KEY='')
    def test_checkout_familia_without_asaas_stays_pending(self):
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'familia',
            'billing_period': 'monthly',
            'payment_method': 'pix',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'pending')
        self.assertEqual(res.data['pending_plan'], self.familia.id)
        self.assertEqual(res.data['pending_billing_period'], 'monthly')

        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.status, Subscription.STATUS_PENDING)
        self.assertEqual(subscription.pending_plan, self.familia)

    def test_checkout_requires_auth(self):
        anon = APIClient()
        res = anon.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly', 'payment_method': 'pix'
        }, format='json')
        self.assertEqual(res.status_code, 401)

    def test_checkout_invalid_plan_returns_400(self):
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'invalid', 'billing_period': 'monthly', 'payment_method': 'pix'
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_checkout_legacy_plan_slug_rejected(self):
        for slug in ('free', 'pro', 'elite'):
            res = self.client.post('/api/billing/subscription/checkout/', {
                'plan_slug': slug, 'billing_period': 'monthly', 'payment_method': 'pix'
            }, format='json')
            self.assertEqual(res.status_code, 400, f'Expected 400 for legacy slug={slug}')

    def test_subscription_detail_creates_individual_if_none(self):
        res = self.client.get('/api/billing/subscription/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['plan_slug'], 'individual')
        self.assertEqual(res.data['status'], 'pending')

    def test_cancel_subscription(self):
        self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly', 'payment_method': 'pix'
        }, format='json')
        # Manually activate to test cancel
        sub = Subscription.objects.get(user=self.user)
        sub.status = Subscription.STATUS_ACTIVE
        sub.save()

        res = self.client.post('/api/billing/subscription/cancel/', {'immediate': True}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'canceled')

    def test_cannot_cancel_already_canceled(self):
        Subscription.objects.create(
            user=self.user, plan=self.individual,
            status=Subscription.STATUS_CANCELED,
        )
        res = self.client.post('/api/billing/subscription/cancel/', {'immediate': True}, format='json')
        self.assertEqual(res.status_code, 400)


class WebhookTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('webhook@example.com')
        self.individual, self.familia, _ = make_plans()
        self.sub = Subscription.objects.create(
            user=self.user,
            plan=self.individual,
            status=Subscription.STATUS_PENDING,
            pending_plan=self.individual,
            asaas_subscription_id='sub_test_123',
        )

    def _post_webhook(self, payload, token='test_token'):
        import os
        os.environ['ASAAS_WEBHOOK_TOKEN'] = token
        with patch.dict('django.conf.settings.__dict__', {'ASAAS_WEBHOOK_TOKEN': token}):
            res = self.client.post(
                '/api/billing/webhooks/asaas/',
                payload,
                format='json',
                HTTP_ASAAS_WEBHOOK_TOKEN=token,
            )
        return res

    def test_webhook_invalid_token_returns_401(self):
        with patch('apps.billing.services.asaas_service.validate_webhook_token', return_value=False):
            res = self.client.post('/api/billing/webhooks/asaas/', {}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_webhook_payment_confirmed_activates_subscription(self):
        payload = {
            'event': 'PAYMENT_CONFIRMED',
            'payment': {
                'id': 'pay_001',
                'subscription': 'sub_test_123',
                'value': 29.90,
                'billingType': 'PIX',
                'description': 'Tennis Hub Individual',
                'externalReference': str(self.user.id),
            }
        }
        with patch('apps.billing.services.asaas_service.validate_webhook_token', return_value=True):
            res = self.client.post('/api/billing/webhooks/asaas/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.STATUS_ACTIVE)
        self.assertEqual(self.sub.plan, self.individual)
        self.assertIsNone(self.sub.pending_plan)

    def test_webhook_payment_overdue_sets_unpaid(self):
        self.sub.status = Subscription.STATUS_ACTIVE
        self.sub.save()
        payload = {
            'event': 'PAYMENT_OVERDUE',
            'payment': {'id': 'pay_002', 'subscription': 'sub_test_123', 'value': 29.90, 'billingType': 'PIX'},
        }
        with patch('apps.billing.services.asaas_service.validate_webhook_token', return_value=True):
            res = self.client.post('/api/billing/webhooks/asaas/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.STATUS_UNPAID)

    def test_webhook_duplicate_event_skipped(self):
        WebhookEvent.objects.create(
            event_type='PAYMENT_CONFIRMED', asaas_id='pay_dup', payload={}, processed=True
        )
        payload = {
            'event': 'PAYMENT_CONFIRMED',
            'payment': {'id': 'pay_dup', 'subscription': 'sub_test_123', 'value': 29.90, 'billingType': 'PIX'},
        }
        with patch('apps.billing.services.asaas_service.validate_webhook_token', return_value=True):
            res = self.client.post('/api/billing/webhooks/asaas/', payload, format='json')
        self.assertEqual(res.status_code, 200)


class FeaturePermissionsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('perms@example.com')
        self.individual, self.familia, self.feat = make_plans()
        self.client.force_authenticate(user=self.user)

    def test_active_user_has_ranking_access(self):
        from apps.billing.permissions import user_has_feature
        Subscription.objects.create(
            user=self.user, plan=self.individual, status=Subscription.STATUS_ACTIVE
        )
        self.assertTrue(user_has_feature(self.user, 'ranking_access'))

    def test_no_subscription_falls_back_to_individual_plan_features(self):
        from apps.billing.permissions import user_has_feature
        self.assertTrue(user_has_feature(self.user, 'ranking_access'))

    def test_my_features_endpoint_returns_map(self):
        res = self.client.get('/api/billing/features/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('ranking_access', res.data)
        self.assertIn('has_access', res.data['ranking_access'])


class FamilyMembershipTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.responsible = make_user('responsible@example.com')
        self.member = make_user('member@example.com')
        _, self.familia, _ = make_plans()
        self.sub = Subscription.objects.create(
            user=self.responsible,
            plan=self.familia,
            status=Subscription.STATUS_ACTIVE,
        )

    def test_family_membership_creation(self):
        membership = FamilyMembership.objects.create(
            subscription=self.sub,
            member_user=self.member,
            status=FamilyMembership.STATUS_ACTIVE,
        )
        self.assertEqual(membership.subscription.user, self.responsible)
        self.assertEqual(membership.member_user, self.member)
        self.assertEqual(membership.status, FamilyMembership.STATUS_ACTIVE)

    def test_family_membership_unique_per_subscription(self):
        FamilyMembership.objects.create(
            subscription=self.sub, member_user=self.member, status=FamilyMembership.STATUS_ACTIVE
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            FamilyMembership.objects.create(
                subscription=self.sub, member_user=self.member, status=FamilyMembership.STATUS_PENDING
            )

    def test_familia_plan_max_members(self):
        self.assertEqual(self.familia.max_members, 5)
