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
    'sync-all-ti-profiles-hourly': {
        'task': 'apps.players.tasks.sync_all_ti_profiles_task',
        'schedule': crontab(minute=50),  # every hour at :50 (ratings, partidas, ranking, inscrições)
    },
    'sync-all-utr-profiles-hourly': {
        'task': 'apps.players.tasks.sync_all_utr_profiles_task',
        'schedule': crontab(minute=40),  # every hour at :40 (rating UTR de perfis vinculados)
    },
    'sync-ti-rankings-daily': {
        'task': 'apps.players.tasks.sync_ti_rankings_task',
        'schedule': crontab(hour=2, minute=0),  # 02:00 UTC daily (import ranking catalogue + backfill links)
    },
    'sync-fpt-sp-entries-hourly': {
        'task': 'apps.registrations.tasks.sync_fpt_sp_entries_task',
        'schedule': crontab(minute=10),  # X:10 every hour
        'kwargs': {'limit': 60},
    },
    'sync-cbt-fct-entries-hourly': {
        'task': 'apps.registrations.tasks.sync_cbt_fct_entries_task',
        'schedule': crontab(minute=20),  # X:20 every hour (after FPT)
        'kwargs': {'sources': ['cbt', 'fct'], 'limit': 60},
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
