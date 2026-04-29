"""Tests for alerts app: task dispatch, field formatting, push notifications."""
from unittest.mock import MagicMock, patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert, UserAlertPreference
from apps.alerts.tasks import _build_change_body, _fmt_value, dispatch_deadline_alerts

User = get_user_model()


class FieldFormattingTestCase(TestCase):
    """Tests for _fmt_value and _build_change_body — human-readable notifications."""

    def test_fmt_iso_datetime_to_brazilian(self):
        val = '2026-04-28T02:59:00+00:00'
        result = _fmt_value('entry_close_at', val)
        # Should produce a Brazilian-format date+time, not the raw ISO string
        self.assertNotIn('T', result)
        self.assertNotIn('+00:00', result)
        self.assertIn('/', result)

    def test_fmt_iso_date_only(self):
        result = _fmt_value('start_date', '2026-05-15')
        self.assertEqual(result, '15/05/2026')

    def test_fmt_none_returns_friendly(self):
        result = _fmt_value('start_date', None)
        self.assertEqual(result, 'não informado')

    def test_fmt_status_label(self):
        result = _fmt_value('status', 'closed')
        self.assertEqual(result, 'Encerrado')

    def test_build_change_body_uses_labels(self):
        field_changes = {
            'entry_close_at': {'old': '2026-04-20T23:59:00+00:00', 'new': '2026-04-28T23:59:00+00:00'}
        }
        body = _build_change_body(field_changes)
        # Must use human-readable label, not raw field name
        self.assertIn('Prazo de inscrição', body)
        self.assertNotIn('entry_close_at', body)

    def test_build_change_body_unknown_field_uses_title(self):
        field_changes = {'some_new_field': {'old': 'A', 'new': 'B'}}
        body = _build_change_body(field_changes)
        # Unknown field should be title-cased, not raw
        self.assertIn('Some New Field', body)

    def test_build_change_body_empty_returns_fallback(self):
        body = _build_change_body({})
        self.assertEqual(body, 'Mudanças detectadas na fonte oficial.')

    def test_build_change_body_string_arrow_format(self):
        """Old alerts stored body as 'old → new' string — must be formatted correctly."""
        field_changes = {
            'entry_close_at': '2026-04-28T02:59:00+00:00 → 2026-04-27T23:59:00+00:00',
        }
        body = _build_change_body(field_changes)
        self.assertIn('Prazo de inscrição', body)
        self.assertNotIn('entry_close_at', body)
        self.assertNotIn('+00:00', body)
        self.assertIn('alterado para', body)


class AlertModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='alert_user@example.com', password='pass123', full_name='Alerta User'
        )

    def test_alert_created_with_correct_defaults(self):
        alert = Alert.objects.create(
            user=self.user,
            kind=Alert.KIND_DEADLINE,
            channel=Alert.CHANNEL_IN_APP,
            title='Test Alert',
            body='Body text',
        )
        self.assertEqual(alert.status, Alert.STATUS_PENDING)
        self.assertIsNone(alert.dispatched_at)

    def test_dedup_key_prevents_duplicate(self):
        from apps.alerts.tasks import _create_alert
        # First alert should be created
        a1 = _create_alert(
            user=self.user, edition=None,
            kind=Alert.KIND_DEADLINE, channel=Alert.CHANNEL_IN_APP,
            title='Deadline Alert', body='body',
            dedup_key='test:dedup:1'
        )
        self.assertIsNotNone(a1)
        # Second call with same dedup_key should return None
        a2 = _create_alert(
            user=self.user, edition=None,
            kind=Alert.KIND_DEADLINE, channel=Alert.CHANNEL_IN_APP,
            title='Deadline Alert', body='body',
            dedup_key='test:dedup:1'
        )
        self.assertIsNone(a2)
        self.assertEqual(Alert.objects.filter(dedup_key='test:dedup:1').count(), 1)


class UserAlertPreferenceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='prefs@example.com', password='pass123'
        )

    def test_get_or_create_defaults(self):
        prefs = UserAlertPreference.get_or_create_defaults(self.user)
        self.assertTrue(prefs.in_app_enabled)
        self.assertTrue(prefs.push_enabled)
        self.assertFalse(prefs.email_enabled)  # email disabled by default

    def test_default_deadline_days(self):
        prefs = UserAlertPreference.get_or_create_defaults(self.user)
        self.assertIn(7, prefs.deadline_days)
        self.assertIn(2, prefs.deadline_days)
        self.assertIn(0, prefs.deadline_days)

    def test_idempotent_get_or_create(self):
        p1 = UserAlertPreference.get_or_create_defaults(self.user)
        p2 = UserAlertPreference.get_or_create_defaults(self.user)
        self.assertEqual(p1.id, p2.id)
