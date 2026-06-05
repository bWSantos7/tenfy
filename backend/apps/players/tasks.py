import logging
import re
import unicodedata
from difflib import SequenceMatcher

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.players')

# Delay (seconds) between consecutive per-profile sync tasks to avoid
# hammering tenisintegrado.com.br with concurrent requests.
_TI_STAGGER_SECONDS = 20
_TI_SOURCES = ('cbt', 'fpt', 'fbt', 'fct')


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    return normalized.encode('ascii', 'ignore').decode('ascii').lower().strip()


def _extract_numeric_ti_external_id(value: str) -> str | None:
    s = str(value or '').strip()
    match = re.match(r'^tenisintegrado:(\d+)$', s) or re.match(r'^(\d+)$', s)
    return match.group(1) if match else None


def _find_ti_id_in_rankings(profile_name: str) -> tuple[str | None, str | None]:
    """
    Resolve a TI id from the imported ranking catalogue (ExternalPlayerRanking).

    This is the higher-coverage source (every ranked athlete, not only those who
    appeared in an imported entry list). Returns (source, 'tenisintegrado:{id}')
    only for a *unique* high-confidence name match; ambiguous matches (more than
    one distinct TI id) are rejected so we never auto-link the wrong athlete.
    """
    from .models import ExternalPlayerRanking

    if not profile_name:
        return None, None

    # Exact normalized-name match first (cheap, indexed).
    rows = list(
        ExternalPlayerRanking.objects
        .filter(player_name_normalized=profile_name)
        .values('ti_player_id', 'source')
        .distinct()
    )

    # Token-subset match: the Tenfy profile often holds a shorter name than the
    # federation record (e.g. "Laura Saviole" vs "Laura Saviole Silva"). Accept it
    # when every token of the profile name is present in the catalogue name, with
    # at least two tokens (avoids matching on a lone first name) and a unique id.
    if not rows:
        profile_tokens = set(profile_name.split())
        if len(profile_tokens) >= 2:
            pivot = max(profile_tokens, key=len)  # most distinctive token, for a cheap DB prefilter
            cand_ids: dict[str, str] = {}
            for r in (
                ExternalPlayerRanking.objects
                .filter(player_name_normalized__contains=pivot)
                .values('ti_player_id', 'source', 'player_name_normalized')
                .distinct()[:5000]
            ):
                if profile_tokens <= set(r['player_name_normalized'].split()):
                    cand_ids[r['ti_player_id']] = r['source']
            rows = [{'ti_player_id': tid, 'source': src} for tid, src in cand_ids.items()]

    # Fall back to fuzzy scan only when still no hit (bounded for safety).
    if not rows:
        candidates: dict[tuple[str, str], float] = {}
        for r in (
            ExternalPlayerRanking.objects
            .exclude(player_name_normalized='')
            .values('ti_player_id', 'source', 'player_name_normalized')
            .distinct()[:5000]
        ):
            score = SequenceMatcher(None, r['player_name_normalized'], profile_name).ratio()
            if score >= 0.985:
                candidates[(r['source'], r['ti_player_id'])] = score
        rows = [{'ti_player_id': tid, 'source': src} for (src, tid) in candidates]

    unique_ids = {r['ti_player_id'] for r in rows}
    if len(unique_ids) != 1:
        if unique_ids:
            logger.info('TI ranking match ambiguous for name=%r: ids=%s', profile_name, sorted(unique_ids))
        return None, None

    row = rows[0]
    return row['source'], f'tenisintegrado:{row["ti_player_id"]}'


def _find_ti_external_id_for_profile(profile) -> tuple[str | None, str | None]:
    """
    Resolve a TI id for a profile, preferring the ranking catalogue and falling
    back to imported federation entry lists.

    The public TI profile pages are keyed by a numeric id; both sources carry
    that id. We only accept a unique exact/high-confidence name match to avoid
    linking two different athletes with the same name.
    """
    from apps.registrations.models import FederationEntry

    profile_name = _normalize_name(profile.display_name)
    if not profile_name:
        return None, None

    # 1. Ranking catalogue (broadest coverage).
    source, external_id = _find_ti_id_in_rankings(profile_name)
    if external_id:
        return source, external_id

    entries = (
        FederationEntry.objects
        .filter(source__in=_TI_SOURCES)
        .exclude(player_external_id='')
        .only('player_name', 'player_external_id', 'source', 'created_at')
        .order_by('-created_at')
    )

    candidates: dict[tuple[str, str], float] = {}
    for entry in entries:
        ti_id = _extract_numeric_ti_external_id(entry.player_external_id)
        if not ti_id:
            continue

        entry_name = _normalize_name(entry.player_name)
        if not entry_name:
            continue

        score = 1.0 if entry_name == profile_name else SequenceMatcher(None, entry_name, profile_name).ratio()
        if score < 0.985:
            continue

        key = (entry.source, f'tenisintegrado:{ti_id}')
        candidates[key] = max(score, candidates.get(key, 0.0))

    if not candidates:
        return None, None

    unique_external_ids = {external_id for _, external_id in candidates}
    if len(unique_external_ids) != 1:
        logger.info(
            'TI bootstrap skipped profile=%s name=%r: ambiguous TI ids=%s',
            profile.pk, profile.display_name, sorted(unique_external_ids),
        )
        return None, None

    source, external_id = max(candidates.items(), key=lambda item: item[1])[0]
    return source, external_id


@shared_task(name='apps.players.tasks.bootstrap_ti_profile_task', bind=True, max_retries=1, default_retry_delay=60)
def bootstrap_ti_profile_task(self, profile_id: int):
    """
    Resolve a Tênis Integrado id for a new profile and enqueue the data sync.

    This runs for every new PlayerProfile, including parent-created dependents.
    If the profile already has a TI id, we skip resolution and only enqueue the
    cache refresh.
    """
    from .models import PlayerProfile
    from .parsers import extract_ti_id

    try:
        profile = PlayerProfile.objects.get(pk=profile_id)
    except PlayerProfile.DoesNotExist:
        logger.warning('bootstrap_ti_profile_task: profile %s not found', profile_id)
        return {'profile_id': profile_id, 'status': 'not_found'}

    ti_id, source = extract_ti_id(profile.external_ids or {})
    resolved = False

    if not ti_id:
        source, external_id = _find_ti_external_id_for_profile(profile)
        if not external_id:
            logger.info('bootstrap_ti_profile_task: no TI id resolved for profile=%s', profile_id)
            return {'profile_id': profile_id, 'status': 'no_ti_id'}

        ext_ids = dict(profile.external_ids or {})
        ext_ids[source] = external_id
        profile.external_ids = ext_ids
        profile.save(update_fields=['external_ids', 'updated_at'])
        ti_id, _ = extract_ti_id(profile.external_ids or {})
        resolved = True
        logger.info(
            'bootstrap_ti_profile_task: resolved profile=%s source=%s external_id=%s',
            profile_id, source, external_id,
        )

    if ti_id:
        sync_ti_data_task.apply_async(args=[profile_id], countdown=5 if resolved else 0)
        return {'profile_id': profile_id, 'status': 'queued_sync', 'ti_id': ti_id, 'resolved': resolved}

    return {'profile_id': profile_id, 'status': 'no_ti_id'}


@shared_task(name='apps.players.tasks.sync_ti_data_task', bind=True, max_retries=2, default_retry_delay=120)
def sync_ti_data_task(self, profile_id: int):
    """Background task: refresh TI results & rankings cache for a player profile."""
    from .models import PlayerProfile
    from .parsers import extract_ti_id
    from .views import _sync_ti_data_inline

    try:
        profile = PlayerProfile.objects.get(pk=profile_id)
    except PlayerProfile.DoesNotExist:
        logger.warning('sync_ti_data_task: profile %s not found', profile_id)
        return

    ti_id, _ = extract_ti_id(profile.external_ids or {})
    if not ti_id:
        return

    logger.info('sync_ti_data_task: syncing profile=%s ti_id=%s', profile_id, ti_id)
    try:
        _sync_ti_data_inline(profile, ti_id)
        logger.info('sync_ti_data_task: done profile=%s results=%d rankings=%d',
                    profile_id, len(profile.ti_results_cache or []), len(profile.ti_rankings_cache or []))
    except Exception as exc:
        logger.error('sync_ti_data_task: unexpected error profile=%s: %s', profile_id, exc)
        raise self.retry(exc=exc)


@shared_task(name='apps.players.tasks.sync_all_ti_profiles_task')
def sync_all_ti_profiles_task():
    """
    Periodic task: enqueue a sync_ti_data_task for every player profile that
    has a Tênis Integrado ID.  Tasks are staggered by _TI_STAGGER_SECONDS to
    avoid sending a burst of HTTP requests to tenisintegrado.com.br.

    Scheduled hourly via Celery Beat (ratings, partidas, ranking, inscrições).
    """
    from .models import PlayerProfile
    from .parsers import extract_ti_id

    profiles = PlayerProfile.objects.exclude(external_ids={}).only(
        'id', 'external_ids', 'display_name',
    )

    dispatched = 0
    for i, profile in enumerate(profiles):
        ti_id, _ = extract_ti_id(profile.external_ids or {})
        if not ti_id:
            continue
        countdown = i * _TI_STAGGER_SECONDS
        sync_ti_data_task.apply_async(args=[profile.pk], countdown=countdown)
        dispatched += 1

    logger.info('sync_all_ti_profiles_task: dispatched %d profile sync(s)', dispatched)


@shared_task(name='apps.players.tasks.sync_ti_rankings_task')
def sync_ti_rankings_task(sources=None, include_federations=True):
    """
    Periodic task: import public Tênis Integrado rankings into the local
    ExternalPlayerRanking catalogue, then backfill profile auto-links.

    Imports both:
      * configured registry sources (--all → CBT Ranking Nacional Juvenil), and
      * federation infantojuvenil/juvenil/juniors rankings (12–18 categories),
        unless a specific `sources` list is given or include_federations is False.

    Scheduled daily. Heavy/rate-limited work runs inside the management command,
    which already throttles its own HTTP requests. Each phase is isolated so a
    failure in one does not abort the others.
    """
    from django.core.management import call_command

    errors = []

    try:
        if sources:
            for src in sources:
                call_command('sync_ti_rankings', source=src, verbosity=0)
        else:
            call_command('sync_ti_rankings', all=True, verbosity=0)
    except Exception as exc:
        logger.error('sync_ti_rankings_task: registry import error: %s', exc)
        errors.append(f'registry: {exc}')

    # Federation rankings (FPT/SP, FCT, …) are not in the registry — they are
    # discovered live and filtered to youth (12–18) categories.
    if include_federations and not sources:
        try:
            call_command('sync_ti_rankings', federations_juvenil=True, verbosity=0)
        except Exception as exc:
            logger.error('sync_ti_rankings_task: federations import error: %s', exc)
            errors.append(f'federations: {exc}')

    # After importing, try to link any still-unlinked profiles (no re-sync here;
    # the hourly sync_all_ti_profiles_task will pick up newly-linked profiles).
    try:
        call_command('match_profiles_to_ti_rankings', no_sync=True, verbosity=0)
    except Exception as exc:
        logger.warning('sync_ti_rankings_task: backfill matching error: %s', exc)

    return {'status': 'done' if not errors else 'partial', 'errors': errors}


_UTR_STAGGER_SECONDS = 30
# Only re-scrape a profile whose UTR is older than this — avoids unnecessary
# external (Playwright) calls when an hourly run finds recently-synced profiles.
_UTR_REFRESH_MIN_AGE_MINUTES = 55


@shared_task(name='apps.players.tasks.sync_all_utr_profiles_task')
def sync_all_utr_profiles_task():
    """
    Periodic task (hourly): refresh the UTR rating for every player profile that
    has a confirmed UTR id and whose rating is stale (older than
    _UTR_REFRESH_MIN_AGE_MINUTES) or never synced. Tasks are staggered to avoid a
    burst of headless-browser scrapes.

    Relevance gate (utr_player_id set) + staleness gate keep external calls down,
    per the "evitar chamadas externas desnecessárias" requirement.
    """
    from datetime import timedelta
    from django.db.models import Q
    from .models import PlayerProfile

    cutoff = timezone.now() - timedelta(minutes=_UTR_REFRESH_MIN_AGE_MINUTES)
    profiles = (
        PlayerProfile.objects
        .exclude(utr_player_id='')
        .filter(Q(utr_synced_at__isnull=True) | Q(utr_synced_at__lte=cutoff))
        .only('id', 'utr_player_id', 'utr_synced_at')
    )

    dispatched = 0
    for i, profile in enumerate(profiles):
        extract_utr_rating_task.apply_async(args=[profile.pk], countdown=i * _UTR_STAGGER_SECONDS)
        dispatched += 1

    logger.info('sync_all_utr_profiles_task: dispatched %d UTR sync(s)', dispatched)
    return dispatched


@shared_task(
    name='apps.players.tasks.extract_utr_rating_task',
    bind=True, max_retries=1, default_retry_delay=60,
    time_limit=120, soft_time_limit=100,
)
def extract_utr_rating_task(self, profile_id: int):
    """
    Background task: open the confirmed UTR profile in a headless browser and
    extract the actual rating from the rendered DOM.

    Requires Playwright + Chromium on the worker:
      pip install playwright
      playwright install chromium

    Called automatically after utr-link; also triggered by utr-sync.
    """
    from .models import PlayerProfile
    from .utr_service import scrape_utr_profile_rating

    try:
        profile = PlayerProfile.objects.get(pk=profile_id)
    except PlayerProfile.DoesNotExist:
        logger.warning('extract_utr_rating_task: profile %s not found', profile_id)
        return

    if not profile.utr_player_id:
        logger.info('extract_utr_rating_task: profile %s has no utr_player_id', profile_id)
        return

    logger.info('extract_utr_rating_task: scraping profile=%s utr_id=%s', profile_id, profile.utr_player_id)

    try:
        result = scrape_utr_profile_rating(
            player_id=profile.utr_player_id,
            player_name=profile.utr_display_name or profile.display_name,
        )
    except Exception as exc:
        logger.error('extract_utr_rating_task: scrape error profile=%s: %s', profile_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            profile.utr_sync_error = f'Scrape falhou: {exc}'[:300]
            profile.save(update_fields=['utr_sync_error', 'updated_at'])
        return

    now = timezone.now()
    if result['success']:
        if result.get('singles_utr'):
            profile.utr_singles = result['singles_utr']
        if result.get('doubles_utr'):
            profile.utr_doubles = result['doubles_utr']
        if result.get('display_name'):
            profile.utr_display_name = result['display_name']
        profile.utr_synced_at  = now
        profile.utr_sync_error = ''
        logger.info(
            'extract_utr_rating_task: done profile=%s singles=%s doubles=%s',
            profile_id, profile.utr_singles, profile.utr_doubles,
        )
    else:
        profile.utr_synced_at  = now
        profile.utr_sync_error = result.get('error', 'Extração falhou')[:300]
        logger.warning('extract_utr_rating_task: no rating found profile=%s: %s', profile_id, result.get('error'))

    profile.save(update_fields=[
        'utr_singles', 'utr_doubles', 'utr_display_name',
        'utr_synced_at', 'utr_sync_error', 'updated_at',
    ])
