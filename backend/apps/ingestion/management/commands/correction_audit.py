"""TASK 8 — Relatório de auditoria das correções aplicadas (read-only).

Imprime um snapshot auditável do estado dos dados após as correções das TASKs
1–7: federações oficiais (SIGLA-UF), nomes sem mojibake, duplicados, datas de
inscrição e enriquecimento de inscritos (ID Tênis Integrado/UF/idade).

Uso:
    python manage.py correction_audit
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Relatório de auditoria das correções (TASK 8).'

    def handle(self, *args, **options):
        from apps.sources.models import Organization as O
        from apps.tournaments.models import TournamentEdition as TE
        from apps.registrations.models import FederationEntry as FE
        from apps.ingestion.text_normalize import demojibake
        from apps.ingestion.persistence import _dedup_fingerprint

        w = self.stdout.write
        w('=== AUDITORIA DE CORREÇÕES (TASKs 1–7) ===')

        # TASK 1 — Federações no formato oficial SIGLA-UF, sem ambiguidade/dup.
        feds = list(O.objects.filter(type=O.TYPE_FEDERATION).exclude(state=''))
        bad = [(f.state, f.short_name) for f in feds
               if not f.short_name.endswith(f'-{f.state}')]
        dup_uf = {u: c for u, c in Counter(f.state for f in feds).items() if c > 1}
        rj = next((f.short_name for f in feds if f.state == 'RJ'), None)
        sc = next((f.short_name for f in feds if f.state == 'SC'), None)
        w(f'[TASK1 Federações] estaduais={len(feds)} fora_do_formato={bad} '
          f'ufs_duplicadas={dup_uf} | RJ={rj} SC={sc}')

        # TASK 4 — Nomes sem mojibake (UTF-8 lido como latin-1).
        broken = [e.external_id for e in TE.objects.all()
                  if demojibake(e.title or '') != (e.title or '')]
        w(f'[TASK4 Nomes] edições com mojibake={len(broken)} {broken[:5]}')

        # TASK 3 — Duplicados (mesmo fingerprint título+data+cidade+UF).
        groups = defaultdict(int)
        for e in TE.objects.select_related('venue').all():
            city = (e.venue.city if e.venue else '') or ''
            st = (e.venue.state if e.venue else '') or ''
            groups[_dedup_fingerprint(e.title or '', e.start_date, city, st)] += 1
        w(f'[TASK3 Duplicados] edições duplicadas (mesmo fingerprint)='
          f'{sum(c - 1 for c in groups.values() if c > 1)}')

        # TASK 5 — Datas de inscrição (federações).
        fededs = TE.objects.filter(tournament__organization__type=O.TYPE_FEDERATION)
        w(f'[TASK5 Datas] edições de federação: total={fededs.count()} '
          f'com_abertura={fededs.exclude(entry_open_at=None).count()} '
          f'com_encerramento={fededs.exclude(entry_close_at=None).count()}')

        # TASK 6 — Inscritos enriquecidos.
        w(f'[TASK6 Inscritos] total={FE.objects.count()} '
          f'com_TI_id={FE.objects.exclude(player_ti_id="").count()} '
          f'com_UF={FE.objects.exclude(player_uf="").count()} '
          f'com_idade={FE.objects.exclude(player_age=None).count()}')

        # Distribuição por fonte (inscritos).
        by_src = dict(Counter(FE.objects.values_list('source', flat=True))
                      .most_common(8))
        w(f'[Fontes] inscritos por source (top): {by_src}')
        w('=== FIM ===')
