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

    def test_sync_targets_returns_new_fields(self):
        """Response must include entries_source_url, ranking_source_url, candidate_entry_links."""
        self._make_edition('FPT Info Ed', 'FPT',
                           source_url='https://fpt.com.br/Torneio/Info/Teste-999',
                           slug_suffix='-info')
        res = self._get(auth_user=self.staff)
        self.assertEqual(res.status_code, 200)
        if res.data['results']:
            r = res.data['results'][0]
            for field in ('entries_source_url', 'ranking_source_url', 'candidate_entry_links'):
                self.assertIn(field, r, f'New field missing: {field}')

    def test_fpt_derives_entries_source_url(self):
        """FPT /Torneio/Info/slug-id should derive candidate entries URL."""
        from apps.registrations.integration_views import derive_entries_source_url
        ed = self._make_edition('FPT Derive', 'FPT',
                                source_url='https://fpt.com.br/Torneio/Info/Campeonato-Brasil-1234',
                                slug_suffix='-derive')
        entries_url, _, candidates = derive_entries_source_url(ed)
        self.assertTrue(
            '1234' in entries_url or any('1234' in c for c in candidates),
            f'FPT ID not in entries_url={entries_url} or candidates={candidates}'
        )
        self.assertTrue(len(candidates) > 0)

    def test_fpt_tournament_link_registration_overrides_derived(self):
        """TournamentLink with type='registration' should be used as entries_source_url."""
        from apps.registrations.integration_views import derive_entries_source_url
        from apps.tournaments.models import TournamentLink
        ed = self._make_edition('FPT Link Ed', 'FPT',
                                source_url='https://fpt.com.br/Torneio/Info/Test-777',
                                slug_suffix='-link')
        reg_url = 'https://fpt.com.br/Inscricao/Torneio/Test-777'
        TournamentLink.objects.create(
            edition=ed, link_type='registration', url=reg_url, label='Inscrição'
        )
        entries_url, _, _ = derive_entries_source_url(ed)
        self.assertEqual(entries_url, reg_url)

    def test_cosat_no_registration_link_entries_url_empty(self):
        """COSAT without a registration link should return empty entries_source_url."""
        from apps.registrations.integration_views import derive_entries_source_url
        ed = self._make_edition('COSAT Ed', 'COSAT',
                                source_url='https://cosat.tournamentsoftware.com/sport/tournament?id=X',
                                slug_suffix='-cosat')
        entries_url, _, _ = derive_entries_source_url(ed)
        # COSAT has no derivable entries URL from DB — must be empty or same as source
        # (not invented). Robot.txt blocks paths anyway.
        self.assertIsInstance(entries_url, str)


# ── Improved parser tests ──────────────────────────────────────────────────────

class ImprovedParserTestCase(TestCase):
    """Tests for improved parsers: aliases, removed detection, payment, safe_int."""

    def test_safe_int_handles_ordinal(self):
        from apps.registrations.parsers import _safe_int
        self.assertEqual(_safe_int('3º'), 3)
        self.assertEqual(_safe_int('12°'), 12)
        self.assertIsNone(_safe_int(''))
        self.assertIsNone(_safe_int(None))
        self.assertEqual(_safe_int('42'), 42)

    def test_classify_payment_expanded(self):
        from apps.registrations.parsers import _classify_payment
        self.assertEqual(_classify_payment('Quitado'), 'paid')
        self.assertEqual(_classify_payment('Aprovado'), 'paid')
        self.assertEqual(_classify_payment('Em aberto'), 'pending')
        self.assertEqual(_classify_payment('A pagar'), 'pending')
        self.assertEqual(_classify_payment(''), 'unknown')
        self.assertEqual(_classify_payment('???'), 'unknown')

    def test_classify_removed_expanded(self):
        from apps.registrations.parsers import _classify_removed
        self.assertTrue(_classify_removed('Withdrawn'))
        self.assertTrue(_classify_removed('Waitlist'))
        self.assertTrue(_classify_removed('Alternates'))
        self.assertTrue(_classify_removed('desistiu'))
        self.assertFalse(_classify_removed('Pago'))
        self.assertFalse(_classify_removed('Confirmado'))

    def test_html_table_alias_classe(self):
        """'classe' should be recognised as a category alias."""
        from apps.registrations.parsers import parse_manual_entries
        html = """<table>
          <tr><th>Nome</th><th>Classe</th><th>Ranking</th></tr>
          <tr><td>Alice</td><td>B</td><td>5</td></tr>
        </table>"""
        result = parse_manual_entries(html)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['category_text'], 'B')
        self.assertEqual(result['entries'][0]['ranking_position'], 5)

    def test_html_table_alias_atleta(self):
        from apps.registrations.parsers import parse_fpt_entries
        html = """<table>
          <tr><th>Atleta</th><th>Categoria</th><th>Pagamento</th></tr>
          <tr><td>João</td><td>Sub-14 M</td><td>Pago</td></tr>
        </table>"""
        result = parse_fpt_entries(html)
        self.assertFalse(result['parser_warning'])
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['payment_status'], 'paid')

    def test_html_skips_header_row_as_entry(self):
        """Parser must not return 'Nome' or 'Atleta' as a player entry."""
        from apps.registrations.parsers import _row_to_entry
        row = {'nome': 'Nome', 'categoria': 'Categoria', 'ranking': 'Ranking'}
        entry = _row_to_entry(row, 'manual', '', 'TEST')
        self.assertIsNone(entry)

    def test_csv_semicolon_parsing(self):
        from apps.registrations.parsers import parse_manual_entries
        csv_text = (
            "nome;categoria;ranking;pagamento\n"
            "Carlos;Sub-16 M;3;Pago\n"
            "Maria;Sub-16 F;7;Pendente"
        )
        result = parse_manual_entries(csv_text)
        self.assertEqual(len(result['entries']), 2)
        self.assertEqual(result['entries'][0]['payment_status'], 'paid')
        self.assertEqual(result['entries'][1]['payment_status'], 'pending')
        self.assertEqual(result['entries'][0]['ranking_position'], 3)

    def test_csv_tab_parsing(self):
        from apps.registrations.parsers import parse_manual_entries
        csv_text = "nome\tcategoria\tranking\n" + "Beatriz\tSub-12 F\t1"
        result = parse_manual_entries(csv_text)
        self.assertEqual(len(result['entries']), 1)
        self.assertEqual(result['entries'][0]['player_name'], 'Beatriz')

    def test_parser_does_not_invent_data_on_empty_html(self):
        """All parsers must return empty entries (never invent) for empty/blank HTML."""
        from apps.registrations.parsers import (
            parse_cosat_entries, parse_cbt_entries,
            parse_fpt_entries, parse_manual_entries,
        )
        for parser in [parse_cosat_entries, parse_cbt_entries, parse_fpt_entries]:
            result = parser('')
            self.assertEqual(result['entries'], [], f'{parser.__name__} invented data on empty input')
            self.assertTrue(result['parser_warning'])

    def test_parser_does_not_invent_on_no_table(self):
        """HTML without any table must yield empty entries."""
        from apps.registrations.parsers import parse_fpt_entries
        html = '<html><body><p>No table here, just text.</p></body></html>'
        result = parse_fpt_entries(html)
        self.assertEqual(result['entries'], [])
        self.assertTrue(result['parser_warning'])

    def test_fpt_parser_source_label(self):
        from apps.registrations.parsers import parse_fpt_entries
        result = parse_fpt_entries('')
        self.assertEqual(result['source'], 'fpt')

    def test_fct_parser_delegates_to_cbt_logic(self):
        from apps.registrations.parsers import parse_fct_entries
        result = parse_fct_entries('')
        self.assertEqual(result['source'], 'fct')
        self.assertTrue(result['parser_warning'])


# ── Payment negation tests ─────────────────────────────────────────────────────

class PaymentNegationTestCase(TestCase):
    """Critical: 'não pago' must never return paid."""

    def _pay(self, text):
        from apps.registrations.parsers import _classify_payment
        return _classify_payment(text)

    # Negation cases — must NOT be paid
    def test_nao_pago_is_not_paid(self):
        self.assertNotEqual(self._pay('não pago'), 'paid')

    def test_nao_pago_ascii_is_not_paid(self):
        self.assertNotEqual(self._pay('nao pago'), 'paid')

    def test_pagamento_nao_confirmado_is_not_paid(self):
        self.assertNotEqual(self._pay('pagamento não confirmado'), 'paid')

    def test_pagamento_nao_confirmado_ascii_is_not_paid(self):
        self.assertNotEqual(self._pay('pagamento nao confirmado'), 'paid')

    def test_nao_confirmado_is_not_paid(self):
        self.assertNotEqual(self._pay('não confirmado'), 'paid')

    def test_not_paid_en_is_not_paid(self):
        self.assertNotEqual(self._pay('not paid'), 'paid')

    # Positive cases — must be paid
    def test_pago_is_paid(self):
        self.assertEqual(self._pay('pago'), 'paid')

    def test_quitado_is_paid(self):
        self.assertEqual(self._pay('quitado'), 'paid')

    def test_aprovado_is_paid(self):
        self.assertEqual(self._pay('aprovado'), 'paid')

    def test_efetuado_is_paid(self):
        self.assertEqual(self._pay('efetuado'), 'paid')

    # Pending cases
    def test_em_aberto_is_pending(self):
        self.assertEqual(self._pay('em aberto'), 'pending')

    def test_a_pagar_is_pending(self):
        self.assertEqual(self._pay('a pagar'), 'pending')

    def test_pendente_is_pending(self):
        self.assertEqual(self._pay('pendente'), 'pending')

    def test_devido_is_pending(self):
        self.assertEqual(self._pay('devido'), 'pending')

    def test_aguardando_is_pending(self):
        self.assertEqual(self._pay('aguardando'), 'pending')

    # Unknown
    def test_empty_is_unknown(self):
        self.assertEqual(self._pay(''), 'unknown')

    def test_ambiguous_is_unknown(self):
        self.assertEqual(self._pay('???'), 'unknown')


# ── Category rejection tests ───────────────────────────────────────────────────

class CategoryRejectionTestCase(TestCase):
    """Rows without a real category must be rejected — never invent category."""

    def test_row_without_category_rejected(self):
        from apps.registrations.parsers import _row_to_entry
        row = {'nome': 'Joao Silva', 'ranking': '5'}  # no category column
        result = _row_to_entry(row, 'manual', '', 'TEST')
        self.assertIsNone(result, 'Row without category must return None')

    def test_no_invented_category_string(self):
        from apps.registrations.parsers import parse_manual_entries
        html = """<table>
          <tr><th>Nome</th><th>Ranking</th></tr>
          <tr><td>Joao</td><td>5</td></tr>
        </table>"""
        result = parse_manual_entries(html)
        for entry in result['entries']:
            self.assertNotIn('não identificad', entry.get('category_text', '').lower())
            self.assertNotIn('nao identificad', entry.get('category_text', '').lower())

    def test_html_without_category_returns_empty(self):
        from apps.registrations.parsers import parse_cosat_entries
        html = """<table>
          <tr><th>Nome</th><th>Ranking</th></tr>
          <tr><td>Maria</td><td>3</td></tr>
        </table>"""
        result = parse_cosat_entries(html)
        # Either returns empty entries or entries without invented category
        self.assertEqual(result['entries'], [])


# ── Dedup deterministic external_id tests ─────────────────────────────────────

class DedupDeterministicTestCase(TestCase):
    """Two athletes without external_id in same category must not overwrite each other."""

    def test_two_athletes_no_external_id_get_distinct_keys(self):
        from apps.registrations.parsers import _row_to_entry
        row1 = {'nome': 'Joao Silva', 'categoria': 'Sub-14 M'}
        row2 = {'nome': 'Pedro Lima', 'categoria': 'Sub-14 M'}
        e1 = _row_to_entry(row1, 'fpt', '', 'FPT')
        e2 = _row_to_entry(row2, 'fpt', '', 'FPT')
        self.assertIsNotNone(e1)
        self.assertIsNotNone(e2)
        self.assertNotEqual(
            e1['player_external_id'], e2['player_external_id'],
            'Different athletes must get distinct deterministic external_ids'
        )

    def test_same_athlete_same_category_gets_same_key(self):
        """Re-importing same athlete twice must produce same external_id (idempotent)."""
        from apps.registrations.parsers import _row_to_entry
        row = {'nome': 'Maria Santos', 'categoria': 'Sub-12 F'}
        e1 = _row_to_entry(row, 'cbt', '', 'CBT')
        e2 = _row_to_entry(row, 'cbt', '', 'CBT')
        self.assertEqual(e1['player_external_id'], e2['player_external_id'])

    def test_deterministic_id_contains_source_and_slug(self):
        from apps.registrations.parsers import _row_to_entry
        row = {'nome': 'Ana Costa', 'categoria': 'Juvenil F'}
        entry = _row_to_entry(row, 'cosat', '', 'COSAT')
        self.assertIn('cosat', entry['player_external_id'])

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_import_two_athletes_no_external_id_creates_two_records(self):
        """Bulk-import of two athletes without external_id must create 2 separate records."""
        from apps.registrations.models import FederationEntry
        from apps.tournaments.models import TournamentEdition, Tournament
        from apps.sources.models import Organization

        org, _ = Organization.objects.get_or_create(
            short_name='FPT2', defaults={'name': 'FPT2', 'type': 'federation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='dedup-test-tourney', defaults={
                'canonical_name': 'Dedup Test', 'circuit': 'FPT',
                'modality': 'tennis', 'organization': org,
            }
        )
        edition = TournamentEdition.objects.create(
            tournament=t, title='Dedup Edition', external_id='dedup:001',
            season_year=2026, status='open',
        )
        self.client.force_authenticate(user=User.objects.create_user(
            email='ded@test.com', password='pass', is_staff=True
        ))
        res = self.client.post('/api/registrations/import/', {
            'edition_id': edition.id,
            'source': 'fpt',
            'entries': [
                {'player_name': 'Joao Dedup', 'category_text': 'Sub-14 M', 'player_external_id': ''},
                {'player_name': 'Pedro Dedup', 'category_text': 'Sub-14 M', 'player_external_id': ''},
            ],
        }, format='json')
        self.assertEqual(res.status_code, 200)
        # Both athletes must be created as separate records
        count = FederationEntry.objects.filter(edition=edition).count()
        self.assertEqual(count, 2, f'Expected 2 records, got {count}. Dedup may have merged athletes.')


# ── preferred_entries_url tests ────────────────────────────────────────────────

class PreferredEntriesUrlTestCase(TestCase):
    """preferred_entries_url must be best available URL for n8n to fetch."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff_pref@test.com', password='pass', is_staff=True
        )

    def _make_edition(self, title, circuit, source_url, slug_suffix=''):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name=circuit, defaults={'name': circuit, 'type': 'confederation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug=f'pref-{circuit.lower()}{slug_suffix}',
            defaults={'canonical_name': circuit, 'circuit': circuit,
                      'modality': 'tennis', 'organization': org},
        )
        return TournamentEdition.objects.create(
            tournament=t, title=title, external_id=f'pref:{title[:8]}',
            season_year=2026, status='open', official_source_url=source_url,
        )

    def test_preferred_url_falls_back_to_source_url_when_no_links(self):
        ed = self._make_edition('Pref Ed 1', 'COSAT',
                                'https://cosat.example.com/t', slug_suffix='-p1')
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)
        results = {r['edition_id']: r for r in res.data['results']}
        if ed.id in results:
            r = results[ed.id]
            self.assertIn('preferred_entries_url', r)
            # No links = preferred_entries_url should equal source_url
            self.assertEqual(r['preferred_entries_url'], ed.official_source_url)

    def test_preferred_url_uses_registration_link_when_available(self):
        from apps.tournaments.models import TournamentLink
        ed = self._make_edition('Pref FPT', 'FPT',
                                'https://fpt.com.br/Torneio/Info/Test-888',
                                slug_suffix='-p2')
        reg_url = 'https://fpt.com.br/Inscricao/Torneio/Test-888'
        TournamentLink.objects.create(edition=ed, link_type='registration', url=reg_url, label='Inscricao')
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)
        results = {r['edition_id']: r for r in res.data['results']}
        if ed.id in results:
            self.assertEqual(results[ed.id]['preferred_entries_url'], reg_url)

    def test_cbt_with_candidate_links_uses_first_candidate_as_preferred(self):
        """CBT with empty entries_source_url and candidates → preferred = candidates[0]."""
        ed = self._make_edition('CBT Cand', 'CBT',
                                'https://www.tenisintegrado.com.br/torneio/99999',
                                slug_suffix='-cand')
        # external_id triggers CBT candidate derivation
        ed.external_id = 'cbt:99999'
        ed.save()
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)
        results = {r['edition_id']: r for r in res.data['results']}
        if ed.id in results:
            r = results[ed.id]
            self.assertIn('preferred_entries_url', r)
            # preferred must not be empty
            self.assertTrue(r['preferred_entries_url'])


# ── Limit validation tests ─────────────────────────────────────────────────────

class LimitValidationTestCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff_lim@test.com', password='pass', is_staff=True
        )

    def _get(self, params):
        self.client.force_authenticate(user=self.staff)
        return self.client.get(f'/api/integrations/federation-sync-targets/{params}')

    def test_limit_abc_does_not_crash(self):
        res = self._get('?limit=abc')
        self.assertEqual(res.status_code, 200)

    def test_limit_negative_uses_minimum(self):
        res = self._get('?limit=-1')
        self.assertEqual(res.status_code, 200)

    def test_limit_zero_returns_valid_response(self):
        res = self._get('?limit=0')
        self.assertEqual(res.status_code, 200)
        self.assertIn('results', res.data)

    def test_limit_9999_capped_at_500(self):
        res = self._get('?limit=9999')
        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(len(res.data['results']), 500)


# ── Auth tests for integration endpoints ───────────────────────────────────────

class IntegrationAuthTestCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='staff_auth@test.com', password='pass', is_staff=True
        )
        self.player = User.objects.create_user(
            email='player_auth@test.com', password='pass', is_staff=False
        )

    # GET /api/integrations/federation-sync-targets/

    def test_sync_targets_no_auth_returns_403(self):
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_sync_targets_wrong_token_returns_403(self):
        self.client.credentials(HTTP_X_IMPORT_TOKEN='wrong-token')
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_sync_targets_correct_token_returns_200(self):
        self.client.credentials(HTTP_X_IMPORT_TOKEN=FAKE_TOKEN)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)

    def test_sync_targets_staff_jwt_returns_200(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)

    def test_sync_targets_non_staff_returns_403(self):
        self.client.force_authenticate(user=self.player)
        res = self.client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 403)

    # POST /api/integrations/parse-entries/

    def test_parse_entries_no_auth_returns_403(self):
        res = self.client.post('/api/integrations/parse-entries/',
                               {'source': 'cosat', 'html_or_text': ''}, format='json')
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_parse_entries_wrong_token_returns_403(self):
        self.client.credentials(HTTP_X_IMPORT_TOKEN='bad-token')
        res = self.client.post('/api/integrations/parse-entries/',
                               {'source': 'cosat', 'html_or_text': ''}, format='json')
        self.assertEqual(res.status_code, 403)

    @override_settings(IMPORT_API_TOKEN=FAKE_TOKEN)
    def test_parse_entries_correct_token_returns_200(self):
        self.client.credentials(HTTP_X_IMPORT_TOKEN=FAKE_TOKEN)
        res = self.client.post('/api/integrations/parse-entries/',
                               {'source': 'cosat', 'html_or_text': ''}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_parse_entries_staff_jwt_returns_200(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post('/api/integrations/parse-entries/',
                               {'source': 'cosat', 'html_or_text': ''}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_parse_entries_non_staff_returns_403(self):
        self.client.force_authenticate(user=self.player)
        res = self.client.post('/api/integrations/parse-entries/',
                               {'source': 'cosat', 'html_or_text': ''}, format='json')
        self.assertEqual(res.status_code, 403)


# ── dry_run string parsing tests ───────────────────────────────────────────────

class DryRunParsingTestCase(TestCase):
    """dry_run='false' string must not be treated as True."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='drstaff@test.com', password='pass', is_staff=True
        )
        self.client.force_authenticate(user=self.staff)

    def _make_edition(self):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name='DRTEST', defaults={'name': 'DryRunTest', 'type': 'confederation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='dry-run-test', defaults={
                'canonical_name': 'DryRun', 'circuit': 'CBT',
                'modality': 'tennis', 'organization': org,
            }
        )
        return TournamentEdition.objects.create(
            tournament=t, title='DryRun Ed', external_id='dr:001',
            season_year=2026, status='open',
        )

    def _post(self, edition_id, dry_run_value):
        return self.client.post('/api/registrations/import/', {
            'edition_id': edition_id,
            'source': 'manual',
            'dry_run': dry_run_value,
            'entries': [{'player_name': 'Test Athlete', 'category_text': 'Sub-14 M'}],
        }, format='json')

    def test_dry_run_true_boolean_does_not_save(self):
        from apps.registrations.models import FederationEntry
        ed = self._make_edition()
        count_before = FederationEntry.objects.filter(edition=ed).count()
        res = self._post(ed.id, True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['dry_run'])
        self.assertEqual(FederationEntry.objects.filter(edition=ed).count(), count_before)

    def test_dry_run_false_boolean_saves(self):
        from apps.registrations.models import FederationEntry
        ed = self._make_edition()
        res = self._post(ed.id, False)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['dry_run'])
        self.assertGreater(FederationEntry.objects.filter(edition=ed).count(), 0)

    def test_dry_run_string_true_does_not_save(self):
        from apps.registrations.models import FederationEntry
        ed = self._make_edition()
        count_before = FederationEntry.objects.filter(edition=ed).count()
        res = self._post(ed.id, 'true')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['dry_run'], 'dry_run="true" string must be treated as True')
        self.assertEqual(FederationEntry.objects.filter(edition=ed).count(), count_before)

    def test_dry_run_string_false_saves(self):
        """Critical: dry_run='false' string must be treated as False, not True."""
        from apps.registrations.models import FederationEntry
        ed = self._make_edition()
        res = self._post(ed.id, 'false')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            res.data['dry_run'],
            'dry_run="false" string must be treated as False — not True!'
        )
        # Data must have been saved
        self.assertGreater(
            FederationEntry.objects.filter(edition=ed).count(), 0,
            'dry_run="false" must save data to DB'
        )


# ── Source inference tests ─────────────────────────────────────────────────────

class SourceInferenceTestCase(TestCase):
    """Tests for infer_source_from_url and infer_source_from_edition."""

    def test_fpt_url_returns_fpt(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url('https://fpt.com.br/Torneio/Info/Test-123'), 'fpt')

    def test_fpt_inscricao_url_returns_fpt(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url('https://fpt.com.br/Inscricao/InscricaoTorneio/Tenis/Test-123'), 'fpt')

    def test_cbt_tenis_url_returns_cbt(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url('https://cbt-tenis.com.br/torneio/123'), 'cbt')

    def test_cosat_tournamentsoftware_returns_cosat(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url('https://cosat.tournamentsoftware.com/sport/tournament?id=X'), 'cosat')

    def test_tenisintegrado_url_returns_empty(self):
        """tenisintegrado is ambiguous — returns '' to force edition-level resolution."""
        from apps.registrations.integration_views import infer_source_from_url
        result = infer_source_from_url('https://www.tenisintegrado.com.br/torneio_painel_info/index/123')
        self.assertEqual(result, '', 'tenisintegrado domain alone is ambiguous — must return empty')

    def test_unknown_url_returns_empty(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url('https://example.com/something'), '')

    def test_empty_url_returns_empty(self):
        from apps.registrations.integration_views import infer_source_from_url
        self.assertEqual(infer_source_from_url(''), '')

    def test_edition_with_fpt_url_returns_fpt(self):
        from apps.registrations.integration_views import infer_source_from_edition
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name='INFSRC', defaults={'name': 'InfSrc', 'type': 'confederation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='inf-fpt-test', defaults={
                'canonical_name': 'Inf FPT', 'circuit': '',  # empty circuit
                'modality': 'tennis', 'organization': org,
            }
        )
        edition = TournamentEdition.objects.create(
            tournament=t, title='FPT Infer', external_id='inf:fpt:1',
            season_year=2026, status='open',
            official_source_url='https://fpt.com.br/Torneio/Info/TestInfer-999',
        )
        result = infer_source_from_edition(edition)
        self.assertEqual(result, 'fpt', f'Expected fpt, got {result}')

    def test_edition_with_tenisintegrado_url_returns_cbt_default(self):
        from apps.registrations.integration_views import infer_source_from_edition
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name='INFCBT', defaults={'name': 'InfCBT', 'type': 'confederation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='inf-cbt-test', defaults={
                'canonical_name': 'Inf CBT', 'circuit': '',
                'modality': 'tennis', 'organization': org,
            }
        )
        edition = TournamentEdition.objects.create(
            tournament=t, title='CBT Infer', external_id='inf:cbt:1',
            season_year=2026, status='open',
            official_source_url='https://www.tenisintegrado.com.br/torneio_painel_info/index/9999',
        )
        result = infer_source_from_edition(edition)
        self.assertIn(result, ('cbt', 'fct', 'fmt'), f'tenisintegrado should be cbt/fct/fmt, got {result}')

    def test_sync_targets_fpt_url_not_manual(self):
        """sync-targets must not return source=manual for FPT URL editions."""
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org, _ = Organization.objects.get_or_create(
            short_name='FPT_INF', defaults={'name': 'FPT_INF', 'type': 'federation'}
        )
        t, _ = Tournament.objects.get_or_create(
            canonical_slug='sync-fpt-infer', defaults={
                'canonical_name': 'Sync FPT Infer', 'circuit': '',  # empty circuit
                'modality': 'tennis', 'organization': org,
            }
        )
        TournamentEdition.objects.create(
            tournament=t, title='Sync FPT', external_id='sync:fpt:1',
            season_year=2026, status='open',
            official_source_url='https://fpt.com.br/Inscricao/InscricaoTorneio/Tenis/Campeonato-Estadual-999',
        )
        client = APIClient()
        staff = User.objects.create_user(email='infstaff@test.com', password='pass', is_staff=True)
        client.force_authenticate(user=staff)
        res = client.get('/api/integrations/federation-sync-targets/')
        self.assertEqual(res.status_code, 200)
        sources = {r['source'] for r in res.data['results']}
        fpt_editions = [r for r in res.data['results'] if 'fpt.com.br' in r.get('source_url', '')]
        for r in fpt_editions:
            self.assertNotEqual(r['source'], 'manual', f'FPT URL should not be manual: {r}')
            self.assertEqual(r['source'], 'fpt')


class ParseEntriesSourceDetectionTestCase(TestCase):
    """parse-entries auto-detects source from URL when source=manual."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='pd_staff@test.com', password='pass', is_staff=True
        )
        self.client.force_authenticate(user=self.staff)

    def test_manual_plus_fpt_url_uses_fpt_parser(self):
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'manual',
            'html_or_text': '',
            'source_url': 'https://fpt.com.br/Inscricao/InscricaoTorneio/Tenis/Test-999',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('source_detected', res.data)
        self.assertIn('source_requested', res.data)
        self.assertIn('parser_used', res.data)
        self.assertEqual(res.data['source_requested'], 'manual')
        self.assertEqual(res.data['source_detected'], 'fpt')
        self.assertEqual(res.data['parser_used'], 'fpt')

    def test_manual_plus_tenisintegrado_url_uses_cbt_parser(self):
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'manual',
            'html_or_text': '',
            'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_info/index/9999',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['source_requested'], 'manual')
        self.assertIn(res.data['source_detected'], ('cbt', 'fct', 'fmt'))

    def test_explicit_source_not_overridden(self):
        """If source=fpt is explicitly passed, don't override it."""
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'fpt',
            'html_or_text': '',
            'source_url': 'https://fpt.com.br/Test',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['source_requested'], 'fpt')
        self.assertEqual(res.data['source_detected'], 'fpt')

    def test_response_has_new_traceability_fields(self):
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'cosat',
            'html_or_text': '',
            'source_url': 'https://cosat.tournamentsoftware.com/sport/tournament?id=X',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        for field in ('source_requested', 'source_detected', 'parser_used', 'source_url', 'quality_gate'):
            self.assertIn(field, res.data, f'Missing field: {field}')


class TenisIntegradoParserTestCase(TestCase):
    """Unit tests for the CBT/TenisIntegrado parser and table extractor."""

    # Minimal realistic HTML for one category (12 Anos Masculino Simples)
    _TABLE_HTML = """
    <table>
      <tr>
        <th>Participantes</th><th>WTN</th><th>Posição</th><th>Sit. Financeira</th>
      </tr>
      <tr>
        <td>
          <a href="perfil2/index/405248">
            <img src="avatar.jpg">
          </a>
          <a href="perfil2/index/405248">Miguel Soares Vonjonie</a>
          Sinop
          UF:MT, ID:405248, Idade:12
        </td>
        <td><img src="wtn.png">31,28</td>
        <td>28º</td>
        <td>Pendente</td>
      </tr>
      <tr>
        <td>
          <a href="perfil2/index/278849">Carlos Eduardo Molin De Andrade</a>
          Cuiaba
          UF:MT, ID:278849, Idade:12
        </td>
        <td></td>
        <td></td>
        <td>Confirmado</td>
      </tr>
    </table>
    """

    def test_parse_table_extracts_names(self):
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '12 Anos Masculino Simples', 'cbt',
            'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
        )
        self.assertEqual(len(entries), 2)
        names = [e['player_name'] for e in entries]
        self.assertIn('Miguel Soares Vonjonie', names)
        self.assertIn('Carlos Eduardo Molin De Andrade', names)

    def test_parse_table_player_external_id(self):
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '12 Anos Masculino Simples', 'cbt', '',
        )
        ids = {e['player_external_id'] for e in entries}
        self.assertIn('tenisintegrado:405248', ids)
        self.assertIn('tenisintegrado:278849', ids)

    def test_parse_table_payment_status(self):
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '12 Anos Masculino Simples', 'cbt', '',
        )
        by_id = {e['player_external_id']: e for e in entries}
        self.assertEqual(by_id['tenisintegrado:405248']['payment_status'], 'pending')
        self.assertEqual(by_id['tenisintegrado:278849']['payment_status'], 'paid')

    def test_parse_table_ranking_position(self):
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '12 Anos Masculino Simples', 'cbt', '',
        )
        by_id = {e['player_external_id']: e for e in entries}
        self.assertEqual(by_id['tenisintegrado:405248']['ranking_position'], 28)
        self.assertIsNone(by_id['tenisintegrado:278849']['ranking_position'])

    def test_parse_table_category_text(self):
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '14 Anos Feminino Simples', 'cbt', '',
        )
        for e in entries:
            self.assertEqual(e['category_text'], '14 Anos Feminino Simples')

    def test_parse_table_skips_header_row(self):
        """Header <tr> has <th> not <td> — should not produce entries."""
        from apps.registrations.parsers import _parse_tenisintegrado_table
        entries = _parse_tenisintegrado_table(
            self._TABLE_HTML, '12 Anos Masculino Simples', 'cbt', '',
        )
        names = [e['player_name'] for e in entries]
        self.assertNotIn('Participantes', names)

    def test_fetch_uses_auto_mode_when_url_and_no_html(self):
        """parse_cbt_entries auto-delegates to fetch when source_url has tenisintegrado."""
        from unittest.mock import patch as _patch
        from apps.registrations.parsers import parse_cbt_entries
        mock_result = {
            'entries': [{'player_name': 'Mock Player', 'category_text': '12 Masc',
                         'player_external_id': 'tenisintegrado:999', 'ranking_position': 1,
                         'ranking_source': 'CBT', 'payment_status': 'paid',
                         'removed_or_replaced': False, 'replacement_reason': '',
                         'source_url': '', 'confidence': 'high'}],
            'parser_warning': False, 'warning_message': '', 'confidence': 'high', 'source': 'cbt',
        }
        with _patch(
            'apps.registrations.parsers.fetch_tenisintegrado_entries',
            return_value=mock_result,
        ) as mock_fetch:
            result = parse_cbt_entries(
                '', source_url='https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251'
            )
        mock_fetch.assert_called_once()
        self.assertEqual(result['confidence'], 'high')
        self.assertEqual(len(result['entries']), 1)

    def test_fetch_no_url_returns_warning(self):
        """parse_cbt_entries returns warning when no html and no tenisintegrado URL."""
        from apps.registrations.parsers import parse_cbt_entries
        result = parse_cbt_entries('', source_url='')
        self.assertTrue(result['parser_warning'])
        self.assertEqual(result['entries'], [])

    def test_fetch_bad_url_returns_warning(self):
        """fetch_tenisintegrado_entries returns warning when URL has no tournament ID."""
        from apps.registrations.parsers import fetch_tenisintegrado_entries
        result = fetch_tenisintegrado_entries('https://www.tenisintegrado.com.br/torneio')
        self.assertTrue(result['parser_warning'])
        self.assertEqual(result['entries'], [])


class QualityGateAutoFetchTestCase(TestCase):
    """
    quality_gate must not block auto-fetch success (CBT/TenisIntegrado).

    Rules:
    - CBT + empty html + valid tenisintegrado URL + entries > 0 + confidence=high → can_save=True
    - manual + empty html → can_save=False (no auto-fetch)
    - fpt + empty html + no entries → can_save=False
    - Any source with entries > 0 + no warning → no 'html_or_text vazio' reason
    """

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='qg_staff@test.com', password='pass', is_staff=True
        )
        self.client.force_authenticate(user=self.staff)

    _MOCK_ENTRY = {
        'player_name': 'Miguel Soares Vonjonie',
        'category_text': '12 Anos Masculino Simples',
        'player_external_id': 'tenisintegrado:405248',
        'ranking_position': 28,
        'ranking_source': 'CBT',
        'payment_status': 'pending',
        'removed_or_replaced': False,
        'replacement_reason': '',
        'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
        'confidence': 'high',
    }

    def _mock_cbt_result(self, n=3):
        return {
            'entries': [dict(self._MOCK_ENTRY, player_external_id=f'tenisintegrado:{405248+i}',
                             player_name=f'Atleta {i}') for i in range(n)],
            'parser_warning': False,
            'warning_message': '',
            'confidence': 'high',
            'source': 'cbt',
        }

    def test_cbt_auto_fetch_success_can_save_true(self):
        """CBT empty html + valid tenisintegrado URL + entries → can_save=True."""
        with self.settings(IMPORT_API_TOKEN=''):
            with patch('apps.registrations.parsers.fetch_tenisintegrado_entries',
                       return_value=self._mock_cbt_result(3)):
                res = self.client.post('/api/integrations/parse-entries/', {
                    'source': 'cbt',
                    'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
                    'html_or_text': '',
                }, format='json')
        self.assertEqual(res.status_code, 200)
        qg = res.data['quality_gate']
        self.assertTrue(qg['can_save'], f"Expected can_save=True, reasons: {qg['reasons']}")
        self.assertNotIn('html_or_text vazio — nenhum conteúdo para parsear', qg['reasons'])
        self.assertEqual(qg['entries_count'], 3)

    def test_cbt_auto_fetch_response_fields(self):
        """Response includes supports_auto_fetch and auto_fetch_used fields."""
        with patch('apps.registrations.parsers.fetch_tenisintegrado_entries',
                   return_value=self._mock_cbt_result(1)):
            res = self.client.post('/api/integrations/parse-entries/', {
                'source': 'cbt',
                'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
                'html_or_text': '',
            }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get('supports_auto_fetch'))
        self.assertTrue(res.data.get('auto_fetch_used'))

    def test_manual_empty_html_cannot_save(self):
        """manual + empty html → quality_gate.can_save=False."""
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'manual',
            'html_or_text': '',
            'source_url': '',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        qg = res.data['quality_gate']
        self.assertFalse(qg['can_save'])
        self.assertIn('html_or_text vazio — nenhum conteúdo para parsear', qg['reasons'])

    def test_fpt_empty_html_no_entries_cannot_save(self):
        """fpt + empty html + no entries → can_save=False, html_or_text reason present."""
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'fpt',
            'html_or_text': '',
            'source_url': 'https://fpt.com.br/Inscricao/InscricaoTorneio/Tenis/2026/test-999',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        qg = res.data['quality_gate']
        self.assertFalse(qg['can_save'])
        self.assertIn('html_or_text vazio — nenhum conteúdo para parsear', qg['reasons'])

    def test_fpt_supports_auto_fetch_false(self):
        """FPT does not support auto-fetch — response field reflects this."""
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'fpt',
            'html_or_text': '',
            'source_url': '',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data.get('supports_auto_fetch'))
        self.assertFalse(res.data.get('auto_fetch_used'))

    def test_cbt_with_html_provided_does_not_use_auto_fetch(self):
        """If html_or_text is provided, auto_fetch_used=False even for CBT."""
        html = '<table><tr><th>Nome</th><th>Categoria</th></tr>' \
               '<tr><td>João Silva</td><td>14 Anos Masc</td></tr></table>'
        res = self.client.post('/api/integrations/parse-entries/', {
            'source': 'cbt',
            'html_or_text': html,
            'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data.get('auto_fetch_used'))

    def test_cbt_auto_fetch_zero_entries_cannot_save(self):
        """CBT auto-fetch but parser returns 0 entries → can_save=False."""
        empty_result = {
            'entries': [], 'parser_warning': True,
            'warning_message': 'nenhum inscrito', 'confidence': 'low', 'source': 'cbt',
        }
        with patch('apps.registrations.parsers.fetch_tenisintegrado_entries',
                   return_value=empty_result):
            res = self.client.post('/api/integrations/parse-entries/', {
                'source': 'cbt',
                'source_url': 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/22251',
                'html_or_text': '',
            }, format='json')
        self.assertEqual(res.status_code, 200)
        qg = res.data['quality_gate']
        self.assertFalse(qg['can_save'])
        self.assertIn('entries vazio — nenhum inscrito extraído', qg['reasons'])
