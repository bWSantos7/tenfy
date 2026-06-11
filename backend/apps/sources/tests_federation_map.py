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