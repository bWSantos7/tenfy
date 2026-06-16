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
from apps.referrals.services.commission import (
    generate_commission_for_payment, reverse_commission_for_payment,
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


# ── Fase 3 — geração e reversão de comissão ─────────────────────────────────────

def make_commission_scenario(commission_value='20', base=None, max_total=None, with_coupon=True):
    base = base or CommissionRule.BASE_NET
    partner = make_partner()
    coupon = None
    rule = None
    if with_coupon:
        coupon = make_coupon(partner, code='PROMO10', discount_value=Decimal('10'), max_total_uses=max_total)
        rule = CommissionRule.objects.create(
            partner=partner, coupon=coupon,
            commission_type=CommissionRule.COMMISSION_PERCENT,
            commission_value=Decimal(commission_value), base_amount_type=base,
        )
    user = User.objects.create_user(email=f'c{Partner.objects.count()}@ex.com', password='x', full_name='C')
    plan = make_paid_plan('individual', '49.90')
    sub = Subscription.objects.create(
        user=user, plan=plan,
        partner=partner if with_coupon else None,
        coupon=coupon,
    )
    return partner, coupon, rule, user, plan, sub


class CommissionGenerationTests(TestCase):
    def _payment(self, user, sub, amount='44.91', net='44.91'):
        return Payment.objects.create(
            user=user, subscription=sub,
            amount=Decimal(amount), paid_net_amount=Decimal(net),
        )

    def test_generates_on_first_payment_net_base(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario('20')
        pay = self._payment(user, sub)
        led = generate_commission_for_payment(pay, sub)
        self.assertIsNotNone(led)
        self.assertEqual(led.status, CommissionLedger.STATUS_PENDING)
        self.assertEqual(led.base_amount, Decimal('44.91'))
        self.assertEqual(led.commission_amount, Decimal('8.98'))  # 20% de 44.91
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)

    def test_no_commission_without_coupon(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario(with_coupon=False)
        pay = self._payment(user, sub)
        self.assertIsNone(generate_commission_for_payment(pay, sub))
        self.assertEqual(CommissionLedger.objects.count(), 0)

    def test_idempotent_same_payment(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        pay = self._payment(user, sub)
        generate_commission_for_payment(pay, sub)
        self.assertIsNone(generate_commission_for_payment(pay, sub))
        self.assertEqual(CommissionLedger.objects.filter(subscription=sub).count(), 1)

    def test_only_first_payment(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        first = self._payment(user, sub)
        generate_commission_for_payment(first, sub)
        second = self._payment(user, sub, amount='49.90', net='49.90')
        self.assertIsNone(generate_commission_for_payment(second, sub))
        self.assertEqual(CommissionLedger.objects.filter(subscription=sub).count(), 1)

    def test_no_rule_skips(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        rule.delete()
        pay = self._payment(user, sub)
        self.assertIsNone(generate_commission_for_payment(pay, sub))

    def test_gross_base(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario('20', base=CommissionRule.BASE_GROSS)
        pay = self._payment(user, sub, amount='44.91', net='40.00')
        led = generate_commission_for_payment(pay, sub)
        self.assertEqual(led.base_amount, Decimal('44.91'))  # usa amount (bruto)

    def test_exhausts_coupon_at_limit(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario(max_total=1)
        pay = self._payment(user, sub)
        generate_commission_for_payment(pay, sub)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_EXHAUSTED)


class CommissionReversalTests(TestCase):
    def test_reverses_and_decrements(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        generate_commission_for_payment(pay, sub)
        rev = reverse_commission_for_payment(pay)
        self.assertEqual(rev.status, CommissionLedger.STATUS_REVERSED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 0)

    def test_reverse_unexhausts(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario(max_total=1)
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        generate_commission_for_payment(pay, sub)
        reverse_commission_for_payment(pay)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)
        self.assertEqual(coupon.times_used, 0)

    def test_reverse_none_when_no_commission(self):
        user = User.objects.create_user(email='nc@ex.com', password='x', full_name='NC')
        pay = Payment.objects.create(user=user, amount=Decimal('10'))
        self.assertIsNone(reverse_commission_for_payment(pay))


class CommissionWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.partner = make_partner()
        self.coupon = make_coupon(self.partner, code='PROMO10', discount_value=Decimal('10'))
        self.rule = CommissionRule.objects.create(
            partner=self.partner, coupon=self.coupon,
            commission_type=CommissionRule.COMMISSION_PERCENT, commission_value=Decimal('20'),
        )
        self.user = User.objects.create_user(email='wh@ex.com', password='x', full_name='WH')
        self.plan = make_paid_plan('individual', '49.90')
        self.sub = Subscription.objects.create(
            user=self.user, plan=self.plan, status=Subscription.STATUS_PENDING,
            pending_plan=self.plan, asaas_subscription_id='sub_comm',
            partner=self.partner, coupon=self.coupon,
        )

    def _post(self, payload, token='test_token'):
        with patch.dict('django.conf.settings.__dict__', {'ASAAS_WEBHOOK_TOKEN': token}):
            return self.client.post(
                '/api/billing/webhooks/asaas/', payload, format='json',
                HTTP_ASAAS_WEBHOOK_TOKEN=token,
            )

    def test_payment_confirmed_generates_commission_net_base(self):
        res = self._post({
            'event': 'PAYMENT_CONFIRMED',
            'payment': {
                'id': 'pay_c1', 'subscription': 'sub_comm',
                'value': 44.91, 'netValue': 43.50, 'billingType': 'PIX',
            },
        })
        self.assertEqual(res.status_code, 200)
        led = CommissionLedger.objects.get(subscription=self.sub)
        self.assertEqual(led.status, CommissionLedger.STATUS_PENDING)
        self.assertEqual(led.base_amount, Decimal('43.50'))         # líquido (RN-006)
        self.assertEqual(led.commission_amount, Decimal('8.70'))    # 20% de 43.50
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.times_used, 1)

    def test_refund_reverses_commission(self):
        self._post({
            'event': 'PAYMENT_CONFIRMED',
            'payment': {'id': 'pay_c1', 'subscription': 'sub_comm', 'value': 44.91, 'netValue': 43.50, 'billingType': 'PIX'},
        })
        self._post({'event': 'PAYMENT_REFUNDED', 'payment': {'id': 'pay_c1'}})
        led = CommissionLedger.objects.get(subscription=self.sub)
        self.assertEqual(led.status, CommissionLedger.STATUS_REVERSED)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.times_used, 0)

    def test_duplicate_confirmed_webhook_no_double_commission(self):
        payload = {
            'event': 'PAYMENT_CONFIRMED',
            'payment': {'id': 'pay_dupc', 'subscription': 'sub_comm', 'value': 44.91, 'netValue': 43.50, 'billingType': 'PIX'},
        }
        self._post(payload)
        self._post(payload)  # webhook reprocessado
        self.assertEqual(CommissionLedger.objects.filter(subscription=self.sub).count(), 1)


# ── Fase 4 — painel admin ────────────────────────────────────────────────────────

def make_superuser(email='master@ex.com'):
    u = User.objects.create_user(email=email, password='x', full_name='Master')
    u.is_staff = True
    u.is_superuser = True
    u.save(update_fields=['is_staff', 'is_superuser'])
    return u


class AdminReferralsAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_staff_non_superuser_blocked(self):
        staff = User.objects.create_user(email='staff@ex.com', password='x', full_name='Staff')
        staff.is_staff = True
        staff.save(update_fields=['is_staff'])
        self.client.force_authenticate(user=staff)
        res = self.client.get('/api/admin-panel/partners/')
        self.assertEqual(res.status_code, 403)

    def test_anon_blocked(self):
        res = self.client.get('/api/admin-panel/partners/')
        self.assertEqual(res.status_code, 401)


class AdminReferralsCrudTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.master = make_superuser()
        self.client.force_authenticate(user=self.master)

    def test_partner_create_and_list(self):
        res = self.client.post('/api/admin-panel/partners/', {
            'name': 'Influ X', 'type': Partner.TYPE_INFLUENCER, 'email': 'x@ex.com',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        pid = res.data['id']
        res = self.client.get('/api/admin-panel/partners/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(p['id'] == pid for p in res.data['results']))

    def test_coupon_create_and_patch(self):
        partner = make_partner()
        res = self.client.post('/api/admin-panel/coupons/', {
            'code': 'promo10', 'partner': partner.id,
            'discount_type': Coupon.DISCOUNT_PERCENT, 'discount_value': '10',
            'plan_scope': Coupon.SCOPE_BOTH, 'status': Coupon.STATUS_ACTIVE,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['code'], 'PROMO10')  # normalizado
        cid = res.data['id']
        res = self.client.patch(f'/api/admin-panel/coupons/{cid}/', {'status': Coupon.STATUS_INACTIVE}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], Coupon.STATUS_INACTIVE)

    def test_commission_rule_create(self):
        partner = make_partner()
        res = self.client.post('/api/admin-panel/commission-rules/', {
            'partner': partner.id, 'commission_type': CommissionRule.COMMISSION_PERCENT,
            'commission_value': '20',
        }, format='json')
        self.assertEqual(res.status_code, 201)

    def test_commissions_list_and_filter(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        generate_commission_for_payment(pay, sub)
        res = self.client.get('/api/admin-panel/commissions/', {'partner': partner.id, 'status': 'pending'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['partner_name'], partner.name)

    def test_commissions_summary(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario('20')
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        generate_commission_for_payment(pay, sub)
        res = self.client.get('/api/admin-panel/commissions/summary/')
        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.data['results'] if r['partner_id'] == partner.id)
        self.assertEqual(row['payable_amount'], '8.98')

    def test_commission_approve_then_block_invalid(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario()
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        led = generate_commission_for_payment(pay, sub)
        res = self.client.patch(f'/api/admin-panel/commissions/{led.id}/', {'status': 'approved'}, format='json')
        self.assertEqual(res.status_code, 200)
        # paid não é transição válida por aqui (só via payout)
        res = self.client.patch(f'/api/admin-panel/commissions/{led.id}/', {'status': 'paid'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_payout_consolidates_and_marks_paid(self):
        partner, coupon, rule, user, plan, sub = make_commission_scenario('20')
        pay = Payment.objects.create(user=user, subscription=sub, amount=Decimal('44.91'), paid_net_amount=Decimal('44.91'))
        led = generate_commission_for_payment(pay, sub)
        res = self.client.post('/api/admin-panel/payouts/', {
            'partner': partner.id, 'method': 'pix', 'reference': 'comprovante123',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['amount'], '8.98')
        led.refresh_from_db()
        self.assertEqual(led.status, CommissionLedger.STATUS_PAID)
        self.assertEqual(led.payout_id, res.data['id'])

    def test_payout_no_pending_returns_400(self):
        partner = make_partner()
        res = self.client.post('/api/admin-panel/payouts/', {'partner': partner.id}, format='json')
        self.assertEqual(res.status_code, 400)
