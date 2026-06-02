"""Celery tasks orchestrating ingestion."""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.sources.models import DataSource
from apps.tournaments.models import TournamentEdition, TournamentChangeEvent
from .connectors.base import get_connector, ConnectorError
from .connectors import cbt as _cbt          # noqa: F401
from .connectors import cosat as _cosat      # noqa: F401
from .connectors import fct as _fct          # noqa: F401
from .connectors import fpt_sp as _fpt_sp    # noqa: F401
from .connectors import itf as _itf          # noqa: F401
from .connectors import utr as _utr          # noqa: F401
from .models import IngestionRun
from .persistence import TournamentPersister

logger = logging.getLogger('apps.ingestion.tasks')

_CB_THRESHOLD = 3   # auto-disable after 3 consecutive failures
_CB_TTL       = 3600  # 1 hour cooldown


def _record_connector_failure(connector_key: str, error: str):
    """Track consecutive connector failures — auto-disables after threshold."""
    from django.core.cache import cache
    failures_key = f'connector:failures:{connector_key}'
    open_key = f'connector:open:{connector_key}'
    failures = cache.get(failures_key, 0) + 1
    cache.set(failures_key, failures, _CB_TTL * 2)
    if failures >= _CB_THRESHOLD:
        cache.set(open_key, True, _CB_TTL)
        logger.error(
            'Connector %s BLOCKED after %d failures (last: %s). '
            'Check /api/admin-panel/connector-status/ and curate manually if needed.',
            connector_key, failures, error[:200],
        )


def _record_connector_success(connector_key: str):
    from django.core.cache import cache
    cache.delete(f'connector:failures:{connector_key}')
    cache.delete(f'connector:open:{connector_key}')


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def run_source(self, data_source_id: int):
    try:
        source = DataSource.objects.select_related('organization').get(pk=data_source_id)
    except DataSource.DoesNotExist:
        logger.error('DataSource %s not found', data_source_id)
        return {'error': 'not_found'}

    if not source.enabled:
        return {'skipped': True, 'reason': 'disabled'}

    # Per-connector circuit breaker — skip if recently blocked
    from django.core.cache import cache as _cache
    if _cache.get(f'connector:open:{source.connector_key}'):
        logger.warning('Connector %s skipped — circuit open (consecutive failures). Admin must curate manually or wait for cooldown.', source.connector_key)
        return {'skipped': True, 'reason': 'circuit_open'}

    connector_cls = get_connector(source.connector_key)
    if not connector_cls:
        logger.error('No connector registered for key %s', source.connector_key)
        source.last_run_status = 'failed_no_connector'
        source.save(update_fields=['last_run_status', 'updated_at'])
        return {'error': 'no_connector'}

    run = IngestionRun.objects.create(
        data_source=source, triggered_by='celery',
    )
    TournamentPersister.invalidate_category_cache()
    persister = TournamentPersister(source, run)

    created_n = 0
    updated_n = 0
    fetched_n = 0
    changes_n = 0
    errors = []

    try:
        connector = connector_cls(data_source=source)
        for item in connector.extract():
            fetched_n += 1
            try:
                ed, created, changes = persister.upsert(item)
                if created:
                    created_n += 1
                else:
                    updated_n += 1
                if changes:
                    changes_n += 1
                    last_event = ed.change_events.order_by('-detected_at').first()
                    if last_event:
                        from apps.alerts.tasks import dispatch_change_alert
                        dispatch_change_alert.delay(ed.id, last_event.id)
            except Exception as exc:
                logger.exception('persist failed for item')
                errors.append(f'persist:{exc}')

        status = IngestionRun.STATUS_SUCCESS if not errors else IngestionRun.STATUS_PARTIAL
    except ConnectorError as exc:
        errors.append(str(exc))
        status = IngestionRun.STATUS_FAILED
        _record_connector_failure(source.connector_key, str(exc))
    except Exception as exc:
        errors.append(str(exc))
        status = IngestionRun.STATUS_FAILED
        _record_connector_failure(source.connector_key, str(exc))
        logger.exception('unhandled ingestion error')
    else:
        _record_connector_success(source.connector_key)

    run.finished_at = timezone.now()
    run.status = status
    run.items_fetched = fetched_n
    run.items_created = created_n
    run.items_updated = updated_n
    run.changes_detected = changes_n
    run.error_summary = '\n'.join(errors)[:4000]
    run.metrics = {
        'fetched': fetched_n, 'created': created_n,
        'updated': updated_n, 'changes': changes_n,
        'errors': len(errors),
    }
    run.save()

    source.last_run_at = run.finished_at
    source.last_run_status = status
    source.save(update_fields=['last_run_at', 'last_run_status', 'updated_at'])

    # Invalidate tournament list caches when new data arrives
    if created_n > 0 or updated_n > 0:
        try:
            from django.core.cache import cache as _cache
            _cache.delete('tournaments:calendar')
            # List caches use MD5 keys — use delete_pattern if available, else skip
            try:
                _cache.delete_pattern('tournaments:list:*')
            except AttributeError:
                pass  # django-redis not configured with delete_pattern
        except Exception:
            pass

    return {
        'status': status, 'run_id': run.id,
        'fetched': fetched_n, 'created': created_n,
        'updated': updated_n, 'changes': changes_n,
        'errors': errors[:5],
    }


@shared_task
def run_all_active_sources():
    ids = list(DataSource.objects.filter(enabled=True).values_list('id', flat=True))
    for sid in ids:
        run_source.delay(sid)
    return {'dispatched': len(ids)}


@shared_task(bind=True, max_retries=0)
def sync_cosat_from_mongo_task(self):
    """
    Periodic COSAT MongoDB → PostgreSQL sync. Runs every 6h via Celery Beat.
    Schedule: crontab(minute=30, hour='*/6') — UTC (00:30, 06:30, 12:30, 18:30).

    Syncs all COSAT tournaments AND player entries (import_entries=True).
    Players without a reliable event link go into category_text='Geral do torneio'.
    Aborts silently when COSAT_MONGO_ENABLED is False or MongoDB is unreachable.
    Uses a cache-based lock (cache.add is atomic) to prevent concurrent runs.
    Never leaks COSAT_MONGO_URL in logs (sanitized by connector).
    """
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'COSAT_MONGO_ENABLED', False):
        logger.info('sync_cosat_from_mongo_task: skipped (COSAT_MONGO_ENABLED=False)')
        return {'skipped': True, 'reason': 'disabled'}

    lock_key = 'sync_cosat:lock'
    lock_ttl = 3600  # 1h max — task should never run longer than this
    if not cache.add(lock_key, True, lock_ttl):
        logger.warning('sync_cosat_from_mongo_task: already running, skipped')
        return {'skipped': True, 'reason': 'already_running'}

    try:
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command(
            'sync_cosat_from_mongo',
            dry_run=False,
            import_entries=True,
            stdout=out,
        )
        tail = out.getvalue()[-400:]
        logger.info('sync_cosat_from_mongo_task complete:\n%s', tail)
        return {'status': 'success'}
    except Exception as exc:
        logger.exception('sync_cosat_from_mongo_task failed: %s', exc)
        return {'status': 'error', 'error': str(exc)[:200]}
    finally:
        cache.delete(lock_key)


@shared_task(bind=True, max_retries=0)
def sync_itf_from_mongo_task(self):
    """
    Periodic ITF MongoDB → PostgreSQL sync. Runs every 12h via Celery Beat.
    Schedule: crontab(minute=0, hour='*/12') — UTC (00:00, 12:00).

    Syncs all ITF tournaments AND player acceptance lists (import_entries=True).
    Aborts silently when ITF_MONGO_ENABLED is False or MongoDB is unreachable.
    Uses a cache-based lock to prevent concurrent runs.
    """
    from django.conf import settings
    from django.core.cache import cache

    if not getattr(settings, 'ITF_MONGO_ENABLED', False):
        logger.info('sync_itf_from_mongo_task: skipped (ITF_MONGO_ENABLED=False)')
        return {'skipped': True, 'reason': 'disabled'}

    lock_key = 'sync_itf:lock'
    lock_ttl = 3600  # 1h max
    if not cache.add(lock_key, True, lock_ttl):
        logger.warning('sync_itf_from_mongo_task: already running, skipped')
        return {'skipped': True, 'reason': 'already_running'}

    try:
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command(
            'sync_itf_from_mongo',
            dry_run=False,
            import_entries=True,
            stdout=out,
        )
        tail = out.getvalue()[-400:]
        logger.info('sync_itf_from_mongo_task complete:\n%s', tail)
        return {'status': 'success'}
    except Exception as exc:
        logger.exception('sync_itf_from_mongo_task failed: %s', exc)
        return {'status': 'error', 'error': str(exc)[:200]}
    finally:
        cache.delete(lock_key)


@shared_task
def detect_tournament_changes():
    now = timezone.now()
    soon = now + timedelta(days=3)
    qs = TournamentEdition.objects.filter(
        entry_close_at__isnull=False,
        entry_close_at__gt=now,
        entry_close_at__lte=soon,
    ).exclude(status=TournamentEdition.STATUS_CLOSING_SOON).exclude(
        status__in=[TournamentEdition.STATUS_CANCELED, TournamentEdition.STATUS_FINISHED]
    )
    n = 0
    for ed in qs:
        prev = ed.status
        ed.status = TournamentEdition.STATUS_CLOSING_SOON
        ed.save(update_fields=['status', 'updated_at'])
        TournamentChangeEvent.objects.create(
            edition=ed, event_type=TournamentChangeEvent.EVENT_STATUS,
            field_changes={'status': {'old': prev, 'new': ed.status}},
        )
        n += 1

    qs2 = TournamentEdition.objects.filter(
        entry_close_at__isnull=False, entry_close_at__lte=now,
        status__in=[
            TournamentEdition.STATUS_OPEN,
            TournamentEdition.STATUS_CLOSING_SOON,
            TournamentEdition.STATUS_ANNOUNCED,
        ],
    )
    closed_n = 0
    for ed in qs2:
        prev = ed.status
        ed.status = TournamentEdition.STATUS_CLOSED
        ed.save(update_fields=['status', 'updated_at'])
        TournamentChangeEvent.objects.create(
            edition=ed, event_type=TournamentChangeEvent.EVENT_STATUS,
            field_changes={'status': {'old': prev, 'new': ed.status}},
        )
        closed_n += 1
    return {'closing_soon': n, 'closed': closed_n}
