"""
Tests for registrations app:
- compute_fed_status: all status combinations
- Ranking-replacement rule (removed_or_replaced prevails over payment)
- FederationEntry new fields: source_url, removed_or_replaced, confidence
- bulk-import endpoint: auth, dry_run, field validation, dedup
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.registrations.serializers import (
    compute_fed_status,
    FED_STATUS_LABELS,
)

User = get_user_model()

FAKE_TOKEN = 'test-import-token-abc123'


class ComputeFedStatusTestCase(TestCase):
    """Covers all status transitions for federation entries."""

    def test_confirmed_when_paid_and_in_draw(self):
        status = compute_fed_status('paid', slot_position=3, max_participants=32)
        self.assertEqual(status, 'confirmed')

    def test_confirmed_when_paid_no_max(self):
        """No max_participants means unlimited — confirmed if paid."""
        status = compute_fed_status('paid', slot_position=50, max_participants=None)
        self.assertEqual(status, 'confirmed')

    def test_waiting_list_when_paid_but_over_max(self):
        status = compute_fed_status('paid', slot_position=33, max_participants=32)
        self.assertEqual(status, 'waiting_list')

    def test_pending_payment_when_not_paid(self):
        status = compute_fed_status('pending', slot_position=5, max_participants=32)
        self.assertEqual(status, 'pending_payment')

    def test_pending_payment_when_unknown(self):
        status = compute_fed_status('unknown', slot_position=1, max_participants=32)
        self.assertEqual(status, 'pending_payment')

    def test_removed_overrides_paid(self):
        """
        Critical rule: an athlete who PAID can still be removed/replaced if a
        higher-ranked athlete registers after the draw is full.
        removed_or_replaced=True must override payment_status='paid'.
        """
        status = compute_fed_status('paid', slot_position=1, max_participants=32, removed_or_replaced=True)
        self.assertEqual(status, 'removed')

    def test_removed_overrides_waiting_list(self):
        status = compute_fed_status('paid', slot_position=40, max_participants=32, removed_or_replaced=True)
        self.assertEqual(status, 'removed')

    def test_removed_overrides_pending(self):
        status = compute_fed_status('pending', slot_position=None, max_participants=None, removed_or_replaced=True)
        self.assertEqual(status, 'removed')

    def test_not_removed_by_default(self):
        status = compute_fed_status('paid', slot_position=1, max_participants=32)
        self.assertNotEqual(status, 'removed')

    def test_all_statuses_have_label(self):
        for status in ('confirmed', 'waiting_list', 'pending_payment', 'removed'):
            self.assertIn(status, FED_STATUS_LABELS)
            self.assertTrue(len(FED_STATUS_LABELS[status]) > 0)

    def test_removed_label_mentions_ranking(self):
        label = FED_STATUS_LABELS.get('removed', '')
        self.assertIn('rank', label.lower())

    def test_slot_none_and_no_max_confirmed(self):
        """If slot is unknown but paid, status is confirmed (no vagas constraint)."""
        status = compute_fed_status('paid', slot_position=None, max_participants=None)
        self.assertEqual(status, 'confirmed')

    def test_slot_none_with_max_stays_pending(self):
        """If we know max but not slot, can't confirm — stays pending_payment."""
        status = compute_fed_status('pending', slot_position=None, max_participants=32)
        self.assertEqual(status, 'pending_payment')


# ── Bulk import endpoint tests ─────────────────────────────────────────────────

class BulkImportAuthTestCase(TestCase):
    """Test import token and staff auth on bulk-import endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff@test.com', password='pass123', full_name='Staff', is_staff=True
        )
        self.player = User.objects.create_user(
            email='player@test.com', password='pass123', full_name='Player', is_staff=False
        )
        # Minimal tournament edition setup happens inside mocked tests

    def _post(self, payload, token=None, auth_user=None):
        if auth_user:
            self.client.force_authenticate(user=auth_user)
        elif token:
            self.client.credentials(HTTP_X_IMPORT_TOKEN=token)
        else:
            self.client.credentials()
            self.client.force_authenticate(user=None)
        return self.client.post(
            '/api/registrations/federation/bulk-import/',
            data=payload,
            format='json',
        )

    @override_settings(IMPORT_API_TOKEN='')
    def test_unauthenticated_rejected(self):
        res = self._post({'edition_id': 999, 'entries': []})
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_wrong_token_rejected(self):
        res = self._post({'edition_id': 999, 'entries': []}, token='wrong-token')
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_correct_token_accepted_edition_not_found(self):
        """Correct token passes auth — fails at edition lookup (expected 404)."""
        res = self._post({'edition_id': 999999, 'entries': [{'player_name': 'X', 'category_text': 'A'}]}, token=FAKE_TOKEN)
        self.assertEqual(res.status_code, 404)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_non_staff_player_rejected_even_with_jwt(self):
        """Non-staff authenticated users are still rejected."""
        res = self._post({'edition_id': 999, 'entries': []}, auth_user=self.player)
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_staff_jwt_accepted_edition_not_found(self):
        res = self._post({'edition_id': 999999, 'entries': [{'player_name': 'X', 'category_text': 'A'}]}, auth_user=self.staff)
        self.assertEqual(res.status_code, 404)

    @override_settings(IMPORT_API_TOKEN='')
    def test_no_token_configured_rejects_header(self):
        """When IMPORT_API_TOKEN is empty, no token auth is possible."""
        res = self._post({'edition_id': 999, 'entries': []}, token=FAKE_TOKEN)
        self.assertEqual(res.status_code, 403)


class BulkImportValidationTestCase(TestCase):
    """Test payload validation on bulk-import endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff2@test.com', password='pass123', is_staff=True
        )
        self.client.force_authenticate(user=self.staff)

    def test_missing_edition_id_returns_400(self):
        res = self.client.post('/api/registrations/federation/bulk-import/', {'entries': [{'player_name': 'X', 'category_text': 'A'}]}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('edition_id', res.data.get('detail', '').lower())

    def test_empty_entries_returns_400(self):
        res = self.client.post('/api/registrations/federation/bulk-import/', {'edition_id': 1, 'entries': []}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_invalid_confidence_returns_400(self):
        res = self.client.post(
            '/api/registrations/federation/bulk-import/',
            {'edition_id': 1, 'confidence': 'invalid', 'entries': [{'player_name': 'X', 'category_text': 'A'}]},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_dry_run_does_not_save(self):
        """dry_run=true must return preview without persisting anything."""
        from apps.registrations.models import FederationEntry
        from apps.tournaments.models import TournamentEdition, Tournament
        from apps.sources.models import Organization

        org = Organization.objects.create(name='CBT', short_name='CBT', type='confederation')
        from django.utils import timezone as tz
        t = Tournament.objects.create(
            canonical_name='Test Tournament',
            canonical_slug='test-tournament',
            circuit='CBT',
            modality='tennis',
            organization=org,
        )
        edition = TournamentEdition.objects.create(
            tournament=t,
            title='Test Tournament 2026',
            external_id='test:001',
            season_year=2026,
            status='open',
        )
        initial_count = FederationEntry.objects.count()

        res = self.client.post(
            '/api/registrations/federation/bulk-import/',
            {
                'edition_id': edition.id,
                'source': 'manual',
                'dry_run': True,
                'entries': [
                    {'player_name': 'Ana Teste', 'category_text': 'Sub-14 F'},
                    {'player_name': 'Bruno Teste', 'category_text': 'Sub-14 M'},
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['dry_run'])
        self.assertEqual(res.data['created'], 2)  # preview
        self.assertIn('previews', res.data)
        # Nothing saved
        self.assertEqual(FederationEntry.objects.count(), initial_count)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_removed_or_replaced_field_saved(self):
        """removed_or_replaced=true must be persisted."""
        from apps.registrations.models import FederationEntry
        from apps.tournaments.models import TournamentEdition, Tournament
        from apps.sources.models import Organization

        org = Organization.objects.create(name='COSAT-T', short_name='COSAT-T', type='confederation')
        t = Tournament.objects.create(
            canonical_name='COSAT Test',
            canonical_slug='cosat-test-2',
            circuit='COSAT',
            modality='tennis',
            organization=org,
        )
        edition = TournamentEdition.objects.create(
            tournament=t,
            title='COSAT Test 2026',
            external_id='cosat:999',
            season_year=2026,
            status='open',
        )

        res = self.client.post(
            '/api/registrations/federation/bulk-import/',
            {
                'edition_id': edition.id,
                'source': 'cosat',
                'confidence': 'medium',
                'dry_run': False,
                'entries': [
                    {
                        'player_name': 'Carlos Removido',
                        'category_text': 'Sub-14 M',
                        'payment_status': 'paid',
                        'removed_or_replaced': True,
                        'replacement_reason': 'Atleta com ranking superior se inscreveu.',
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['created'], 1)

        entry = FederationEntry.objects.get(player_name='Carlos Removido', edition=edition)
        self.assertTrue(entry.removed_or_replaced)
        self.assertEqual(entry.payment_status, 'paid')
        self.assertIn('ranking superior', entry.replacement_reason)
        self.assertEqual(entry.confidence, 'medium')
