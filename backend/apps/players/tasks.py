import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.players')

# Delay (seconds) between consecutive per-profile sync tasks to avoid
# hammering tenisintegrado.com.br with concurrent requests.
_TI_STAGGER_SECONDS = 20


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

    Scheduled every 2 hours via Celery Beat.
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
