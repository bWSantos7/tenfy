"""
Management command: classify existing TournamentEditions as is_youth=True/False.

Usage:
    python manage.py classify_youth           # classify only NULL entries
    python manage.py classify_youth --all     # reclassify all entries
    python manage.py classify_youth --dry-run # preview without saving
"""
from django.core.management.base import BaseCommand
from apps.tournaments.models import TournamentEdition
from apps.ingestion.persistence import _classify_is_youth


class Command(BaseCommand):
    help = 'Classifica torneios existentes como is_youth=True/False'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Reclassificar todos (inclusive já classificados)')
        parser.add_argument('--dry-run', action='store_true', help='Apenas exibir o resultado, sem salvar')

    def handle(self, *args, **options):
        reclassify_all = options['all']
        dry_run = options['dry_run']

        qs = TournamentEdition.objects.prefetch_related('categories').all()
        if not reclassify_all:
            qs = qs.filter(is_youth__isnull=True)

        total = qs.count()
        self.stdout.write(f'Classificando {total} torneio(s)...')

        youth_count = 0
        adult_count = 0
        to_update = []

        for ed in qs.iterator():
            categories = [
                {'source_text': c.source_category_text}
                for c in ed.categories.all()
            ]
            circuit = ed.tournament.circuit if ed.tournament_id else ''
            result = _classify_is_youth(circuit, ed.title, categories)

            if result:
                youth_count += 1
            else:
                adult_count += 1

            if not dry_run:
                ed.is_youth = result
                to_update.append(ed)

            if options['verbosity'] >= 2:
                marker = '✓ JUVENIL' if result else '✗ ADULTO'
                self.stdout.write(f'  [{marker}] {ed.title} ({ed.season_year})')

        if not dry_run and to_update:
            TournamentEdition.objects.bulk_update(to_update, ['is_youth'], batch_size=200)
            self.stdout.write(self.style.SUCCESS(
                f'Concluído: {youth_count} juvenis, {adult_count} adultos ({total} total).'
            ))
        else:
            self.stdout.write(
                f'[DRY-RUN] Seria: {youth_count} juvenis, {adult_count} adultos ({total} total).'
            )
