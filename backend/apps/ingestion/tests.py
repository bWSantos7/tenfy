"""Tests for ingestion: dedup fingerprint, youth classifier, persistence logic, COSAT Mongo connector."""
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase, override_settings


class DedupFingerprintTestCase(TestCase):
    def test_same_title_date_city_produces_same_fingerprint(self):
        from apps.ingestion.persistence import _dedup_fingerprint
        fp1 = _dedup_fingerprint('Open São Paulo 2026', '2026-03-15', 'São Paulo', 'SP')
        fp2 = _dedup_fingerprint('Open São Paulo 2026', '2026-03-15', 'São Paulo', 'SP')
        self.assertEqual(fp1, fp2)

    def test_different_cities_produce_different_fingerprints(self):
        from apps.ingestion.persistence import _dedup_fingerprint
        fp1 = _dedup_fingerprint('Open 2026', '2026-03-15', 'São Paulo', 'SP')
        fp2 = _dedup_fingerprint('Open 2026', '2026-03-15', 'Campinas', 'SP')
        self.assertNotEqual(fp1, fp2)

    def test_accents_normalized(self):
        from apps.ingestion.persistence import _dedup_fingerprint
        fp1 = _dedup_fingerprint('Torneio Júnior', '2026-04-01', 'São Paulo', 'SP')
        fp2 = _dedup_fingerprint('Torneio Junior', '2026-04-01', 'Sao Paulo', 'SP')
        self.assertEqual(fp1, fp2)

    def test_fingerprint_is_16_chars(self):
        from apps.ingestion.persistence import _dedup_fingerprint
        fp = _dedup_fingerprint('Test Tournament', '2026-01-01', 'Brasilia', 'DF')
        self.assertEqual(len(fp), 16)

    def test_empty_inputs_dont_crash(self):
        from apps.ingestion.persistence import _dedup_fingerprint
        fp = _dedup_fingerprint('', None, '', '')
        self.assertIsInstance(fp, str)


class YouthClassifierTestCase(TestCase):
    def test_infantojuvenil_keyword(self):
        from apps.ingestion.persistence import _classify_is_youth
        self.assertTrue(_classify_is_youth('CBT', 'Torneio Infantojuvenil SP', []))

    def test_junior_keyword(self):
        from apps.ingestion.persistence import _classify_is_youth
        self.assertTrue(_classify_is_youth('ITF', 'ITF Junior Tournament', []))

    def test_age_category_in_title(self):
        from apps.ingestion.persistence import _classify_is_youth
        cats = [{'source_text': '14 anos Masculino'}]
        self.assertTrue(_classify_is_youth('FPT', 'Open SP', cats))

    def test_adult_open_not_youth(self):
        from apps.ingestion.persistence import _classify_is_youth
        cats = [{'source_text': 'Open Masculino'}, {'source_text': '40+ Masculino'}]
        self.assertFalse(_classify_is_youth('FPT', 'Aberto SP', cats))

    def test_sub_keyword(self):
        from apps.ingestion.persistence import _classify_is_youth
        cats = [{'source_text': 'Sub-16 Feminino'}]
        self.assertTrue(_classify_is_youth('CBT', 'Circuit', cats))


# ── COSAT MongoDB connector tests ─────────────────────────────────────────────

class CosatMongoNormalizationTestCase(TestCase):
    """Unit tests for MongoDB document normalizers — no real MongoDB needed."""

    # ── _normalize_tournament ─────────────────────────────────────────────────

    def test_normalize_tournament_full(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'abc123',
            'name': 'COSAT Junior Open 2025',
            'url': 'https://cosat.tournamentsoftware.com/sport/tournament?id=abc123',
            'organization': 'COSAT',
            'location': 'Buenos Aires, AR',
            'country': 'AR',
            'dateRange': '10 - 15 Nov 2025',
            'events': [
                {'name': 'U14 Boys Singles'},
                {'name': 'U14 Girls Singles'},
            ],
            'lastUpdated': datetime(2025, 11, 15, 12, 0, 0),
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['external_id'], 'cosat:abc123')
        self.assertEqual(result['circuit'], 'COSAT')
        self.assertEqual(result['title'], 'COSAT Junior Open 2025')
        self.assertEqual(result['start_date'], '2025-11-10')
        self.assertEqual(result['end_date'], '2025-11-15')
        self.assertEqual(len(result['categories']), 2)
        self.assertEqual(result['categories'][0]['source_text'], 'U14 Boys Singles')
        self.assertIn('Buenos Aires', result['venue']['city'])

    def test_normalize_tournament_missing_cosat_id_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        result = _normalize_tournament({'name': 'Some Tournament'})
        self.assertIsNone(result)

    def test_normalize_tournament_missing_name_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        result = _normalize_tournament({'cosatId': 'xyz'})
        self.assertIsNone(result)

    def test_normalize_tournament_no_date_range_ok(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {'cosatId': 'xyz', 'name': 'COSAT Open', 'url': 'https://cosat.tournamentsoftware.com/x'}
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertIsNone(result['start_date'])
        self.assertIsNone(result['end_date'])

    def test_normalize_tournament_raw_has_no_secrets(self):
        """_raw block must not leak any credential-like keys."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {'cosatId': 'abc', 'name': 'T', 'url': ''}
        result = _normalize_tournament(doc)
        raw_keys = set((result or {}).get('_raw', {}).keys())
        forbidden = {'password', 'token', 'secret', 'api_key', 'auth'}
        self.assertEqual(raw_keys & forbidden, set())

    # ── _normalize_player ─────────────────────────────────────────────────────

    def test_normalize_player_full(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {
            'name': 'Maria González',
            'tournamentId': 'abc123',
            'profileId': 'P-9999',
            'tournamentPlayerId': 'TP-001',
            'rankingCategory': 'U16 Girls',
            'lastUpdated': datetime(2025, 11, 1),
        }
        result = _normalize_player(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['player_name'], 'Maria González')
        self.assertEqual(result['player_external_id'], 'cosat:P-9999')
        self.assertEqual(result['tournament_cosat_id'], 'abc123')
        self.assertEqual(result['category_text'], 'U16 Girls')
        self.assertEqual(result['payment_status'], 'unknown')
        self.assertFalse(result['removed_or_replaced'])

    def test_normalize_player_missing_name_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        result = _normalize_player({'tournamentId': 'abc', 'profileId': '99'})
        self.assertIsNone(result)

    def test_normalize_player_no_profile_id_empty_external_id(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {'name': 'Player X', 'tournamentId': 'abc'}
        result = _normalize_player(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['player_external_id'], '')

    # ── _normalize_ranking ────────────────────────────────────────────────────

    def test_normalize_ranking_full(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_ranking
        doc = {
            'playerName': 'Carlos Alcaraz Jr',
            'rank': 3,
            'category': 'U18 Boys Singles',
            'profileId': 'PROF-777',
            'sourceUrl': 'https://cosat.tournamentsoftware.com/ranking/2025',
            'singlesPoints': '150',
            'totalPoints': '150',
        }
        result = _normalize_ranking(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['player_name'], 'Carlos Alcaraz Jr')
        self.assertEqual(result['ranking_position'], 3)
        self.assertEqual(result['category_text'], 'U18 Boys Singles')
        self.assertEqual(result['player_external_id'], 'cosat:PROF-777')
        self.assertEqual(result['confidence'], 'high')
        self.assertEqual(result['source_url'], 'https://cosat.tournamentsoftware.com/ranking/2025')

    def test_normalize_ranking_missing_name_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_ranking
        result = _normalize_ranking({'rank': 1, 'category': 'U14'})
        self.assertIsNone(result)

    def test_normalize_ranking_absent_rank_is_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_ranking
        doc = {'playerName': 'X', 'category': 'U14', 'rank': None}
        result = _normalize_ranking(doc)
        self.assertIsNone(result['ranking_position'])

    # ── Date parsing ──────────────────────────────────────────────────────────

    def test_parse_date_range_same_month(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        start, end = _parse_date_range('10 - 15 Nov 2025')
        from datetime import date
        self.assertEqual(start, date(2025, 11, 10))
        self.assertEqual(end, date(2025, 11, 15))

    def test_parse_date_range_cross_month(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        start, end = _parse_date_range('28 Nov - 3 Dec 2025')
        from datetime import date
        self.assertEqual(start, date(2025, 11, 28))
        self.assertEqual(end, date(2025, 12, 3))

    def test_parse_date_range_empty_returns_none_tuple(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        start, end = _parse_date_range('')
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_parse_location_city_and_code(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_location
        city, state = _parse_location('Buenos Aires, AR', 'AR')
        self.assertEqual(city, 'Buenos Aires')
        self.assertEqual(state, 'AR')

    def test_parse_location_city_only_uses_country(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_location
        city, state = _parse_location('Bogotá', 'CO')
        self.assertEqual(city, 'Bogotá')
        self.assertEqual(state, 'CO')


class CosatMongoConnectorOfflineTestCase(TestCase):
    """Connector handles MongoDB being offline without crashing."""

    @override_settings(COSAT_MONGO_URL='mongodb://localhost:27099/nonexistent')
    def test_is_available_returns_false_when_offline(self):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        result = conn.is_available()
        self.assertFalse(result)

    @override_settings(COSAT_MONGO_URL='mongodb://localhost:27099/nonexistent')
    def test_iter_tournaments_yields_nothing_when_offline(self):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        items = list(conn.iter_tournaments())
        self.assertEqual(items, [])

    @override_settings(COSAT_MONGO_URL='mongodb://localhost:27099/nonexistent')
    def test_iter_players_yields_nothing_when_offline(self):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        items = list(conn.iter_players())
        self.assertEqual(items, [])

    @override_settings(COSAT_MONGO_URL='mongodb://localhost:27099/nonexistent')
    def test_iter_rankings_yields_nothing_when_offline(self):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        items = list(conn.iter_rankings())
        self.assertEqual(items, [])

    @override_settings(COSAT_MONGO_URL='')
    def test_no_url_configured_returns_false(self):
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        result = conn.is_available()
        self.assertFalse(result)


class SyncCosatCommandDryRunTestCase(TestCase):
    """sync_cosat_from_mongo --dry-run makes no DB writes."""

    SAMPLE_TOURNAMENT = {
        'external_id': 'cosat:test001',
        'canonical_name': 'COSAT Test Open 2025',
        'canonical_slug': 'cosat-test001-cosat-test-open-2025',
        'circuit': 'COSAT',
        'modality': 'tennis',
        'season_year': 2025,
        'title': 'COSAT Test Open 2025',
        'start_date': '2025-11-10',
        'end_date': '2025-11-15',
        'entry_open_at': None,
        'entry_close_at': None,
        'status': 'unknown',
        'surface': 'unknown',
        'venue': {'name': 'COSAT', 'city': 'Buenos Aires', 'state': 'AR', 'address': ''},
        'base_price_brl': None,
        'official_source_url': 'https://cosat.tournamentsoftware.com/test',
        'categories': [{'source_text': 'U14 Boys', 'price_brl': None, 'notes': ''}],
        'links': [],
        '_raw': {'cosatId': 'test001', 'organization': 'COSAT', 'source': 'cosat_mongo',
                 'location': 'Buenos Aires, AR', 'country': 'AR',
                 'categoriesCount': 1, 'entriesCount': 10, 'lastUpdated': ''},
    }

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_dry_run_does_not_create_editions(self):
        from django.core.management import call_command
        from apps.tournaments.models import TournamentEdition

        before = TournamentEdition.objects.count()

        with patch(
            'apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
            return_value=True,
        ), patch(
            'apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_tournaments',
            return_value=iter([self.SAMPLE_TOURNAMENT]),
        ):
            call_command('sync_cosat_from_mongo', '--dry-run', verbosity=0)

        after = TournamentEdition.objects.count()
        self.assertEqual(before, after)

    @override_settings(COSAT_MONGO_ENABLED=False)
    def test_disabled_flag_exits_without_connecting(self):
        """COSAT_MONGO_ENABLED=False should exit before any MongoDB call."""
        from django.core.management import call_command

        with patch(
            'apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available'
        ) as mock_avail:
            call_command('sync_cosat_from_mongo', verbosity=0)
            mock_avail.assert_not_called()

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_mongo_unavailable_exits_without_db_writes(self):
        from django.core.management import call_command
        from apps.tournaments.models import TournamentEdition

        before = TournamentEdition.objects.count()

        with patch(
            'apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
            return_value=False,
        ):
            call_command('sync_cosat_from_mongo', '--no-dry-run', verbosity=0)

        self.assertEqual(TournamentEdition.objects.count(), before)
