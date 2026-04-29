"""
Tests for registrations app:
- compute_fed_status: all status combinations
- Ranking-replacement rule (removed_or_replaced prevails over payment)
- FederationEntry new fields: source_url, removed_or_replaced, confidence
- bulk-import endpoint: auth, dry_run, field validation, dedup
- federation-sync-targets endpoint: priority, filtering, exclusions
- parse_entries endpoint + parsers: HTML table, empty input, warnings
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


# ── Parser tests ───────────────────────────────────────────────────────────────

class ParserTestCase(TestCase):
    """Tests for federation entry parsers."""

    # ── COSAT ──

    def test_cosat_empty_input_returns_warning(self):
        from apps.registrations.parsers import parse_cosat_entries
        result = parse_cosat_entries('')
        self.assertTrue(result['parser_warning'])
        self.assertEqual(result['entries'], [])
        self.assertIn('COSAT', result['warning_message'])

    def test_cosat_html_table_extracts_entries(self):
        from apps.registrations.parsers import parse_cosat_entries
        html = """<table>
          <tr><th>Nome</th><th>Categoria</th><th>Ranking</th><th>Pagamento</th></tr>
          <tr><td>Joao Silva</td><td>Sub-14 Masculino</td><td>8</td><td>Pago</td></tr>
          <tr><td>Ana Costa</td><td>Sub-14 Feminino</td><td>12</td><td>Pendente</td></tr>
        </table>"""
        result = parse_cosat_entries(html, source_url='https://cosat.tournamentsoftware.com/test')
        self.assertFalse(result['parser_warning'])
        self.assertEqual(len(result['entries']), 2)
        joao = result['entries'][0]
        self.assertEqual(joao['player_name'], 'Joao Silva')
        self.assertEqual(joao['category_text'], 'Sub-14 Masculino')
        self.assertEqual(joao['ranking_position'], 8)
        self.assertEqual(joao['payment_status'], 'paid')
        self.assertEqual(result['confidence'], 'medium')

    def test_cosat_csv_text_extracts_entries(self):
        from apps.registrations.parsers import parse_cosat_entries
        csv_text = "nome;categoria;ranking;pagamento\nPedro Lima;Sub-16 M;5;Pago\nMaria Santos;Sub-16 F;3;Pendente"
        result = parse_cosat_entries(csv_text)
        self.assertEqual(len(result['entries']), 2)
        self.assertEqual(result['entries'][0]['player_name'], 'Pedro Lima')
        self.assertEqual(result['entries'][0]['ranking_position'], 5)

    def test_cosat_removed_status_detected(self):
        from apps.registrations.parsers import parse_cosat_entries
        html = """<table>
          <tr><th>Nome</th><th>Categoria</th><th>Status</th><th>Pagamento</th></tr>
          <tr><td>Bruno X</td><td>Sub-14 M</td><td>Substituído</td><td>Pago</td></tr>
        </table>"""
        result = parse_cosat_entries(html)
        self.assertEqual(len(result['entries']), 1)
        entry = result['entries'][0]
        self.assertTrue(entry['removed_or_replaced'])
        # Removed overrides payment — the compute_fed_status function handles this,
        # but the field itself must be True in the raw parsed entry.

    # ── CBT ──

    def test_cbt_empty_input_returns_warning(self):
        from apps.registrations.parsers import parse_cbt_entries
        result = parse_cbt_entries('')
        self.assertTrue(result['parser_warning'])
        self.assertEqual(result['entries'], [])

    def test_cbt_html_table_extracts_entries(self):
        from apps.registrations.parsers import parse_cbt_entries
        html = """<table>
          <tr><th>Atleta</th><th>Categoria</th><th>Ranking</th></tr>
          <tr><td>Carlos CBT</td><td>Juvenil Masculino</td><td>15</td></tr>
        </table>"""
        result = parse_cbt_entries(html)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['player_name'], 'Carlos CBT')
        self.assertEqual(result['source'], 'cbt')

    # ── FPT ──

    def test_fpt_empty_input_returns_warning(self):
        from apps.registrations.parsers import parse_fpt_entries
        result = parse_fpt_entries('')
        self.assertTrue(result['parser_warning'])

    # ── Manual ──

    def test_manual_parser_html(self):
        from apps.registrations.parsers import parse_manual_entries
        html = """<table>
          <tr><th>player_name</th><th>category_text</th><th>ranking_position</th></tr>
          <tr><td>Test Athlete</td><td>Open</td><td>1</td></tr>
        </table>"""
        result = parse_manual_entries(html)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['confidence'], 'high')
        self.assertFalse(result['parser_warning'])

    def test_manual_parser_empty_returns_warning(self):
        from apps.registrations.parsers import parse_manual_entries
        result = parse_manual_entries('')
        self.assertTrue(result['parser_warning'])

    # ── Parser registry ──

    def test_get_parser_known_sources(self):
        from apps.registrations.parsers import get_parser
        for src in ('cosat', 'cbt', 'fpt', 'fct', 'manual'):
            self.assertIsNotNone(get_parser(src), f'No parser for {src}')

    def test_get_parser_unknown_source_returns_none(self):
        from apps.registrations.parsers import get_parser
        self.assertIsNone(get_parser('unknown_xyz'))


# ── Sync-targets endpoint tests ────────────────────────────────────────────────

class SyncTargetsEndpointTestCase(TestCase):
    """Tests for GET /api/integrations/federation-sync-targets/."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff3@test.com', password='pass123', is_staff=True,
        )

    def _get(self, params='', token=None, auth_user=None):
        if auth_user:
            self.client.force_authenticate(user=auth_user)
        elif token:
            self.client.credentials(HTTP_X_IMPORT_TOKEN=token)
        else:
            self.client.credentials()
            self.client.force_authenticate(user=None)
        return self.client.get(f'/api/integrations/federation-sync-targets/{params}')

    def _make_edition(self, title, circuit, status='open', source_url='', slug_suffix=''):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name=circuit, defaults={'name': circuit, 'type': 'confederation'},
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug=f'test-{circuit.lower()}{slug_suffix}',
            defaults={
                'canonical_name': f'Test {circuit}',
                'circuit': circuit,
                'modality': 'tennis',
                'organization': org,
            },
        )
        return TournamentEdition.objects.create(
            tournament=t, title=title, external_id=f'test:{title[:8]}',
            season_year=2026, status=status,
            official_source_url=source_url or f'https://example.com/{title[:10]}',
        )

    def test_unauthenticated_returns_403(self):
        res = self._get()
        self.assertEqual(res.status_code, 403)

    def test_staff_jwt_accepted(self):
        res = self._get(auth_user=self.staff)
        self.assertEqual(res.status_code, 200)
        self.assertIn('results', res.data)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_token_accepted(self):
        res = self._get(token=FAKE_TOKEN)
        self.assertEqual(res.status_code, 200)

    def test_excludes_edition_without_source_url(self):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name='CBT2', defaults={'name': 'CBT2', 'type': 'confederation'},
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='no-url-tourney', defaults={
                'canonical_name': 'No URL', 'circuit': 'CBT', 'modality': 'tennis', 'organization': org,
            },
        )
        TournamentEdition.objects.create(
            tournament=t, title='No URL Edition', external_id='no:url',
            season_year=2026, status='open', official_source_url='',
        )
        res = self._get(auth_user=self.staff)
        self.assertEqual(res.status_code, 200)
        ids = [r['edition_id'] for r in res.data['results']]
        no_url = TournamentEdition.objects.get(external_id='no:url')
        self.assertNotIn(no_url.id, ids)

    def test_excludes_finished_editions(self):
        ed = self._make_edition('Finished Ed', 'CBT', status='finished',
                                 source_url='https://example.com/fin', slug_suffix='-fin')
        res = self._get(auth_user=self.staff)
        ids = [r['edition_id'] for r in res.data['results']]
        self.assertNotIn(ed.id, ids)

    def test_open_editions_have_higher_priority(self):
        ed_open = self._make_edition('Open ED', 'FPT', status='open',
                                      source_url='https://fpt.com.br/open', slug_suffix='-open')
        ed_announced = self._make_edition('Ann ED', 'FPT', status='announced',
                                           source_url='https://fpt.com.br/ann', slug_suffix='-ann')
        res = self._get(auth_user=self.staff)
        results = {r['edition_id']: r for r in res.data['results']}
        if ed_open.id in results and ed_announced.id in results:
            self.assertGreaterEqual(
                results[ed_open.id]['sync_priority'],
                results[ed_announced.id]['sync_priority'],
            )

    def test_source_filter(self):
        self._make_edition('CBT Tour', 'CBT', source_url='https://cbt.com/t', slug_suffix='-sf')
        res = self._get('?source=cbt', auth_user=self.staff)
        self.assertEqual(res.status_code, 200)
        for r in res.data['results']:
            self.assertEqual(r['source'], 'cbt')

    def test_response_has_required_fields(self):
        self._make_edition('Complete Ed', 'COSAT',
                           source_url='https://cosat.example.com/t', slug_suffix='-comp')
        res = self._get(auth_user=self.staff)
        self.assertEqual(res.status_code, 200)
        if res.data['results']:
            r = res.data['results'][0]
            for field in ('edition_id', 'tournament_name', 'source', 'source_url',
                          'needs_sync', 'sync_priority', 'parser_available', 'parser_limitation'):
                self.assertIn(field, r, f'Missing field: {field}')

    def test_parse_entries_endpoint_auth(self):
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'cosat', 'html_or_text': '',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_parse_entries_with_html(self):
        self.client.force_authenticate(user=self.staff)
        html = """<table>
          <tr><th>Nome</th><th>Categoria</th></tr>
          <tr><td>Test Player</td><td>Sub-12 M</td></tr>
        </table>"""
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'cosat', 'html_or_text': html,
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('entries', res.data)
        self.assertIn('parser_warning', res.data)
        self.assertIn('count', res.data)

    def test_parse_entries_empty_returns_warning(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'cosat', 'html_or_text': '',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['parser_warning'])
        self.assertEqual(res.data['count'], 0)

    def test_import_not_run_if_entries_empty(self):
        """_run_import returns 400 when entries=[]. Parsers returning [] should not auto-import."""
        self.client.force_authenticate(user=self.staff)
        res = self.client.post('/api/registrations/import/', {
            'edition_id': 1, 'source': 'cosat', 'entries': [],
        }, format='json')
        self.assertEqual(res.status_code, 400)
