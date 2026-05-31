"""
Detecta e remove TournamentEditions duplicadas.

Critérios de duplicata (em ordem de prioridade):
  1. Mesmo external_id em editions distintas → duplicata certa
  2. Mesmo (tournament, start_date, end_date) → mesma edição importada duas vezes
  3. Mesmo (organization, start_date, end_date, venue_city, venue_state) com
     título similar (≥ 80%) → provável duplicata de fontes diferentes

Estratégia de merge: mantém a edição mais antiga (menor id) e remove as demais,
migrando WatchlistItems, FederationEntries e TournamentRegistrations para a
edição sobrevivente antes de deletar.

Usage:
    python manage.py deduplicate_editions --dry-run        # só lista, não remove
    python manage.py deduplicate_editions                  # remove após confirmação
    python manage.py deduplicate_editions --yes            # remove sem pedir confirmação
"""
import unicodedata
import re
from difflib import SequenceMatcher
from django.core.management.base import BaseCommand
from django.db import transaction


def _normalize(text: str) -> str:
    s = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]+', ' ', s).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


class Command(BaseCommand):
    help = 'Encontra e remove TournamentEditions duplicadas'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas lista duplicatas, não remove')
        parser.add_argument('--yes', action='store_true', help='Remove sem pedir confirmação')
        parser.add_argument('--min-similarity', type=float, default=0.80,
                            help='Similaridade mínima de título para considerar duplicata (padrão 0.80)')

    def handle(self, *args, **options):
        from apps.tournaments.models import TournamentEdition
        from apps.watchlist.models import WatchlistItem

        dry_run = options['dry_run']
        auto_yes = options['yes']
        min_sim = options['min_similarity']

        self.stdout.write('Carregando edições...')
        editions = list(
            TournamentEdition.objects.select_related('tournament__organization')
            .order_by('id')
        )
        self.stdout.write(f'Total: {len(editions)} edições\n')

        duplicate_groups = []  # list of lists — each inner list = group of duplicates

        # ── Critério 1: mesmo external_id (excluindo None/vazio) ──────────────
        from collections import defaultdict
        by_eid = defaultdict(list)
        for ed in editions:
            if ed.external_id:
                by_eid[ed.external_id].append(ed)
        for eid, group in by_eid.items():
            if len(group) > 1:
                duplicate_groups.append(('external_id', eid, group))

        already_grouped = {ed.id for g in duplicate_groups for ed in g[2]}

        # ── Critério 2: mesmo tournament + mesmas datas ───────────────────────
        by_tournament_dates = defaultdict(list)
        for ed in editions:
            if ed.id in already_grouped:
                continue
            key = (ed.tournament_id, str(ed.start_date), str(ed.end_date))
            by_tournament_dates[key].append(ed)
        for key, group in by_tournament_dates.items():
            if len(group) > 1:
                duplicate_groups.append(('tournament+dates', str(key), group))
                already_grouped.update(ed.id for ed in group)

        # ── Critério 3: mesma org + datas + local + título similar ────────────
        remaining = [ed for ed in editions if ed.id not in already_grouped]
        checked = set()
        for i, a in enumerate(remaining):
            if a.id in checked:
                continue
            group = [a]
            for b in remaining[i+1:]:
                if b.id in checked:
                    continue
                same_dates = (str(a.start_date) == str(b.start_date) and
                              str(a.end_date) == str(b.end_date))
                same_org = (a.tournament.organization_id == b.tournament.organization_id)
                same_city = ((a.venue_city or '').lower() == (b.venue_city or '').lower())
                same_state = ((a.venue_state or '') == (b.venue_state or ''))
                if same_dates and same_org and same_city and same_state:
                    sim = _similarity(a.title, b.title)
                    if sim >= min_sim:
                        group.append(b)
                        checked.add(b.id)
            if len(group) > 1:
                duplicate_groups.append(('title_similarity', f'{a.title[:40]}…', group))
            checked.add(a.id)

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS('Nenhuma duplicata encontrada.'))
            return

        # ── Exibir grupos ─────────────────────────────────────────────────────
        total_to_remove = 0
        for criterion, key, group in duplicate_groups:
            keep = group[0]  # menor id = mais antigo
            remove = group[1:]
            total_to_remove += len(remove)
            self.stdout.write(f'\n[{criterion}] {key}')
            self.stdout.write(f'  MANTER  [{keep.id}] {keep.title[:70]}')
            for r in remove:
                self.stdout.write(self.style.WARNING(f'  REMOVER [{r.id}] {r.title[:70]}'))

        self.stdout.write(f'\nTotal: {len(duplicate_groups)} grupos | {total_to_remove} edições a remover')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] Nenhuma alteração feita.'))
            return

        if not auto_yes:
            resp = input('\nConfirmar remoção? (s/N): ').strip().lower()
            if resp != 's':
                self.stdout.write('Cancelado.')
                return

        # ── Remover com migração de dados ─────────────────────────────────────
        removed_total = 0
        for criterion, key, group in duplicate_groups:
            keep = group[0]
            remove_list = group[1:]
            try:
                with transaction.atomic():
                    for dup in remove_list:
                        # Migrar WatchlistItems
                        WatchlistItem.objects.filter(edition=dup).update(edition=keep)

                        # Migrar FederationEntries
                        try:
                            from apps.registrations.models import FederationEntry
                            FederationEntry.objects.filter(edition=dup).update(edition=keep)
                        except Exception:
                            pass

                        # Migrar TournamentRegistrations
                        try:
                            from apps.registrations.models import TournamentRegistration
                            TournamentRegistration.objects.filter(edition=dup).update(edition=keep)
                        except Exception:
                            pass

                        dup.delete()
                        removed_total += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'  Removido [{dup.id}] → mantido [{keep.id}]'
                        ))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'  ERRO no grupo {key}: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'\nConcluído: {removed_total} edições removidas.'))
