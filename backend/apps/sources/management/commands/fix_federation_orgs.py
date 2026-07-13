"""TASK 1 — Corrige as Organizations das federações estaduais para as
siglas/nomes OFICIAIS (formato ``SIGLA-UF``), renomeando **in-place pela UF**
(chave autoritativa). Não cria duplicadas nem apaga registros; preserva o
vínculo dos torneios (que é por org, e a org permanece a mesma — só muda
nome/sigla).

Dry-run por padrão (seguro). Use ``--apply`` para gravar.

Uso:
    python manage.py fix_federation_orgs            # dry-run + relatório
    python manage.py fix_federation_orgs --apply    # grava
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.federations import BRAZIL_TENNIS_FEDERATIONS
from apps.sources.models import Organization


class Command(BaseCommand):
    help = 'Renomeia as federações estaduais para as siglas/nomes oficiais (por UF).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Grava as mudanças (sem isso é dry-run).')

    def handle(self, *args, **options):
        apply = options['apply']
        renamed = created = unchanged = 0
        ambiguous = []

        with transaction.atomic():
            for uf, name, short in BRAZIL_TENNIS_FEDERATIONS:
                orgs = list(
                    Organization.objects
                    .filter(type=Organization.TYPE_FEDERATION, state=uf)
                    .order_by('id')
                )
                if len(orgs) > 1:
                    ambiguous.append((uf, [o.short_name for o in orgs]))

                if not orgs:
                    self.stdout.write(f'  [{uf}] CRIAR  {short} — {name}')
                    if apply:
                        Organization.objects.create(
                            name=name, short_name=short,
                            type=Organization.TYPE_FEDERATION,
                            state=uf, is_active=True,
                        )
                    created += 1
                    continue

                # Renomeia a canônica (a 1ª por id — a mesma que _resolve_org usa).
                org = orgs[0]
                if (org.name, org.short_name) == (name, short):
                    unchanged += 1
                    continue
                self.stdout.write(
                    f'  [{uf}] {org.short_name!r}->{short!r} | {org.name!r}->{name!r}'
                )
                if apply:
                    org.name = name
                    org.short_name = short
                    org.save(update_fields=['name', 'short_name'])
                renamed += 1

            if not apply:
                transaction.set_rollback(True)

        for uf, shorts in ambiguous:
            self.stdout.write(self.style.WARNING(
                f'  ATENÇÃO {uf}: múltiplas orgs {shorts} — renomeada a 1ª. '
                f'Rode dedupe_federation_orgs para unificar.'
            ))

        mode = 'APLICADO' if apply else 'DRY-RUN (nada gravado)'
        self.stdout.write(self.style.SUCCESS(
            f'[{mode}] renomeadas={renamed} criadas={created} '
            f'inalteradas={unchanged} ufs_ambiguas={len(ambiguous)}'
        ))