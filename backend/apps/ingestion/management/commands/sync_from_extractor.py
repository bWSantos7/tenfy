"""
Management command — sincroniza os dados do *tournament-extractor* (schema
``extractor`` no mesmo PostgreSQL) para o PostgreSQL do Tenfy.

O tournament-extractor é um serviço externo (roda no Railway) que extrai torneios
juvenis e inscritos de COSAT, UTR, FPT, CBT, ITF e Federações, e grava no schema
``extractor``. Este comando LÊ esse schema e faz upsert em TournamentEdition /
FederationEntry reusando a camada de persistência existente.

Substitui os meios antigos de ingestão (conectores in-backend, syncs Mongo de
COSAT/ITF, workflows n8n de inscritos).

Uso:
    python manage.py sync_from_extractor                 # dry-run (seguro)
    python manage.py sync_from_extractor --no-dry-run    # grava
    python manage.py sync_from_extractor --source cbt --limit 20
    python manage.py sync_from_extractor --no-dry-run --import-entries

Regras (CLAUDE.md):
    - Dry-run é o padrão. --no-dry-run para gravar.
    - Idempotente: upsert por external_id / unique_together.
    - Nunca deleta torneios; nunca inventa dados.
    - Preserva origem (raw_payload, official_source_url, confidence).
    - removed_or_replaced prevalece sobre payment_status=paid.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ingestion.connectors import extractor_reader
from apps.ingestion.models import IngestionRun
from apps.ingestion.persistence import TournamentPersister
from apps.registrations.models import FederationEntry
from apps.sources.models import DataSource, Organization
from apps.tournaments.models import TournamentEdition

logger = logging.getLogger('apps.ingestion.extractor')

CONNECTOR_KEY = 'extractor'

# Fonte do extractor -> short_name da Organization no Tenfy.
SOURCE_ORG = {
    'cosat': ('COSAT', Organization.TYPE_CONFEDERATION),
    'utr': ('UTR', Organization.TYPE_PLATFORM),
    'fpt': ('FPT', Organization.TYPE_FEDERATION),
    'cbt': ('CBT', Organization.TYPE_CONFEDERATION),
    'itf': ('ITF', Organization.TYPE_CONFEDERATION),
    'federations': ('CBT', Organization.TYPE_CONFEDERATION),  # org real resolvida por torneio
}

# status do extractor -> TournamentEdition.STATUS_*
STATUS_MAP = {
    'inscricoes_abertas': TournamentEdition.STATUS_OPEN,
    'inscricoes_encerradas': TournamentEdition.STATUS_CLOSED,
    'encerrado': TournamentEdition.STATUS_CLOSED,
    'finalizado': TournamentEdition.STATUS_FINISHED,
    'em_andamento': TournamentEdition.STATUS_IN_PROGRESS,
    'cancelado': TournamentEdition.STATUS_CANCELED,
    'agendado': TournamentEdition.STATUS_ANNOUNCED,
}


# Nome de país (pt/en) -> código 3 letras (ISO/IOC) p/ a bandeira do frontend.
# ITF já traz hostNationCode; inscritos ITF/COSAT já vêm com código 3 letras
# (resolvidos por passthrough). Este mapa cobre os nomes que aparecem como TEXTO:
# Brasil (todas as fontes BR) + países sul-americanos (nomes nos torneios COSAT).
NAME_TO_CODE3 = {
    'brasil': 'BRA', 'brazil': 'BRA',
    'argentina': 'ARG', 'bolivia': 'BOL', 'bolívia': 'BOL', 'chile': 'CHL',
    'colombia': 'COL', 'colômbia': 'COL', 'ecuador': 'ECU', 'equador': 'ECU',
    'paraguay': 'PAR', 'paraguai': 'PAR', 'peru': 'PER', 'perú': 'PER',
    'uruguay': 'URY', 'uruguai': 'URY', 'venezuela': 'VEN',
    'estados unidos': 'USA', 'united states': 'USA',
}


def _slug(text: str) -> str:
    s = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:60] or 'torneio'


def _country_code(value, hint: str | None = None) -> str:
    """Resolve um código de país 3-letras para a bandeira. ``hint`` (ex.: ITF
    hostNationCode) tem prioridade. Passa adiante valores que já são código."""
    if hint and str(hint).strip().isalpha():
        return str(hint).strip().upper()[:3]
    v = (value or '').strip()
    if len(v) in (2, 3) and v.isalpha():
        return v.upper()  # já é código (inscritos ITF/COSAT)
    return NAME_TO_CODE3.get(v.lower(), '')


def _iso(d) -> str | None:
    return d.isoformat() if d is not None else None


def _map_payment(entrant: dict) -> tuple[str, bool, str]:
    """(payment_status, removed_or_replaced, replacement_reason) p/ FederationEntry."""
    pay = (entrant.get('payment_status') or '').lower()
    reg = (entrant.get('registration_status') or '').lower()
    if 'cancel' in pay or 'cancel' in reg:
        return FederationEntry.PAYMENT_UNKNOWN, True, 'Cancelado/retirado conforme a fonte'
    if pay in ('pago', 'paid', 'isento'):
        return FederationEntry.PAYMENT_PAID, False, ''
    if pay in ('pendente', 'nao_pago', 'pending'):
        return FederationEntry.PAYMENT_PENDING, False, ''
    # ITF: sem pagamento, mas situação de entrada confirmada -> mantém unknown.
    return FederationEntry.PAYMENT_UNKNOWN, False, ''


class Command(BaseCommand):
    help = 'Sincroniza torneios e inscritos do schema extractor para o PostgreSQL do Tenfy'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=True,
                            help='Pré-visualiza sem gravar (padrão).')
        parser.add_argument('--no-dry-run', dest='dry_run', action='store_false',
                            help='Grava as alterações no banco.')
        parser.add_argument('--source', default=None,
                            help='Sincroniza apenas esta fonte (cosat|utr|fpt|cbt|itf|federations).')
        parser.add_argument('--limit', type=int, default=None,
                            help='Limita o número de torneios (testes).')
        parser.add_argument('--import-entries', action='store_true', default=False,
                            help='Também importa os inscritos (FederationEntry).')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        source = opts['source']
        limit = opts['limit']
        import_entries = opts['import_entries']

        if not extractor_reader.is_available():
            raise CommandError(
                'Schema "extractor" não encontrado no banco. O serviço '
                'tournament-extractor precisa ter rodado ao menos uma vez.'
            )

        mode = 'DRY-RUN' if dry_run else 'COMMIT'
        self.stdout.write(self.style.WARNING(f'== sync_from_extractor [{mode}] =='))

        self._org_cache: dict[str, Organization] = {}
        self._ds_cache: dict[str, DataSource] = {}
        self._run_cache: dict[int, IngestionRun] = {}
        stats = Counter()

        try:
            with transaction.atomic():
                for t in extractor_reader.iter_tournaments(source=source, limit=limit):
                    self._sync_tournament(t, import_entries, stats)
                # Fecha as IngestionRun abertas (uma por fonte) para não
                # acumularem como "running" a cada execução horária.
                for run in self._run_cache.values():
                    run.status = IngestionRun.STATUS_SUCCESS
                    run.finished_at = timezone.now()
                    run.save(update_fields=['status', 'finished_at', 'updated_at'])
                if dry_run:
                    transaction.set_rollback(True)
        except Exception as exc:  # noqa: BLE001
            logger.exception('sync_from_extractor falhou: %s', exc)
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            '\nResumo: '
            f'torneios={stats["tournaments"]} criados={stats["created"]} '
            f'atualizados={stats["updated"]} inscritos={stats["entries"]} '
            f'(novos={stats["entries_created"]} antigos_removidos={stats["entries_deleted"]})'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'DRY-RUN: nada foi gravado. Rode com --no-dry-run para persistir.'
            ))

    # ------------------------------------------------------------------ helpers
    def _sync_tournament(self, t: dict, import_entries: bool, stats: Counter):
        source = t['source_name']
        org = self._resolve_org(source, t.get('federation'))
        ds = self._resolve_data_source(source, org)
        run = self._resolve_run(ds)

        data = self._build_edition_data(t, source)
        persister = TournamentPersister(data_source=ds, run=run)
        ed, created, _changes = persister.upsert(data)

        stats['tournaments'] += 1
        stats['created' if created else 'updated'] += 1
        run.items_fetched += 1
        run.items_created += 1 if created else 0
        run.items_updated += 0 if created else 1
        run.save(update_fields=['items_fetched', 'items_created', 'items_updated', 'updated_at'])

        if import_entries:
            self._sync_entries(ed, t, source, stats)

    def _build_edition_data(self, t: dict, source: str) -> dict:
        name = (t.get('name') or '').strip()
        year = None
        for d in (t.get('start_date'), t.get('end_date')):
            if d is not None:
                year = d.year
                break
        raw = t.get('raw_data') or {}
        if isinstance(raw, str):  # jsonb pode vir como str em SQL bruto
            import json
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raw = {}
        venue = {
            'name': t.get('venue') or '',
            'city': t.get('city') or '',
            'state': t.get('state') or '',
            'address': t.get('address') or '',
            'country': t.get('country') or '',
            # Código p/ a bandeira (ITF: hostNationCode; demais: nome -> código).
            'country_code': _country_code(t.get('country'), hint=raw.get('hostNationCode')),
        }
        categories = [{'source_text': c['name']} for c in t.get('categories', []) if c.get('name')]
        return {
            'external_id': f'{source}:{t.get("external_id") or t["id"]}',
            'canonical_name': name,
            'canonical_slug': _slug(name),
            'circuit': 'Infantojuvenil',
            'modality': t.get('modality') or 'tennis',
            'season_year': year or timezone.now().year,
            'title': name,
            'start_date': _iso(t.get('start_date')),
            'end_date': _iso(t.get('end_date')),
            'entry_open_at': _iso(t.get('registration_start_date')),
            'entry_close_at': _iso(t.get('registration_end_date')),
            'status': STATUS_MAP.get((t.get('status') or '').lower(), TournamentEdition.STATUS_UNKNOWN),
            'surface': TournamentEdition.SURFACE_UNKNOWN,
            'venue': venue,
            # float (não Decimal): vai para raw_payload (JSONField) e Decimal
            # não é serializável em JSON. DecimalField do modelo aceita float.
            'base_price_brl': (float(t['registration_fee'])
                               if t.get('registration_fee') is not None else None),
            'official_source_url': t.get('original_url') or '',
            'source_name': f'extractor:{source}',
            'categories': categories,
        }

    def _sync_entries(self, ed, t: dict, source: str, stats: Counter):
        entrants = t.get('entrants', [])
        if not entrants:
            # O extractor não trouxe inscritos para este torneio (ex.: lista
            # ainda não publicada). Preserva os existentes — não esvazia.
            return
        # Refresh por torneio: o extractor passa a ser a fonte dos inscritos
        # desta edição. Remove os FederationEntry atuais (de qualquer meio antigo)
        # e reinsere os do extractor, evitando duplicação. NÃO toca em
        # TournamentRegistration (inscrições internas da plataforma, outro modelo).
        deleted, _ = FederationEntry.objects.filter(edition_id=ed.id).delete()
        stats['entries_deleted'] += deleted
        for e in entrants:
            name = (e.get('name') or '').strip()
            if not name:
                continue  # nunca inventar atleta
            # Categoria real quando existe; senão um balde genérico "Inscritos"
            # (ex.: UTR traz lista nominal sem divisão por inscrito) para não
            # perder o inscrito. Não inventamos categoria de idade.
            category_text = (e.get('category_name') or '').strip() or 'Inscritos'
            pay, removed, reason = _map_payment(e)
            ext = e.get('external_id') or f'{source}:{_slug(name)}:{_slug(category_text)}'
            raw = e.get('raw_data') or {}
            if isinstance(raw, str):  # jsonb pode vir como str em SQL bruto
                import json
                try:
                    raw = json.loads(raw)
                except (ValueError, TypeError):
                    raw = {}
            # Nome cheio do país quando a fonte o fornece (ITF: raw.country_name);
            # senão usa o valor de country (que já pode ser código ou nome).
            country_name = (raw.get('country_name') or e.get('country') or '')
            country_code = _country_code(raw.get('country_code') or e.get('country'))
            _, created = FederationEntry.objects.update_or_create(
                edition_id=ed.id,
                category_text=category_text[:200],
                player_external_id=str(ext)[:100],
                source=source[:50],
                defaults={
                    'player_name': name[:200],
                    'ranking_position': e.get('position') or _int_or_none(e.get('ranking')),
                    'payment_status': pay,
                    'removed_or_replaced': removed,
                    'replacement_reason': reason[:300],
                    'source_url': t.get('original_url') or '',
                    'confidence': FederationEntry.CONFIDENCE_MEDIUM,
                    'player_country_name': country_name[:100],
                    'player_country_code': country_code,
                    'notes': (f'rating={e["rating"]}' if e.get('rating') else '')[:300],
                    'raw_data': {k: e.get(k) for k in (
                        'ranking', 'rating', 'state', 'city',
                        'payment_status', 'registration_status')},
                },
            )
            stats['entries'] += 1
            stats['entries_created'] += 1 if created else 0

    # --------------------------------------------------------- org / datasource
    def _resolve_org(self, source: str, federation_name: str | None) -> Organization:
        if source == 'federations' and federation_name:
            key = f'fed:{federation_name.strip().lower()}'
            if key not in self._org_cache:
                org, _ = Organization.objects.get_or_create(
                    name=federation_name.strip()[:200],
                    defaults={'type': Organization.TYPE_FEDERATION,
                              'short_name': federation_name.strip()[:20]},
                )
                self._org_cache[key] = org
            return self._org_cache[key]
        short, otype = SOURCE_ORG.get(source, ('CBT', Organization.TYPE_CONFEDERATION))
        if short not in self._org_cache:
            org = (Organization.objects.filter(short_name=short).first()
                   or Organization.objects.create(name=short, short_name=short, type=otype))
            self._org_cache[short] = org
        return self._org_cache[short]

    def _resolve_data_source(self, source: str, org: Organization) -> DataSource:
        slug = f'extractor-{source}-{_slug(org.short_name or org.name)}'
        if slug not in self._ds_cache:
            ds, _ = DataSource.objects.get_or_create(
                slug=slug,
                defaults={
                    'organization': org,
                    'source_name': f'Extractor — {source}',
                    'source_type': DataSource.SOURCE_TYPE_JSON,
                    'base_url': 'https://extractor.internal',
                    'connector_key': CONNECTOR_KEY,
                    'enabled': True,
                },
            )
            self._ds_cache[slug] = ds
        return self._ds_cache[slug]

    def _resolve_run(self, ds: DataSource) -> IngestionRun:
        if ds.id not in self._run_cache:
            self._run_cache[ds.id] = IngestionRun.objects.create(
                data_source=ds, status=IngestionRun.STATUS_RUNNING,
                triggered_by='sync_from_extractor',
            )
        return self._run_cache[ds.id]


def _int_or_none(v):
    if v is None:
        return None
    m = re.search(r'\d+', str(v))
    return int(m.group()) if m else None
