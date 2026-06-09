"""Tests for the enhanced admin user-management endpoints (Áreas 2/3/4/5)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import security
from apps.accounts.models import ParentChild
from apps.audit.models import AuditLog
from apps.billing.models import Plan, Subscription

User = get_user_model()


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@example.com', password='pass', role='admin', is_staff=True
        )
        self.user = User.objects.create_user(
            email='player@example.com', password='pass', role='player', full_name='Maria Silva'
        )
        Plan.objects.create(slug='individual', name='Individual', max_members=1)
        Plan.objects.create(slug='tester', name='Tester', max_members=5)
        self.client.force_authenticate(user=self.admin)

    def test_detail_returns_rich_payload(self):
        res = self.client.get(f'/api/admin-panel/users/{self.user.id}/')
        self.assertEqual(res.status_code, 200)
        for key in ('id', 'profile_label', 'plan_status', 'sport_profile', 'tournaments', 'links',
                    'failed_login_attempts'):
            self.assertIn(key, res.data)
        self.assertEqual(res.data['profile_label'], 'Jogador')

    def test_patch_can_change_email(self):
        res = self.client.patch(
            f'/api/admin-panel/users/{self.user.id}/',
            {'email': 'new@example.com'}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertTrue(AuditLog.objects.filter(entity_id=str(self.user.id),
                                                 action=AuditLog.ACTION_UPDATE).exists())

    def test_patch_duplicate_email_rejected(self):
        User.objects.create_user(email='taken@example.com', password='pass')
        res = self.client.patch(
            f'/api/admin-panel/users/{self.user.id}/',
            {'email': 'taken@example.com'}, format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_set_plan_tester_activates(self):
        res = self.client.post(
            f'/api/admin-panel/users/{self.user.id}/plan/',
            {'plan_slug': 'tester'}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.plan.slug, 'tester')
        self.assertEqual(sub.status, Subscription.STATUS_ACTIVE)
        self.assertFalse(res.data['plan_is_blocked'])

    def test_release_blocked_plan(self):
        plan = Plan.objects.get(slug='individual')
        Subscription.objects.create(user=self.user, plan=plan, status=Subscription.STATUS_PENDING)
        res = self.client.post(
            f'/api/admin-panel/users/{self.user.id}/plan/',
            {'status': 'active'}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.status, Subscription.STATUS_ACTIVE)

    def test_unlock_login(self):
        security.register_failed_attempt(self.user)
        security.register_failed_attempt(self.user)
        security.register_failed_attempt(self.user)
        self.user.refresh_from_db()
        self.assertTrue(security.is_locked(self.user))
        res = self.client.post(f'/api/admin-panel/users/{self.user.id}/unlock-login/', {}, format='json')
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(security.is_locked(self.user))

    def test_manage_link_add_and_remove(self):
        parent = User.objects.create_user(email='parent@example.com', password='pass', role='parent')
        # add parent as responsible of self.user
        res = self.client.post(
            f'/api/admin-panel/users/{self.user.id}/links/',
            {'action': 'add', 'role': 'parent', 'counterpart_id': parent.id}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(ParentChild.objects.filter(parent=parent, child=self.user, is_active=True).exists())
        # remove
        res = self.client.post(
            f'/api/admin-panel/users/{self.user.id}/links/',
            {'action': 'remove', 'role': 'parent', 'counterpart_id': parent.id}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ParentChild.objects.filter(parent=parent, child=self.user, is_active=True).exists())

    def test_manage_link_add_respects_responsible_limit(self):
        p1 = User.objects.create_user(email='p1@example.com', password='pass', role='parent')
        p2 = User.objects.create_user(email='p2@example.com', password='pass', role='parent')
        ParentChild.objects.create(parent=p1, child=self.user, is_active=True)
        # common plan → second responsible blocked
        res = self.client.post(
            f'/api/admin-panel/users/{self.user.id}/links/',
            {'action': 'add', 'role': 'parent', 'counterpart_id': p2.id}, format='json',
        )
        self.assertEqual(res.status_code, 400)
