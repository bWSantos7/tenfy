import logging
from celery import shared_task

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
