"""
Federation integration views.

GET /api/integrations/federation-sync-targets/
  Returns tournament editions that need federation entry sync, ordered by priority.
  Auth: staff JWT or X-Import-Token.

POST /api/integrations/parse-entries/
  Parse raw HTML/text/CSV into entry list without saving.
  Returns entries + parser_warning. No DB write.
  Auth: staff JWT or X-Import-Token.
"""
import logging
from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from apps.registrations.views import _check_import_auth
from apps.registrations.models import FederationEntry
from apps.registrations.parsers import get_parser, get_limitation, PARSER_LIMITATIONS
from apps.tournaments.models import TournamentEdition

logger = logging.getLogger('apps.registrations.integration')

# Statuses worth syncing (exclude finished/canceled)
_SYNC_STATUSES = {
    TournamentEdition.STATUS_OPEN,
    TournamentEdition.STATUS_CLOSING_SOON,
    TournamentEdition.STATUS_ANNOUNCED,
    TournamentEdition.STATUS_DRAWS_PUBLISHED,
    TournamentEdition.STATUS_IN_PROGRESS,
    TournamentEdition.STATUS_CLOSED,   # closed but entries may still update
    TournamentEdition.STATUS_UNKNOWN,
}

# Circuit name → source identifier
_CIRCUIT_TO_SOURCE = {
    'CBT':   'cbt',
    'FPT':   'fpt',
    'FCT':   'fct',
    'COSAT': 'cosat',
    'ITF':   'itf',
    'UTR':   'utr',
}


def _edition_source(edition: TournamentEdition) -> str:
    """Infer source from circuit name."""
    circuit = (edition.tournament.circuit or '').upper().strip()
    for key, src in _CIRCUIT_TO_SOURCE.items():
        if key in circuit:
            return src
    return 'manual'


def _sync_priority(edition: TournamentEdition, dynamic_status: str,
                   last_synced_at) -> int:
    """
    0–30 priority score. Higher = sync sooner.
    """
    score = 0
    now = timezone.now()

    # Status priority
    if dynamic_status in ('open', 'closing_soon'):
        score += 10
    elif dynamic_status in ('draws_published', 'in_progress'):
        score += 7
    elif dynamic_status == 'announced':
        score += 3
    elif dynamic_status == 'closed':
        score += 2

    # Never synced
    if last_synced_at is None:
        score += 8
    else:
        hours_since = (now - last_synced_at).total_seconds() / 3600
        if hours_since > 48:
            score += 6
        elif hours_since > 24:
            score += 4
        elif hours_since > 6:
            score += 1

    # Entry close proximity
    if edition.entry_close_at:
        days_to_close = (edition.entry_close_at - now).days
        if 0 <= days_to_close <= 3:
            score += 7
        elif 0 <= days_to_close <= 7:
            score += 4
        elif -7 <= days_to_close < 0:
            score += 2  # recently closed

    return min(score, 30)


class SyncTargetSerializer(serializers.Serializer):
    edition_id          = serializers.IntegerField()
    tournament_name     = serializers.CharField()
    circuit             = serializers.CharField()
    source              = serializers.CharField()
    source_url          = serializers.CharField()
    status              = serializers.CharField()
    dynamic_status      = serializers.CharField()
    start_date          = serializers.DateField(allow_null=True)
    entry_close_at      = serializers.DateTimeField(allow_null=True)
    last_synced_at      = serializers.DateTimeField(allow_null=True)
    needs_sync          = serializers.BooleanField()
    sync_priority       = serializers.IntegerField()
    parser_available    = serializers.BooleanField()
    parser_limitation   = serializers.CharField()


@api_view(['GET'])
@permission_classes([AllowAny])
def federation_sync_targets(request):
    """
    GET /api/integrations/federation-sync-targets/

    Returns tournament editions that need federation entry sync, ordered by priority.
    Excludes: finished, canceled, and editions without official_source_url.

    Filters:
      ?source=cosat|cbt|fpt|...
      ?needs_sync=true
      ?limit=50 (default 100)
    """
    if not _check_import_auth(request):
        return Response(
            {'detail': 'Autenticação necessária. Use JWT de staff ou X-Import-Token.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    source_filter = request.query_params.get('source', '').strip().lower()
    needs_sync_only = request.query_params.get('needs_sync', '').lower() == 'true'
    limit = min(int(request.query_params.get('limit', 100)), 500)

    now = timezone.now()
    stale_threshold = now - timedelta(hours=12)

    # Base queryset: has source URL, not finished/canceled
    qs = (
        TournamentEdition.objects
        .select_related('tournament')
        .filter(official_source_url__gt='')
        .exclude(status__in=[TournamentEdition.STATUS_FINISHED, TournamentEdition.STATUS_CANCELED])
    )

    # Get last_synced_at per edition from FederationEntry
    synced_map = dict(
        FederationEntry.objects
        .filter(edition__in=qs)
        .values('edition_id')
        .annotate(last=Max('synced_at'))
        .values_list('edition_id', 'last')
    )

    results = []
    for edition in qs.select_related('tournament')[:limit * 3]:
        source = _edition_source(edition)
        dynamic_status = edition.compute_dynamic_status()

        # Skip non-syncable statuses
        if dynamic_status not in _SYNC_STATUSES and edition.status not in _SYNC_STATUSES:
            continue

        last_synced = synced_map.get(edition.id)
        needs_sync = (last_synced is None) or (last_synced < stale_threshold)

        # Source filter
        if source_filter and source != source_filter:
            continue
        if needs_sync_only and not needs_sync:
            continue

        priority = _sync_priority(edition, dynamic_status, last_synced)

        results.append({
            'edition_id': edition.id,
            'tournament_name': edition.title,
            'circuit': edition.tournament.circuit or '',
            'source': source,
            'source_url': edition.official_source_url,
            'status': edition.status,
            'dynamic_status': dynamic_status,
            'start_date': edition.start_date,
            'entry_close_at': edition.entry_close_at,
            'last_synced_at': last_synced,
            'needs_sync': needs_sync,
            'sync_priority': priority,
            'parser_available': bool(get_parser(source)),
            'parser_limitation': get_limitation(source),
        })

    # Sort by priority desc, then by entry_close_at asc (soonest first)
    results.sort(
        key=lambda r: (-r['sync_priority'], r['entry_close_at'] or now.replace(year=2099)),
    )

    return Response({
        'count': len(results[:limit]),
        'total_with_source_url': qs.count(),
        'results': results[:limit],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def parse_entries(request):
    """
    POST /api/integrations/parse-entries/

    Parse raw HTML/text/CSV into entry list without saving to DB.
    Use this to preview what would be imported before calling /api/registrations/import/.

    Payload:
      {
        "source": "cosat|cbt|fpt|manual",
        "html_or_text": "<html>...</html> or CSV text or plain text",
        "source_url": "https://..."  (optional, attached to each entry)
      }

    Returns:
      {
        "entries": [...],        # ready for /api/registrations/import/
        "parser_warning": bool,
        "warning_message": str,
        "confidence": str,
        "source": str,
        "count": int
      }
    """
    if not _check_import_auth(request):
        return Response(
            {'detail': 'Autenticação necessária. Use JWT de staff ou X-Import-Token.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    source = (request.data.get('source') or 'manual').strip().lower()
    html_or_text = (request.data.get('html_or_text') or '').strip()
    source_url = (request.data.get('source_url') or '').strip()

    parser = get_parser(source)
    if not parser:
        return Response({
            'entries': [],
            'parser_warning': True,
            'warning_message': f'Source "{source}" não tem parser registrado. Fontes: {", ".join(sorted(["cosat","cbt","fpt","fct","manual"]))}',
            'confidence': 'low',
            'source': source,
            'count': 0,
        })

    try:
        result = parser(html_or_text, source_url=source_url)
    except Exception as exc:
        logger.warning('Parser failed for source=%s: %s', source, exc)
        result = {
            'entries': [],
            'parser_warning': True,
            'warning_message': f'Erro no parser: {exc}',
            'confidence': 'low',
            'source': source,
        }

    result['count'] = len(result.get('entries', []))
    return Response(result)
