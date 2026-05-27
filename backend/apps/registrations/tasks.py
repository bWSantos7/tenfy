import logging
import unicodedata
from difflib import SequenceMatcher

from celery import shared_task
from django.db import transaction

from .models import FederationEntry, MatchingLog, TournamentRegistration

logger = logging.getLogger('apps.registrations')


def _normalize(text: str) -> str:
    """Lowercase and strip accents for fuzzy name comparison."""
    normalized = unicodedata.normalize('NFKD', text)
    return normalized.encode('ascii', 'ignore').decode('ascii').lower().strip()


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def match_federation_entries(self, edition_id: int) -> dict:
    """
    Zero-click auto-discovery: match FederationEntries against PlayerProfiles
    of users who added the tournament to their watchlist.

    Match strategy (in order):
      1. Exact match via profile.external_ids[source] == entry.player_external_id
      2. Fuzzy name match using SequenceMatcher; threshold > 0.95

    On a confirmed match:
      - Creates a TournamentRegistration (skips if one already exists).
      - Persists player_external_id into profile.external_ids so future
        matches use the faster exact-ID path.

    Called by n8n immediately after bulk-import completes via
    POST /api/registrations/match/<edition_id>/
    """
    from apps.players.models import PlayerProfile
    from apps.tournaments.models import TournamentEdition
    from apps.watchlist.models import WatchlistItem

    try:
        edition = TournamentEdition.objects.get(pk=edition_id)
    except TournamentEdition.DoesNotExist:
        logger.error('match_federation_entries: edition %s not found', edition_id)
        return {'error': f'Edition {edition_id} not found'}

    entries = list(FederationEntry.objects.filter(edition=edition))
    if not entries:
        logger.info('match_federation_entries: no entries for edition %s', edition_id)
        return {'edition_id': edition_id, 'entries_processed': 0, 'registrations_created': 0}

    # Only consider profiles of users who expressed intent via watchlist, plus their dependents
    watcher_user_ids = list(
        WatchlistItem.objects
        .filter(edition=edition)
        .values_list('user_id', flat=True)
        .distinct()
    )
    if not watcher_user_ids:
        logger.info('match_federation_entries: no watchers for edition %s', edition_id)
        return {
            'edition_id': edition_id,
            'entries_processed': len(entries),
            'registrations_created': 0,
            'note': 'No watchers',
        }

    from apps.accounts.models import ParentChild
    children_user_ids = list(
        ParentChild.objects
        .filter(parent_id__in=watcher_user_ids)
        .values_list('child_id', flat=True)
    )
    all_target_user_ids = set(watcher_user_ids + children_user_ids)

    profiles = list(PlayerProfile.objects.filter(user_id__in=all_target_user_ids))
    if not profiles:
        return {
            'edition_id': edition_id,
            'entries_processed': len(entries),
            'registrations_created': 0,
            'note': 'No profiles found for watchers',
        }

    logs_to_create = []
    registrations_created = 0

    for entry in entries:
        matched_profile = None
        method = MatchingLog.METHOD_NONE
        score = None
        confidence = MatchingLog.CONFIDENCE_NONE

        # ── Step 1: exact ID match ────────────────────────────────────────────
        if entry.player_external_id:
            for profile in profiles:
                ext_ids = profile.external_ids or {}
                if str(ext_ids.get(entry.source, '')) == entry.player_external_id:
                    matched_profile = profile
                    method = MatchingLog.METHOD_EXTERNAL_ID
                    score = 1.0
                    confidence = MatchingLog.CONFIDENCE_HIGH
                    break

        # ── Step 2: fuzzy name match ─────────────────────────────────────────
        if not matched_profile and entry.player_name:
            entry_norm = _normalize(entry.player_name)
            best_score = 0.0
            best_profile = None
            for profile in profiles:
                if not profile.display_name:
                    continue
                ratio = SequenceMatcher(None, entry_norm, _normalize(profile.display_name)).ratio()
                if ratio > best_score:
                    best_score = ratio
                    best_profile = profile

            if best_score > 0.95 and best_profile:
                matched_profile = best_profile
                method = MatchingLog.METHOD_NAME_FUZZY
                score = best_score
                confidence = MatchingLog.CONFIDENCE_MEDIUM

        # ── Act on a confirmed match ──────────────────────────────────────────
        reg_created = False
        if matched_profile:
            already_registered = TournamentRegistration.objects.filter(
                profile=matched_profile,
                edition=edition,
                is_withdrawn=False,
            ).exists()

            if not already_registered:
                try:
                    with transaction.atomic():
                        TournamentRegistration.objects.create(
                            profile=matched_profile,
                            edition=edition,
                            category=None,
                            payment_status=(
                                TournamentRegistration.PAYMENT_PAID
                                if entry.payment_status == FederationEntry.PAYMENT_PAID
                                else TournamentRegistration.PAYMENT_PENDING
                            ),
                            ranking_position=entry.ranking_position,
                            notes=(
                                f'Auto-matched via {method}'
                                + (f' (score={score:.3f})' if score is not None else '')
                            ),
                        )
                        reg_created = True
                        registrations_created += 1

                        # "The secret sauce": persist external_id for fast future matching
                        if method == MatchingLog.METHOD_NAME_FUZZY and entry.player_external_id:
                            ext_ids = dict(matched_profile.external_ids or {})
                            ext_ids[entry.source] = entry.player_external_id
                            matched_profile.external_ids = ext_ids
                            matched_profile.save(update_fields=['external_ids'])

                except Exception as exc:
                    logger.warning(
                        'match_federation_entries: failed to create registration '
                        'for profile=%s entry=%s: %s',
                        matched_profile.pk, entry.pk, exc,
                    )

        logs_to_create.append(MatchingLog(
            entry=entry,
            profile=matched_profile,
            confidence=confidence,
            method=method,
            score=score,
            registration_created=reg_created,
        ))

    MatchingLog.objects.bulk_create(logs_to_create)

    logger.info(
        'match_federation_entries edition=%s: %d entries, %d registrations created',
        edition_id, len(entries), registrations_created,
    )
    return {
        'edition_id': edition_id,
        'entries_processed': len(entries),
        'registrations_created': registrations_created,
        'logs_created': len(logs_to_create),
    }
