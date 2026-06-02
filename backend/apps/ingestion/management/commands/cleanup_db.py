"""
Management command — cleanup de dados obsoletos do banco PostgreSQL.

Libera espaço removendo registros que não têm valor operacional:
  - IngestionRun antigas (mantém as últimas N por fonte)
  - raw_payload de TournamentEdition (grandes JSONs do scraper, desnecessários após ingestão)
  - WebhookEvent processados com mais de 30 dias
  - AuditLog com mais de 90 dias

Usage:
    python manage.py cleanup_db                  # dry-run (mostra o que seria removido)
    python manage.py cleanup_db --no-dry-run     # executa a limpeza
    python manage.py cleanup_db --no-dry-run --keep-runs 5
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('apps.ingestion')


class Command(BaseCommand):
    help = 'Remove dados obsoletos do banco para liberar espaço no volume Postgres'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=True)
        parser.add_argument('--no-dry-run', dest='dry_run', action='store_false')
        parser.add_argument('--keep-runs', type=int, default=3,
                            help='Manter as últimas N IngestionRun por fonte (default: 3)')
        parser.add_argument('--runs-older-days', type=int, default=7,
                            help='Deletar runs com mais de N dias (default: 7)')
        parser.add_argument('--webhook-days', type=int, default=30,
                            help='Manter WebhookEvent dos últimos N dias (default: 30)')
        parser.add_argument('--audit-days', type=int, default=90,
                            help='Manter AuditLog dos últimos N dias (default: 90)')
        parser.add_argument('--skip-raw-payload', action='store_true', default=False,
                            help='Não limpar raw_payload das TournamentEditions')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        keep_runs = options['keep_runs']
        runs_older_days = options['runs_older_days']
        webhook_days = options['webhook_days']
        audit_days = options['audit_days']
        skip_raw = options['skip_raw_payload']

        mode = '[DRY-RUN]' if dry_run else '[EXECUTANDO]'
        self.stdout.write(self.style.SUCCESS(f'\n=== cleanup_db {mode} ===\n'))

        now = timezone.now()
        total_freed = 0

        # ── 1. IngestionRun antigas ──────────────────────────────────────────
        self.stdout.write('--- IngestionRun ---')
        freed = self._cleanup_ingestion_runs(dry_run, keep_runs, runs_older_days, now)
        total_freed += freed

        # ── 2. raw_payload em TournamentEdition ──────────────────────────────
        if not skip_raw:
            self.stdout.write('\n--- TournamentEdition.raw_payload ---')
            freed = self._cleanup_raw_payloads(dry_run)
            total_freed += freed

        # ── 3. WebhookEvent processados ───────────────────────────────────────
        self.stdout.write('\n--- WebhookEvent ---')
        freed = self._cleanup_webhook_events(dry_run, webhook_days, now)
        total_freed += freed

        # ── 4. AuditLog antigos ───────────────────────────────────────────────
        self.stdout.write('\n--- AuditLog ---')
        freed = self._cleanup_audit_logs(dry_run, audit_days, now)
        total_freed += freed

        self.stdout.write(f'\nTotal de registros que seriam/foram removidos: {total_freed}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nDRY-RUN — nenhuma alteração feita. Use --no-dry-run para executar.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nCleanup concluído.'))

    def _cleanup_ingestion_runs(self, dry_run, keep_runs, older_days, now):
        from apps.ingestion.models import IngestionRun
        from django.db.models import Subquery, OuterRef

        cutoff = now - timedelta(days=older_days)

        # Para cada data_source, manter as últimas keep_runs runs
        # Deletar todas as outras + qualquer run mais antiga que older_days
        total = 0

        # Runs mais antigas que o cutoff (independente de fonte)
        old_qs = IngestionRun.objects.filter(started_at__lt=cutoff)
        count_old = old_qs.count()
        self.stdout.write(f'  Runs com mais de {older_days} dias: {count_old}')
        if not dry_run and count_old:
            old_qs.delete()
        total += count_old

        # Runs recentes mas além do limite keep_runs por fonte
        from django.db.models import F
        sources = IngestionRun.objects.filter(
            started_at__gte=cutoff
        ).values_list('data_source_id', flat=True).distinct()

        excess = 0
        for source_id in sources:
            # IDs das N mais recentes desta fonte — manter
            keep_ids = list(
                IngestionRun.objects.filter(
                    data_source_id=source_id,
                    started_at__gte=cutoff,
                ).order_by('-started_at').values_list('id', flat=True)[:keep_runs]
            )
            excess_qs = IngestionRun.objects.filter(
                data_source_id=source_id,
                started_at__gte=cutoff,
            ).exclude(id__in=keep_ids)
            c = excess_qs.count()
            if not dry_run and c:
                excess_qs.delete()
            excess += c

        self.stdout.write(f'  Runs excedentes (além de {keep_runs} por fonte): {excess}')
        total += excess
        self.stdout.write(f'  → Total runs a remover: {total}')
        return total

    def _cleanup_raw_payloads(self, dry_run):
        from apps.tournaments.models import TournamentEdition
        from django.db.models import Q

        # Limpar raw_payload de edições que já foram revisadas manualmente
        # OU de edições com data de início já passada (não precisam mais do raw)
        from django.utils import timezone
        past_qs = TournamentEdition.objects.filter(
            Q(is_manual_override=True) | Q(end_date__lt=timezone.now().date())
        ).exclude(raw_payload={})

        count = past_qs.count()
        self.stdout.write(f'  Edições com raw_payload limpável: {count}')
        if not dry_run and count:
            past_qs.update(raw_payload={})
        return count

    def _cleanup_webhook_events(self, dry_run, days, now):
        from apps.billing.models import WebhookEvent
        cutoff = now - timedelta(days=days)
        qs = WebhookEvent.objects.filter(processed=True, created_at__lt=cutoff)
        count = qs.count()
        self.stdout.write(f'  WebhookEvents processados com mais de {days} dias: {count}')
        if not dry_run and count:
            qs.delete()
        return count

    def _cleanup_audit_logs(self, dry_run, days, now):
        from apps.audit.models import AuditLog
        cutoff = now - timedelta(days=days)
        qs = AuditLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        self.stdout.write(f'  AuditLogs com mais de {days} dias: {count}')
        if not dry_run and count:
            qs.delete()
        return count
