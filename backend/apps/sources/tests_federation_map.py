"""TASK 1 — testes da correção de federações para siglas oficiais SIGLA-UF."""
from django.core.management import call_command
from django.test import TestCase

from apps.sources.federations import BRAZIL_TENNIS_FEDERATIONS
from apps.sources.models import Organization


class FixFederationOrgsTest(TestCase):
    """O comando fix_federation_orgs renomeia in-place as federações estaduais
    (seedadas com nomes antigos pela migração 0012) para o oficial, por UF."""

    def test_seed_list_is_official_sigla_uf(self):
        for uf, name, short in BRAZIL_TENNIS_FEDERATIONS:
            self.assertTrue(short.endswith(f'-{uf}'),
                            f'{uf}: sigla {short} fora do formato SIGLA-UF')
        # casos que colidiam por sigla solta — devem ser distintos por UF
        by_uf = {uf: short for uf, _, short in BRAZIL_TENNIS_FEDERATIONS}
        self.assertEqual(by_uf['RJ'], 'ADTERJ-RJ')
        self.assertEqual(by_uf['SC'], 'FCT-SC')
        self.assertEqual(by_uf['CE'], 'FCT-CE')   # não colide com SC
        self.assertEqual(by_uf['MG'], 'FMTBT-MG')
        self.assertEqual(by_uf['SP'], 'FPT-SP')

    def test_rename_to_official_by_uf(self):
        call_command('fix_federation_orgs', '--apply', verbosity=0)
        rj = Organization.objects.get(state='RJ', type=Organization.TYPE_FEDERATION)
        self.assertEqual(rj.short_name, 'ADTERJ-RJ')
        self.assertEqual(
            rj.name, 'Associação Desportiva de Tênis do Estado do Rio de Janeiro')
        sc = Organization.objects.get(state='SC', type=Organization.TYPE_FEDERATION)
        self.assertEqual(sc.short_name, 'FCT-SC')
        # Todas as estaduais no formato SIGLA-UF (sem sigla solta).
        for org in (Organization.objects
                    .filter(type=Organization.TYPE_FEDERATION).exclude(state='')):
            self.assertTrue(org.short_name.endswith(f'-{org.state}'),
                            f'{org.state}: {org.short_name}')

    def test_no_rj_tournament_bound_to_sc_federation(self):
        """Validação do task.md: nenhum RJ vinculado a FCT-SC."""
        call_command('fix_federation_orgs', '--apply', verbosity=0)
        rj = Organization.objects.get(state='RJ', type=Organization.TYPE_FEDERATION)
        self.assertNotEqual(rj.short_name, 'FCT-SC')
        self.assertEqual(rj.state, 'RJ')

    def test_idempotente(self):
        call_command('fix_federation_orgs', '--apply', verbosity=0)
        before = {o.id: (o.name, o.short_name)
                  for o in Organization.objects.filter(
                      type=Organization.TYPE_FEDERATION)}
        call_command('fix_federation_orgs', '--apply', verbosity=0)
        after = {o.id: (o.name, o.short_name)
                 for o in Organization.objects.filter(
                     type=Organization.TYPE_FEDERATION)}
        self.assertEqual(before, after)

class OrganizationFilterListTest(TestCase):
    """Filtro de torneios (list de organizations, não-admin) mostra só as
    entidades oficiais: federações com UF + CBT/COSAT/ITF/UTR — exclui beach
    tennis (sem UF) e plataformas fora da lista."""

    def setUp(self):
        from rest_framework.test import APIClient
        from django.contrib.auth import get_user_model
        from apps.sources.models import DataSource
        from apps.tournaments.models import Tournament, TournamentEdition
        self.client = APIClient()
        self.client.force_authenticate(
            user=get_user_model().objects.create_user(email='of@test.com', password='p'))
        dso = Organization.objects.create(
            name='dsorg', short_name='DSO', type=Organization.TYPE_CONFEDERATION)
        self.ds = DataSource.objects.create(
            organization=dso, source_name='x', slug='org-filter-ds',
            source_type=DataSource.SOURCE_TYPE_JSON, base_url='https://x')

        def mk(name, short, otype, state):
            o = Organization.objects.create(name=name, short_name=short, type=otype, state=state)
            t = Tournament.objects.create(canonical_name=name, canonical_slug='cs-' + short.lower(), organization=o)
            TournamentEdition.objects.create(
                tournament=t, data_source=self.ds, season_year=2026, title=name, external_id='x:' + short)
        mk('Fed Paulista X', 'FPTX-SP', Organization.TYPE_FEDERATION, 'SP')
        mk('Fed Praia X', 'FBTX', Organization.TYPE_FEDERATION, '')
        mk('CBT', 'CBT', Organization.TYPE_CONFEDERATION, '')
        mk('LetzPlay X', 'LZPX', Organization.TYPE_PLATFORM, '')

    def test_filtro_so_oficiais(self):
        res = self.client.get('/api/sources/organizations/')
        data = res.data if isinstance(res.data, list) else res.data.get('results', res.data)
        shorts = {o['short_name'] for o in data}
        self.assertIn('FPTX-SP', shorts)
        self.assertIn('CBT', shorts)
        self.assertNotIn('FBTX', shorts)
        self.assertNotIn('LZPX', shorts)
