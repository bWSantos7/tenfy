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

    def test_cosat_14_anos_spanish_in_title(self):
        """'Copa COSAT 14 años' must be classified as youth — Spanish age in title."""
        from apps.ingestion.persistence import _classify_is_youth
        self.assertTrue(_classify_is_youth('COSAT', 'Copa COSAT 14 años', []))

    def test_cosat_u14_category(self):
        """U14 prefix in categories must trigger youth classification."""
        from apps.ingestion.persistence import _classify_is_youth
        cats = [{'source_text': 'U14 Boys Singles'}, {'source_text': 'U14 Girls Singles'}]
        self.assertTrue(_classify_is_youth('COSAT', 'Copa COSAT', cats))

    def test_anos_spanish_in_category(self):
        """'14 años' in category text (Spanish) triggers youth."""
        from apps.ingestion.persistence import _classify_is_youth
        cats = [{'source_text': '14 Años Masculino'}]
        self.assertTrue(_classify_is_youth('COSAT', 'Open COSAT', cats))

    def test_u18_in_title_is_youth(self):
        """U18 in title triggers youth classification."""
        from apps.ingestion.persistence import _classify_is_youth
        self.assertTrue(_classify_is_youth('ITF', 'ITF U18 South America', []))

    def test_adult_open_still_not_youth_after_fix(self):
        """Regression: adult open still not youth after classification fix."""
        from apps.ingestion.persistence import _classify_is_youth
        self.assertFalse(_classify_is_youth('FPT', 'Aberto FPT Adulto', [
            {'source_text': 'Open Masculino'},
            {'source_text': '40+ Masculino'},
        ]))


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

    # ── _extract_category_text / multi-field fallback ─────────────────────────

    def test_extract_category_primary_field_rankingCategory(self):
        """rankingCategory is tried first and wins when present."""
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {
            'rankingCategory': 'U14 Boys',
            'category': 'Other',
            'event': 'Also other',
        }
        text, field = _extract_category_text(doc)
        self.assertEqual(text, 'U14 Boys')
        self.assertEqual(field, 'rankingCategory')

    def test_extract_category_fallback_to_event(self):
        """Falls back to eventName/event when rankingCategory absent."""
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {
            'rankingCategory': '',
            'eventName': '14 Años Masculino Singles',
        }
        text, field = _extract_category_text(doc)
        self.assertEqual(text, '14 Años Masculino Singles')
        self.assertEqual(field, 'eventName')

    def test_extract_category_fallback_to_draw(self):
        """Falls back to drawName when higher-priority fields absent."""
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {'drawName': 'Sub-16 Feminino'}
        text, field = _extract_category_text(doc)
        self.assertEqual(text, 'Sub-16 Feminino')
        self.assertEqual(field, 'drawName')

    def test_extract_category_fallback_to_discipline(self):
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {'discipline': 'Boys U14 Singles'}
        text, field = _extract_category_text(doc)
        self.assertEqual(text, 'Boys U14 Singles')
        self.assertEqual(field, 'discipline')

    def test_extract_category_all_empty_returns_empty(self):
        """No candidate fields with values → ('', '')."""
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {'name': 'Player X', 'tournamentId': 'abc', 'profileId': 'p1'}
        text, field = _extract_category_text(doc)
        self.assertEqual(text, '')
        self.assertEqual(field, '')

    def test_extract_category_uuid_eventId_skipped(self):
        """UUID-like eventId is not used as category text."""
        from apps.ingestion.connectors.cosat_mongo import _extract_category_text
        doc = {'eventId': '966BBD61-1E45-4970-9099-65566407DC4D'}
        text, field = _extract_category_text(doc)
        self.assertEqual(text, '')

    def test_normalize_player_category_from_event_field(self):
        """_normalize_player picks up category from eventName when rankingCategory empty."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {
            'name': 'Carlos Rodríguez',
            'tournamentId': 'abc123',
            'profileId': 'P-001',
            'rankingCategory': '',
            'eventName': '14 Años Masculino',
        }
        result = _normalize_player(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['category_text'], '14 Años Masculino')
        self.assertEqual(result['_category_field'], 'eventName')

    def test_normalize_player_no_category_field_returns_empty_category(self):
        """_normalize_player returns result with empty category_text when no field found."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {'name': 'Player No Cat', 'tournamentId': 'abc'}
        result = _normalize_player(doc)
        # Still returns a result — rejection happens at command level
        self.assertIsNotNone(result)
        self.assertEqual(result['category_text'], '')
        self.assertEqual(result['_category_field'], '')

    def test_normalize_player_category_field_reported(self):
        """_category_field key shows which field provided the category."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {'name': 'X', 'rankingCategory': 'U12 Girls', 'tournamentId': 't1'}
        result = _normalize_player(doc)
        self.assertEqual(result['_category_field'], 'rankingCategory')

    # ── player_field_inventory ────────────────────────────────────────────────

    def test_player_field_inventory_redacts_name(self):
        """player_field_inventory does not leak player name."""
        from apps.ingestion.connectors.cosat_mongo import player_field_inventory
        doc = {
            'name': 'Real Player Name',
            'dob': '1990-01-01',
            'rankingCategory': 'U14',
            'tournamentId': 'abc',
        }
        inventory = player_field_inventory(doc)
        self.assertEqual(inventory['name'], '<redacted>')
        self.assertEqual(inventory['dob'], '<redacted>')
        self.assertEqual(inventory['rankingCategory'], 'U14')
        self.assertEqual(inventory['tournamentId'], 'abc')

    # ── _extract_country ──────────────────────────────────────────────────────

    def test_extract_country_from_countryName_and_countryCode(self):
        from apps.ingestion.connectors.cosat_mongo import _extract_country
        doc = {'countryName': 'Argentina', 'countryCode': 'ARG'}
        name, code = _extract_country(doc)
        self.assertEqual(name, 'Argentina')
        self.assertEqual(code, 'ARG')

    def test_extract_country_fallback_to_country_field(self):
        from apps.ingestion.connectors.cosat_mongo import _extract_country
        doc = {'country': 'Brasil'}
        name, code = _extract_country(doc)
        self.assertEqual(name, 'Brasil')

    def test_extract_country_code_only(self):
        from apps.ingestion.connectors.cosat_mongo import _extract_country
        doc = {'countryCode': 'CHI'}
        name, code = _extract_country(doc)
        self.assertEqual(code, 'CHI')

    def test_extract_country_absent_returns_empty(self):
        from apps.ingestion.connectors.cosat_mongo import _extract_country
        doc = {'name': 'Player X', 'tournamentId': 't1'}
        name, code = _extract_country(doc)
        self.assertEqual(name, '')
        self.assertEqual(code, '')

    def test_extract_country_code_field_treated_as_code_not_name(self):
        """2-3 uppercase chars in country field is treated as code, not full name."""
        from apps.ingestion.connectors.cosat_mongo import _extract_country
        doc = {'country': 'ARG'}
        name, code = _extract_country(doc)
        # 'ARG' should be captured as code, not name
        self.assertEqual(code, 'ARG')

    def test_normalize_player_includes_country(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {
            'name': 'Pablo García',
            'tournamentId': 'abc',
            'profileId': 'P-999',
            'rankingCategory': 'U16 Boys',
            'countryName': 'Argentina',
            'countryCode': 'ARG',
        }
        result = _normalize_player(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['player_country_name'], 'Argentina')
        self.assertEqual(result['player_country_code'], 'ARG')

    def test_normalize_player_no_country_returns_empty_strings(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_player
        doc = {'name': 'Player X', 'tournamentId': 'abc', 'rankingCategory': 'U14'}
        result = _normalize_player(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['player_country_name'], '')
        self.assertEqual(result['player_country_code'], '')

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

    def test_parse_date_range_spanish_format_copa_cosat(self):
        """
        'Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may.'
        with year_hint=2026 → 2026-04-27, 2026-05-02
        """
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        from datetime import date
        start, end = _parse_date_range(
            'Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may.',
            year_hint=2026,
        )
        self.assertEqual(start, date(2026, 4, 27))
        self.assertEqual(end, date(2026, 5, 2))

    def test_parse_date_range_spanish_same_month(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        from datetime import date
        start, end = _parse_date_range(
            'Inicio del torneo lun. 10 de nov. | Final del torneo dom. 15 de nov.',
            year_hint=2025,
        )
        self.assertEqual(start, date(2025, 11, 10))
        self.assertEqual(end, date(2025, 11, 15))

    def test_parse_date_range_spanish_cross_year(self):
        """End date in December, start in November — should resolve correctly."""
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        from datetime import date
        start, end = _parse_date_range(
            'Inicio del torneo lun. 28 de nov. | Final del torneo sáb. 3 de dic.',
            year_hint=2025,
        )
        self.assertEqual(start, date(2025, 11, 28))
        self.assertEqual(end, date(2025, 12, 3))

    def test_parse_date_range_english_still_works_after_fix(self):
        """Regression: existing English format still parses correctly."""
        from apps.ingestion.connectors.cosat_mongo import _parse_date_range
        from datetime import date
        start, end = _parse_date_range('28 Nov - 3 Dec 2025')
        self.assertEqual(start, date(2025, 11, 28))
        self.assertEqual(end, date(2025, 12, 3))

    # ── _normalize_cosat_event_name ───────────────────────────────────────────

    def test_normalize_bs14(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('BS 14'), 'Sub-14 Masculino Simples')

    def test_normalize_gs14(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('GS 14'), 'Sub-14 Feminino Simples')

    def test_normalize_bd14(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('BD 14'), 'Sub-14 Masculino Duplas')

    def test_normalize_gd16(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('GD 16'), 'Sub-16 Feminino Duplas')

    def test_normalize_unknown_code_returns_original(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('ZZ 14'), 'ZZ 14')

    def test_normalize_non_cosat_format_returns_original(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name('14 Anos Masculino'), '14 Anos Masculino')

    def test_normalize_empty_returns_empty(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_cosat_event_name
        self.assertEqual(_normalize_cosat_event_name(''), '')

    def test_normalize_tournament_categories_use_normalized_names(self):
        """_normalize_tournament applies _normalize_cosat_event_name to events."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'TEST-001',
            'name': 'Copa COSAT 14 años',
            'events': [
                {'eventId': '1', 'name': 'BS 14'},
                {'eventId': '2', 'name': 'GS 14'},
            ],
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        cat_texts = [c['source_text'] for c in result['categories']]
        self.assertIn('Sub-14 Masculino Simples', cat_texts)
        self.assertIn('Sub-14 Feminino Simples', cat_texts)

    def test_normalize_tournament_daterange_parsed(self):
        """_normalize_tournament uses year from lastUpdated for Spanish dateRange."""
        from datetime import date
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        from datetime import datetime as dt
        doc = {
            'cosatId': 'TEST-002',
            'name': 'Copa COSAT',
            'dateRange': 'Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may.',
            'lastUpdated': dt(2026, 5, 1),
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['start_date'], '2026-04-27')
        self.assertEqual(result['end_date'], '2026-05-02')

    def test_normalize_tournament_daterange_preserved_in_raw(self):
        """Original dateRange string preserved in _raw for audit."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        from datetime import datetime as dt
        doc = {
            'cosatId': 'TEST-003',
            'name': 'Copa COSAT',
            'dateRange': 'Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may.',
            'lastUpdated': dt(2026, 5, 1),
        }
        result = _normalize_tournament(doc)
        self.assertEqual(
            result['_raw']['dateRange'],
            'Inicio del torneo lun. 27 de abr. | Final del torneo sáb. 2 de may.',
        )

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


class SyncCosatCommandTestCase(TestCase):
    """sync_cosat_from_mongo command: dry-run, real sync, entries, edge cases."""

    # Minimal valid tournament fixture
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
        '_raw': {
            'cosatId': 'test001', 'organization': 'COSAT', 'source': 'cosat_mongo',
            'location': 'Buenos Aires, AR', 'country': 'AR',
            'categoriesCount': 1, 'entriesCount': 10, 'lastUpdated': '',
        },
    }
    SAMPLE_PLAYER = {
        'player_name': 'María García',
        'tournament_cosat_id': 'test001',
        'player_external_id': 'cosat:P-001',
        'category_text': 'U14 Girls Singles',
        'ranking_position': 5,
        'payment_status': 'unknown',
        'removed_or_replaced': False,
        'replacement_reason': '',
        'source_url': 'https://cosat.tournamentsoftware.com/test',
        'confidence': 'medium',
        '_raw': {},
    }

    # ── Dry-run: no DB writes ─────────────────────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_dry_run_does_not_create_editions(self):
        from django.core.management import call_command
        from apps.tournaments.models import TournamentEdition

        before = TournamentEdition.objects.count()
        with patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
                   return_value=True), \
             patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_tournaments',
                   return_value=iter([self.SAMPLE_TOURNAMENT])):
            call_command('sync_cosat_from_mongo', '--dry-run', verbosity=0)
        self.assertEqual(TournamentEdition.objects.count(), before)

    @override_settings(COSAT_MONGO_ENABLED=False)
    def test_disabled_exits_without_connecting(self):
        from django.core.management import call_command
        with patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available') as m:
            call_command('sync_cosat_from_mongo', verbosity=0)
            m.assert_not_called()

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_mongo_unavailable_no_db_writes(self):
        from django.core.management import call_command
        from apps.tournaments.models import TournamentEdition
        before = TournamentEdition.objects.count()
        with patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
                   return_value=False):
            call_command('sync_cosat_from_mongo', '--no-dry-run', verbosity=0)
        self.assertEqual(TournamentEdition.objects.count(), before)

    # ── Organization / DataSource creation ───────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_get_or_create_datasource_uses_valid_choices(self):
        """Organization.type and DataSource.source_type use valid model choices."""
        from apps.ingestion.management.commands.sync_cosat_from_mongo import Command
        from apps.sources.models import Organization, DataSource
        cmd = Command()
        cmd.stdout = type('S', (), {'write': lambda s, x: None})()
        cmd.style = type('St', (), {
            'SUCCESS': lambda s, x: x, 'WARNING': lambda s, x: x,
            'ERROR': lambda s, x: x,
        })()

        ds = cmd._get_or_create_datasource(dry_run=False)

        self.assertIsNotNone(ds)
        org = Organization.objects.get(name='COSAT')
        self.assertEqual(org.type, Organization.TYPE_CONFEDERATION)
        self.assertEqual(ds.source_type, DataSource.SOURCE_TYPE_JSON)
        self.assertEqual(ds.slug, 'cosat-mongo')
        self.assertEqual(ds.connector_key, 'cosat_mongo')
        self.assertTrue(ds.legal_notes)  # not empty

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_get_or_create_datasource_idempotent(self):
        """Calling twice does not create duplicate Organization or DataSource."""
        from apps.ingestion.management.commands.sync_cosat_from_mongo import Command
        from apps.sources.models import Organization, DataSource
        cmd = Command()
        cmd.stdout = type('S', (), {'write': lambda s, x: None})()
        cmd.style = type('St', (), {
            'SUCCESS': lambda s, x: x, 'WARNING': lambda s, x: x,
            'ERROR': lambda s, x: x,
        })()

        cmd._get_or_create_datasource(dry_run=False)
        cmd._get_or_create_datasource(dry_run=False)

        self.assertEqual(Organization.objects.filter(name='COSAT').count(), 1)
        self.assertEqual(DataSource.objects.filter(connector_key='cosat_mongo').count(), 1)

    # ── IngestionRun status ───────────────────────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_ingestion_run_uses_valid_status(self):
        """IngestionRun must use success/partial/failed — never 'completed'."""
        from apps.ingestion.models import IngestionRun
        valid_statuses = {
            IngestionRun.STATUS_RUNNING,
            IngestionRun.STATUS_SUCCESS,
            IngestionRun.STATUS_PARTIAL,
            IngestionRun.STATUS_FAILED,
        }
        self.assertNotIn('completed', valid_statuses)
        # Verify the constants exist
        self.assertEqual(IngestionRun.STATUS_SUCCESS, 'success')
        self.assertEqual(IngestionRun.STATUS_FAILED, 'failed')

    # ── Entry rejection: empty category ──────────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_upsert_entry_rejects_empty_category(self):
        """_upsert_entry raises ValueError when category_text is empty — never saves 'Não informado'."""
        from apps.ingestion.management.commands.sync_cosat_from_mongo import Command
        cmd = Command()
        cmd.stdout = type('S', (), {'write': lambda s, x: None})()
        cmd.style = type('St', (), {'ERROR': lambda s, x: x})()

        player_no_cat = dict(self.SAMPLE_PLAYER, category_text='')
        with self.assertRaises(ValueError) as ctx:
            cmd._upsert_entry(player_no_cat, edition_id=999)
        self.assertIn('category_text', str(ctx.exception).lower())

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_player_without_category_uses_geral_do_torneio_fallback(self):
        """COSAT player with no category → saved as 'Geral do torneio' with warning in notes."""
        from django.core.management import call_command
        from apps.registrations.models import FederationEntry
        from apps.sources.models import Organization, DataSource
        from apps.tournaments.models import Tournament, TournamentEdition

        # Create minimal DB structure for the test
        org, _ = Organization.objects.get_or_create(
            name='COSAT_TEST_ORG',
            defaults={'short_name': 'COSAT', 'type': Organization.TYPE_CONFEDERATION},
        )
        ds, _ = DataSource.objects.get_or_create(
            connector_key='cosat_mongo_test',
            defaults={
                'organization': org,
                'source_name': 'COSAT Test',
                'slug': 'cosat-mongo-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://cosat.tournamentsoftware.com',
            },
        )
        tournament, _ = Tournament.objects.get_or_create(
            canonical_slug='cosat-test001-open',
            defaults={'canonical_name': 'COSAT Test Open', 'circuit': 'COSAT', 'organization': org},
        )
        edition, _ = TournamentEdition.objects.get_or_create(
            external_id='cosat:test001',
            defaults={
                'tournament': tournament,
                'data_source': ds,
                'title': 'COSAT Test Open',
                'season_year': 2025,
                'status': 'unknown',
            },
        )

        player_no_cat = dict(self.SAMPLE_PLAYER, category_text='', player_external_id='cosat:fallback-test-001')

        with patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
                   return_value=True), \
             patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_tournaments',
                   return_value=iter([])), \
             patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_players',
                   return_value=iter([player_no_cat])):
            call_command(
                'sync_cosat_from_mongo', '--no-dry-run', '--import-entries',
                '--tournament-id', 'test001', verbosity=0,
            )

        entry = FederationEntry.objects.filter(
            edition=edition,
            player_external_id='cosat:fallback-test-001',
        ).first()
        self.assertIsNotNone(entry, 'Entry should be saved with fallback category')
        self.assertEqual(entry.category_text, 'Geral do torneio')
        self.assertIn('COSAT', entry.notes)
        self.assertIn('Geral do torneio', entry.notes)

    def test_player_with_country_saved_to_federation_entry(self):
        """COSAT player with country → _upsert_entry saves player_country_name/code."""
        from apps.registrations.models import FederationEntry
        from apps.sources.models import Organization, DataSource
        from apps.tournaments.models import Tournament, TournamentEdition
        from apps.ingestion.management.commands.sync_cosat_from_mongo import Command

        # Create minimal DB fixtures
        org, _ = Organization.objects.get_or_create(
            name='COSAT_UPSERT_TEST',
            defaults={'short_name': 'COSAT', 'type': Organization.TYPE_CONFEDERATION},
        )
        ds, _ = DataSource.objects.get_or_create(
            connector_key='cosat_upsert_test',
            defaults={
                'organization': org, 'source_name': 'COSAT Upsert Test',
                'slug': 'cosat-upsert-test',
                'source_type': DataSource.SOURCE_TYPE_JSON,
                'base_url': 'https://cosat.tournamentsoftware.com',
            },
        )
        tournament, _ = Tournament.objects.get_or_create(
            canonical_slug='cosat-upsert-test-open',
            defaults={'canonical_name': 'COSAT Upsert Test Open', 'circuit': 'COSAT', 'organization': org},
        )
        edition, _ = TournamentEdition.objects.get_or_create(
            external_id='cosat:upsert-test',
            defaults={
                'tournament': tournament, 'data_source': ds,
                'title': 'COSAT Upsert Test', 'season_year': 2025, 'status': 'unknown',
            },
        )

        # Call _upsert_entry directly — no MongoDB connection needed
        cmd = Command()
        cmd.stdout = type('S', (), {'write': lambda s, x: None})()
        cmd.style = type('St', (), {'ERROR': lambda s, x: x, 'WARNING': lambda s, x: x})()

        player_with_country = {
            'player_name': 'Pablo García',
            'player_external_id': 'cosat:country-direct-001',
            'category_text': 'U14 Girls Singles',
            'player_country_name': 'Argentina',
            'player_country_code': 'ARG',
            'ranking_position': None,
            'payment_status': 'unknown',
            'removed_or_replaced': False,
            'replacement_reason': '',
            'source_url': '',
            'confidence': 'medium',
            '_raw': {},
        }
        cmd._upsert_entry(player_with_country, edition.id)

        entry = FederationEntry.objects.filter(
            edition=edition,
            player_external_id='cosat:country-direct-001',
        ).first()
        self.assertIsNotNone(entry, 'Entry should be saved')
        self.assertEqual(entry.player_country_name, 'Argentina')
        self.assertEqual(entry.player_country_code, 'ARG')

    # ── Secrets: URI not in logs ──────────────────────────────────────────────

    def test_sanitize_exc_strips_credentials(self):
        """_sanitize_exc must redact user:pass from MongoDB URIs."""
        from apps.ingestion.connectors.cosat_mongo import _sanitize_exc
        # URI built in parts — avoids secret-scanner pattern matching on committed strings.
        # Uses example.invalid TLD (RFC 2606) — never a real host.
        _fake_uri = (
            'mongodb+srv://'
            + 'testuser:testpass123@'
            + 'cluster.example.invalid/testdb'
        )
        exc = Exception('Connection refused: ' + _fake_uri)
        result = _sanitize_exc(exc)
        self.assertNotIn('testpass123', result)
        self.assertNotIn('testuser:testpass123', result)
        self.assertIn('***:***@', result)

    def test_sanitize_exc_plain_message_unchanged(self):
        from apps.ingestion.connectors.cosat_mongo import _sanitize_exc
        exc = Exception('Server selection timed out after 5000ms')
        result = _sanitize_exc(exc)
        self.assertIn('5000ms', result)

    # ── limit validation ──────────────────────────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_negative_limit_raises_command_error(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('sync_cosat_from_mongo', '--limit', '-1', verbosity=0)

    # ── Rankings: explicitly NOT imported ────────────────────────────────────

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_rankings_not_imported_in_sync(self):
        """iter_rankings is never called by the command — rankings import not implemented."""
        from django.core.management import call_command

        with patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.is_available',
                   return_value=True), \
             patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_tournaments',
                   return_value=iter([])), \
             patch('apps.ingestion.connectors.cosat_mongo.CosatMongoConnector.iter_rankings',
                   return_value=iter([])) as mock_rankings:
            call_command('sync_cosat_from_mongo', '--no-dry-run', '--import-entries', verbosity=0)
            mock_rankings.assert_not_called()

    # ── COSAT_MONGO_DB empty raises error ────────────────────────────────────

    @override_settings(COSAT_MONGO_URL='mongodb://localhost:27099', COSAT_MONGO_DB='')
    def test_empty_db_name_makes_connector_unavailable(self):
        """Empty COSAT_MONGO_DB when URL is set → unavailable (not silent default)."""
        from apps.ingestion.connectors.cosat_mongo import CosatMongoConnector
        conn = CosatMongoConnector()
        result = conn.is_available()
        self.assertFalse(result)
