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

    # Withdraw registrations for removed/cancelled entries
    withdrawn_count = 0
    removed_entries = [e for e in entries if e.removed_or_replaced]
    if removed_entries:
        from apps.watchlist.models import WatchlistItem
        for entry in removed_entries:
            for profile in profiles:
                ext_ids = profile.external_ids or {}
                if str(ext_ids.get(entry.source, '')) == str(entry.player_external_id):
                    # Withdraw TournamentRegistration
                    updated = TournamentRegistration.objects.filter(
                        edition=edition, profile=profile, is_withdrawn=False,
                    ).update(is_withdrawn=True)
                    if updated:
                        # Update WatchlistItem to withdrawn
                        WatchlistItem.objects.filter(
                            user_id=profile.user_id, edition=edition,
                        ).exclude(user_status='withdrawn').update(user_status='withdrawn')
                        withdrawn_count += 1
                        logger.info(
                            'match_federation_entries: withdrew profile=%s edition=%s entry=%s',
                            profile.id, edition_id, entry.player_external_id,
                        )

    logger.info(
        'match_federation_entries edition=%s: %d entries, %d registrations created, %d withdrawn',
        edition_id, len(entries), counter[0], withdrawn_count,
    )
    return {
        'edition_id': edition_id,
        'entries_processed': len(entries),
        'registrations_created': counter[0],
        'registrations_withdrawn': withdrawn_count,
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
                    category_text=category_text[:200],
                    source=FederationEntry.SOURCE_FPT,
                    defaults={
                        'player_name': player_name[:200],
                        'ranking_position': entry_data.get('ranking_position'),
                        'payment_status': raw_pay,
                        'removed_or_replaced': bool(entry_data.get('removed_or_replaced', False)),
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


def _sync_withdrawals(edition, db_source, source_key: str, log) -> int:
    """
    For all FederationEntries with removed_or_replaced=True for this edition+source,
    find linked TournamentRegistrations and mark them as withdrawn.
    Also updates WatchlistItem.user_status to 'withdrawn'.
    Returns count of registrations withdrawn.
    """
    from apps.watchlist.models import WatchlistItem

    removed_entries = FederationEntry.objects.filter(
        edition=edition,
        source=db_source,
        removed_or_replaced=True,
    ).values_list('player_external_id', flat=True)

    withdrawn_count = 0
    for ext_id in removed_entries:
        # Find TournamentRegistrations for profiles linked via external_id
        regs = TournamentRegistration.objects.filter(
            edition=edition,
            is_withdrawn=False,
            profile__external_ids__has_key=source_key,
        ).select_related('profile')

        for reg in regs:
            profile_ext = (reg.profile.external_ids or {}).get(source_key, '')
            if str(profile_ext) == str(ext_id):
                reg.is_withdrawn = True
                reg.save(update_fields=['is_withdrawn', 'updated_at'])
                # Update WatchlistItem status
                WatchlistItem.objects.filter(
                    user=reg.profile.user,
                    edition=edition,
                ).exclude(user_status='withdrawn').update(user_status='withdrawn')
                withdrawn_count += 1
                log.info(
                    'sync_withdrawals: retirado profile=%s edition=%s ext_id=%s',
                    reg.profile_id, edition.id, ext_id,
                )

    return withdrawn_count


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_cbt_fct_entries_task(self, sources=None, limit: int = 500):
    """
    Sync CBT and FCT tournament entries via TenisIntegrado torneio_painel_insc.

    Same mechanism used for tournament 278 (GA/GA+ Brasileirao):
      1. fetch_tenisintegrado_entries(torneio_painel_insc/index/{tid})
      2. upsert FederationEntry records
      3. mark stale entries as removed_or_replaced
      4. dispatch match_federation_entries.delay() per edition
    """
    import re as _re
    import unicodedata as _ud
    from django.utils import timezone as _tz
    from apps.registrations.parsers import fetch_tenisintegrado_entries
    from apps.tournaments.models import TournamentEdition

    log = logging.getLogger('apps.registrations.sync_cbt_fct')

    if sources is None:
        sources = ['cbt', 'fct']

    _TI_INSC = 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/{tid}'
    _SOURCE_DB = {'cbt': FederationEntry.SOURCE_CBT, 'fct': FederationEntry.SOURCE_FCT}
    _VALID_PAY = {FederationEntry.PAYMENT_PAID, FederationEntry.PAYMENT_PENDING, FederationEntry.PAYMENT_UNKNOWN}
    _SKIP_STATUSES = [TournamentEdition.STATUS_CANCELED, TournamentEdition.STATUS_FINISHED]

    def _slug(t):
        s = _ud.normalize('NFKD', t).encode('ascii', 'ignore').decode()
        return _re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]

    def _extract_tid(edition):
        m = _re.match(r'(?:cbt|fct|fmt):(\d+)', edition.external_id or '')
        if m:
            return m.group(1)
        src = edition.official_source_url or ''
        m = _re.search(r'/(?:torneio_painel_insc|torneio_painel_info|torneio)/(?:index/)?(\d+)', src)
        if m:
            return m.group(1)
        m = _re.search(r'/(\d{4,})/?$', src)
        return m.group(1) if m else None

    task_start = _tz.now()
    summary = {
        'started_at': task_start.isoformat(),
        'sources': sources,
        'editions_processed': 0,
        'editions_skipped': 0,
        'editions_error': 0,
        'created_total': 0,
        'updated_total': 0,
        'stale_marked': 0,
        'matching_dispatched': 0,
        'details': [],
    }

    for src in sources:
        qs = list(
            TournamentEdition.objects
            .filter(external_id__startswith=f'{src}:')
            .exclude(status__in=_SKIP_STATUSES)
            .select_related('tournament')
            .order_by('entry_close_at', 'start_date')
        )[:limit]

        log.info('sync_cbt_fct [%s] editions to process: %d', src.upper(), len(qs))

        for edition in qs:
            ed_log = {'edition_id': edition.id, 'title': edition.title[:60], 'source': src}

            tid = _extract_tid(edition)
            if not tid:
                ed_log['result'] = 'no_tid'
                summary['editions_skipped'] += 1
                summary['details'].append(ed_log)
                log.debug('sync_cbt_fct skip edition=%s no TI id', edition.id)
                continue

            insc_url = _TI_INSC.format(tid=tid)
            ed_log['url'] = insc_url

            try:
                result = fetch_tenisintegrado_entries(insc_url, source=src)
            except Exception as exc:
                ed_log['result'] = 'fetch_error'
                ed_log['error'] = str(exc)[:200]
                summary['editions_error'] += 1
                summary['details'].append(ed_log)
                log.warning('sync_cbt_fct fetch_error edition=%s: %s', edition.id, exc)
                continue

            entries = result.get('entries', [])
            if not entries:
                ed_log['result'] = 'no_entries'
                ed_log['warning'] = result.get('warning_message', '')[:200]
                summary['editions_skipped'] += 1
                summary['details'].append(ed_log)
                log.debug('sync_cbt_fct no_entries edition=%s warning=%s', edition.id, result.get('warning_message', ''))
                continue

            db_source = _SOURCE_DB[src]
            now = _tz.now()
            created_ed = updated_ed = error_ed = 0
            saved_eids = set()

            for entry_data in entries:
                player_name = (entry_data.get('player_name') or '').strip()
                category_text = (entry_data.get('category_text') or '').strip()
                if not player_name or not category_text:
                    continue

                raw_eid = (entry_data.get('player_external_id') or '').strip()
                external_id = raw_eid or f'{src}:{_slug(player_name)}:{_slug(category_text)}'
                saved_eids.add(external_id)

                raw_pay = (entry_data.get('payment_status') or FederationEntry.PAYMENT_UNKNOWN).strip()
                if raw_pay not in _VALID_PAY:
                    raw_pay = FederationEntry.PAYMENT_UNKNOWN

                try:
                    _, created = FederationEntry.objects.update_or_create(
                        edition=edition,
                        player_external_id=external_id,
                        category_text=category_text[:200],
                        source=db_source,
                        defaults={
                            'player_name': player_name[:200],
                            'ranking_position': entry_data.get('ranking_position'),
                            'payment_status': raw_pay,
                            'removed_or_replaced': bool(entry_data.get('removed_or_replaced', False)),
                            'replacement_reason': (entry_data.get('replacement_reason') or '')[:500],
                            'source_url': insc_url[:500],
                            'confidence': FederationEntry.CONFIDENCE_HIGH,
                            'synced_at': now,
                        },
                    )
                    if created:
                        created_ed += 1
                    else:
                        updated_ed += 1
                except Exception as exc:
                    error_ed += 1
                    log.warning('sync_cbt_fct upsert_error edition=%s eid=%s: %s', edition.id, external_id, exc)

            # Mark stale entries (in DB but not in current fetch) as removed_or_replaced
            stale = (
                FederationEntry.objects
                .filter(edition=edition, source=db_source, removed_or_replaced=False)
                .exclude(player_external_id__in=saved_eids)
                .update(removed_or_replaced=True, replacement_reason='Não encontrado na última sincronização automática')
            )

            # Withdraw TournamentRegistrations for cancelled/removed entries
            _sync_withdrawals(edition, db_source, src, log)

            summary['created_total'] += created_ed
            summary['updated_total'] += updated_ed
            summary['stale_marked'] += stale
            summary['editions_processed'] += 1

            ed_log.update({
                'result': 'ok',
                'entries': len(entries),
                'created': created_ed,
                'updated': updated_ed,
                'stale_marked': stale,
                'errors': error_ed,
            })
            summary['details'].append(ed_log)
            log.info(
                'sync_cbt_fct edition=%s [%s] entries=%d created=%d updated=%d stale=%d',
                edition.id, src.upper(), len(entries), created_ed, updated_ed, stale,
            )

            # Dispatch matching — same as what worked for edition 278
            if created_ed + updated_ed > 0:
                try:
                    match_federation_entries.delay(edition.id)
                    summary['matching_dispatched'] += 1
                except Exception as exc:
                    log.warning('sync_cbt_fct match_dispatch_error edition=%s: %s', edition.id, exc)

    summary['finished_at'] = _tz.now().isoformat()
    summary['duration_s'] = round((_tz.now() - task_start).total_seconds(), 1)
    log.info(
        'sync_cbt_fct DONE | editions=%d skipped=%d errors=%d created=%d updated=%d stale=%d matching=%d | %.1fs',
        summary['editions_processed'], summary['editions_skipped'], summary['editions_error'],
        summary['created_total'], summary['updated_total'], summary['stale_marked'],
        summary['matching_dispatched'], summary['duration_s'],
    )
    return summary
