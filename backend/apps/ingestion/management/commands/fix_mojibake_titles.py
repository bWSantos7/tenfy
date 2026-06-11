"""TASK 4 — Conserta nomes de torneios com mojibake (UTF-8 lido como latin-1).

A causa raiz foi corrigida no extractor (passou a ler as páginas como UTF-8);
este comando repara os registros JÁ existentes no Tenfy. Dry-run por padrão;
``--apply`` grava. Seguro: usa ``demojibake`` (só altera mojibake real).

Uso:
    python manage.py fix_mojibake_titles            # dry-run + relatório
    python manage.py fix_mojibake_titles --apply    # grava
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ingestion.text_normalize import demojibake
from apps.tournaments.models import Tournament, TournamentEdition


class Command(BaseCommand):
    help = 'Conserta nomes de torneios com mojibake (acentuação quebrada).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Grava as correções (sem isso é dry-run).')

    def handle(self, *args, **options):
        apply = options['apply']
        ed_fixed = t_fixed = 0
        with transaction.atomic():
            for e in TournamentEdition.objects.all():
                new = demojibake(e.title or '')
                if new != (e.title or ''):
                    if ed_fixed < 25:
                        self.stdout.write(f'  ed {e.external_id}: {e.title!r} -> {new!r}')
                    if apply:
                        e.title = new
                        e.save(update_fields=['title'])
                    ed_fixed += 1
            for t in Tournament.objects.all():
                new = demojibake(t.canonical_name or '')
                if new != (t.canonical_name or ''):
                    if apply:
                        t.canonical_name = new
                        t.save(update_fields=['canonical_name'])
                    t_fixed += 1
            if not apply:
                transaction.set_rollback(True)
        mode = 'APLICADO' if apply else 'DRY-RUN (nada gravado)'
        self.stdout.write(self.style.SUCCESS(
            f'[{mode}] edicoes_corrigidas={ed_fixed} torneios_corrigidos={t_fixed}'))