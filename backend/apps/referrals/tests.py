"""Testes de modelo/estado do app referrals (Fase 1 — cupons/comissões)."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import Payment, Plan, Subscription
from apps.referrals.models import (
    CommissionLedger, CommissionRule, Coupon, Partner, Payout,
)
from apps.referrals.services.coupons import compute_discount, validate_coupon

User = get_user_model()


def make_partner(**kw):
    defaults = dict(name='Influencer X', type=Partner.TYPE_INFLUENCER)
    defaults.update(kw)
    return Partner.objects.create(**defaults)


def make_coupon(partner, **kw):
    defaults = dict(
        code='promo10', discount_type=Coupon.DISCOUNT_PERCENT,
        discount_value=Decimal('10'), plan_scope=Coupon.SCOPE_BOTH,
        status=Coupon.STATUS_ACTIVE,
    )
    defaults.update(kw)
    return Coupon.objects.create(partner=partner, **defaults)


class PartnerModelTests(TestCase):
    def test_defaults(self):
        p = make_partner()
        self.assertEqual(p.status, Partner.STATUS_ACTIVE)
        self.assertTrue(p.is_active)

    def test_inactive(self):
        p = make_partner(status=Partner.STATUS_INACTIVE)
        self.assertFalse(p.is_active)


class CouponModelTests(TestCase):
    def setUp(self):
        self.partner = make_partner()

    def test_code_normalized_uppercase(self):
        c = make_coupon(self.partner, code='  meucupom ')
        self.assertEqual(c.code, 'MEUCUPOM')

    def test_default_status_draft_when_unset(self):
        c = Coupon.objects.create(partner=self.partner, code='NEW')
        self.assertEqual(c.status, Coupon.STATUS_DRAFT)

    def test_unique_code(self):
        make_coupon(self.partner, code='DUP')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_coupon(make_partner(name='Outro'), code='DUP')

    def test_scope_allows_plan(self):
        both = make_coupon(self.partner, code='BOTH', plan_scope=Coupon.SCOPE_BOTH)
        self.assertTrue(both.scope_allows_plan('individual'))
        self.assertTrue(both.scope_allows_plan('familia'))
        only_ind = make_coupon(self.partner, code='IND', plan_scope=Coupon.SCOPE_INDIVIDUAL)
        self.assertTrue(only_ind.scope_allows_plan('individual'))
        self.assertFalse(only_ind.scope_allows_plan('familia'))


class CommissionRuleTests(TestCase):
    def setUp(self):
        self.partner = make_partner()

    def test_percent_compute(self):
        rule = CommissionRule.objects.create(
            partner=self.partner, commission_type=CommissionRule.COMMISSION_PERCENT,
            commission_value=Decimal('20'),
        )
        self.assertEqual(rule.compute(Decimal('44.91')), Decimal('8.98'))

    def test_fixed_compute(self):
        rule = CommissionRule.objects.create(
            partner=self.partner, commission_type=CommissionRule.COMMISSION_FIXED,
            commission_value=Decimal('15.00'),
        )
        self.assertEqual(rule.compute(Decimal('80.91')), Decimal('15.00'))

    def test_mvp_defaults(self):
        rule = CommissionRule.objects.create(partner=self.partner, commission_value=Decimal('10'))
        self.assertEqual(rule.rule_scope, CommissionRule.SCOPE_FIRST_PAYMENT)
        self.assertEqual(rule.base_amount_type, CommissionRule.BASE_NET)
        self.assertEqual(rule.status, CommissionRule.STATUS_ACTIVE)


class CommissionLedgerTests(TestCase):
    def setUp(self):
        self.partner = make_partner()
        self.user = User.objects.create_user(email='c@example.com', password='x', full_name='C')
        self.plan = Plan.objects.create(name='Individual', slug='individual', price_monthly='49.90', max_members=1)
        self.sub = Subscription.objects.create(user=self.user, plan=self.plan, partner=self.partner)
        self.payment = Payment.objects.create(user=self.user, subscription=self.sub, amount=Decimal('44.91'))

    def test_default_status_pending(self):
        led = CommissionLedger.objects.create(
            partner=self.partner, subscription=self.sub, payment=self.payment,
            base_amount=Decimal('44.91'), commission_amount=Decimal('8.98'),
        )
        self.assertEqual(led.status, CommissionLedger.STATUS_PENDING)

    def test_one_commission_per_payment(self):
        CommissionLedger.objects.create(
            partner=self.partner, payment=self.payment,
            base_amount=Decimal('44.91'), commission_amount=Decimal('8.98'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CommissionLedger.objects.create(
                    partner=self.partner, payment=self.payment,
                    base_amount=Decimal('44.91'), commission_amount=Decimal('8.98'),
                )

    def test_null_payment_allowed_multiple(self):
        # Constraint só vale quando payment não é nulo — manuais sem payment coexistem.
        CommissionLedger.objects.create(partner=self.partner, commission_amount=Decimal('1'))
        CommissionLedger.objects.create(partner=self.partner, commission_amount=Decimal('2'))
        self.assertEqual(CommissionLedger.objects.filter(payment__isnull=True).count(), 2)


class BillingFKTests(TestCase):
    def test_subscription_partner_coupon_fks(self):
        partner = make_partner()
        coupon = make_coupon(partner, code='LINK')
        user = User.objects.create_user(email='s@example.com', password='x', full_name='S')
        plan = Plan.objects.create(name='Individual', slug='individual', price_monthly='49.90', max_members=1)
        sub = Subscription.objects.create(user=user, plan=plan, partner=partner, coupon=coupon)
        self.assertEqual(sub.partner, partner)
        self.assertEqual(sub.coupon, coupon)
        self.assertIn(sub, partner.subscriptions.all())

    def test_payment_new_fields_default(self):
        user = User.objects.create_user(email='p@example.com', password='x', full_name='P')
        pay = Payment.objects.create(user=user, amount=Decimal('49.90'))
        self.assertEqual(pay.discount_amount, Decimal('0'))
        self.assertIsNone(pay.paid_net_amount)


# ── Fase 2 — validação de cupom e checkout ──────────────────────────────────────

def make_paid_plan(slug='individual', price='49.90', max_members=1):
    return Plan.objects.create(name=slug.title(), slug=slug, price_monthly=price, max_members=max_members)


class CouponValidationServiceTests(TestCase):
    def setUp(self):
        self.partner = make_partner()
        self.plan = make_paid_plan('individual', '49.90')

    def test_compute_percent_and_fixed(self):
        c_pct = make_coupon(self.partner, code='P10', discount_type=Coupon.DISCOUNT_PERCENT, discount_value=Decimal('10'))
        self.assertEqual(compute_discount(c_pct, Decimal('49.90')), Decimal('4.99'))
        c_fix = make_coupon(self.partner, code='F5', discount_type=Coupon.DISCOUNT_FIXED, discount_value=Decimal('5'))
        self.assertEqual(compute_discount(c_fix, Decimal('49.90')), Decimal('5.00'))

    def test_fixed_never_exceeds_price(self):
        c = make_coupon(self.partner, code='BIG', discount_type=Coupon.DISCOUNT_FIXED, discount_value=Decimal('999'))
        self.assertEqual(compute_discount(c, Decimal('49.90')), Decimal('49.90'))

    def test_valid_coupon(self):
        make_coupon(self.partner, code='PROMO10', discount_value=Decimal('10'))
        r = validate_coupon('promo10', self.plan, 'monthly')
        self.assertTrue(r.valid)
        self.assertEqual(r.original, Decimal('49.90'))
        self.assertEqual(r.discount, Decimal('4.99'))
        self.assertEqual(r.final, Decimal('44.91'))

    def test_not_found(self):
        r = validate_coupon('NOPE', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'not_found')

    def test_inactive_partner(self):
        p = make_partner(name='Off', status=Partner.STATUS_INACTIVE)
        make_coupon(p, code='OFF')
        r = validate_coupon('OFF', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'partner_inactive')

    def test_non_active_status(self):
        make_coupon(self.partner, code='DRAFT', status=Coupon.STATUS_DRAFT)
        r = validate_coupon('DRAFT', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'draft')

    def test_expired_by_date(self):
        make_coupon(self.partner, code='OLD', expires_at=timezone.now() - timedelta(days=1))
        r = validate_coupon('OLD', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'expired')

    def test_not_started(self):
        make_coupon(self.partner, code='SOON', starts_at=timezone.now() + timedelta(days=1))
        r = validate_coupon('SOON', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'not_started')

    def test_plan_scope_rejected(self):
        make_coupon(self.partner, code='FAMONLY', plan_scope=Coupon.SCOPE_FAMILIA)
        r = validate_coupon('FAMONLY', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'plan_not_allowed')

    def test_exhausted_total(self):
        make_coupon(self.partner, code='LIM', max_total_uses=2, times_used=2)
        r = validate_coupon('LIM', self.plan, 'monthly')
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'exhausted')

    def test_already_used_by_customer(self):
        coupon = make_coupon(self.partner, code='ONCE', max_uses_per_customer=1)
        user = User.objects.create_user(email='u@example.com', password='x', full_name='U')
        sub = Subscription.objects.create(user=user, plan=self.plan, coupon=coupon, partner=self.partner)
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'))
        CommissionLedger.objects.create(
            partner=self.partner, coupon=coupon, subscription=sub, payment=pay,
            commission_amount=Decimal('8.98'), status=CommissionLedger.STATUS_PENDING,
        )
        r = validate_coupon('ONCE', self.plan, 'monthly', user=user)
        self.assertFalse(r.valid)
        self.assertEqual(r.reason, 'already_used')


class ValidateCouponEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='e@example.com', password='x', full_name='E')
        self.client.force_authenticate(user=self.user)
        self.partner = make_partner()
        self.plan = make_paid_plan('individual', '49.90')

    def test_valid(self):
        make_coupon(self.partner, code='PROMO10', discount_value=Decimal('10'))
        res = self.client.post('/api/billing/checkout/validate-coupon/', {
            'coupon_code': 'promo10', 'plan_slug': 'individual', 'billing_period': 'monthly',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['valid'])
        self.assertEqual(res.data['final'], '44.91')

    def test_invalid_returns_valid_false(self):
        res = self.client.post('/api/billing/checkout/validate-coupon/', {
            'coupon_code': 'NOPE', 'plan_slug': 'individual',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['valid'])
        self.assertEqual(res.data['reason'], 'not_found')

    def test_requires_auth(self):
        res = APIClient().post('/api/billing/checkout/validate-coupon/', {'coupon_code': 'X'}, format='json')
        self.assertEqual(res.status_code, 401)


@override_settings(ASAAS_API_KEY='')
class CheckoutWithCouponTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='co@example.com', password='x', full_name='Co')
        self.client.force_authenticate(user=self.user)
        self.partner = make_partner()
        self.plan = make_paid_plan('individual', '49.90')

    def test_checkout_stores_partner_and_coupon(self):
        make_coupon(self.partner, code='PROMO10', discount_value=Decimal('10'))
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly',
            'payment_method': 'pix', 'coupon_code': 'PROMO10',
        }, format='json')
        self.assertIn(res.status_code, [200, 201])
        self.assertTrue(res.data['coupon']['applied'])
        self.assertEqual(res.data['coupon']['discount'], '4.99')
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.coupon.code, 'PROMO10')
        self.assertEqual(sub.partner, self.partner)

    def test_checkout_invalid_coupon_not_applied(self):
        # Sob TESTING o gate é ignorado; cupom inválido não bloqueia, só não aplica.
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly',
            'payment_method': 'pix', 'coupon_code': 'NOPE',
        }, format='json')
        self.assertIn(res.status_code, [200, 201])
        self.assertFalse(res.data['coupon']['applied'])
        sub = Subscription.objects.get(user=self.user)
        self.assertIsNone(sub.coupon)

    @override_settings(TESTING=False)
    def test_paid_plan_blocked_without_coupon(self):
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly', 'payment_method': 'pix',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    @override_settings(TESTING=False)
    def test_paid_plan_allowed_with_valid_coupon(self):
        make_coupon(self.partner, code='PROMO10', discount_value=Decimal('10'))
        res = self.client.post('/api/billing/subscription/checkout/', {
            'plan_slug': 'individual', 'billing_period': 'monthly',
            'payment_method': 'pix', 'coupon_code': 'PROMO10',
        }, format='json')
        self.assertIn(res.status_code, [200, 201])
        self.assertTrue(res.data['coupon']['applied'])


class AsaasFirstDiscountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='a@example.com', password='x', full_name='A')
        self.plan = make_paid_plan('individual', '49.90')

    @override_settings(ASAAS_API_KEY='test-key', ASAAS_ENVIRONMENT='sandbox')
    def test_creates_avulsa_then_full_recurrence(self):
        from apps.billing.services import asaas_service
        calls = []

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs.get('json')))
            if path == '/payments':
                return {'id': 'pay_first', 'value': kwargs['json']['value']}
            if path == '/subscriptions':
                return {'id': 'sub_full', 'value': kwargs['json']['value']}
            return {}

        with patch.object(asaas_service, 'get_or_create_customer', return_value='cus_1'), \
             patch.object(asaas_service, '_request', side_effect=fake_request):
            out = asaas_service.create_subscription_with_first_discount(
                user=self.user, plan=self.plan, billing_period='monthly',
                payment_method='PIX', discount_amount=Decimal('4.99'),
            )

        self.assertEqual(out['first_payment']['id'], 'pay_first')
        self.assertEqual(out['subscription']['id'], 'sub_full')
        # 1ª cobrança descontada
        pay_call = next(c for c in calls if c[1] == '/payments')
        self.assertEqual(pay_call[2]['value'], 44.91)
        # recorrência a preço cheio
        sub_call = next(c for c in calls if c[1] == '/subscriptions')
        self.assertEqual(sub_call[2]['value'], 49.90)

    @override_settings(ASAAS_API_KEY='test-key', ASAAS_ENVIRONMENT='sandbox')
    def test_no_discount_falls_back_to_normal(self):
        from apps.billing.services import asaas_service
        with patch.object(asaas_service, 'create_subscription', return_value={'id': 'sub_x'}) as m:
            out = asaas_service.create_subscription_with_first_discount(
                user=self.user, plan=self.plan, billing_period='monthly',
                payment_method='PIX', discount_amount=Decimal('0'),
            )
        m.assert_called_once()
        self.assertEqual(out['subscription']['id'], 'sub_x')
