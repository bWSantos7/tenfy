# -*- coding: utf-8 -*-
"""
Regressão item 5 — FCT prazo de inscrição.

A página FCT traz "Inscrições abertas até DD/MM/YYYY" (com cedilha em
Inscri-ç-ões e, às vezes, a data dentro de um <span>). O regex antigo usava
'c' simples (Inscric...) e nunca casava, então todas as editions FCT vinham
sem entry_close_at.
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.ingestion.connectors.fct import FCTPublicConnector


def _resp(html: str):
    r = MagicMock()
    r.status_code = 200
    r.text = html
    return r


class FctDeadlineRegexTestCase(TestCase):
    @patch.object(FCTPublicConnector, 'fetch')
    def test_deadline_with_cedilla_and_span(self, mock_fetch):
        # Estrutura real: data dentro de <span>, palavra com cedilha.
        html = (
            '<html><body>'
            '<div>Inscrições abertas até <span class="lbl">30/03/2026</span> '
            'e cancelamentos até 30/03/2026.</div>'
            '</body></html>'
        )
        mock_fetch.return_value = _resp(html)
        c = FCTPublicConnector(data_source=None)
        detail = c._fetch_detail('http://x/22644')
        self.assertTrue(detail.get('deadline'), f'deadline vazio: {detail}')
        self.assertIn('30/03/2026', detail['deadline'])
        d = c._parse_detail_deadline(detail['deadline'])
        self.assertIsNotNone(d)
        self.assertEqual((d.year, d.month, d.day), (2026, 3, 30))

    @patch.object(FCTPublicConnector, 'fetch')
    def test_deadline_unaccented_form(self, mock_fetch):
        html = '<html><body><div>Inscricoes abertas ate 12/04/2026</div></body></html>'
        mock_fetch.return_value = _resp(html)
        c = FCTPublicConnector(data_source=None)
        detail = c._fetch_detail('http://x/1')
        self.assertTrue(detail.get('deadline'))
        d = c._parse_detail_deadline(detail['deadline'])
        self.assertEqual((d.year, d.month, d.day), (2026, 4, 12))

    @patch.object(FCTPublicConnector, 'fetch')
    def test_no_deadline_returns_none(self, mock_fetch):
        html = '<html><body><div>Sem prazo aqui.</div></body></html>'
        mock_fetch.return_value = _resp(html)
        c = FCTPublicConnector(data_source=None)
        detail = c._fetch_detail('http://x/2')
        self.assertFalse(detail.get('deadline'))
        self.assertIsNone(c._parse_detail_deadline(detail.get('deadline')))
