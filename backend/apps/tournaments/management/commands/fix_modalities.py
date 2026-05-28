"""
Management command: fix_modalities

Re-classifies the modality field of all Tournament rows based on their
canonical_name and circuit using the shared modality inference utility.

This is a one-shot repair command for data already in the database.
Future ingestion runs will keep modalities up-to-date automatically via
the persistence layer fix.

Usage:
    python manage.py fix_modalities          # dry-run (default)
    python manage.py fix_modalities --apply  # save changes
    python manage.py fix_modalities --apply --slug cbt-beach-2025-123
"""
import logging

from django.core.management.base import BaseCommand

from apps.ingestion.modality_utils import infer_modality
from apps.tournaments.models import Tournament

logger = logging.getLogger(__name__)

# Minimum confidence: modality changes are only applied when the inferred
# value differs AND there is at least one strong keyword signal in the text.
_STRONG_BEACH_KW = frozenset({'beach', 'praia'})
_STRONG_WHEELCHAIR_KW = frozenset({'wheelchair', 'cadeira'})
_STRONG_PADEL_KW = frozenset({'padel', 'pádel'})


def _has_strong_signal(inferred: str, combined: str) -> bool:
    """Return True only when a strong keyword unambiguously signals the modality."""
    if inferred == 'beach_tennis':
        return any(kw in combined for kw in _STRONG_BEACH_KW)
    if inferred == 'wheelchair':
        return any(kw in combined for kw in _STRONG_WHEELCHAIR_KW)
    if inferred == 'padel':
        return any(kw in combined for kw in _STRONG_PADEL_KW)
    # 'tennis' is the fallback — only update if there are no ambiguous signals
    return inferred == 'tennis'


class Command(BaseCommand):
    help = 'Re-classify Tournament.modality from canonical_name + circuit using shared inference.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Write changes to the database (default: dry-run only).',
        )
        parser.add_argument(
            '--slug',
            type=str,
            default='',
            help='Restrict to a single tournament slug.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        slug_filter = options['slug']

        qs = Tournament.objects.all()
        if slug_filter:
            qs = qs.filter(canonical_slug=slug_filter)

        total = qs.count()
        self.stdout.write(f'Inspecting {total} tournament(s)  [apply={apply}]')

        changed = 0
        skipped = 0
        strong_only = 0

        for t in qs.prefetch_related('editions__venue').iterator(chunk_size=500):
            # Also inspect venue names from related editions so that tournaments
            # held at "Arena Guto Beach Tennis" are correctly classified even
            # when the title itself has no beach/praia keyword.
            venue_names = list({
                v for ed in t.editions.all()
                if ed.venue and ed.venue.name
                for v in [ed.venue.name]
            })
            venue_text = ' '.join(venue_names)
            combined = (t.canonical_name + ' ' + t.circuit + ' ' + venue_text).lower()
            inferred = infer_modality(t.canonical_name, t.circuit, venue_text)

            if inferred == t.modality:
                continue

            if not _has_strong_signal(inferred, combined):
                strong_only += 1
                logger.debug(
                    'Skipped %s: inferred=%s but no strong signal (combined=%r)',
                    t.canonical_slug, inferred, combined[:80],
                )
                continue

            self.stdout.write(
                f'  {"APPLY" if apply else "DRY"} {t.canonical_slug}: '
                f'{t.modality} -> {inferred}'
            )

            if apply:
                Tournament.objects.filter(pk=t.pk).update(modality=inferred)
                changed += 1
            else:
                changed += 1

        skipped = strong_only
        self.stdout.write(
            self.style.SUCCESS(
                f'Done. would_change={changed} skipped_no_strong_signal={skipped} '
                f'(total inspected={total}, apply={apply})'
            )
        )
        if not apply and changed:
            self.stdout.write(
                self.style.WARNING(
                    'Run with --apply to persist the changes.'
                )
            )
