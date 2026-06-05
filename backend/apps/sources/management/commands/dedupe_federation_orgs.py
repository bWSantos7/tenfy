"""
Merge duplicate state-federation Organizations into a single canonical org per UF.

Production accumulated more than one federation org per state (e.g. the accented
"Federação Paulista de Tênis" seeded by players.0012 vs the ingestion-created
"Federacao Paulista de Tenis" that actually holds the tournaments). This command
keeps one survivor per UF — the one that holds the tournaments / data source —
repoints every reference (Tournament, DataSource, PlayerProfile) to it, deletes
the extras, and renames the survivor to the canonical accented name so it matches
seed_sources (preventing future duplicates).

Safe by default: dry-run. Pass --apply to commit.

    python manage.py dedupe_federation_orgs            # preview
    python manage.py dedupe_federation_orgs --apply     # commit
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sources.models import Organization, DataSource
from apps.sources.federations import BRAZIL_TENNIS_FEDERATIONS
from apps.tournaments.models import Tournament
from apps.players.models import PlayerProfile

_CANONICAL_NAME_BY_UF = {uf: name for uf, name, _short in BRAZIL_TENNIS_FEDERATIONS}


def _tournament_count(org):
    return Tournament.objects.filter(organization=org).count()


def _has_datasource(org):
    return DataSource.objects.filter(organization=org).exists()


def _survivor(orgs):
    """Pick the org to keep: most tournaments, then has a data source, then lowest pk."""
    return max(orgs, key=lambda o: (_tournament_count(o), _has_datasource(o), -o.pk))


class Command(BaseCommand):
    help = 'Merge duplicate state-federation Organizations into one canonical org per UF.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Commit the merge (default is a dry-run preview).')

    def handle(self, *args, **options):
        apply = options['apply']
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'=== dedupe_federation_orgs ({mode}) ===')

        groups = defaultdict(list)
        for org in Organization.objects.filter(type=Organization.TYPE_FEDERATION):
            uf = (org.state or '').upper()
            if uf:
                groups[uf].append(org)

        merged_total = 0
        for uf in sorted(groups):
            orgs = groups[uf]
            if len(orgs) < 2:
                continue
            survivor = _survivor(orgs)
            losers = [o for o in orgs if o.pk != survivor.pk]
            self.stdout.write(
                f'\n[{uf}] survivor: #{survivor.pk} "{survivor.name}" '
                f'(tournaments={_tournament_count(survivor)}, ds={_has_datasource(survivor)})'
            )
            for o in losers:
                self.stdout.write(
                    f'      merge  #{o.pk} "{o.name}" '
                    f'(tournaments={_tournament_count(o)}, profiles={PlayerProfile.objects.filter(federation=o).count()})'
                )

            if apply:
                with transaction.atomic():
                    for o in losers:
                        Tournament.objects.filter(organization=o).update(organization=survivor)
                        DataSource.objects.filter(organization=o).update(organization=survivor)
                        PlayerProfile.objects.filter(federation=o).update(federation=survivor)
                        o.delete()
                        merged_total += 1
                    # Rename survivor to canonical accented name (now collision-free).
                    canonical = _CANONICAL_NAME_BY_UF.get(uf)
                    if canonical and survivor.name != canonical and not (
                        Organization.objects.filter(name=canonical).exclude(pk=survivor.pk).exists()
                    ):
                        survivor.name = canonical
                        survivor.save(update_fields=['name'])

        if apply:
            self.stdout.write(self.style.SUCCESS(f'\nDone. {merged_total} duplicate org(s) merged.'))
        else:
            self.stdout.write('\nDry-run only. Re-run with --apply to commit.')
