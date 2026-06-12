"""
Testes do auto-vínculo de inscritos COSAT/ITF/UTR com a Agenda (WatchlistItem).

Cobre o caso real Julia Alves Nardy (perfil) × Julia Nardy (COSAT) + negativos
(gênero incompatível, sobrenome diferente), dedup com acompanhamento manual e a
garantia de que o caminho legado (CBT/FPT/FCT) NÃO mudou.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.players.models import PlayerProfile
from apps.sources.models import Organization
from apps.tournaments.models import Tournament, TournamentEdition
from apps.registrations.models import FederationEntry, TournamentRegistration, MatchingLog
from apps.registrations.tasks import match_federation_entries
from apps.watchlist.models import WatchlistItem

User = get_user_model()


def _run_match(edition_id):
    return match_federation_entries.apply(args=[edition_id]).result


class AutoAgendaMatchingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='COSAT', short_name='COSAT', type='confederation')
        self.tournament = Tournament.objects.create(
            canonical_name='Copa Instituto Icaro', canonical_slug='copa-instituto-icaro',
            circuit='COSAT', modality='tennis', organization=self.org,
        )
        self.edition = TournamentEdition.objects.create(
            tournament=self.tournament, title='Copa Instituto Icaro',
            external_id='cosat:0bd3753d', season_year=2026, status='open',
        )

    def _profile(self, email, name, gender='', birth_year=None):
        user = User.objects.create_user(email=email, password='pass123')
        return PlayerProfile.objects.create(
            user=user, display_name=name, gender=gender, birth_year=birth_year,
        )

    def _entry(self, name, category='Girls Singles U16', source='cosat', **kw):
        return FederationEntry.objects.create(
            edition=self.edition, player_name=name, category_text=category,
            player_external_id=kw.get('ext_id', ''), source=source,
            ranking_position=kw.get('ranking_position'),
            removed_or_replaced=kw.get('removed_or_replaced', False),
        )

    # ── Caso real: Julia Nardy (COSAT) → Julia Alves Nardy (perfil) ──
    def test_julia_auto_agenda(self):
        prof = self._profile('julia@test.com', 'Julia Alves Nardy', gender='F', birth_year=2010)
        self._entry('Julia Nardy')

        res = _run_match(self.edition.id)
        self.assertGreaterEqual(res['registrations_created'], 1)

        reg = TournamentRegistration.objects.filter(profile=prof, edition=self.edition).first()
        self.assertIsNotNone(reg)
        self.assertFalse(reg.is_withdrawn)

        item = WatchlistItem.objects.filter(user=prof.user, edition=self.edition).first()
        self.assertIsNotNone(item, 'torneio deve entrar na Agenda automaticamente')
        self.assertEqual(item.user_status, WatchlistItem.STATUS_REGISTERED, 'status = inscrito')
        self.assertEqual(item.profile_id, prof.id, 'vinculado ao perfil esportivo correto')

        log = MatchingLog.objects.filter(profile=prof, registration_created=True).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.method, MatchingLog.METHOD_NAME_TOKEN)
        self.assertEqual(log.confidence, MatchingLog.CONFIDENCE_HIGH)

    def test_julia_without_profile_gender_still_matches(self):
        prof = self._profile('julia2@test.com', 'Julia Alves Nardy')  # sem gênero/idade
        self._entry('Julia Nardy')
        _run_match(self.edition.id)
        self.assertTrue(TournamentRegistration.objects.filter(profile=prof).exists())

    # ── Negativos (evitar falso positivo) ──
    def test_gender_mismatch_blocked(self):
        # Nome idêntico, mas categoria feminina × perfil masculino → bloqueia.
        prof = self._profile('carlos@test.com', 'Carlos Lino', gender='M', birth_year=2010)
        self._entry('Carlos Lino', category='Girls Singles U16')
        _run_match(self.edition.id)
        self.assertFalse(TournamentRegistration.objects.filter(profile=prof).exists())

    def test_different_surname_not_matched(self):
        prof = self._profile('maria@test.com', 'Maria Santos', gender='F', birth_year=2010)
        self._entry('Maria Silva')  # mesmo 1º nome, sobrenome diferente
        _run_match(self.edition.id)
        self.assertFalse(TournamentRegistration.objects.filter(profile=prof).exists())

    def test_age_far_above_cap_blocked(self):
        # Perfil claramente fora da faixa (adulto) não casa com U16.
        prof = self._profile('velho@test.com', 'Julia Nardy', gender='F', birth_year=1990)
        self._entry('Julia Nardy', category='Girls Singles U16')
        _run_match(self.edition.id)
        self.assertFalse(TournamentRegistration.objects.filter(profile=prof).exists())

    def test_medium_without_corroboration_is_possible_only(self):
        # 1º+último nome iguais, meio diferente, sem gênero/idade → possível, não auto.
        prof = self._profile('jcn@test.com', 'Julia Costa Nardy')
        self._entry('Julia Alves Nardy')
        _run_match(self.edition.id)
        self.assertFalse(TournamentRegistration.objects.filter(profile=prof).exists())
        log = MatchingLog.objects.filter(profile=prof).first()
        self.assertIsNotNone(log, 'possível correspondência deve ser registrada para auditoria')
        self.assertFalse(log.registration_created)
        self.assertEqual(log.confidence, MatchingLog.CONFIDENCE_MEDIUM)

    # ── Dedup + upgrade de status ──
    def test_dedup_with_manual_follow_upgrades_status(self):
        prof = self._profile('julia3@test.com', 'Julia Alves Nardy', gender='F', birth_year=2010)
        # Acompanhamento manual prévio (status 'none').
        WatchlistItem.objects.create(user=prof.user, edition=self.edition,
                                      user_status=WatchlistItem.STATUS_NONE)
        self._entry('Julia Nardy')
        _run_match(self.edition.id)
        items = WatchlistItem.objects.filter(user=prof.user, edition=self.edition)
        self.assertEqual(items.count(), 1, 'não deve duplicar a Agenda')
        self.assertEqual(items.first().user_status, WatchlistItem.STATUS_REGISTERED)

    # ── Garante que o caminho legado (CBT) NÃO mudou (continua estrito) ──
    def test_cbt_legacy_path_stays_strict(self):
        prof = self._profile('julia4@test.com', 'Julia Alves Nardy', gender='F', birth_year=2010)
        self._entry('Julia Nardy', category='Sub-16 Feminino', source='cbt')
        _run_match(self.edition.id)
        # Legado usa SequenceMatcher>0.95 → nome abreviado NÃO casa.
        self.assertFalse(
            TournamentRegistration.objects.filter(profile=prof).exists(),
            'CBT deve manter o match estrito (sem flexível)',
        )

    # ── removed_or_replaced (desistência) entra como retirado ──
    def test_removed_entry_registers_as_withdrawn(self):
        prof = self._profile('julia5@test.com', 'Julia Alves Nardy', gender='F', birth_year=2010)
        self._entry('Julia Nardy', removed_or_replaced=True)
        _run_match(self.edition.id)
        reg = TournamentRegistration.objects.filter(profile=prof, edition=self.edition).first()
        self.assertIsNotNone(reg)
        self.assertTrue(reg.is_withdrawn)
