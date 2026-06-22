"""Testes da área exclusiva do parceiro: acesso (admin define login), dashboard e isolamento."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.referrals.models import CommissionLedger

from .tests import make_partner, make_coupon

User = get_user_model()


def make_commission(partner, coupon, *, amount='5', base='50',
                    status=CommissionLedger.STATUS_PENDING, subscription=None):
    return CommissionLedger.objects.create(
        partner=partner, coupon=coupon, subscription=subscription,
        base_amount=Decimal(base), commission_amount=Decimal(amount), status=status,
    )


class PartnerAccessAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('master@tenfy.com', 'StrongPass!234')
        self.partner = make_partner(name='Parceiro A')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_creates_partner_login(self):
        resp = self.client.post(
            f'/api/admin-panel/partners/{self.partner.id}/login/',
            {'email': 'parceiroa@ex.com', 'password': 'StrongPass!234'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.partner.refresh_from_db()
        self.assertIsNotNone(self.partner.user_id)
        self.assertEqual(self.partner.user.role, User.ROLE_PARTNER)
        self.assertFalse(self.partner.user.is_staff)
        self.assertTrue(self.partner.user.check_password('StrongPass!234'))
        self.assertTrue(resp.data['has_login'])

    def test_reset_password_reuses_same_user(self):
        self.client.post(f'/api/admin-panel/partners/{self.partner.id}/login/',
                         {'email': 'p@ex.com', 'password': 'StrongPass!234'}, format='json')
        self.partner.refresh_from_db()
        uid = self.partner.user_id
        self.client.post(f'/api/admin-panel/partners/{self.partner.id}/login/',
                         {'email': 'p@ex.com', 'password': 'NewStrong!999'}, format='json')
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.user_id, uid)
        self.assertTrue(self.partner.user.check_password('NewStrong!999'))

    def test_email_clash_rejected(self):
        User.objects.create_user('taken@ex.com', 'StrongPass!234')
        resp = self.client.post(f'/api/admin-panel/partners/{self.partner.id}/login/',
                                {'email': 'taken@ex.com', 'password': 'StrongPass!234'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_disable_login(self):
        self.client.post(f'/api/admin-panel/partners/{self.partner.id}/login/',
                         {'email': 'p@ex.com', 'password': 'StrongPass!234'}, format='json')
        resp = self.client.delete(f'/api/admin-panel/partners/{self.partner.id}/login/')
        self.assertEqual(resp.status_code, 200)
        self.partner.refresh_from_db()
        self.assertFalse(self.partner.user.is_active)


class PartnerDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser('master@tenfy.com', 'StrongPass!234')

        # Parceiro A com login + cupom + comissões
        self.pa = make_partner(name='A')
        self.ua = User.objects.create_user('a@ex.com', 'StrongPass!234', role=User.ROLE_PARTNER)
        self.pa.user = self.ua
        self.pa.save()
        self.ca = make_coupon(self.pa, code='AAA')
        make_commission(self.pa, self.ca, amount='5', base='50', status=CommissionLedger.STATUS_PENDING)
        make_commission(self.pa, self.ca, amount='7', base='70', status=CommissionLedger.STATUS_PAID)

        # Parceiro B (dados que A não pode ver)
        self.pb = make_partner(name='B')
        self.ub = User.objects.create_user('b@ex.com', 'StrongPass!234', role=User.ROLE_PARTNER)
        self.pb.user = self.ub
        self.pb.save()
        self.cb = make_coupon(self.pb, code='BBB')
        make_commission(self.pb, self.cb, amount='99', base='990', status=CommissionLedger.STATUS_PENDING)

    def test_login_returns_partner_role(self):
        resp = self.client.post('/api/auth/login/', {'email': 'a@ex.com', 'password': 'StrongPass!234'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn('access', resp.data)

    def test_dashboard_numbers(self):
        self.client.force_authenticate(self.ua)
        resp = self.client.get('/api/partner/dashboard/')
        self.assertEqual(resp.status_code, 200, resp.data)
        d = resp.data
        self.assertEqual(Decimal(d['commission_pending']), Decimal('5'))
        self.assertEqual(Decimal(d['commission_paid']), Decimal('7'))
        self.assertEqual(Decimal(d['commission_payable']), Decimal('5'))   # pending + approved
        self.assertEqual(Decimal(d['revenue_generated']), Decimal('120'))  # 50 + 70 (live)
        self.assertEqual(d['total_conversions'], 2)
        self.assertEqual(d['active_coupons'], 1)

    def test_isolation_usages(self):
        self.client.force_authenticate(self.ua)
        resp = self.client.get('/api/partner/usages/')
        self.assertEqual(resp.status_code, 200)
        codes = {row['coupon_code'] for row in resp.data['results']}
        self.assertEqual(codes, {'AAA'})  # nunca BBB

    def test_isolation_coupons(self):
        self.client.force_authenticate(self.ub)
        resp = self.client.get('/api/partner/coupons/')
        codes = {c['code'] for c in resp.data['results']}
        self.assertEqual(codes, {'BBB'})

    def test_partner_blocked_from_admin(self):
        self.client.force_authenticate(self.ua)
        resp = self.client.get('/api/admin-panel/partners/')
        self.assertIn(resp.status_code, (401, 403))

    def test_non_partner_blocked_from_partner_area(self):
        player = User.objects.create_user('player@ex.com', 'StrongPass!234', role=User.ROLE_PLAYER)
        self.client.force_authenticate(player)
        resp = self.client.get('/api/partner/dashboard/')
        self.assertEqual(resp.status_code, 403)

    def test_partner_without_link_blocked(self):
        orphan = User.objects.create_user('orphan@ex.com', 'StrongPass!234', role=User.ROLE_PARTNER)
        self.client.force_authenticate(orphan)
        resp = self.client.get('/api/partner/dashboard/')
        self.assertEqual(resp.status_code, 403)
