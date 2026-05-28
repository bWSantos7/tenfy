"""
Sync FPT (SP) tournament entries from fpt.tenisintegrado.com.br.

Calls the public Tenis Integrado inscription endpoint for each active FPT (SP)
tournament edition and creates / updates FederationEntry records.

Usage:
    python manage.py sync_fpt_sp_entries
    python manage.py sync_fpt_sp_entries --dry-run           # preview only
    python manage.py sync_fpt_sp_entries --edition-id 349   # single edition
    python manage.py sync_fpt_sp_entries --limit 10          # cap number of editions
"""
import logging
import unicodedata
import re
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as tz

from apps.tournaments.models import TournamentEdition
from apps.registrations.models import FederationEntry
from apps.sources.models import Organization

logger = logging.getLogger('apps.registrations.sync_fpt_sp')

_VALID_PAYMENT = {
    FederationEntry.PAYMENT_PAID,
    FederationEntry.PAYMENT_PENDING,
    FederationEntry.PAYMENT_UNKNOWN,
}


def _slug(text: str) -> str:
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]


class Command(BaseCommand):
    help = 'Sync FPT (SP) inscritos from fpt.tenisintegrado.com.br'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Fetch and parse but do not save to DB.',
        )
        parser.add_argument(
            '--edition-id', type=int, default=None,
            help='Sync a single TournamentEdition by ID.',
        )
        parser.add_argument(
            '--limit', type=int, default=50,
            help='Max number of editions to sync (default 50).',
        )
        parser.add_argument(
            '--all-statuses', action='store_true',
            help='Include finished/canceled editions (default: skip).',
        )

    def handle(self, *args, **options):
        from apps.registrations.parsers import fetch_tenisintegrado_entries

        dry_run = options['dry_run']
        edition_id = options['edition_id']
        limit = max(1, min(options['limit'], 500))
        all_statuses = options['all_statuses']

        # Find FPT (SP) org
        fpt_sp_org = Organization.objects.filter(short_name='FPT', state='SP').first()
        if not fpt_sp_org:
            raise CommandError('Organização FPT (SP) não encontrada. Verifique o DB.')

        self.stdout.write(f'Org: {fpt_sp_org.name} (id={fpt_sp_org.id})')

        # Build queryset
        if edition_id:
            qs = TournamentEdition.objects.filter(
                id=edition_id,
                tournament__organization=fpt_sp_org,
            )
            if not qs.exists():
                raise CommandError(f'Edição {edition_id} não encontrada para FPT (SP).')
        else:
            qs = TournamentEdition.objects.filter(
                tournament__organization=fpt_sp_org,
                official_source_url__icontains='tenisintegrado',
            ).select_related('tournament')

            if not all_statuses:
                qs = qs.exclude(status__in=[
                    TournamentEdition.STATUS_CANCELED,
                    TournamentEdition.STATUS_FINISHED,
                ])

            qs = qs.order_by('entry_close_at', 'start_date')[:limit]

        total = qs.count()
        self.stdout.write(f'Edições a sincronizar: {total} | dry_run={dry_run}')

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0

        for edition in qs:
            url = edition.official_source_url or ''
            if 'tenisintegrado' not in url.lower():
                self.stdout.write(self.style.WARNING(
                    f'  [{edition.id}] {edition.title[:50]} — sem URL TenisIntegrado, pulando'
                ))
                continue

            self.stdout.write(f'\n  [{edition.id}] {edition.title[:60]}')
            self.stdout.write(f'         URL: {url}')

            try:
                result = fetch_tenisintegrado_entries(url, source='fpt')
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'         ERRO ao buscar: {exc}'))
                total_errors += 1
                continue

            entries = result.get('entries', [])
            parser_warning = result.get('parser_warning', False)

            if parser_warning or not entries:
                self.stdout.write(self.style.WARNING(
                    f'         Aviso: {result.get("warning_message", "sem inscritos")}'
                ))
                total_skipped += 1
                continue

            self.stdout.write(f'         {len(entries)} inscritos encontrados')

            if dry_run:
                for e in entries[:3]:
                    self.stdout.write(
                        f'           [PREVIEW] {e.get("player_name")} | '
                        f'{e.get("category_text")} | {e.get("payment_status")}'
                    )
                if len(entries) > 3:
                    self.stdout.write(f'           ... e mais {len(entries) - 3}')
                continue

            # Upsert FederationEntry records
            now = tz.now()
            for entry_data in entries:
                try:
                    player_name = (entry_data.get('player_name') or '').strip()
                    category_text = (entry_data.get('category_text') or '').strip()
                    if not player_name or not category_text:
                        continue

                    raw_eid = (entry_data.get('player_external_id') or '').strip()
                    external_id = raw_eid or f'fpt:{_slug(player_name)}:{_slug(category_text)}'

                    raw_payment = (entry_data.get('payment_status') or FederationEntry.PAYMENT_UNKNOWN).strip()
                    if raw_payment not in _VALID_PAYMENT:
                        raw_payment = FederationEntry.PAYMENT_UNKNOWN

                    defaults = {
                        'player_name': player_name[:200],
                        'category_text': category_text[:200],
                        'ranking_position': entry_data.get('ranking_position'),
                        'payment_status': raw_payment,
                        'removed_or_replaced': bool(entry_data.get('removed_or_replaced', False)),
                        'replacement_reason': (entry_data.get('replacement_reason') or '')[:500],
                        'source': FederationEntry.SOURCE_FPT,
                        'source_url': (entry_data.get('source_url') or url)[:500],
                        'confidence': FederationEntry.CONFIDENCE_HIGH,
                        'notes': (entry_data.get('notes') or '')[:500],
                        'player_country_name': (entry_data.get('player_country_name') or '')[:100],
                        'player_country_code': (entry_data.get('player_country_code') or '')[:10],
                        'synced_at': now,
                    }

                    _, created = FederationEntry.objects.update_or_create(
                        edition=edition,
                        player_external_id=external_id,
                        defaults=defaults,
                    )

                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

                except Exception as exc:
                    logger.warning('Erro ao upsert entry: %s | %s', entry_data, exc)
                    total_errors += 1

            self.stdout.write(self.style.SUCCESS(
                f'         Salvo: {len(entries)} inscritos para edição {edition.id}'
            ))

        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] Nenhum dado salvo.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Concluído: {total_created} criados | {total_updated} atualizados | '
                f'{total_skipped} sem inscritos | {total_errors} erros'
            ))
