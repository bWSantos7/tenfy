import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('tenfy')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Fallback beat schedule (used when DatabaseScheduler is NOT active / for reference).
# The authoritative schedule lives in the DB — run `setup_periodic_tasks` after each deploy.
app.conf.beat_schedule = {
    'ingest-all-active-sources-hourly': {
        'task': 'apps.ingestion.tasks.run_all_active_sources',
        'schedule': crontab(minute=0),
    },
    'dispatch-deadline-alerts-hourly': {
        'task': 'apps.alerts.tasks.dispatch_deadline_alerts',
        'schedule': crontab(minute=15),
    },
    'detect-tournament-changes-every-2h': {
        'task': 'apps.ingestion.tasks.detect_tournament_changes',
        'schedule': crontab(minute=30, hour='*/2'),
    },
    'cleanup-old-logs-daily': {
        'task': 'apps.audit.tasks.cleanup_old_logs',
        'schedule': crontab(hour=3, minute=0),
    },
    'expire-stale-invites-daily': {
        'task': 'apps.accounts.tasks.expire_stale_invites',
        'schedule': crontab(hour=1, minute=30),  # 01:30 UTC daily
    },
    'sync-cosat-every-6h': {
        'task': 'apps.ingestion.tasks.sync_cosat_from_mongo_task',
        'schedule': crontab(minute=30, hour='*/6'),  # 00:30, 06:30, 12:30, 18:30 UTC
    },
    'sync-all-ti-profiles-every-2h': {
        'task': 'apps.players.tasks.sync_all_ti_profiles_task',
        'schedule': crontab(minute=50, hour='*/2'),  # 00:50, 02:50, 04:50 … UTC
    },
}


@app.on_after_configure.connect
def _ensure_periodic_tasks(sender, **kwargs):
    """
    Auto-register periodic tasks in the DB on worker/beat startup.
    Runs only when Django ORM is available (i.e. not during early import).
    """
    try:
        from django.db import connection
        connection.ensure_connection()
    except Exception:
        return

    try:
        from django.core.management import call_command
        call_command('setup_periodic_tasks', verbosity=0)
    except Exception:
        pass


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
