"""Testes do push nativo (Expo) — registro de dispositivo e envio."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Alert, DevicePushToken, PushSubscription

User = get_user_model()


class RegisterDeviceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='dev@example.com', password='Str0ngPass!')
        self.client.force_authenticate(self.user)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        res = self.client.post('/api/alerts/register-device/', {'token': 'ExponentPushToken[a]'}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_token_required(self):
        res = self.client.post('/api/alerts/register-device/', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_register_creates_token_and_enables_push(self):
        res = self.client.post(
            '/api/alerts/register-device/',
            {'token': 'ExponentPushToken[abc]', 'platform': 'ios'}, format='json',
        )
        self.assertEqual(res.status_code, 200)
        tok = DevicePushToken.objects.get(token='ExponentPushToken[abc]')
        self.assertEqual(tok.user, self.user)
        self.assertEqual(tok.platform, 'ios')
        self.assertTrue(self.user.alert_preference.push_enabled)

    def test_register_is_idempotent(self):
        for _ in range(2):
            self.client.post(
                '/api/alerts/register-device/',
                {'token': 'ExponentPushToken[abc]', 'platform': 'android'}, format='json',
            )
        self.assertEqual(DevicePushToken.objects.filter(token='ExponentPushToken[abc]').count(), 1)

    def test_token_reassigned_to_new_user_on_relogin(self):
        DevicePushToken.objects.create(token='ExponentPushToken[shared]', user=self.user, platform='ios')
        other = User.objects.create_user(email='other@example.com', password='Str0ngPass!')
        self.client.force_authenticate(other)
        self.client.post(
            '/api/alerts/register-device/',
            {'token': 'ExponentPushToken[shared]', 'platform': 'ios'}, format='json',
        )
        tok = DevicePushToken.objects.get(token='ExponentPushToken[shared]')
        self.assertEqual(tok.user, other)
        self.assertEqual(DevicePushToken.objects.filter(token='ExponentPushToken[shared]').count(), 1)

    def test_delete_removes_token(self):
        DevicePushToken.objects.create(token='ExponentPushToken[x]', user=self.user)
        res = self.client.delete(
            '/api/alerts/register-device/', {'token': 'ExponentPushToken[x]'}, format='json',
        )
        self.assertEqual(res.status_code, 204)
        self.assertFalse(DevicePushToken.objects.filter(token='ExponentPushToken[x]').exists())


class SendPushAlertTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='push@example.com', password='Str0ngPass!')

    def _alert(self):
        return Alert.objects.create(
            user=self.user, kind=Alert.KIND_DEADLINE, channel=Alert.CHANNEL_PUSH,
            title='Prazo', body='Encerra hoje',
        )

    def test_no_target_marks_failed(self):
        from .tasks import send_push_alert
        alert = self._alert()
        send_push_alert(alert.id)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_FAILED)
        self.assertEqual(alert.error, 'no_push_target')

    @patch('apps.alerts.expo_push.requests.post')
    def test_native_push_sent(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {'data': [{'status': 'ok', 'id': '1'}]}
        DevicePushToken.objects.create(token='ExponentPushToken[ok]', user=self.user, platform='ios')

        from .tasks import send_push_alert
        alert = self._alert()
        send_push_alert(alert.id)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_SENT)
        self.assertTrue(mock_post.called)

    @patch('apps.alerts.expo_push.requests.post')
    def test_dead_token_is_deleted(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            'data': [{'status': 'error', 'details': {'error': 'DeviceNotRegistered'}}]
        }
        DevicePushToken.objects.create(token='ExponentPushToken[dead]', user=self.user, platform='android')

        from .tasks import send_push_alert
        alert = self._alert()
        send_push_alert(alert.id)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_FAILED)
        self.assertFalse(DevicePushToken.objects.filter(token='ExponentPushToken[dead]').exists())

    @patch('apps.alerts.expo_push.send_expo_push_messages', return_value=(1, [], []))
    def test_native_success_when_web_push_unconfigured(self, _mock):
        # Com token nativo entregue, ausência de VAPID não deve falhar o alerta.
        DevicePushToken.objects.create(token='ExponentPushToken[n]', user=self.user, platform='ios')
        PushSubscription.objects.create(
            user=self.user, endpoint='https://example/endpoint', p256dh='k', auth='a',
        )
        from .tasks import send_push_alert
        alert = self._alert()
        with self.settings(VAPID_PRIVATE_KEY=''):
            send_push_alert(alert.id)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_SENT)

    @patch('apps.alerts.expo_push.requests.post')
    def test_transient_expo_error_triggers_retry(self, mock_post):
        # Erro transitório (rate limit) com 0 enviados deve reagendar (retry → levanta).
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            'data': [{'status': 'error', 'details': {'error': 'MessageRateExceeded'}}]
        }
        DevicePushToken.objects.create(token='ExponentPushToken[rl]', user=self.user, platform='ios')
        from .tasks import send_push_alert
        alert = self._alert()
        # self.retry propaga uma exceção (Retry em runtime; a própria exc em chamada direta).
        with self.assertRaises(Exception):
            send_push_alert(alert.id)
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_FAILED)
        self.assertIn('MessageRateExceeded', alert.error)
        # token transitório NÃO é removido (não é DeviceNotRegistered)
        self.assertTrue(DevicePushToken.objects.filter(token='ExponentPushToken[rl]').exists())

    def test_web_only_no_vapid_does_not_retry(self):
        # Erro permanente de configuração (sem VAPID) não deve gastar retries.
        PushSubscription.objects.create(
            user=self.user, endpoint='https://example/endpoint', p256dh='k', auth='a',
        )
        from .tasks import send_push_alert
        alert = self._alert()
        with self.settings(VAPID_PRIVATE_KEY=''):
            send_push_alert(alert.id)  # não deve levantar Retry
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.STATUS_FAILED)
