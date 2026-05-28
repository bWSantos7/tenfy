"""
Run a connector by key synchronously (for manual/CLI use).

Usage:
    python manage.py run_connector fpt_sp_public
    python manage.py run_connector fpt_sp_public --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from apps.sources.models import DataSource


class Command(BaseCommand):
    help = 'Run a connector by connector_key synchronously'

    def add_arguments(self, parser):
        parser.add_argument('connector_key', type=str)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Extract and print records without saving to DB',
        )

    def handle(self, *args, **options):
        key = options['connector_key']
        dry_run = options['dry_run']

        try:
            ds = DataSource.objects.get(connector_key=key)
        except DataSource.DoesNotExist:
            raise CommandError(
                f'DataSource with connector_key="{key}" not found.\n'
                'Run seed_sources first or check the key.'
            )

        self.stdout.write(f'Source: {ds.source_name} (id={ds.id})')

        if dry_run:
            self._dry_run(ds)
        else:
            self._run(ds)

    def _run(self, ds):
        from apps.ingestion.tasks import run_source
        self.stdout.write('Dispatching Celery task...')
        result = run_source.delay(ds.id)
        self.stdout.write(self.style.SUCCESS(f'Task dispatched: {result.id}'))
        self.stdout.write('Check worker logs for progress.')

    def _dry_run(self, ds):
        from apps.ingestion.connectors import registered_connectors
        ConnectorClass = registered_connectors(ds.connector_key)
        if not ConnectorClass:
            raise CommandError(f'Connector class not found for key "{ds.connector_key}"')

        connector = ConnectorClass(config=ds.config_json or {})
        self.stdout.write('[DRY RUN] Extracting records...')
        count = 0
        for record in connector.extract():
            count += 1
            self.stdout.write(
                f'  [{count}] {record.get("external_id")} | {record.get("title")} | '
                f'{record.get("status")} | {record.get("modality")}'
            )
        self.stdout.write(self.style.SUCCESS(f'[DRY RUN] {count} records extracted.'))
