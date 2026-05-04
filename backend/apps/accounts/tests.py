"""Tests for accounts app: registration, OTP, LGPD export, data export."""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import ParentChild

User = get_user_model()


class RegistrationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('apps.accounts.tasks.send_otp_email.delay')
    @patch('apps.accounts.otp.cache')
    def test_register_creates_user(self, mock_cache, mock_task):
        mock_cache.set.return_value = None
        mock_cache.delete.return_value = None
        mock_cache.get.return_value = 0  # no lockout, no existing attempts
        res = self.client.post('/api/auth/register/', {
            'email': 'test@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!',
            'full_name': 'Test User',
            'phone': '+5511999999999',
            'role': 'player',
            'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertIn('access', res.data)
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_register_duplicate_email_returns_400(self):
        User.objects.create_user(email='dup@example.com', password='pass')
        res = self.client.post('/api/auth/register/', {
            'email': 'dup@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!',
            'full_name': 'Dup',
            'phone': '+5511999999999',
            'role': 'player',
            'accept_terms': True,
        }, format='json')
        self.assertIn(res.status_code, [400, 422])

    @patch('apps.accounts.tasks.send_otp_email.apply')
    @patch('apps.accounts.tasks.send_otp_email.delay')
    @patch('apps.accounts.otp.cache')
    def test_register_falls_back_to_sync_otp_when_enqueue_fails(self, mock_cache, mock_delay, mock_apply):
        mock_cache.set.return_value = None
        mock_cache.delete.return_value = None
        mock_delay.side_effect = RuntimeError('broker unavailable')
        mock_result = MagicMock()
        mock_result.get.return_value = None
        mock_apply.return_value = mock_result

        res = self.client.post('/api/auth/register/', {
            'email': 'fallback@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!',
            'full_name': 'Fallback User',
            'phone': '+5511988887777',
            'role': 'player',
            'accept_terms': True,
        }, format='json')

        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['email_otp_sent'])
        mock_apply.assert_called_once()
        mock_result.get.assert_called_once_with(propagate=True)

    @patch('apps.accounts.tasks.send_otp_email.apply')
    @patch('apps.accounts.tasks.send_otp_email.delay')
    @patch('apps.accounts.otp.cache')
    def test_resend_email_otp_returns_503_when_dispatch_fails(self, mock_cache, mock_delay, mock_apply):
        user = User.objects.create_user(email='otp-fail@example.com', password='pass')
        self.client.force_authenticate(user=user)
        mock_cache.set.return_value = None
        mock_cache.delete.return_value = None
        mock_delay.side_effect = RuntimeError('broker unavailable')
        mock_apply.side_effect = RuntimeError('email provider unavailable')

        res = self.client.post('/api/auth/send-email-otp/', {}, format='json')

        self.assertEqual(res.status_code, 503)


class OTPTestCase(TestCase):
    def test_generate_invalid_type_raises(self):
        from apps.accounts.otp import generate_and_store, VALID_OTP_TYPES
        with self.assertRaises(ValueError):
            generate_and_store(1, 'invalid_type')

    def test_valid_types_accepted(self):
        from apps.accounts.otp import generate_and_store, VALID_OTP_TYPES
        from unittest.mock import patch
        for otp_type in VALID_OTP_TYPES:
            with patch('apps.accounts.otp.cache') as mock_cache:
                mock_cache.set.return_value = None
                mock_cache.delete.return_value = None
                code = generate_and_store(1, otp_type)
                self.assertEqual(len(code), 6)
                self.assertTrue(code.isdigit())

    def test_verify_correct_code(self):
        from apps.accounts.otp import generate_and_store, verify
        from unittest.mock import patch, MagicMock
        mock_cache = MagicMock()
        mock_cache.get.side_effect = lambda key, default=None: '654321' if 'code' in key else 0
        with patch('apps.accounts.otp.cache', mock_cache):
            result = verify(1, 'email', '654321')
        self.assertTrue(result)

    def test_verify_wrong_code(self):
        from apps.accounts.otp import verify
        from unittest.mock import patch, MagicMock
        mock_cache = MagicMock()
        mock_cache.get.side_effect = lambda key, default=None: '654321' if 'code' in key else 0
        with patch('apps.accounts.otp.cache', mock_cache):
            result = verify(1, 'email', '000000')
        self.assertFalse(result)


class ParentChildTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.parent = User.objects.create_user(
            email='parent@example.com',
            password='testpass123',
            full_name='Parent User',
            role=User.ROLE_PARENT,
        )

    def test_parent_can_create_child_account(self):
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child Player',
            'email': 'child@example.com',
            'phone': '+5511999991111',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!',
        }, format='json')

        self.assertEqual(res.status_code, 201)
        child = User.objects.get(email='child@example.com')
        self.assertEqual(child.role, User.ROLE_PLAYER)
        self.assertTrue(ParentChild.objects.filter(parent=self.parent, child=child).exists())

    def test_non_parent_cannot_create_child_account(self):
        player = User.objects.create_user(email='player@example.com', password='testpass123')
        self.client.force_authenticate(user=player)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child Player',
            'email': 'child2@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!',
        }, format='json')

        self.assertEqual(res.status_code, 403)


class LGPDDataExportTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='export@example.com',
            password='testpass123',
            full_name='Export User',
        )

    def test_data_export_requires_auth(self):
        res = self.client.get('/api/auth/data-export/')
        self.assertEqual(res.status_code, 401)

    def test_data_export_returns_json(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get('/api/auth/data-export/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/json', res.get('Content-Type', ''))
        data = res.json()
        self.assertIn('user', data)
        self.assertIn('player_profiles', data)
        self.assertIn('watchlist', data)
        self.assertIn('alerts', data)
        self.assertEqual(data['user']['email'], 'export@example.com')

    def test_data_export_has_attachment_header(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get('/api/auth/data-export/')
        self.assertIn('Content-Disposition', res)
        self.assertIn('attachment', res['Content-Disposition'])
