"""
Sync CBT and FCT tournament entries via the TenisIntegrado inscription panel.

Both federations host their tournaments on the same platform as FPT
(www.tenisintegrado.com.br/torneio_painel_insc/index/{id}), so the same
auto-fetch strategy applies.

The tournament ID is extracted from:
  1. edition.external_id  e.g. "cbt:12345" or "fct:67890"
  2. edition.official_source_url  e.g. ".../torneio/index/12345"

Usage:
    python manage.py sync_cbt_fct_entries
    python manage.py sync_cbt_fct_entries --dry-run
    python manage.py sync_cbt_fct_entries --source cbt
    python manage.py sync_cbt_fct_entries --source fct
    python manage.py sync_cbt_fct_entries --edition-id 500
    python manage.py sync_cbt_fct_entries --limit 20
"""
import logging
import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as tz

from apps.tournaments.models import TournamentEdition
from apps.registrations.models import FederationEntry

logger = logging.getLogger('apps.registrations.sync_cbt_fct')

_TI_INSC_URL = 'https://www.tenisintegrado.com.br/torneio_painel_insc/index/{tid}'

_SOURCE_MAP = {
    'cbt': FederationEntry.SOURCE_CBT,
    'fct': FederationEntry.SOURCE_FCT,
}

_VALID_PAYMENT = {
    FederationEntry.PAYMENT_PAID,
    FederationEntry.PAYMENT_PENDING,
    FederationEntry.PAYMENT_UNKNOWN,
}


def _slug(text: str) -> str:
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:50]


def _extract_tid(edition: TournamentEdition) -> str | None:
    """Extract the TenisIntegrado tournament ID for this edition."""
    # 1. external_id: "cbt:12345" or "fct:67890"
    m = re.match(r'(?:cbt|fct|fmt):(\d+)', edition.external_id or '')
    if m:
        return m.group(1)
    # 2. source_url path: /torneio/index/12345 or /torneio_painel_insc/index/12345
    src = edition.official_source_url or ''
    m = re.search(r'/(?:torneio_painel_insc|torneio_painel_info|torneio)/(?:index/)?(\d+)', src)
    if m:
        return m.group(1)
    # 3. any numeric ID at end of URL
    m = re.search(r'/(\d{4,})/?$', src)
    if m:
        return m.group(1)
    return None


class Command(BaseCommand):
    help = 'Sync CBT and FCT inscritos via TenisIntegrado torneio_painel_insc'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Fetch and parse but do not save to DB.',
        )
        parser.add_argument(
            '--source', choices=['cbt', 'fct', 'both'], default='both',
            help='Which federation to sync (default: both).',
        )
        parser.add_argument(
            '--edition-id', type=int, default=None,
            help='Sync a single TournamentEdition by ID.',
        )
        parser.add_argument(
            '--limit', type=int, default=50,
            help='Max editions per source (default 50).',
        )
        parser.add_argument(
            '--all-statuses', action='store_true',
            help='Include finished/canceled editions (default: skip).',
        )

    def handle(self, *args, **options):
        from apps.registrations.parsers import fetch_tenisintegrado_entries

        dry_run = options['dry_run']
        source_filter = options['source']
        edition_id = options['edition_id']
        limit = max(1, min(options['limit'], 500))
        all_statuses = options['all_statuses']

        sources = ['cbt', 'fct'] if source_filter == 'both' else [source_filter]

        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0

        for src in sources:
            self.stdout.write(f'\n{"=" * 60}')
            self.stdout.write(f'Fonte: {src.upper()}')

            if edition_id:
                qs = TournamentEdition.objects.filter(
                    id=edition_id,
                    external_id__startswith=f'{src}:',
                )
                if not qs.exists():
                    self.stdout.write(self.style.WARNING(
                        f'Edição {edition_id} não encontrada para {src.upper()}.'
                    ))
                    continue
            else:
                qs = TournamentEdition.objects.filter(
                    external_id__startswith=f'{src}:',
                ).select_related('tournament')

                if not all_statuses:
                    qs = qs.exclude(status__in=[
                        TournamentEdition.STATUS_CANCELED,
                        TournamentEdition.STATUS_FINISHED,
                    ])

                qs = qs.order_by('entry_close_at', 'start_date')[:limit]

            total = qs.count()
            self.stdout.write(f'Edições encontradas: {total} | dry_run={dry_run}')

            for edition in qs:
                tid = _extract_tid(edition)
                if not tid:
                    self.stdout.write(self.style.WARNING(
                        f'  [{edition.id}] {edition.title[:50]} — ID não encontrado, pulando'
                    ))
                    total_skipped += 1
                    continue

                insc_url = _TI_INSC_URL.format(tid=tid)
                self.stdout.write(f'\n  [{edition.id}] {edition.title[:60]}')
                self.stdout.write(f'         TI URL: {insc_url}')

                try:
                    result = fetch_tenisintegrado_entries(insc_url, source=src)
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f'         ERRO: {exc}'))
                    total_errors += 1
                    continue

                entries = result.get('entries', [])
                if result.get('parser_warning') or not entries:
                    self.stdout.write(self.style.WARNING(
                        f'         {result.get("warning_message", "sem inscritos")}'
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

                db_source = _SOURCE_MAP[src]
                now = tz.now()
                for entry_data in entries:
                    try:
                        player_name = (entry_data.get('player_name') or '').strip()
                        category_text = (entry_data.get('category_text') or '').strip()
                        if not player_name or not category_text:
                            continue

                        raw_eid = (entry_data.get('player_external_id') or '').strip()
                        external_id = raw_eid or f'{src}:{_slug(player_name)}:{_slug(category_text)}'

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
                            'source': db_source,
                            'source_url': insc_url[:500],
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
                f'{total_skipped} sem inscritos/ID | {total_errors} erros'
            ))
