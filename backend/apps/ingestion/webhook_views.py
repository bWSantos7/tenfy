"""
Webhook endpoint para pipelines externos (n8n) enviarem torneios já parseados.

POST /api/ingestion/webhook/import-tournaments/
Headers: X-Import-Token: <IMPORT_API_TOKEN>

Body:
{
    "source_key": "itf_junior",
    "dry_run": true,
    "tournaments": [
        {
            "external_id": "itf:12345",
            "canonical_name": "...",
            "canonical_slug": "...",
            "circuit": "ITF Junior",
            "modality": "tennis",
            "season_year": 2026,
            "title": "...",
            "start_date": "2026-05-01",
            "end_date": "2026-05-05",
            "entry_close_at": "2026-04-20",
            "status": "open",
            "surface": "clay",
            "venue": {"name": "", "city": "São Paulo", "state": "SP", "address": ""},
            "base_price_brl": null,
            "official_source_url": "https://...",
            "categories": [{"source_text": "Boys U18", "price_brl": null, "notes": ""}],
            "links": [{"link_type": "other", "url": "https://...", "label": "ITF"}]
        }
    ]
}

dry_run=true → valida e retorna preview sem salvar nada (obrigatório revisar antes do save real).
dry_run=false → persiste via TournamentPersister. Requer aprovação explícita.
"""
import hmac
import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.sources.models import DataSource
from apps.tournaments.models import TournamentEdition
from .models import IngestionRun
from .persistence import TournamentPersister

logger = logging.getLogger('apps.ingestion.webhook')

_REQUIRED_FIELDS = {'external_id', 'title', 'canonical_name', 'canonical_slug', 'season_year'}

# Configurações mínimas para criar DataSources automaticamente se não existirem
_DATASOURCE_DEFAULTS = {
    'itf_junior': {
        'org_name': 'International Tennis Federation',
        'org_short': 'ITF',
        'org_type': 'confederation',
        'source_name': 'ITF Junior Circuit',
        'source_type': 'json',
        'base_url': 'https://www.itftennis.com',
        'priority': 'P1',
    },
    'utr_public': {
        'org_name': 'Universal Tennis Rating',
        'org_short': 'UTR',
        'org_type': 'platform',
        'source_name': 'UTR Sports Brazil',
        'source_type': 'json',
        'base_url': 'https://api.utrsports.net',
        'priority': 'P2',
    },
}


def _get_or_create_datasource(source_key: str):
    """Cria DataSource e Organization se não existirem, sem depender de seed_sources."""
    from apps.sources.models import Organization
    defaults = _DATASOURCE_DEFAULTS.get(source_key)
    if not defaults:
        logger.warning('webhook: sem defaults para source_key=%s', source_key)
        return None
    try:
        org, _ = Organization.objects.get_or_create(
            name=defaults['org_name'],
            defaults={
                'short_name': defaults['org_short'],
                'type': defaults['org_type'],
            },
        )
        import re, unicodedata
        slug = re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', source_key).encode('ascii', 'ignore').decode().lower()).strip('-')
        ds, created = DataSource.objects.get_or_create(
            connector_key=source_key,
            defaults={
                'organization': org,
                'slug': slug,
                'source_name': defaults['source_name'],
                'source_type': defaults['source_type'],
                'base_url': defaults['base_url'],
                'priority': defaults['priority'],
                'enabled': True,
            },
        )
        if created:
            logger.info('webhook: DataSource "%s" criado automaticamente', source_key)
        return ds
    except Exception as exc:
        logger.error('webhook: falha ao criar DataSource "%s": %s', source_key, exc)
        return None


def _check_auth(request) -> bool:
    if request.user and request.user.is_authenticated and request.user.is_staff:
        return True
    token = getattr(settings, 'IMPORT_API_TOKEN', '')
    if not token:
        return False
    incoming = request.META.get('HTTP_X_IMPORT_TOKEN', '')
    return bool(incoming) and hmac.compare_digest(incoming.encode(), token.encode())


def _validate_tournament(t: dict) -> str | None:
    """Retorna mensagem de erro ou None se válido."""
    missing = _REQUIRED_FIELDS - {k for k, v in t.items() if v}
    if missing:
        return f'campos obrigatórios ausentes: {", ".join(sorted(missing))}'
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def import_tournaments_webhook(request):
    if not _check_auth(request):
        return Response({'detail': 'Autenticação necessária.'}, status=status.HTTP_403_FORBIDDEN)

    source_key = request.data.get('source_key', '').strip()
    dry_run = bool(request.data.get('dry_run', True))
    tournaments = request.data.get('tournaments', [])

    if not source_key:
        return Response({'detail': '"source_key" é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(tournaments, list) or not tournaments:
        return Response({'detail': '"tournaments" deve ser uma lista não-vazia.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        data_source = DataSource.objects.select_related('organization').get(connector_key=source_key)
    except DataSource.DoesNotExist:
        data_source = _get_or_create_datasource(source_key)
        if data_source is None:
            return Response(
                {'detail': f'DataSource "{source_key}" não encontrado e não foi possível criar automaticamente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if dry_run:
        return _dry_run_response(tournaments, source_key)

    return _persist_tournaments(tournaments, data_source)


def _dry_run_response(tournaments: list, source_key: str) -> Response:
    preview = []
    valid = invalid = 0

    for t in tournaments:
        err = _validate_tournament(t)
        ext_id = t.get('external_id', '?')
        exists = TournamentEdition.objects.filter(external_id=ext_id).exists() if t.get('external_id') else None
        if err:
            preview.append({'external_id': ext_id, 'status': 'invalid', 'reason': err})
            invalid += 1
        else:
            preview.append({
                'external_id': ext_id,
                'title': t.get('title'),
                'start_date': t.get('start_date'),
                'end_date': t.get('end_date'),
                'status': t.get('status'),
                'venue_city': (t.get('venue') or {}).get('city', ''),
                'action': 'update' if exists else 'create',
            })
            valid += 1

    return Response({
        'dry_run': True,
        'source_key': source_key,
        'total': len(tournaments),
        'valid': valid,
        'invalid': invalid,
        'preview': preview,
    })


def _persist_tournaments(tournaments: list, data_source: DataSource) -> Response:
    run = IngestionRun.objects.create(
        data_source=data_source,
        triggered_by='webhook_n8n',
    )

    persister = TournamentPersister(data_source=data_source, run=run)
    created = updated = skipped = 0
    errors = []

    for t in tournaments:
        err = _validate_tournament(t)
        if err:
            skipped += 1
            errors.append({'external_id': t.get('external_id', '?'), 'error': err})
            continue

        ext_id = t.get('external_id', '')
        pre_exists = TournamentEdition.objects.filter(external_id=ext_id).exists()

        try:
            persister.upsert(t)
            if pre_exists:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            skipped += 1
            errors.append({'external_id': ext_id, 'error': str(exc)})
            logger.error('webhook upsert error ext_id=%s: %s', ext_id, exc)

    run.finished_at = timezone.now()
    run.items_fetched = len(tournaments)
    run.items_created = created
    run.items_updated = updated
    run.status = IngestionRun.STATUS_SUCCESS if not errors else IngestionRun.STATUS_PARTIAL
    run.error_summary = '; '.join(e['error'] for e in errors[:5]) if errors else ''
    run.save(update_fields=[
        'finished_at', 'items_fetched', 'items_created', 'items_updated', 'status', 'error_summary', 'updated_at',
    ])

    logger.info(
        'webhook import done source=%s run=%s created=%d updated=%d skipped=%d errors=%d',
        data_source.connector_key, run.pk, created, updated, skipped, len(errors),
    )

    return Response({
        'dry_run': False,
        'run_id': run.pk,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
    }, status=status.HTTP_200_OK)
