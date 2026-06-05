"""
Ensure Celery Beat periodic tasks exist in the database.
Run after migrate on every deploy:
    python manage.py setup_periodic_tasks
"""
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask
import json


TASKS = [
    {
        'name': 'ingest-all-active-sources-hourly',
        'task': 'apps.ingestion.tasks.run_all_active_sources',
        'cron': {'minute': '0', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Ingest all active sources every hour',
    },
    {
        'name': 'dispatch-deadline-alerts-hourly',
        'task': 'apps.alerts.tasks.dispatch_deadline_alerts',
        'cron': {'minute': '15', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Dispatch deadline alerts every hour at :15',
    },
    {
        'name': 'detect-tournament-changes-every-2h',
        'task': 'apps.ingestion.tasks.detect_tournament_changes',
        'cron': {'minute': '30', 'hour': '*/2', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Detect tournament field changes every 2 hours',
    },
    {
        'name': 'cleanup-old-logs-daily',
        'task': 'apps.audit.tasks.cleanup_old_logs',
        'cron': {'minute': '0', 'hour': '3', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Clean up old audit logs daily at 03:00',
    },
    {
        'name': 'sync-cosat-every-6h',
        'task': 'apps.ingestion.tasks.sync_cosat_from_mongo_task',
        'cron': {'minute': '30', 'hour': '*/6', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync COSAT tournaments from MongoDB every 6 hours (00:30, 06:30, 12:30, 18:30 UTC)',
    },
    {
        'name': 'sync-utr-every-12h',
        'task': 'apps.ingestion.tasks.sync_utr_task',
        'cron': {'minute': '45', 'hour': '*/12', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync UTR Brazil youth tournaments every 12h (00:45, 12:45 UTC)',
    },
    {
        'name': 'sync-fpt-sp-entries-hourly',
        'task': 'apps.registrations.tasks.sync_fpt_sp_entries_task',
        'cron': {'minute': '10', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync FPT (SP) tournament inscritos from fpt.tenisintegrado.com.br every hour at :10',
        'kwargs': {'limit': 60},
    },
    {
        'name': 'sync-cbt-fct-entries-hourly',
        'task': 'apps.registrations.tasks.sync_cbt_fct_entries_task',
        'cron': {'minute': '20', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync CBT and FCT tournament inscritos via TenisIntegrado every hour at :20',
        'kwargs': {'sources': ['cbt', 'fct'], 'limit': 60},
    },
    {
        'name': 'sync-itf-every-12h',
        'task': 'apps.ingestion.tasks.sync_itf_from_mongo_task',
        'cron': {'minute': '0', 'hour': '*/12', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync ITF tournaments + acceptance lists from MongoDB every 12 hours (00:00, 12:00 UTC)',
    },
    {
        'name': 'sync-all-ti-profiles-hourly',
        'task': 'apps.players.tasks.sync_all_ti_profiles_task',
        'cron': {'minute': '50', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Sync TI results, rankings, partidas e inscrições for all profiles with a Tênis Integrado ID every hour at :50',
    },
    {
        'name': 'sync-all-utr-profiles-hourly',
        'task': 'apps.players.tasks.sync_all_utr_profiles_task',
        'cron': {'minute': '40', 'hour': '*', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Refresh UTR rating for profiles with a confirmed UTR id (stale only) every hour at :40',
    },
    {
        'name': 'sync-ti-rankings-daily',
        'task': 'apps.players.tasks.sync_ti_rankings_task',
        'cron': {'minute': '0', 'hour': '2', 'day_of_week': '*', 'day_of_month': '*', 'month_of_year': '*'},
        'description': 'Import public TI ranking catalogue (ExternalPlayerRanking) and backfill profile auto-links daily at 02:00 UTC',
    },
]

# Periodic tasks that were renamed/retired — removed so a previous deploy's
# schedule does not keep firing them (e.g. the old every-2h TI sync).
OBSOLETE_TASKS = [
    'sync-all-ti-profiles-every-2h',
]


class Command(BaseCommand):
    help = 'Create or update Celery Beat periodic tasks in the database'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for task_def in TASKS:
            schedule, _ = CrontabSchedule.objects.get_or_create(**task_def['cron'])
            task, created = PeriodicTask.objects.update_or_create(
                name=task_def['name'],
                defaults={
                    'task': task_def['task'],
                    'crontab': schedule,
                    'enabled': True,
                    'description': task_def['description'],
                    'args': json.dumps([]),
                    'kwargs': json.dumps(task_def.get('kwargs', {})),
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f'  Created: {task.name}')
            else:
                updated_count += 1
                self.stdout.write(f'  Updated: {task.name}')

        removed_count, _ = PeriodicTask.objects.filter(name__in=OBSOLETE_TASKS).delete()
        if removed_count:
            self.stdout.write(f'  Removed {removed_count} obsolete task(s): {", ".join(OBSOLETE_TASKS)}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created_count}, Updated: {updated_count}, '
            f'Removed: {removed_count} periodic tasks.'
        ))
