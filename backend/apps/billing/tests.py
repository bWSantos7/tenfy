"""Tests for billing app: plans, subscriptions, checkout flow, webhook processing."""
from unittest.mock import patch, MagicMock
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.billing.models import Feature, FamilyMembership, Plan, PlanFeature, Subscription, Payment, WebhookEvent

User = get_user_model()


def make_user(email='test@example.com', password='testpass123', role='player'):
    return User.objects.create_user(email=email, password=password, full_name='Test User', role=role)


def make_plans():
    individual = Plan.objects.create(
        name='Individual', slug='individual', price_monthly='29.90', price_yearly='299.00',
        display_order=0, is_active=True, max_members=1,
    )
    familia = Plan.objects.create(
        name='Família', slug='familia', price_monthly='49.90', price_yearly='499.00',
        display_order=1, is_active=True, max_members=5, max_responsibles=2,
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

    def test_subscription_detail_returns_404_if_none(self):
        # Endpoint returns 404 (not auto-create) when user has no subscription.
        res = self.client.get('/api/billing/subscription/')
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.data.get('has_subscription', True))

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

    def test_immediate_cancel_demotes_family_co_responsibles(self):
        sub = Subscription.objects.create(
            user=self.user, plan=self.familia, status=Subscription.STATUS_ACTIVE,
        )
        co_responsible = make_user(email='co@example.com', role='parent')
        membership = FamilyMembership.objects.create(
            subscription=sub, member_user=co_responsible, status=FamilyMembership.STATUS_ACTIVE,
        )

        res = self.client.post('/api/billing/subscription/cancel/', {'immediate': True}, format='json')
        self.assertEqual(res.status_code, 200)

        membership.refresh_from_db()
        self.assertEqual(membership.status, FamilyMembership.STATUS_REMOVED)


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
                'description': 'Tenfy Individual',
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

    def test_familia_plan_max_responsibles(self):
        self.assertEqual(self.familia.max_responsibles, 2)


class FamilyMemberEndpointsTestCase(TestCase):
    """Tests for /api/billing/family/members/ — invite/accept/remove a co-responsável."""

    def setUp(self):
        self.client = APIClient()
        self.individual, self.familia, _ = make_plans()
        self.titular = make_user(email='titular@example.com', role='parent')
        self.co1 = make_user(email='co1@example.com', role='parent')
        self.co2 = make_user(email='co2@example.com', role='parent')
        self.sub = Subscription.objects.create(
            user=self.titular, plan=self.familia,
            status=Subscription.STATUS_ACTIVE,
        )

    def test_list_requires_familia_subscription(self):
        # User with Individual plan cannot list the family's responsável seats
        other = make_user(email='ind@example.com', role='parent')
        Subscription.objects.create(user=other, plan=self.individual, status=Subscription.STATUS_ACTIVE)
        self.client.force_authenticate(user=other)
        res = self.client.get('/api/billing/family/members/')
        self.assertEqual(res.status_code, 403)

    def test_list_returns_only_non_removed(self):
        FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        FamilyMembership.objects.create(
            subscription=self.sub, member_user=self.co2,
            status=FamilyMembership.STATUS_REMOVED,
        )
        self.client.force_authenticate(user=self.titular)
        res = self.client.get('/api/billing/family/members/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['member_email'], 'co1@example.com')

    def test_add_member_by_email(self):
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'co1@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['member_email'], 'co1@example.com')
        self.assertEqual(res.data['status'], 'pending')

    def test_add_member_rejects_non_parent_role(self):
        player = make_user(email='player@example.com', role='player')
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'player@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('Responsável', res.data['detail'])

    def test_add_member_unknown_user_returns_404(self):
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'nobody@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 404)

    def test_add_member_titular_self_rejected(self):
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': self.titular.email},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_add_member_duplicate_rejected(self):
        FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'co1@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_add_member_rejects_user_already_in_another_family(self):
        other_titular = make_user(email='other_titular@example.com', role='parent')
        other_sub = Subscription.objects.create(
            user=other_titular, plan=self.familia, status=Subscription.STATUS_ACTIVE,
        )
        FamilyMembership.objects.create(
            subscription=other_sub, member_user=self.co1, status=FamilyMembership.STATUS_ACTIVE,
        )
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'co1@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_add_member_revives_removed_entry(self):
        FamilyMembership.objects.create(
            subscription=self.sub, member_user=self.co1,
            status=FamilyMembership.STATUS_REMOVED,
        )
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(
            '/api/billing/family/members/',
            {'email': 'co1@example.com'},
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'pending')

    def test_max_responsibles_limit_enforced(self):
        # Família max_responsibles=2 → titular + 1 co-responsável only.
        FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        res = self.client_post_invite(self.titular, self.co2.email)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Limite', res.data['detail'])

    def client_post_invite(self, user, email):
        self.client.force_authenticate(user=user)
        return self.client.post('/api/billing/family/members/', {'email': email}, format='json')

    def test_co_responsible_can_accept_invite(self):
        m = FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.co1)
        res = self.client.post(f'/api/billing/family/members/{m.pk}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'active')

    def test_titular_cannot_accept_for_co_responsible(self):
        m = FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.titular)
        res = self.client.post(f'/api/billing/family/members/{m.pk}/')
        self.assertEqual(res.status_code, 403)

    def test_accept_mirrors_existing_dependents_to_co_responsible(self):
        from apps.accounts.models import ParentChild
        child = make_user(email='child@example.com')
        ParentChild.objects.create(parent=self.titular, child=child, is_active=True)

        m = FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.co1)
        res = self.client.post(f'/api/billing/family/members/{m.pk}/')
        self.assertEqual(res.status_code, 200)

        self.assertTrue(
            ParentChild.objects.filter(parent=self.co1, child=child, is_active=True).exists()
        )

    def test_titular_can_remove_co_responsible(self):
        m = FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.titular)
        res = self.client.delete(f'/api/billing/family/members/{m.pk}/')
        self.assertEqual(res.status_code, 204)
        m.refresh_from_db()
        self.assertEqual(m.status, FamilyMembership.STATUS_REMOVED)

    def test_co_responsible_cannot_remove_self(self):
        m = FamilyMembership.objects.create(subscription=self.sub, member_user=self.co1)
        self.client.force_authenticate(user=self.co1)
        res = self.client.delete(f'/api/billing/family/members/{m.pk}/')
        self.assertEqual(res.status_code, 403)


# ── PCI-DSS / Card security ────────────────────────────────────────────────────

class CardRawDataSecurityTestCase(TestCase):
    """Guarantee the public checkout endpoint never accepts raw card data."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user('cardsec@example.com')
        self.individual, _, _ = make_plans()
        self.client.force_authenticate(user=self.user)

    _RAW_CARD_FIELDS = [
        'cardNumber', 'number', 'ccv', 'cvv', 'expiryMonth',
        'expiryYear', 'creditCard', 'card',
    ]

    @override_settings(ASAAS_API_KEY='')
    def test_credit_card_without_token_returns_400(self):
        """CREDIT_CARD with no card_token must be rejected before calling Asaas."""
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual',
            'billing_period': 'monthly',
            'payment_method': 'credit_card',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    @override_settings(ASAAS_API_KEY='')
    def test_credit_card_with_empty_token_returns_400(self):
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual',
            'billing_period': 'monthly',
            'payment_method': 'credit_card',
            'card_token': '',
        }, format='json')
        self.assertEqual(res.status_code, 400)

    @override_settings(ASAAS_API_KEY='')
    def test_raw_card_fields_in_body_do_not_reach_service(self):
        """Sending raw card fields alongside a valid token must not leak to the service.

        The service should only receive card_token; raw fields are unknown to
        CheckoutSerializer and must be silently ignored (not forwarded).
        """
        with patch('apps.billing.services.asaas_service.create_subscription') as mock_svc:
            mock_svc.return_value = {'id': 'sub_test', 'status': 'PENDING'}
            self.client.post('/api/billing/subscription/checkout/', {
                'plan_slug': 'individual',
                'billing_period': 'monthly',
                'payment_method': 'credit_card',
                'card_token': 'tok_valid_test',
                # Attempt to inject raw fields
                'cardNumber': '4111111111111111',
                'number': '4111111111111111',
                'ccv': '123',
                'cvv': '123',
                'expiryMonth': '12',
                'expiryYear': '2030',
                'creditCard': {'number': '4111111111111111'},
            }, format='json')

        if mock_svc.called:
            _, kwargs = mock_svc.call_args
            # card_token must be the provided token
            self.assertEqual(kwargs.get('card_token'), 'tok_valid_test')
            # Service must not have received any raw card kwarg
            for field in self._RAW_CARD_FIELDS:
                self.assertNotIn(field, kwargs, f'Raw card field "{field}" leaked to service')

    @override_settings(ASAAS_API_KEY='')
    def test_raw_card_fields_without_token_still_returns_400(self):
        """Sending raw card fields without card_token must be rejected (not processed)."""
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual',
            'billing_period': 'monthly',
            'payment_method': 'credit_card',
            'cardNumber': '4111111111111111',
            'ccv': '123',
            'expiryMonth': '12',
            'expiryYear': '2030',
        }, format='json')
        self.assertEqual(res.status_code, 400)


class CreateSubscriptionServiceTestCase(TestCase):
    """Unit tests for asaas_service.create_subscription() PCI-DSS contract."""

    def setUp(self):
        self.user = make_user('svctest@example.com')
        self.individual, _, _ = make_plans()

    def test_credit_card_without_token_raises_value_error(self):
        from apps.billing.services.asaas_service import create_subscription
        with self.assertRaises(ValueError) as ctx:
            create_subscription(
                user=self.user,
                plan=self.individual,
                billing_period='monthly',
                payment_method='CREDIT_CARD',
                card_token='',
            )
        self.assertIn('card_token', str(ctx.exception))

    @patch('apps.billing.services.asaas_service._request')
    @patch('apps.billing.services.asaas_service.get_or_create_customer', return_value='cus_test')
    def test_credit_card_with_token_sends_only_creditcardtoken(self, _mock_cust, mock_req):
        mock_req.return_value = {'id': 'sub_test', 'status': 'PENDING'}
        from apps.billing.services.asaas_service import create_subscription
        create_subscription(
            user=self.user,
            plan=self.individual,
            billing_period='monthly',
            payment_method='CREDIT_CARD',
            card_token='tok_abc123',
        )
        self.assertTrue(mock_req.called)
        _, kwargs = mock_req.call_args
        payload = kwargs['json']
        self.assertEqual(payload.get('creditCardToken'), 'tok_abc123')
        # No raw card fields must appear in the payload
        for field in ('creditCard', 'number', 'ccv', 'cvv', 'expiryMonth', 'expiryYear'):
            self.assertNotIn(field, payload, f'Raw field "{field}" present in Asaas payload')
