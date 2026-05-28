import logging
import unicodedata
from difflib import SequenceMatcher

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import FederationEntry, MatchingLog, TournamentRegistration

logger = logging.getLogger('apps.registrations')


def _normalize(text: str) -> str:
    """Lowercase and strip accents for fuzzy name comparison."""
    normalized = unicodedata.normalize('NFKD', text)
    return normalized.encode('ascii', 'ignore').decode('ascii').lower().strip()


def _ensure_watchlist(user_id: int, edition) -> None:
    """Create a WatchlistItem(registered_declared) for user+edition if one does not exist."""
    from apps.watchlist.models import WatchlistItem
    WatchlistItem.objects.get_or_create(
        user_id=user_id,
        edition=edition,
        defaults={'user_status': 'registered_declared'},
    )


def _do_match(entries, profiles, edition, registrations_created_ref: list) -> list:
    """
    Core matching loop shared by both tasks.

    Returns list of MatchingLog instances (not yet saved).
    registrations_created_ref is a 1-element list used as a mutable counter.
    """
    logs_to_create = []

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
                        registrations_created_ref[0] += 1

                        # Persist external_id for fast future exact matching
                        if method == MatchingLog.METHOD_NAME_FUZZY and entry.player_external_id:
                            ext_ids = dict(matched_profile.external_ids or {})
                            ext_ids[entry.source] = entry.player_external_id
                            matched_profile.external_ids = ext_ids
                            matched_profile.save(update_fields=['external_ids'])

                        # Guarantee the tournament appears in the user's agenda
                        _ensure_watchlist(matched_profile.user_id, edition)

                except Exception as exc:
                    logger.warning(
                        '_do_match: failed to create registration for profile=%s entry=%s: %s',
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

    return logs_to_create


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def match_federation_entries(self, edition_id: int) -> dict:
    """
    Eixo 1 — Torneio → Usuários.

    Triggered by n8n after bulk-import via POST /api/registrations/match/<edition_id>/.
    Matches ALL FederationEntries for an edition against ALL PlayerProfiles in the DB.

    On a confirmed match:
      - Creates TournamentRegistration (skips if already exists).
      - Creates WatchlistItem(registered_declared) so the tournament pops up on
        the user's agenda automatically.
      - Persists player_external_id into profile.external_ids for future fast matching.
    """
    from apps.players.models import PlayerProfile
    from apps.tournaments.models import TournamentEdition

    try:
        edition = TournamentEdition.objects.get(pk=edition_id)
    except TournamentEdition.DoesNotExist:
        logger.error('match_federation_entries: edition %s not found', edition_id)
        return {'error': f'Edition {edition_id} not found'}

    entries = list(FederationEntry.objects.filter(edition=edition))
    if not entries:
        logger.info('match_federation_entries: no entries for edition %s', edition_id)
        return {'edition_id': edition_id, 'entries_processed': 0, 'registrations_created': 0}

    # Match against ALL profiles in the platform (universal discovery)
    profiles = list(PlayerProfile.objects.all().only('id', 'user_id', 'display_name', 'external_ids'))
    if not profiles:
        return {
            'edition_id': edition_id,
            'entries_processed': len(entries),
            'registrations_created': 0,
            'note': 'No profiles in database',
        }

    counter = [0]
    logs = _do_match(entries, profiles, edition, counter)
    MatchingLog.objects.bulk_create(logs)

    logger.info(
        'match_federation_entries edition=%s: %d entries, %d registrations created',
        edition_id, len(entries), counter[0],
    )
    return {
        'edition_id': edition_id,
        'entries_processed': len(entries),
        'registrations_created': counter[0],
        'logs_created': len(logs),
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def match_new_profile_to_entries(self, profile_id: int) -> dict:
    """
    Eixo 2 — Novo Perfil → Torneios Existentes (viagem no tempo).

    Triggered immediately after a new PlayerProfile is created (player onboarding
    or parent creating a dependent profile).

    Searches ALL FederationEntries from editions that have not yet finished
    (end_date >= today or end_date is null) for matches with the new profile.

    On a confirmed match:
      - Creates TournamentRegistration.
      - Creates WatchlistItem so the tournament appears on the agenda instantly.
    """
    from apps.players.models import PlayerProfile
    from apps.tournaments.models import TournamentEdition

    try:
        profile = PlayerProfile.objects.get(pk=profile_id)
    except PlayerProfile.DoesNotExist:
        logger.error('match_new_profile_to_entries: profile %s not found', profile_id)
        return {'error': f'Profile {profile_id} not found'}

    today = timezone.now().date()
    # Editions still active or with unknown end date
    active_edition_ids = list(
        TournamentEdition.objects
        .filter(
            models_end_date_filter(today)
        )
        .values_list('id', flat=True)
    )

    entries = list(
        FederationEntry.objects
        .filter(edition_id__in=active_edition_ids)
        .select_related('edition')
    )

    if not entries:
        return {
            'profile_id': profile_id,
            'entries_scanned': 0,
            'registrations_created': 0,
        }

    # Group entries by edition to reuse _do_match per edition
    from itertools import groupby
    entries_sorted = sorted(entries, key=lambda e: e.edition_id)
    counter = [0]
    all_logs = []

    for edition_id, edition_entries in groupby(entries_sorted, key=lambda e: e.edition_id):
        edition_entries_list = list(edition_entries)
        edition = edition_entries_list[0].edition
        logs = _do_match(edition_entries_list, [profile], edition, counter)
        all_logs.extend(logs)

    if all_logs:
        MatchingLog.objects.bulk_create(all_logs)

    logger.info(
        'match_new_profile_to_entries profile=%s: %d entries scanned, %d registrations created',
        profile_id, len(entries), counter[0],
    )
    return {
        'profile_id': profile_id,
        'entries_scanned': len(entries),
        'registrations_created': counter[0],
        'logs_created': len(all_logs),
    }


def models_end_date_filter(today):
    """Return a Q filter for editions that are still active or have no end date."""
    from django.db.models import Q
    return Q(end_date__gte=today) | Q(end_date__isnull=True)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_fpt_sp_entries_task(self, limit: int = 50):
    """Sync FPT (SP) tournament inscritos from fpt.tenisintegrado.com.br."""
    import unicodedata as _ud
    import re as _re
    from django.utils import timezone as _tz
    from apps.registrations.parsers import fetch_tenisintegrado_entries
    from apps.tournaments.models import TournamentEdition
    from apps.sources.models import Organization

    log = logging.getLogger('apps.registrations.sync_fpt_sp')

    fpt_sp = Organization.objects.filter(short_name='FPT', state='SP').first()
    if not fpt_sp:
        log.error('FPT (SP) org not found')
        return {'error': 'org_not_found'}

    qs = (
        TournamentEdition.objects
        .filter(tournament__organization=fpt_sp, official_source_url__icontains='tenisintegrado')
        .exclude(status__in=[TournamentEdition.STATUS_CANCELED, TournamentEdition.STATUS_FINISHED])
        .select_related('tournament')
        .order_by('entry_close_at', 'start_date')
    )[:limit]

    def _slug(t):
        s = _ud.normalize('NFKD', t).encode('ascii', 'ignore').decode()
        return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]

    created_total = updated_total = skipped_total = 0
    now = _tz.now()

    for edition in qs:
        try:
            result = fetch_tenisintegrado_entries(edition.official_source_url, source='fpt')
        except Exception as exc:
            log.warning('sync_fpt_sp fetch failed edition=%s: %s', edition.id, exc)
            skipped_total += 1
            continue

        entries = result.get('entries', [])
        if not entries or result.get('parser_warning'):
            skipped_total += 1
            continue

        for entry_data in entries:
            player_name = (entry_data.get('player_name') or '').strip()
            category_text = (entry_data.get('category_text') or '').strip()
            if not player_name or not category_text:
                continue

            raw_eid = (entry_data.get('player_external_id') or '').strip()
            external_id = raw_eid or f'fpt:{_slug(player_name)}:{_slug(category_text)}'

            raw_pay = (entry_data.get('payment_status') or FederationEntry.PAYMENT_UNKNOWN).strip()
            if raw_pay not in {FederationEntry.PAYMENT_PAID, FederationEntry.PAYMENT_PENDING, FederationEntry.PAYMENT_UNKNOWN}:
                raw_pay = FederationEntry.PAYMENT_UNKNOWN

            try:
                _, created = FederationEntry.objects.update_or_create(
                    edition=edition,
                    player_external_id=external_id,
                    defaults={
                        'player_name': player_name[:200],
                        'category_text': category_text[:200],
                        'ranking_position': entry_data.get('ranking_position'),
                        'payment_status': raw_pay,
                        'removed_or_replaced': bool(entry_data.get('removed_or_replaced', False)),
                        'source': FederationEntry.SOURCE_FPT,
                        'source_url': (entry_data.get('source_url') or edition.official_source_url)[:500],
                        'confidence': FederationEntry.CONFIDENCE_HIGH,
                        'synced_at': now,
                    },
                )
                if created:
                    created_total += 1
                else:
                    updated_total += 1
            except Exception as exc:
                log.warning('sync_fpt_sp upsert failed: %s', exc)

    log.info('sync_fpt_sp done: created=%s updated=%s skipped=%s', created_total, updated_total, skipped_total)
    return {'created': created_total, 'updated': updated_total, 'skipped': skipped_total}
