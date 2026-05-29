import logging
from celery import shared_task

logger = logging.getLogger('apps.players')


@shared_task(name='apps.players.tasks.sync_ti_data_task', bind=True, max_retries=2, default_retry_delay=120)
def sync_ti_data_task(self, profile_id: int):
    """Background task: refresh TI results & rankings cache for a player profile."""
    from .models import PlayerProfile
    from .parsers import extract_ti_id, TenisScrapeError
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
