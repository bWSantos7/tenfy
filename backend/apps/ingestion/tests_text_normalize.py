"""TASK 4 — testes do conserto de mojibake nos nomes de torneios."""
from django.core.management import call_command
from django.test import TestCase

from apps.ingestion.text_normalize import demojibake


class DemojibakeTest(TestCase):
    def test_conserta_mojibake(self):
        self.assertEqual(demojibake('TÃªnis'), 'Tênis')
        self.assertEqual(demojibake('8Âª Etapa'), '8ª Etapa')
        self.assertEqual(demojibake('PoÃ§os de Caldas'), 'Poços de Caldas')
        self.assertEqual(demojibake('FEST TÃ\x8aNIS 2026'), 'FEST TÊNIS 2026')
        self.assertEqual(demojibake('25Âª Copa Thomas Engel de TÃªnis'),
                         '25ª Copa Thomas Engel de Tênis')

    def test_preserva_nomes_corretos(self):
        # Não estraga nomes já corretos (round-trip falha -> original).
        self.assertEqual(demojibake('São Paulo'), 'São Paulo')
        self.assertEqual(demojibake('Tênis'), 'Tênis')
        self.assertEqual(demojibake('Circuito Infantojuvenil'), 'Circuito Infantojuvenil')
        self.assertEqual(demojibake('J30 Montevideo'), 'J30 Montevideo')
        self.assertEqual(demojibake(''), '')
        self.assertIsNone(demojibake(None))

    def test_comando_repara_edicoes(self):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, TournamentEdition
        org = Organization.objects.create(
            name='Org Teste', short_name='OT', type=Organization.TYPE_CONFEDERATION)
        t = Tournament.objects.create(
            canonical_name='Copa de TÃªnis', canonical_slug='copa-tenis-x', organization=org)
        e = TournamentEdition.objects.create(
            tournament=t, season_year=2026, title='Copa de TÃªnis')
        call_command('fix_mojibake_titles', '--apply', verbosity=0)
        e.refresh_from_db()
        t.refresh_from_db()
        self.assertEqual(e.title, 'Copa de Tênis')
        self.assertEqual(t.canonical_name, 'Copa de Tênis')