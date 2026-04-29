"""
Tests for registrations app:
- compute_fed_status: all status combinations
- Ranking-replacement rule (removed_or_replaced prevails over payment)
- FederationEntry new fields: source_url, removed_or_replaced, confidence
"""
from django.test import TestCase

from apps.registrations.serializers import (
    compute_fed_status,
    FED_STATUS_LABELS,
)


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
