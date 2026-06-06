"""Tests for ingestion: dedup fingerprint, youth classifier, persistence logic, COSAT Mongo connector."""
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase, override_settings


class MaterialFieldsTestCase(TestCase):
    def test_withdrawal_deadline_at_is_material(self):
        """withdrawal_deadline_at must trigger TournamentChangeEvent on change."""
        from apps.ingestion.persistence import MATERIAL_FIELDS
        self.assertIn('withdrawal_deadline_at', MATERIAL_FIELDS)

    def test_core_dates_are_material(self):
        from apps.ingestion.persistence import MATERIAL_FIELDS
        for field in ('start_date', 'end_date', 'entry_open_at', 'entry_close_at'):
            self.assertIn(field, MATERIAL_FIELDS)


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


class CategoryCodeInferenceTestCase(TestCase):
    def test_embedded_age_gender_code_is_inferred(self):
        from apps.ingestion.persistence import TournamentPersister

        self.assertEqual(
            TournamentPersister._infer_category_code('Ranking Infantojuvenil 2026 - 14M'),
            '14M',
        )


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
        # COSAT is international → venue carries country/country_code (Task 6).
        self.assertEqual(result['venue']['country'], 'Argentina')
        self.assertEqual(result['venue']['country_code'], 'ARG')

    def test_normalize_tournament_country_mapping(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        # COSAT uses some NON-standard 2-letter codes (PA=Paraguai, CH=Chile, UR=Uruguai).
        cases = [
            ('Lambaré, PA', 'Paraguai', 'PRY'),
            ('Santiago, CH', 'Chile', 'CHL'),
            ('Montevideo, UR', 'Uruguai', 'URY'),
            ('Cali, CO', 'Colômbia', 'COL'),
            ('Porto Alegre, BR', 'Brasil', 'BRA'),
        ]
        for loc, name, code in cases:
            doc = {
                'cosatId': 'x', 'name': 'T', 'location': loc,
                'dateRange': '10 - 15 Nov 2025', 'lastUpdated': datetime(2025, 11, 15),
            }
            r = _normalize_tournament(doc)
            self.assertEqual(r['venue']['country'], name, loc)
            self.assertEqual(r['venue']['country_code'], code, loc)

    def test_normalize_tournament_with_new_fields(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'abc123',
            'name': 'COSAT Junior Open 2026',
            'url': 'https://cosat.tournamentsoftware.com/sport/tournament?id=abc123',
            'tournament_start_at': '2026-05-16T00:00:00-05:00',
            'tournament_end_at': '2026-05-23T00:00:00-05:00',
            'registration_open_at': '2026-02-18T00:00:00-05:00',
            'registration_close_at': '2026-04-27T23:59:00-05:00',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['start_date'], '2026-05-16')
        self.assertEqual(result['end_date'], '2026-05-23')
        self.assertEqual(result['entry_open_at'], '2026-02-18T00:00:00-05:00')
        self.assertEqual(result['entry_close_at'], '2026-04-27T23:59:00-05:00')

    def test_normalize_tournament_withdrawal_deadline_and_online_entry(self):
        """withdrawal_deadline_at and has_online_entry extracted from new crawler schema."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'wd01',
            'name': 'COSAT Open 2026',
            'registration_open_at': '2026-02-04T00:00:00-03:00',
            'registration_close_at': '2026-04-13T23:59:00-04:00',
            'withdrawal_deadline_at': '2026-04-21T00:59:00-04:00',
            'tournament_start_at': '2026-05-02T00:00:00-04:00',
            'tournament_end_at': '2026-05-09T00:00:00-04:00',
            'hasOnlineEntry': True,
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['withdrawal_deadline_at'], '2026-04-21T00:59:00-04:00')
        self.assertTrue(result['has_online_entry'])

    def test_normalize_tournament_withdrawal_absent_is_none(self):
        """withdrawal_deadline_at is None when not present in doc."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {'cosatId': 'wd02', 'name': 'Open 2026'}
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertIsNone(result['withdrawal_deadline_at'])
        self.assertFalse(result['has_online_entry'])

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

    def test_trunc_short_value_unchanged(self):
        from apps.ingestion.connectors.cosat_mongo import _trunc
        self.assertEqual(_trunc('Buenos Aires', 120, 'city'), 'Buenos Aires')

    def test_trunc_long_value_cut_to_max(self):
        from apps.ingestion.connectors.cosat_mongo import _trunc
        long_city = 'A' * 150
        result = _trunc(long_city, 120, 'venue.city')
        self.assertEqual(len(result), 120)

    def test_trunc_normalizes_whitespace(self):
        from apps.ingestion.connectors.cosat_mongo import _trunc
        result = _trunc('City   Name   Extra', 120, 'city')
        self.assertEqual(result, 'City Name Extra')

    def test_normalize_tournament_long_city_truncated(self):
        """Tournament with location >120 chars must not raise — city truncated."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        long_location = 'X' * 130  # no comma → whole string becomes city
        doc = {
            'cosatId': 'test-long-city',
            'name': 'Long City Test',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-long-city',
            'location': long_location,
            'country': 'BR',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        city = (result.get('venue') or {}).get('city', '')
        self.assertLessEqual(len(city), 120, 'city must be ≤120 chars')

    def test_normalize_tournament_long_organization_truncated(self):
        """Tournament with organization name >200 chars must not raise — truncated."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        long_org = 'O' * 250
        doc = {
            'cosatId': 'test-long-org',
            'name': 'Long Org Test',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-long-org',
            'organization': long_org,
            'location': 'Bogotá, CO',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        venue_name = (result.get('venue') or {}).get('name', '')
        self.assertLessEqual(len(venue_name), 200, 'venue.name must be ≤200 chars')

    def test_normalize_tournament_long_location_preserved_in_raw(self):
        """Original location (>120 chars) must be preserved in _raw even when truncated."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        long_location = 'L' * 130
        doc = {
            'cosatId': 'test-raw-location',
            'name': 'Raw Location Test',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-raw-location',
            'location': long_location,
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['_raw']['location'], long_location,
                         'Original full location must be in _raw')


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


# ── Inscription date parsing ──────────────────────────────────────────────────

class ParseInscriptionDateTestCase(TestCase):
    """Tests for _parse_inscription_date and _parse_inscription_dates helpers (TAREFA 1)."""

    def test_iso_date(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        self.assertEqual(_parse_inscription_date('2026-04-27'), date(2026, 4, 27))

    def test_iso_datetime_string(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import datetime, timezone
        self.assertEqual(_parse_inscription_date('2026-05-02T00:00:00Z'), datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc))

    def test_br_format(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        self.assertEqual(_parse_inscription_date('27/04/2026'), date(2026, 4, 27))

    def test_spanish_textual_with_year_hint(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        self.assertEqual(_parse_inscription_date('sáb. 2 de may.', year_hint=2026), date(2026, 5, 2))

    def test_spanish_textual_explicit_year(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        self.assertEqual(_parse_inscription_date('27 de abr. 2026'), date(2026, 4, 27))

    def test_prefixed_text_stripped(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        result = _parse_inscription_date('Entries close: sáb. 2 de may.', year_hint=2026)
        self.assertEqual(result, date(2026, 5, 2))

    def test_withdrawal_deadline_prefix_stripped(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        from datetime import date
        result = _parse_inscription_date('Withdrawal deadline: 2026-04-20', year_hint=2026)
        self.assertEqual(result, date(2026, 4, 20))

    def test_null_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        self.assertIsNone(_parse_inscription_date(None))

    def test_empty_string_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        self.assertIsNone(_parse_inscription_date(''))

    def test_not_informed_text_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_date
        self.assertIsNone(_parse_inscription_date('Inscrição não informada'))

    def test_parse_inscription_dates_both_from_pt_fields(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_dates
        from datetime import date
        doc = {'Inscrição_Inicio': '2026-04-01', 'Inscrição_Fim': '2026-04-25'}
        open_d, close_d = _parse_inscription_dates(doc)
        self.assertEqual(open_d, date(2026, 4, 1))
        self.assertEqual(close_d, date(2026, 4, 25))

    def test_parse_inscription_dates_close_only(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_dates
        from datetime import date
        doc = {'Entries close': '2026-04-25'}
        open_d, close_d = _parse_inscription_dates(doc)
        self.assertIsNone(open_d)
        self.assertEqual(close_d, date(2026, 4, 25))

    def test_parse_inscription_dates_entry_close_at_field(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_dates
        from datetime import date
        doc = {'entry_close_at': '2026-05-10', 'entry_open_at': '2026-04-10'}
        open_d, close_d = _parse_inscription_dates(doc)
        self.assertEqual(open_d, date(2026, 4, 10))
        self.assertEqual(close_d, date(2026, 5, 10))

    def test_parse_inscription_dates_empty_doc_returns_none(self):
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_dates
        open_d, close_d = _parse_inscription_dates({})
        self.assertIsNone(open_d)
        self.assertIsNone(close_d)

    def test_normalize_tournament_includes_entry_dates_from_inscription_fields(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'test-insc-001',
            'name': 'Test Inscription Tournament',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-insc-001',
            'dateRange': '10 - 15 Nov 2026',
            'Inscrição_Inicio': '2026-10-01',
            'Inscrição_Fim': '2026-10-31',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertEqual(result['entry_open_at'], '2026-10-01')
        self.assertEqual(result['entry_close_at'], '2026-10-31')

    def test_normalize_tournament_no_inscription_fields_yields_none(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'test-noinsc-001',
            'name': 'Test No Inscription',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-noinsc-001',
            'dateRange': '10 - 15 Nov 2026',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertIsNone(result['entry_open_at'])
        self.assertIsNone(result['entry_close_at'])

    def test_inscription_fields_preserved_in_raw(self):
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'test-raw-001',
            'name': 'Test Raw Preserve',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-raw-001',
            'Inscrição_Fim': '2026-10-31',
        }
        result = _normalize_tournament(doc)
        self.assertIn('inscriptionFields', result['_raw'])
        self.assertIn('Inscrição_Fim', result['_raw']['inscriptionFields'])


# ── Celery task: sync_cosat_from_mongo_task ───────────────────────────────────

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'sync-cosat-task-tests',
    },
})
class SyncCosatTaskTestCase(TestCase):
    """Tests for the periodic sync_cosat_from_mongo_task Celery task (TAREFA 8)."""

    def setUp(self):
        from django.core.cache import cache
        cache.delete('sync_cosat:lock')

    def tearDown(self):
        from django.core.cache import cache
        cache.delete('sync_cosat:lock')

    @override_settings(COSAT_MONGO_ENABLED=False)
    def test_task_skipped_when_disabled(self):
        """Task returns skipped:disabled when COSAT_MONGO_ENABLED=False."""
        from apps.ingestion.tasks import sync_cosat_from_mongo_task
        result = sync_cosat_from_mongo_task()
        self.assertEqual(result.get('skipped'), True)
        self.assertEqual(result.get('reason'), 'disabled')

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_task_skipped_when_lock_held(self):
        """Task skips gracefully if cache lock indicates another instance is running."""
        from django.core.cache import cache
        from apps.ingestion.tasks import sync_cosat_from_mongo_task
        cache.set('sync_cosat:lock', True, 60)
        try:
            result = sync_cosat_from_mongo_task()
            self.assertEqual(result.get('skipped'), True)
            self.assertEqual(result.get('reason'), 'already_running')
        finally:
            cache.delete('sync_cosat:lock')

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_task_result_has_no_mongo_uri(self):
        """Task result dict must never contain a MongoDB connection string."""
        from apps.ingestion.tasks import sync_cosat_from_mongo_task
        with patch('django.core.management.call_command') as mock_cmd:
            mock_cmd.return_value = None
            result = sync_cosat_from_mongo_task()
        result_str = str(result)
        self.assertNotIn('mongodb://', result_str)
        self.assertNotIn('mongodb+srv://', result_str)

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_task_lock_released_after_success(self):
        """Cache lock is deleted after successful run."""
        from django.core.cache import cache
        from apps.ingestion.tasks import sync_cosat_from_mongo_task
        with patch('django.core.management.call_command') as mock_cmd:
            mock_cmd.return_value = None
            sync_cosat_from_mongo_task()
        self.assertIsNone(cache.get('sync_cosat:lock'))

    @override_settings(COSAT_MONGO_ENABLED=True)
    def test_task_calls_import_entries_true(self):
        """Task must pass import_entries=True so players are synced automatically."""
        from apps.ingestion.tasks import sync_cosat_from_mongo_task
        with patch('django.core.management.call_command') as mock_cmd:
            mock_cmd.return_value = None
            sync_cosat_from_mongo_task()
        # Find the sync_cosat_from_mongo call among all call_command invocations
        cosat_calls = [c for c in mock_cmd.call_args_list
                       if c.args and c.args[0] == 'sync_cosat_from_mongo']
        self.assertEqual(len(cosat_calls), 1, 'sync_cosat_from_mongo must be called once')
        kwargs = cosat_calls[0].kwargs
        self.assertTrue(kwargs.get('import_entries'), 'import_entries must be True')
        self.assertFalse(kwargs.get('dry_run'), 'dry_run must be False')


# ── Withdrawal deadline NOT mapped to entry_close_at ─────────────────────────

class WithdrawalDeadlineTestCase(TestCase):
    """Withdrawal deadline is NOT an inscription close date (TAREFA A1)."""

    def test_withdrawal_deadline_not_in_inscription_close_fields(self):
        """Withdrawal deadline field must NOT appear in _INSCRIPTION_CLOSE_FIELDS."""
        from apps.ingestion.connectors.cosat_mongo import _INSCRIPTION_CLOSE_FIELDS
        self.assertNotIn('Withdrawal deadline', _INSCRIPTION_CLOSE_FIELDS)
        self.assertNotIn('withdrawal_deadline', _INSCRIPTION_CLOSE_FIELDS)

    def test_withdrawal_deadline_does_not_set_entry_close_at(self):
        """_parse_inscription_dates must NOT map withdrawal_deadline to entry_close_at."""
        from apps.ingestion.connectors.cosat_mongo import _parse_inscription_dates
        doc = {
            'Withdrawal deadline': '2026-05-15',
            'withdrawal_deadline': '2026-05-15',
        }
        _, close_d = _parse_inscription_dates(doc)
        self.assertIsNone(close_d, 'withdrawal_deadline must not populate entry_close_at')

    def test_withdrawal_deadline_preserved_in_raw(self):
        """Withdrawal deadline IS preserved in _raw.inscriptionFields for audit."""
        from apps.ingestion.connectors.cosat_mongo import _normalize_tournament
        doc = {
            'cosatId': 'test-wd-001',
            'name': 'Test Withdrawal',
            'url': 'https://cosat.tournamentsoftware.com/tournament/test-wd-001',
            'Withdrawal deadline': '2026-05-15',
        }
        result = _normalize_tournament(doc)
        self.assertIsNotNone(result)
        self.assertIsNone(result['entry_close_at'], 'entry_close_at must remain null')
        inscription_fields = result['_raw'].get('inscriptionFields', {})
        self.assertIn('Withdrawal deadline', inscription_fields, 'withdrawal preserved in _raw')


# ── FBT seed idempotent ───────────────────────────────────────────────────────

class FbtSeedTestCase(TestCase):
    """FBT Organization + DataSource seed is idempotent (TAREFA B3)."""

    def test_fbt_seed_creates_organization(self):
        """seed_sources creates FBT Organization."""
        from django.core.management import call_command
        call_command('seed_sources', verbosity=0)
        from apps.sources.models import Organization
        self.assertTrue(
            Organization.objects.filter(short_name='FBT').exists(),
            'FBT Organization must exist after seed_sources'
        )

    def test_fbt_seed_creates_datasource(self):
        """seed_sources creates FBT DataSource with enabled=False."""
        from django.core.management import call_command
        call_command('seed_sources', verbosity=0)
        from apps.sources.models import DataSource
        ds = DataSource.objects.filter(slug='fbt-public').first()
        self.assertIsNotNone(ds, 'FBT DataSource must exist after seed_sources')
        self.assertFalse(ds.enabled, 'FBT DataSource must be disabled (no connector yet)')
        self.assertEqual(ds.connector_key, 'fbt_public')

    def test_fbt_seed_idempotent(self):
        """Running seed_sources twice must not duplicate FBT records."""
        from django.core.management import call_command
        from apps.sources.models import Organization, DataSource
        call_command('seed_sources', verbosity=0)
        call_command('seed_sources', verbosity=0)
        self.assertEqual(Organization.objects.filter(short_name='FBT').count(), 1)
        self.assertEqual(DataSource.objects.filter(slug='fbt-public').count(), 1)


class UTRConnectorTestCase(TestCase):
    """UTR v2 connector parsing — youth filter, venue country, entrants, price."""

    def _conn(self):
        from apps.ingestion.connectors.utr import UTRConnector
        return UTRConnector(config={'youth_only': True, 'youth_min': 12, 'youth_max': 18})

    def _youth_source(self):
        return {
            'id': 364159, 'name': 'Kirmayr UTR',
            'eventDivisions': [{'name': 'Masculino Sub-14'}, {'name': 'Feminino Sub-16'}],
            'eventSchedule': {
                'eventStartUtc': '2026-06-19T06:00:00', 'eventEndUtc': '2026-06-21T06:00:00',
                'registrationStartUtc': '2026-05-01T06:00:00', 'registrationEndUtc': '2026-06-09T22:00:00',
            },
            'eventState': {'registrationState': {'value': 'open_registration'}},
            'surfaceType': 'clay',
            'priceRange': '200 Division Fees', 'currencyInfo': {'abbreviation': 'BRL'},
            'eventLocations': [{
                'cityName': 'Sao Paulo', 'stateAbbr': 'SP', 'stateName': 'Sao Paulo',
                'countryName': 'Brazil', 'countryCode3': 'BRA', 'streetAddress': 'Rua X',
            }],
            'club': {'name': 'Kirmayr Country Club'},
            'utrRange': '1.0 - 16.0', 'gender': 'Co-ed',
            'registeredMembers': [
                {'memberId': 1, 'firstName': 'Joao', 'lastName': 'Silva'},
                {'memberId': 2, 'firstName': 'Maria', 'lastName': 'Souza'},
            ],
        }

    def test_parses_youth_brazil_event(self):
        src = self._youth_source()
        loc0 = src['eventLocations'][0]
        p = self._conn()._parse_event(src, loc0, youth_only=True, lo=12, hi=18)
        self.assertIsNotNone(p)
        self.assertEqual(p['external_id'], 'utr:364159')
        self.assertEqual(p['circuit'], 'UTR')
        self.assertEqual(p['modality'], 'tennis')
        self.assertEqual(p['status'], 'open')
        self.assertEqual(p['surface'], 'clay')
        self.assertEqual(p['start_date'], '2026-06-19')
        self.assertEqual(p['venue']['country'], 'Brazil')
        self.assertEqual(p['venue']['country_code'], 'BRA')
        self.assertEqual(p['venue']['city'], 'Sao Paulo')
        self.assertEqual(p['venue']['state'], 'SP')
        # BRL price parsed
        self.assertEqual(p['base_price_brl'], 200.0)
        # entrants captured
        self.assertEqual(len(p['acceptance_list'][0]['players']), 2)
        names = [pl['name'] for pl in p['acceptance_list'][0]['players']]
        self.assertIn('Joao Silva', names)

    def test_excludes_adult_event(self):
        src = self._youth_source()
        src['name'] = 'CSA Tennis Tour Livre'
        src['eventDivisions'] = [{'name': 'Masculino Livre'}, {'name': 'Feminino Livre'}]
        loc0 = src['eventLocations'][0]
        p = self._conn()._parse_event(src, loc0, youth_only=True, lo=12, hi=18)
        self.assertIsNone(p)

    def test_youth_matcher(self):
        c = self._conn()
        self.assertTrue(c._matches_youth('Copa Sub-14', [], 12, 18))
        self.assertTrue(c._matches_youth('Torneio', ['U16 Masculino'], 12, 18))
        self.assertTrue(c._matches_youth('Juvenil', [], 12, 18))
        self.assertFalse(c._matches_youth('Open Livre', ['Masculino Livre'], 12, 18))
        self.assertFalse(c._matches_youth('Sub-10 Kids', [], 12, 18))  # below 12

    def test_usd_price_not_set_as_brl(self):
        src = self._youth_source()
        src['priceRange'] = 'Free–235 Division Fees'
        src['currencyInfo'] = {'abbreviation': 'USD'}
        loc0 = src['eventLocations'][0]
        p = self._conn()._parse_event(src, loc0, youth_only=True, lo=12, hi=18)
        self.assertIsNone(p['base_price_brl'])
        self.assertIn('USD', p['price_notes'])
