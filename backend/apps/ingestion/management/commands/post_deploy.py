"""
Post-deploy command — executa automaticamente a cada deploy no Railway.

1. Aplica migrations pendentes
2. Registra/atualiza periodic tasks no banco (setup_periodic_tasks)
3. Dispara sync imediato de inscritos FPT, CBT e FCT via Celery

Configurado no Procfile como processo 'release', que o Railway executa
antes de iniciar os demais processos a cada novo deploy.
"""
import logging

from django.core.management.base import BaseCommand
from django.core.management import call_command

logger = logging.getLogger('apps.ingestion.post_deploy')


class Command(BaseCommand):
    help = 'Tarefas pós-deploy: migrations, periodic tasks e sync imediato de inscritos'

    def handle(self, *args, **options):
        # 1. Migrations
        self.stdout.write('▶ Aplicando migrations...')
        try:
            call_command('migrate', '--run-syncdb', verbosity=1)
            self.stdout.write(self.style.SUCCESS('✓ Migrations OK'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Migrations: {exc}'))

        # 2. Seed data sources (idempotent — cria/atualiza Organization e DataSource)
        self.stdout.write('▶ Sincronizando fontes de dados (seed_sources)...')
        try:
            call_command('seed_sources', verbosity=1)
            self.stdout.write(self.style.SUCCESS('✓ Sources OK'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Sources: {exc}'))

        # 2b. Garante as siglas oficiais SIGLA-UF das federações (TASK 1) — idempotente.
        # Enforça por UF mesmo que algum seeder volte a usar sigla antiga.
        self.stdout.write('▶ Federações no formato oficial (fix_federation_orgs)...')
        try:
            call_command('fix_federation_orgs', '--apply', verbosity=0)
            self.stdout.write(self.style.SUCCESS('✓ Federações OK'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Federações: {exc}'))

        # 3. Periodic tasks
        self.stdout.write('▶ Registrando periodic tasks...')
        try:
            call_command('setup_periodic_tasks', verbosity=0)
            self.stdout.write(self.style.SUCCESS('✓ Periodic tasks OK'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Periodic tasks: {exc}'))

        # 4. Dispara ingestão de torneios (connector run) para todas as fontes ativas
        self.stdout.write('▶ Disparando ingestão de torneios (todas as fontes ativas)...')
        try:
            from apps.ingestion.tasks import run_all_active_sources
            run_all_active_sources.delay()
            self.stdout.write(self.style.SUCCESS(
                '✓ Ingestão enfileirada: torneios FPT, CBT, COSAT e demais serão atualizados assim que o Worker iniciar'
            ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Ingestão enfileiramento: {exc}'))

        # 5. Dispara sync imediato de inscritos (enfileira no Redis/Celery)
        self.stdout.write('▶ Disparando sync imediato de inscritos...')
        try:
            from apps.registrations.tasks import (
                sync_fpt_sp_entries_task,
                sync_cbt_fct_entries_task,
            )
            sync_fpt_sp_entries_task.delay(limit=60)
            sync_cbt_fct_entries_task.delay(sources=['cbt', 'fct'], limit=60)
            self.stdout.write(self.style.SUCCESS(
                '✓ Sync enfileirado: FPT, CBT e FCT serão sincronizados assim que o Worker iniciar'
            ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'⚠ Sync enfileiramento: {exc}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Post-deploy concluído'))
