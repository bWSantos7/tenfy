from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import AuditLog
from .tasks import cleanup_old_logs

User = get_user_model()


class AuditLogModelTests(APITestCase):
    def test_str_includes_action_and_entity(self):
        log = AuditLog.objects.create(
            action=AuditLog.ACTION_UPDATE, entity_type='TournamentEdition', entity_id='42')
        self.assertIn('update', str(log))
        self.assertIn('TournamentEdition:42', str(log))


class CleanupOldLogsTaskTests(APITestCase):
    def _backdate(self, log, days):
        # created_at é auto_now_add; para simular idade, atualiza direto no banco.
        AuditLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=days))

    def test_removes_old_keeps_recent(self):
        old = AuditLog.objects.create(
            action=AuditLog.ACTION_CREATE, entity_type='X', entity_id='1')
        recent = AuditLog.objects.create(
            action=AuditLog.ACTION_CREATE, entity_type='X', entity_id='2')
        self._backdate(old, 200)  # além do corte padrão de 180 dias

        deleted = cleanup_old_logs()

        self.assertEqual(deleted, 1)
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=recent.pk).exists())

    def test_respects_custom_days_arg(self):
        log = AuditLog.objects.create(
            action=AuditLog.ACTION_CREATE, entity_type='X', entity_id='3')
        self._backdate(log, 10)

        self.assertEqual(cleanup_old_logs(days=365), 0)  # 10 < 365 → mantém
        self.assertEqual(cleanup_old_logs(days=5), 1)     # 10 > 5 → remove


class AuditLogEndpointTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com', password='pass', role='admin',
            is_staff=True, is_superuser=True)
        self.player = User.objects.create_user(
            email='player@example.com', password='pass', role='player')
        AuditLog.objects.create(
            action=AuditLog.ACTION_LOGIN, entity_type='User', entity_id='1')

    def test_anonymous_denied(self):
        resp = self.client.get('/api/audit/logs/')
        self.assertIn(resp.status_code, (401, 403))

    def test_player_forbidden(self):
        self.client.force_authenticate(user=self.player)
        self.assertEqual(self.client.get('/api/audit/logs/').status_code, 403)

    def test_admin_can_list(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get('/api/audit/logs/').status_code, 200)

    def test_read_only_no_create(self):
        # AuditLogViewSet é ReadOnly: POST deve ser 405 mesmo para admin.
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/audit/logs/', {
            'action': 'create', 'entity_type': 'X', 'entity_id': '9'})
        self.assertEqual(resp.status_code, 405)
