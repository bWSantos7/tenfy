# -*- coding: utf-8 -*-
"""
Regressão item 6 — ITF lista de inscritos.

O scraper passou a guardar os jogadores numa coleção separada (itfplayers) em
vez de embutir 'inscritos' no doc do torneio. O connector agora junta os dois
por tournament_id == slug_externo e reconstrói a estrutura 'inscritos' que o
restante do pipeline (normalize_acceptance_list / iter_player_entries) consome.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.ingestion.connectors.itf_mongo import (
    ItfMongoConnector,
    normalize_acceptance_list,
    iter_player_entries,
)

FAKE_PLAYERS = [
    {'tournament_id': 'J-J60-BRA-2026-001', 'genero': 'masculino', 'secao': 'draw_principal',
     'secao_label': 'Draw Principal (Masculino)', 'nome': 'Joao Silva', 'pais': 'Brazil',
     'codigo_pais': 'BRA', 'ranking': '10', 'posicao': '1', 'prioridade': '1', 'wtn': '15.0'},
    {'tournament_id': 'J-J60-BRA-2026-001', 'genero': 'masculino', 'secao': 'qualifying',
     'secao_label': 'Qualifying (Masculino)', 'nome': 'Pedro Souza', 'pais': 'Brazil',
     'codigo_pais': 'BRA', 'ranking': '120', 'posicao': '1', 'prioridade': '1', 'wtn': '12.0'},
    {'tournament_id': 'J-J60-BRA-2026-001', 'genero': 'feminino', 'secao': 'draw_principal',
     'secao_label': 'Draw Principal (Feminino)', 'nome': 'Ana Lima', 'pais': 'Argentina',
     'codigo_pais': 'ARG', 'ranking': '8', 'posicao': '1', 'prioridade': '1', 'wtn': '16.0'},
]


class FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *_args, **_kwargs):
        return list(self._docs)


class ItfPlayersJoinTestCase(TestCase):
    def _connector(self, docs):
        c = ItfMongoConnector()
        c._players_lookup = None
        return c

    @patch.object(ItfMongoConnector, '_players_collection')
    def test_lookup_groups_by_gender_and_section(self, mock_coll):
        mock_coll.return_value = FakeCollection(FAKE_PLAYERS)
        c = self._connector(FAKE_PLAYERS)
        lookup = c._build_players_lookup()
        insc = lookup.get('J-J60-BRA-2026-001')
        self.assertIsNotNone(insc)
        self.assertIn('masculino', insc)
        self.assertIn('feminino', insc)
        # masculino tem 2 seções (principal + qualifying)
        secoes = {s['secao'] for s in insc['masculino']}
        self.assertEqual(secoes, {'draw_principal', 'qualifying'})

    @patch.object(ItfMongoConnector, '_players_collection')
    def test_case_insensitive_lookup(self, mock_coll):
        mock_coll.return_value = FakeCollection(FAKE_PLAYERS)
        c = self._connector(FAKE_PLAYERS)
        lookup = c._build_players_lookup()
        # slug com caixa diferente ainda encontra
        self.assertIsNotNone(lookup.get('j-j60-bra-2026-001'))

    @patch.object(ItfMongoConnector, '_players_collection')
    def test_acceptance_list_built_from_players(self, mock_coll):
        mock_coll.return_value = FakeCollection(FAKE_PLAYERS)
        c = self._connector(FAKE_PLAYERS)
        insc = c._build_players_lookup().get('J-J60-BRA-2026-001')
        al = normalize_acceptance_list(insc)
        total = sum(len(s['players']) for s in al)
        self.assertEqual(total, 3)
        # confere campos ricos (país, ranking, posição) preservados
        p = al[0]['players'][0]
        self.assertIn('country', p)
        self.assertIn('ranking', p)
        self.assertTrue(p['name'])

    @patch.object(ItfMongoConnector, '_players_collection')
    def test_iter_player_entries_yields_federation_entries(self, mock_coll):
        mock_coll.return_value = FakeCollection(FAKE_PLAYERS)
        c = self._connector(FAKE_PLAYERS)
        insc = c._build_players_lookup().get('J-J60-BRA-2026-001')
        entries = list(iter_player_entries(insc, 'J-J60-BRA-2026-001'))
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e.get('player_name') for e in entries))


class ItfVenueCountryTestCase(TestCase):
    """Card 1 (tasks2): o connector ITF deve capturar o NOME do país (pais), não só o código."""

    def test_normalize_captures_country_name(self):
        from apps.ingestion.connectors.itf_mongo import _normalize_tournament
        doc = {
            'slug_externo': 'j-j60-sui-2026-001',
            'nome': 'J60 Geneva',
            'pais': 'Switzerland',
            'codigo_pais': 'SUI',
            'cidade': 'Geneva',
            'data_inicio': '2026-06-15',
            'data_fim': '2026-06-21',
        }
        out = _normalize_tournament(doc)
        self.assertIsNotNone(out)
        self.assertEqual(out['venue']['country'], 'Switzerland')
        self.assertEqual(out['venue']['country_code'], 'SUI')

    def test_venue_created_when_only_country(self):
        from apps.ingestion.connectors.itf_mongo import _normalize_tournament
        doc = {
            'slug_externo': 'j-j60-bel-2026-001', 'nome': 'J60 X',
            'pais': 'Belgium', 'codigo_pais': 'BEL', 'cidade': '',
        }
        out = _normalize_tournament(doc)
        self.assertIsNotNone(out['venue'])
        self.assertEqual(out['venue']['country'], 'Belgium')
