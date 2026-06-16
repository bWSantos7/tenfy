"""Testes de modelo/estado do app referrals (Fase 1 — cupons/comissões)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.billing.models import Payment, Plan, Subscription
from apps.referrals.models import (
    CommissionLedger, CommissionRule, Coupon, Partner, Payout,
)

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
