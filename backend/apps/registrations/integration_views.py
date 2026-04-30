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
import re
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from apps.registrations.views import _check_import_auth
from apps.registrations.models import FederationEntry
from apps.registrations.parsers import get_parser, get_limitation
from apps.tournaments.models import TournamentEdition

logger = logging.getLogger('apps.registrations.integration')

# Statuses worth syncing (exclude finished/canceled)
_SYNC_STATUSES = {
    TournamentEdition.STATUS_OPEN,
    TournamentEdition.STATUS_CLOSING_SOON,
    TournamentEdition.STATUS_ANNOUNCED,
    TournamentEdition.STATUS_DRAWS_PUBLISHED,
    TournamentEdition.STATUS_IN_PROGRESS,
    TournamentEdition.STATUS_CLOSED,
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

# Inscription link URL path patterns (lowercased)
_ENTRY_LINK_PATTERNS = [
    '/inscrit', '/inscricao', '/inscrição', '/entry', '/entries',
    '/players', '/draw', '/chaves', '/acceptance', '/participant',
]
_RANKING_LINK_PATTERNS = ['/ranking', '/classificacao', '/classification']


def _edition_source(edition: TournamentEdition) -> str:
    """Infer source from circuit name."""
    circuit = (edition.tournament.circuit or '').upper().strip()
    for key, src in _CIRCUIT_TO_SOURCE.items():
        if key in circuit:
            return src
    return 'manual'


def derive_entries_source_url(edition: TournamentEdition):
    """
    Compute (entries_source_url, ranking_source_url, candidate_entry_links)
    without making HTTP requests. Pure DB lookup + URL pattern derivation.

    Uses edition.links.all() (prefetch_related cache) instead of per-edition
    TournamentLink.objects.filter() calls — avoids N+1 queries when the view
    calls prefetch_related('links') on the queryset.

    Returns:
        entries_source_url: str  — best known URL for the entry/inscritos page
        ranking_source_url: str  — best known URL for ranking page
        candidate_links:    list — other URLs worth trying
    """
    source_url = edition.official_source_url or ''
    entries_url = ''
    ranking_url = ''
    candidates = []

    # 1. Use prefetched links (no extra DB query when prefetch_related('links') used)
    try:
        from apps.tournaments.models import TournamentLink
        # edition.links.all() hits the prefetch cache — O(1), no N+1
        all_links = list(edition.links.all())
        for link in all_links:
            lurl = (link.url or '').lower()
            if link.link_type == TournamentLink.TYPE_REGISTRATION and not entries_url:
                entries_url = link.url
                candidates.append(link.url)
            elif any(p in lurl for p in _ENTRY_LINK_PATTERNS) and link.url not in candidates:
                candidates.append(link.url)
            elif any(p in lurl for p in _RANKING_LINK_PATTERNS):
                ranking_url = ranking_url or link.url
    except Exception as exc:
        logger.debug('TournamentLink lookup failed for edition %s: %s', edition.id, exc)

    if entries_url:
        return entries_url, ranking_url, candidates

    # 2. FPT: try to derive inscrição URL from /Torneio/Info/ pattern
    if 'fpt.com.br' in source_url:
        m = re.search(r'/Torneio/Info/(.+)-(\d+)/?$', source_url)
        if m:
            slug, tid = m.group(1), m.group(2)
            fpt_candidates = [
                f'https://fpt.com.br/Inscricao/Torneio/{slug}-{tid}',
                f'https://fpt.com.br/Torneio/Inscritos/{slug}-{tid}',
                f'https://fpt.com.br/Inscricao/Lista/{slug}-{tid}',
            ]
            candidates.extend(fpt_candidates)
            # First candidate is best guess
            if not entries_url:
                entries_url = fpt_candidates[0]

    # 3. CBT: check raw_payload for redirect URLs that may have entry pages
    if not entries_url and ('tenisintegrado' in source_url or 'cbt-tenis' in source_url.lower()):
        payload = edition.raw_payload or {}
        redirect = (
            payload.get('redirect_tenisintegrado')
            or payload.get('redirect_site_personal')
            or ''
        ).strip()
        if redirect and redirect != source_url:
            candidates.append(redirect)
        # Extract tournament ID from external_id: cbt:12345
        m = re.match(r'cbt:(\d+)', edition.external_id or '')
        if m:
            tid = m.group(1)
            cbt_candidates = [
                f'https://www.tenisintegrado.com.br/torneio/{tid}',
                f'https://www.tenisintegrado.com.br/torneio/{tid}/inscricoes',
            ]
            candidates.extend(cbt_candidates)

    # 4. COSAT: official_source_url is best we have
    if not entries_url and 'tournamentsoftware' in source_url:
        # Can't add /entry suffix without knowing tournament ID format
        # Limitation noted — robots.txt also blocks /sport/
        pass

    # 5. Deduplicate candidates (preserve order)
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    return entries_url or '', ranking_url or '', unique_candidates


def _sync_priority(edition: TournamentEdition, dynamic_status: str,
                   last_synced_at) -> int:
    """0–30 priority score. Higher = sync sooner."""
    score = 0
    now = timezone.now()

    if dynamic_status in ('open', 'closing_soon'):
        score += 10
    elif dynamic_status in ('draws_published', 'in_progress'):
        score += 7
    elif dynamic_status == 'announced':
        score += 3
    elif dynamic_status == 'closed':
        score += 2

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

    if edition.entry_close_at:
        days_to_close = (edition.entry_close_at - now).days
        if 0 <= days_to_close <= 3:
            score += 7
        elif 0 <= days_to_close <= 7:
            score += 4
        elif -7 <= days_to_close < 0:
            score += 2

    return min(score, 30)


@api_view(['GET'])
@permission_classes([AllowAny])
def federation_sync_targets(request):
    """
    GET /api/integrations/federation-sync-targets/

    Returns tournament editions that need federation entry sync, ordered by priority.
    Excludes: finished, canceled, editions without official_source_url.

    Filters:
      ?source=cosat|cbt|fpt|...
      ?needs_sync=true
      ?limit=50 (default 100, max 500)

    Response includes computed fields:
      entries_source_url   — best URL for the entry/inscritos page
      ranking_source_url   — best URL for rankings (when derivable)
      candidate_entry_links — other URLs worth trying
    """
    if not _check_import_auth(request):
        return Response(
            {'detail': 'Autenticação necessária. Use JWT de staff ou X-Import-Token.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    source_filter = request.query_params.get('source', '').strip().lower()
    needs_sync_only = request.query_params.get('needs_sync', '').lower() == 'true'
    try:
        limit = int(request.query_params.get('limit', 100))
    except (ValueError, TypeError):
        limit = 100
    limit = max(1, min(limit, 500))

    now = timezone.now()
    stale_threshold = now - timedelta(hours=12)

    qs = (
        TournamentEdition.objects
        .select_related('tournament')
        .prefetch_related('links')
        .filter(official_source_url__gt='')
        .exclude(status__in=[TournamentEdition.STATUS_FINISHED, TournamentEdition.STATUS_CANCELED])
    )

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

        if dynamic_status not in _SYNC_STATUSES and edition.status not in _SYNC_STATUSES:
            continue

        last_synced = synced_map.get(edition.id)
        needs_sync = (last_synced is None) or (last_synced < stale_threshold)

        if source_filter and source != source_filter:
            continue
        if needs_sync_only and not needs_sync:
            continue

        priority = _sync_priority(edition, dynamic_status, last_synced)
        entries_url, ranking_url, candidate_links = derive_entries_source_url(edition)

        # preferred_entries_url: best URL for n8n to fetch entry data
        # Order: registration link > derived entries URL > first candidate > source_url
        preferred_entries_url = (
            entries_url
            or (candidate_links[0] if candidate_links else '')
            or edition.official_source_url
        )

        results.append({
            'edition_id': edition.id,
            'tournament_name': edition.title,
            'circuit': edition.tournament.circuit or '',
            'source': source,
            'source_url': edition.official_source_url,
            'entries_source_url': entries_url,
            'preferred_entries_url': preferred_entries_url,
            'ranking_source_url': ranking_url,
            'candidate_entry_links': candidate_links[:5],
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

    Payload:
      { "source": str, "html_or_text": str, "source_url": str }
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
            'warning_message': (
                f'Source "{source}" não tem parser. '
                f'Fontes: {", ".join(sorted(["cosat","cbt","fpt","fct","manual"]))}'
            ),
            'confidence': 'low',
            'source': source,
            'count': 0,
        })

    try:
        result = parser(html_or_text, source_url=source_url)
    except Exception as exc:
        logger.warning('Parser failed source=%s: %s', source, exc)
        result = {
            'entries': [],
            'parser_warning': True,
            'warning_message': f'Erro no parser: {exc}',
            'confidence': 'low',
            'source': source,
        }

    result['count'] = len(result.get('entries', []))
    return Response(result)
