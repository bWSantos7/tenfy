"""Tests for login lockout (Área 1) and responsible-link rules (Área 5)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.billing.models import FamilyMembership, Plan, Subscription
from . import security, services
from .models import ParentChild

User = get_user_model()

PWD = 'Str0ngPass!1'
LOGIN_URL = '/api/auth/login/'


def _plan(slug, name):
    is_familia = slug == 'familia'
    return Plan.objects.create(
        slug=slug, name=name,
        max_members=5 if is_familia else 1,
        max_responsibles=2 if is_familia else 1,
    )


def _sub(user, plan, status=Subscription.STATUS_ACTIVE):
    return Subscription.objects.create(user=user, plan=plan, status=status)


class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(email='lock@example.com', password=PWD)

    def _attempt(self, password):
        return self.client.post(LOGIN_URL, {'email': self.user.email, 'password': password}, format='json')

    def test_locks_after_three_failed_attempts(self):
        r1 = self._attempt('wrong1')
        self.assertEqual(r1.status_code, 401)
        r2 = self._attempt('wrong2')
        self.assertEqual(r2.status_code, 401)
        r3 = self._attempt('wrong3')
        self.assertEqual(r3.status_code, 403)  # locked on the 3rd invalid attempt
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, security.MAX_LOGIN_ATTEMPTS)
        self.assertTrue(security.is_locked(self.user))

    def test_locked_blocks_even_correct_password(self):
        for p in ('a', 'b', 'c'):
            self._attempt(p)
        # Now correct password must still be refused while locked.
        r = self._attempt(PWD)
        self.assertEqual(r.status_code, 403)

    def test_reset_on_successful_login(self):
        self._attempt('wrong1')
        self._attempt('wrong2')
        r = self._attempt(PWD)
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.login_locked_until)

    def test_admin_reset_unlocks(self):
        for p in ('a', 'b', 'c'):
            self._attempt(p)
        self.user.refresh_from_db()
        self.assertTrue(security.is_locked(self.user))
        security.reset_attempts(self.user)
        self.user.refresh_from_db()
        self.assertFalse(security.is_locked(self.user))
        self.assertEqual(self.user.failed_login_attempts, 0)

    def test_unknown_email_is_generic_and_does_not_500(self):
        r = self.client.post(LOGIN_URL, {'email': 'nobody@example.com', 'password': 'x'}, format='json')
        self.assertEqual(r.status_code, 401)


class ResponsibleLinkRuleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.individual = _plan('individual', 'Individual')
        self.tester = _plan('tester', 'Tester')
        self.familia = _plan('familia', 'Família')
        self.child = User.objects.create_user(email='child@example.com', password=PWD, role='player')
        self.p1 = User.objects.create_user(email='p1@example.com', password=PWD, role='parent')
        self.p2 = User.objects.create_user(email='p2@example.com', password=PWD, role='parent')
        self.p3 = User.objects.create_user(email='p3@example.com', password=PWD, role='parent')

    def _link(self, parent, child):
        return ParentChild.objects.create(parent=parent, child=child, is_active=True)

    def test_common_blocks_second_responsible(self):
        self._link(self.p1, self.child)
        with self.assertRaises(ValidationError):
            services.assert_can_link_responsible(self.child, self.p2)

    def test_common_allows_first_responsible(self):
        # No existing parents → fine.
        services.assert_can_link_responsible(self.child, self.p1)

    def test_idempotent_existing_link_passes(self):
        self._link(self.p1, self.child)
        # Re-linking the same parent must not raise.
        services.assert_can_link_responsible(self.child, self.p1)

    def test_tester_parent_allows_second(self):
        _sub(self.p1, self.tester)
        self._link(self.p1, self.child)
        # p1 is tester → exception applies → 2nd allowed.
        services.assert_can_link_responsible(self.child, self.p2)

    def test_tester_child_allows_second(self):
        _sub(self.child, self.tester)
        self._link(self.p1, self.child)
        services.assert_can_link_responsible(self.child, self.p2)

    def test_tester_blocks_third(self):
        _sub(self.p1, self.tester)
        self._link(self.p1, self.child)
        self._link(self.p2, self.child)
        with self.assertRaises(ValidationError):
            services.assert_can_link_responsible(self.child, self.p3)

    def test_familia_titular_allows_second(self):
        _sub(self.p1, self.familia)
        self._link(self.p1, self.child)
        # p1 owns a Família subscription → exception applies → 2nd allowed.
        services.assert_can_link_responsible(self.child, self.p2)

    def test_familia_blocks_third(self):
        _sub(self.p1, self.familia)
        self._link(self.p1, self.child)
        self._link(self.p2, self.child)
        with self.assertRaises(ValidationError):
            services.assert_can_link_responsible(self.child, self.p3)

    def test_familia_second_responsible_via_membership_allows_second(self):
        # p2 has no subscription of their own — inherits p1's Família plan via
        # an active FamilyMembership (co-responsável), same as the real invite flow.
        sub = _sub(self.p1, self.familia)
        FamilyMembership.objects.create(
            subscription=sub, member_user=self.p2, status=FamilyMembership.STATUS_ACTIVE,
        )
        self._link(self.p1, self.child)
        services.assert_can_link_responsible(self.child, self.p2)

    def test_familia_and_tester_do_not_stack_past_two(self):
        # Both exceptions apply (p1 is Tester, child ends up in a Família family via p2)
        # but the hard cap stays at 2, never 4.
        _sub(self.p1, self.tester)
        self._link(self.p1, self.child)
        _sub(self.p2, self.familia)
        self._link(self.p2, self.child)
        with self.assertRaises(ValidationError):
            services.assert_can_link_responsible(self.child, self.p3)
