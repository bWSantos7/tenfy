"""Tests for accounts app: registration, OTP, LGPD export, data export."""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.billing.models import Plan, Subscription
from .models import ParentChild, PendingRegistration

User = get_user_model()


class DeferredRegistrationTests(TestCase):
    """Cadastro diferido: conta só criada quando o usuário entra de fato."""
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        Plan.objects.create(name='Tester', slug='tester', price_monthly='0', max_members=4)
        Plan.objects.create(name='Individual', slug='individual', price_monthly='49.90', max_members=1)

    def _start(self, plan_slug='tester', email='novo@example.com', cpf='111.444.777-35'):
        return self.client.post('/api/auth/register/start/', {
            'email': email, 'full_name': 'Novo User', 'phone': '11999999999',
            'cpf': cpf, 'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'accept_terms': True, 'plan_slug': plan_slug, 'billing_period': 'monthly',
        }, format='json')

    def _code_for(self, email):
        from django.core.cache import cache
        from apps.accounts.otp import _email_identifier, _code_key
        return cache.get(_code_key(_email_identifier(email), 'dependent_email'))

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_start_does_not_create_user(self, _delay):
        res = self._start('tester')
        self.assertEqual(res.status_code, 201)
        self.assertIn('token', res.data)
        self.assertFalse(User.objects.filter(email='novo@example.com').exists())
        self.assertTrue(PendingRegistration.objects.filter(email='novo@example.com').exists())

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_complete_tester_creates_user_and_logs_in(self, _delay):
        token = self._start('tester').data['token']
        code = self._code_for('novo@example.com')
        self.assertIsNotNone(code)
        v = self.client.post('/api/auth/register/verify-email/', {'token': token, 'code': code}, format='json')
        self.assertEqual(v.status_code, 200)
        c = self.client.post('/api/auth/register/complete/', {'token': token}, format='json')
        self.assertEqual(c.status_code, 201)
        self.assertIn('access', c.data)
        u = User.objects.get(email='novo@example.com')
        self.assertTrue(u.email_verified)
        self.assertEqual(u.subscription.status, Subscription.STATUS_ACTIVE)

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_complete_paid_requires_payment(self, _delay):
        token = self._start('individual').data['token']
        code = self._code_for('novo@example.com')
        self.client.post('/api/auth/register/verify-email/', {'token': token, 'code': code}, format='json')
        c = self.client.post('/api/auth/register/complete/', {'token': token}, format='json')
        self.assertEqual(c.status_code, 400)  # plano pago exige pagamento
        self.assertFalse(User.objects.filter(email='novo@example.com').exists())

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_duplicate_cpf_blocked_at_start(self, _delay):
        User.objects.create_user(email='ex@example.com', password='x', cpf='11144477735')
        res = self._start('tester', email='outro@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cpf', res.data)


class RegistrationTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset register throttle (anon rate limit) between tests
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
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            'full_name': 'Test User',
            'phone': '+5511999999999',
            'role': 'player',
            'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertIn('access', res.data)
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    @patch('apps.accounts.tasks.send_otp_email.delay')
    @patch('apps.accounts.otp.cache')
    def test_register_stores_valid_cpf(self, mock_cache, mock_task):
        mock_cache.set.return_value = None
        mock_cache.delete.return_value = None
        mock_cache.get.return_value = 0
        res = self.client.post('/api/auth/register/', {
            'email': 'cpf@example.com',
            'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'full_name': 'Cpf User', 'phone': '+5511999999999',
            'cpf': '111.444.777-35', 'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        u = User.objects.get(email='cpf@example.com')
        self.assertEqual(u.cpf, '11144477735')  # normalizado p/ dígitos

    def test_register_duplicate_cpf_returns_400(self):
        User.objects.create_user(email='first@example.com', password='x', cpf='11144477735')
        res = self.client.post('/api/auth/register/', {
            'email': 'second@example.com',
            'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'full_name': 'Second', 'phone': '+5511999999999',
            'cpf': '111.444.777-35', 'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cpf', res.data)

    def test_register_invalid_cpf_returns_400(self):
        res = self.client.post('/api/auth/register/', {
            'email': 'badcpf@example.com',
            'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'full_name': 'Bad Cpf', 'phone': '+5511999999999',
            'cpf': '12345678900', 'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cpf', res.data)

    def test_register_duplicate_email_returns_400(self):
        User.objects.create_user(email='dup@example.com', password='pass')
        res = self.client.post('/api/auth/register/', {
            'email': 'dup@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
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
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
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
        # Task 10: a confirmação por OTP do e-mail do dependente é exercitada em
        # testes dedicados; aqui assumimos código válido para focar no resto.
        _vp = patch('apps.accounts.otp.verify_email_code', return_value=True)
        _vp.start()
        self.addCleanup(_vp.stop)
        self.client = APIClient()
        self.parent = User.objects.create_user(
            email='parent@example.com',
            password='testpass123',
            full_name='Parent User',
            role=User.ROLE_PARENT,
        )
        self.familia = Plan.objects.create(
            name='Familia',
            slug=Plan.SLUG_FAMILIA,
            max_members=5,
            max_responsibles=2,
            is_active=True,
        )
        Subscription.objects.create(
            user=self.parent,
            plan=self.familia,
            status=Subscription.STATUS_ACTIVE,
        )

    def test_parent_can_create_child_account(self):
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child Player',
            'email': 'child@example.com',
            'phone': '+5511999991111',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')

        self.assertEqual(res.status_code, 201)
        child = User.objects.get(email='child@example.com')
        self.assertEqual(child.role, User.ROLE_PLAYER)
        self.assertTrue(ParentChild.objects.filter(parent=self.parent, child=child).exists())

    def test_create_child_rejects_invalid_email(self):
        # Task 10: e-mail inválido deve ser bloqueado no backend com mensagem clara.
        self.client.force_authenticate(user=self.parent)
        for bad in ['semarroba', 'a@', '@dominio.com', 'nome@dominio']:
            res = self.client.post('/api/auth/children/', {
                'full_name': 'Child Player',
                'email': bad,
                'password': 'Str0ngPass!',
                'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            }, format='json')
            self.assertEqual(res.status_code, 400, f'{bad} deveria ser rejeitado')
            self.assertIn('email', res.data)
        self.assertFalse(User.objects.filter(full_name='Child Player').exists())

    def test_non_parent_cannot_create_child_account(self):
        player = User.objects.create_user(email='player@example.com', password='testpass123')
        self.client.force_authenticate(user=player)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child Player',
            'email': 'child2@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')

        self.assertEqual(res.status_code, 403)


class DependentManagementTestCase(TestCase):
    """Tests for parent/responsible creating and managing dependent accounts."""

    def setUp(self):
        # Task 10: confirmação por OTP exercitada em teste dedicado.
        _vp = patch('apps.accounts.otp.verify_email_code', return_value=True)
        _vp.start()
        self.addCleanup(_vp.stop)
        self.client = APIClient()
        self.tester_plan = Plan.objects.create(
            name='Tester', slug=Plan.SLUG_TESTER, max_members=4, is_active=True,
        )
        self.familia_plan = Plan.objects.create(
            name='Familia', slug=Plan.SLUG_FAMILIA, max_members=5, max_responsibles=2, is_active=True,
        )
        self.individual_plan = Plan.objects.create(
            name='Individual', slug=Plan.SLUG_INDIVIDUAL, max_members=1, is_active=True,
        )
        self.parent = User.objects.create_user(
            email='responsible@example.com', password='Str0ngPass!',
            full_name='Responsible User', role=User.ROLE_PARENT,
        )

    def _activate_plan(self, user, plan):
        from apps.billing.models import Subscription
        Subscription.objects.create(user=user, plan=plan, status='active')

    # ── Account creation ────────────────────────────────────────────────────────

    def test_tester_parent_can_create_child_account(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child One',
            'email': 'child1@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        child = User.objects.get(email='child1@example.com')
        self.assertEqual(child.role, User.ROLE_PLAYER)
        self.assertTrue(ParentChild.objects.filter(parent=self.parent, child=child).exists())

    def test_familia_parent_can_create_child_account(self):
        self._activate_plan(self.parent, self.familia_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child Familia',
            'email': 'childfam@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertEqual(res.status_code, 201)

    def test_individual_plan_cannot_create_child(self):
        self._activate_plan(self.parent, self.individual_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Should Fail',
            'email': 'fail@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_player_role_cannot_create_child(self):
        player = User.objects.create_user(
            email='player2@example.com', password='Str0ngPass!', role=User.ROLE_PLAYER,
        )
        self.client.force_authenticate(user=player)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Nope',
            'email': 'nope@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_dependent_limit_is_respected(self):
        """Tester plan: max_members=4 → max 3 dependents."""
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        for i in range(3):
            res = self.client.post('/api/auth/children/', {
                'full_name': f'Child {i}',
                'email': f'child{i}@example.com',
                'password': 'Str0ngPass!',
                'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            }, format='json')
            self.assertEqual(res.status_code, 201, f'Child {i} creation failed')
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Child 4 blocked',
            'email': 'child4@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertIn(res.status_code, [400, 403])

    def test_familia_shared_dependent_quota_across_two_responsibles(self):
        """Família max_members=5, max_responsibles=2 → 3 dependentes compartilhados
        pelos dois responsáveis (cota única, não 3 por responsável)."""
        from apps.billing.models import FamilyMembership

        self._activate_plan(self.parent, self.familia_plan)
        sub = self.parent.subscription
        co_parent = User.objects.create_user(
            email='co-parent@example.com', password='Str0ngPass!',
            full_name='Co Responsible', role=User.ROLE_PARENT,
        )
        FamilyMembership.objects.create(
            subscription=sub, member_user=co_parent, status=FamilyMembership.STATUS_ACTIVE,
        )

        self.client.force_authenticate(user=self.parent)
        for i in range(2):
            res = self.client.post('/api/auth/children/', {
                'full_name': f'Shared Child {i}',
                'email': f'shared{i}@example.com',
                'password': 'Str0ngPass!',
                'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            }, format='json')
            self.assertEqual(res.status_code, 201, f'Shared child {i} creation failed')

        # Co-responsável creates the family's 3rd (last) dependent — quota is shared.
        self.client.force_authenticate(user=co_parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Shared Child 2',
            'email': 'shared2@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertEqual(res.status_code, 201)

        # 4th dependent must be blocked regardless of which responsável tries.
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Shared Child 3 blocked',
            'email': 'shared3@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertIn(res.status_code, [400, 403])

        # Every dependent, regardless of who created it, is visible to both responsáveis.
        self.client.force_authenticate(user=self.parent)
        res = self.client.get('/api/auth/children/')
        self.assertEqual(res.data['count'], 3)

    def test_familia_single_responsible_can_use_spare_seat_for_fourth_dependent(self):
        """Com apenas 1 responsável, a vaga extra (max_members=5 - 1) vira um 4º
        dependente — só cai para 3 quando um 2º responsável realmente ocupa a vaga."""
        self._activate_plan(self.parent, self.familia_plan)
        self.client.force_authenticate(user=self.parent)
        for i in range(4):
            res = self.client.post('/api/auth/children/', {
                'full_name': f'Solo Child {i}',
                'email': f'solo{i}@example.com',
                'password': 'Str0ngPass!',
                'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            }, format='json')
            self.assertEqual(res.status_code, 201, f'Solo child {i} creation failed')

        # 5th dependent would leave 0 room for any responsável seat beyond the titular.
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Solo Child 4 blocked',
            'email': 'solo4@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.assertIn(res.status_code, [400, 403])

    # ── Authentication ──────────────────────────────────────────────────────────

    def test_dependent_can_authenticate(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        self.client.post('/api/auth/children/', {
            'full_name': 'Auth Child',
            'email': 'authchild@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        self.client.force_authenticate(user=None)
        res = self.client.post('/api/auth/login/', {
            'email': 'authchild@example.com',
            'password': 'Str0ngPass!',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)

    # ── Sports profile management ───────────────────────────────────────────────

    def test_parent_can_create_sports_profile_for_child(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Profile Child',
            'email': 'profchild@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        link_id = res.data['id']
        res = self.client.post(f'/api/auth/children/{link_id}/profile/', {
            'display_name': 'Profile Child',
            'birth_year': 2010,
            'gender': 'M',
            'home_state': 'SP',
            'competitive_level': 'pro',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['user_id'], User.objects.get(email='profchild@example.com').id)

    def test_parent_cannot_create_duplicate_profile_for_child(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/', {
            'full_name': 'Dup Child',
            'email': 'dupchild@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }, format='json')
        link_id = res.data['id']
        self.client.post(f'/api/auth/children/{link_id}/profile/', {
            'display_name': 'Dup Child', 'home_state': 'SP',
        }, format='json')
        res2 = self.client.post(f'/api/auth/children/{link_id}/profile/', {
            'display_name': 'Dup Child', 'home_state': 'RJ',
        }, format='json')
        self.assertEqual(res2.status_code, 400)

    def test_parent_can_view_child_profiles(self):
        from apps.players.models import PlayerProfile
        self._activate_plan(self.parent, self.tester_plan)
        child = User.objects.create_user(email='viewchild@example.com', password='pass')
        ParentChild.objects.create(parent=self.parent, child=child, is_active=True)
        PlayerProfile.objects.create(user=child, display_name='View Child', home_state='SP', is_primary=True)
        self.client.force_authenticate(user=self.parent)
        res = self.client.get(f'/api/players/profiles/?user_id={child.id}')
        self.assertEqual(res.status_code, 200)
        results = res.data.get('results', res.data)
        self.assertTrue(any(p['display_name'] == 'View Child' for p in results))

    def test_parent_can_edit_child_profile(self):
        from apps.players.models import PlayerProfile
        self._activate_plan(self.parent, self.tester_plan)
        child = User.objects.create_user(email='editchild@example.com', password='pass')
        ParentChild.objects.create(parent=self.parent, child=child, is_active=True)
        profile = PlayerProfile.objects.create(user=child, display_name='Edit Child', home_state='SP', is_primary=True)
        self.client.force_authenticate(user=self.parent)
        res = self.client.patch(f'/api/players/profiles/{profile.id}/', {
            'home_city': 'Campinas',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.home_city, 'Campinas')

    def test_reset_password_for_child(self):
        from unittest.mock import patch
        self._activate_plan(self.parent, self.tester_plan)
        child = User.objects.create_user(email='resetkid@example.com', password='pass')
        link = ParentChild.objects.create(parent=self.parent, child=child, is_active=True)
        self.client.force_authenticate(user=self.parent)
        with patch('apps.accounts.tasks.send_password_reset_email.delay') as mock_task:
            res = self.client.post(f'/api/auth/children/{link.id}/reset-password/')
        self.assertEqual(res.status_code, 200)
        mock_task.assert_called_once()

    def test_parent_can_remove_child_link(self):
        self._activate_plan(self.parent, self.tester_plan)
        child = User.objects.create_user(email='removekid@example.com', password='pass')
        link = ParentChild.objects.create(parent=self.parent, child=child, is_active=True)
        self.client.force_authenticate(user=self.parent)

        res = self.client.delete(f'/api/auth/children/{link.id}/remove/')

        self.assertEqual(res.status_code, 204)
        link.refresh_from_db()
        self.assertFalse(link.is_active)

    def test_non_parent_cannot_access_child_profile_endpoint(self):
        player = User.objects.create_user(email='player3@example.com', password='pass')
        self.client.force_authenticate(user=player)
        res = self.client.post('/api/auth/children/999/profile/', {}, format='json')
        self.assertEqual(res.status_code, 403)

    # ── Atomic create-with-profile ───────────────────────────────────────────────

    def _create_with_profile_payload(self, email='cwp@example.com'):
        return {
            'full_name': 'CWP Child',
            'email': email,
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
            'profile': {
                'birth_year': 2012,
                'gender': 'M',
                'home_state': 'SP',
                'home_city': 'São Paulo',
                'competitive_level': 'pro',
                'tennis_class': '',
                'travel_states': ['SP', 'RJ'],
            },
        }

    def test_create_with_profile_success(self):
        from apps.players.models import PlayerProfile
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/create-with-profile/', self._create_with_profile_payload(), format='json')
        self.assertEqual(res.status_code, 201)
        child = User.objects.get(email='cwp@example.com')
        self.assertTrue(PlayerProfile.objects.filter(user=child, birth_year=2012, gender='M').exists())

    def test_create_with_profile_missing_profile_section(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        payload = {
            'full_name': 'No Profile Child',
            'email': 'noprofile@example.com',
            'password': 'Str0ngPass!',
            'password_confirm': 'Str0ngPass!', 'email_code': '000000',
        }
        res = self.client.post('/api/auth/children/create-with-profile/', payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('profile', res.data)

    def test_create_with_profile_missing_required_profile_fields(self):
        self._activate_plan(self.parent, self.tester_plan)
        self.client.force_authenticate(user=self.parent)
        payload = self._create_with_profile_payload(email='partial@example.com')
        payload['profile'] = {'home_state': 'SP'}
        res = self.client.post('/api/auth/children/create-with-profile/', payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('birth_year', res.data.get('profile', {}))
        self.assertIn('gender', res.data.get('profile', {}))
        self.assertIn('competitive_level', res.data.get('profile', {}))

    def test_create_with_profile_individual_plan_forbidden(self):
        self._activate_plan(self.parent, self.individual_plan)
        self.client.force_authenticate(user=self.parent)
        res = self.client.post('/api/auth/children/create-with-profile/', self._create_with_profile_payload(), format='json')
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


class DependentEmailOtpTestCase(TestCase):
    """Task 10: confirmação por código (OTP) do e-mail do dependente ANTES de criar."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.parent = User.objects.create_user(
            email='parent-otp@example.com', password='x',
            role=User.ROLE_PARENT, full_name='Pai OTP',
        )
        plan = Plan.objects.create(name='Familia', slug=Plan.SLUG_FAMILIA, max_members=5, max_responsibles=2, is_active=True)
        Subscription.objects.create(user=self.parent, plan=plan, status=Subscription.STATUS_ACTIVE)
        self.client.force_authenticate(self.parent)

    def _payload(self, email, code):
        return {
            'full_name': 'Filho OTP', 'email': email,
            'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'email_code': code,
        }

    def test_request_code_rejects_invalid_email(self):
        res = self.client.post('/api/auth/children/request-email-code/', {'email': 'invalido'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('email', res.data)

    def test_request_code_rejects_duplicate(self):
        User.objects.create_user(email='ja@existe.com', password='x')
        res = self.client.post('/api/auth/children/request-email-code/', {'email': 'ja@existe.com'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_create_requires_valid_code(self):
        from apps.accounts.otp import generate_email_code
        email = 'novo@dependente.com'
        code = generate_email_code(email)  # mesmo código que o endpoint geraria/enviaria
        # Código errado → bloqueia
        res_bad = self.client.post('/api/auth/children/', self._payload(email, '999999'), format='json')
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn('email_code', res_bad.data)
        self.assertFalse(User.objects.filter(email=email).exists())
        # Código certo → cria
        res_ok = self.client.post('/api/auth/children/', self._payload(email, code), format='json')
        self.assertEqual(res_ok.status_code, 201, res_ok.data)
        self.assertTrue(User.objects.filter(email=email).exists())


class FullNameDedupTestCase(TestCase):
    """Task 11: bloqueio absoluto de cadastro com nome completo idêntico (normalizado)."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset register throttle (anon rate limit) between tests
        self.client = APIClient()
        User.objects.create_user(
            email='existente@example.com', password='x', full_name='Bruno Alves Pereira',
        )

    def _register(self, full_name, email):
        return self.client.post('/api/auth/register/', {
            'email': email, 'full_name': full_name,
            'password': 'Str0ngPass!', 'password_confirm': 'Str0ngPass!',
            'role': 'player', 'accept_terms': True,
        }, format='json')

    def test_normalize_full_name(self):
        from apps.accounts.serializers import normalize_full_name
        self.assertEqual(normalize_full_name('  Bruno   ALVES  Péreira '), 'bruno alves pereira')

    def test_blocks_exact_duplicate(self):
        res = self._register('Bruno Alves Pereira', 'novo@example.com')
        self.assertEqual(res.status_code, 400)
        self.assertIn('full_name', res.data)
        self.assertFalse(User.objects.filter(email='novo@example.com').exists())

    def test_blocks_case_space_accent_variants(self):
        for variant in ['bruno alves pereira', '  Bruno   Alves   Pereira  ', 'Brúno Álves Pereira']:
            res = self._register(variant, 'v@example.com')
            self.assertEqual(res.status_code, 400, f'{variant!r} deveria ser bloqueado')
            self.assertIn('full_name', res.data)

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_allows_different_name(self, _mock):
        res = self._register('Carlos Souza', 'carlos@example.com')
        self.assertEqual(res.status_code, 201, res.data)

    @patch('apps.accounts.tasks.send_otp_email.delay')
    def test_allows_multiple_blank_names(self, _mock):
        r1 = self._register('', 'a@example.com')
        r2 = self._register('', 'b@example.com')
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(r2.status_code, 201, r2.data)


class StrongPasswordValidatorTestCase(TestCase):
    """Task 14: senha exige maiúscula + número + caractere especial."""

    def _validate(self, pwd):
        from apps.accounts.validators import StrongPasswordValidator
        StrongPasswordValidator().validate(pwd)

    def test_rejects_weak_passwords(self):
        from django.core.exceptions import ValidationError
        for weak in ['minuscula1!', 'MAIUSCULA1!'.lower(), 'SemNumero!', 'SemEspecial1']:
            with self.assertRaises(ValidationError, msg=f'{weak!r} deveria ser rejeitada'):
                self._validate(weak)

    def test_accepts_strong_password(self):
        # não deve levantar
        self._validate('Str0ngPass!')
        self._validate('Abc12345#')
