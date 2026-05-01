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
                    'kwargs': json.dumps({}),
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f'  Created: {task.name}')
            else:
                updated_count += 1
                self.stdout.write(f'  Updated: {task.name}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created_count}, Updated: {updated_count} periodic tasks.'
        ))
