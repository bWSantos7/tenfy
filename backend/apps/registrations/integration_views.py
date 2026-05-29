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
from apps.registrations.parsers import get_parser, get_limitation, supports_auto_fetch
from apps.tournaments.models import TournamentEdition

logger = logging.getLogger('apps.registrations.integration')


def _bulk_update_sync_fields(updates: list):
    """
    Bulk-update sync tracking fields on TournamentEdition rows.
    Each item in updates must have 'id' plus any subset of:
      entries_source_url, candidate_entry_links, needs_sync,
      sync_priority, parser_available, parser_limitation.
    Skips rows where is_manual_override=True to avoid overwriting admin data.
    """
    if not updates:
        return
    update_fields = [
        'entries_source_url', 'candidate_entry_links', 'needs_sync',
        'sync_priority', 'parser_available', 'parser_limitation',
    ]
    id_map = {u['id']: u for u in updates}
    editions = list(
        TournamentEdition.objects
        .filter(pk__in=id_map.keys(), is_manual_override=False)
        .only('id', *update_fields)
    )
    for edition in editions:
        upd = id_map[edition.id]
        for field in update_fields:
            if field in upd:
                setattr(edition, field, upd[field])
    if editions:
        TournamentEdition.objects.bulk_update(editions, update_fields)
        logger.debug('federation_sync_targets: bulk-updated %d editions', len(editions))


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
    'FBT':   'fbt',
    'FCT':   'fct',
    'FMT':   'fmt',
    'COSAT': 'cosat',
    'ITF':   'itf',
    'UTR':   'utr',
}

# connector_key prefix → source
_CONNECTOR_TO_SOURCE = {
    'cbt_':    'cbt',
    'fpt_':    'fpt',
    'fbt_':    'fbt',
    'fct_':    'fct',
    'fmt_':    'fmt',
    'cosat_':  'cosat',
    'itf_':    'itf',
    'utr_':    'utr',
    'cbt':     'cbt',
    'fpt':     'fpt',
    'fbt':     'fbt',
    'fct':     'fct',
    'cosat':   'cosat',
}

# URL domain → source (tenisintegrado handled separately: could be cbt/fct/fmt)
_URL_DOMAIN_TO_SOURCE = [
    ('fbt.com.br',                   'fbt'),
    ('cbt-tenis.com.br',             'cbt'),
    ('tennistool.tenisintegrado.com', None),   # need connector_key to distinguish
    ('tenisintegrado.com.br',        None),    # need connector_key to distinguish
    ('tournamentsoftware.com',       'cosat'),
    ('itftennis.com',                'itf'),
    ('utrsports.net',                'utr'),
]

# Inscription link URL path patterns (lowercased)
_ENTRY_LINK_PATTERNS = [
    '/inscrit', '/inscricao', '/inscrição', '/entry', '/entries',
    '/players', '/draw', '/chaves', '/acceptance', '/participant',
    '/torneio_painel', '/inscritos',
]
_RANKING_LINK_PATTERNS = ['/ranking', '/classificacao', '/classification']


def infer_source_from_url(url: str) -> str:
    """
    Infer federation source from URL domain.
    Returns source key or '' when domain not recognised.

    Note: tenisintegrado.com.br returns '' (ambiguous: could be CBT, FCT, FMT).
    Use infer_source_from_edition() for full resolution with connector_key context.
    """
    if not url:
        return ''
    url_lower = url.lower()
    for domain, src in _URL_DOMAIN_TO_SOURCE:
        if domain in url_lower:
            return src or ''   # None → '' for ambiguous domains
    return ''


def infer_source_from_edition(edition: TournamentEdition) -> str:
    """
    Infer source using full edition context, in priority order:

    1. data_source.connector_key  — most reliable; set by ingestion pipeline
    2. tournament.circuit         — set when ingested from known circuit
    3. official_source_url domain — URL pattern matching
    4. source_name                — fallback text hint
    5. raw_payload host fields    — CBT payload has 'host' key
    6. 'manual'                   — default when no evidence found

    For tenisintegrado.com.br (ambiguous): resolves to cbt/fct/fmt via
    connector_key or circuit; defaults to 'cbt' when unknown (most common).
    """
    # 1. connector_key from data_source FK
    try:
        ck = (getattr(edition.data_source, 'connector_key', None) or '').lower()
        if ck:
            for prefix, src in _CONNECTOR_TO_SOURCE.items():
                if ck.startswith(prefix) or ck == prefix.rstrip('_'):
                    return src
    except Exception:
        pass

    # 2. circuit field
    circuit = (edition.tournament.circuit or '').upper().strip()
    for key, src in _CIRCUIT_TO_SOURCE.items():
        if key in circuit:
            return src

    # 3. official_source_url domain
    url = edition.official_source_url or ''
    url_src = infer_source_from_url(url)
    if url_src:
        return url_src

    # tenisintegrado is ambiguous — check hints before defaulting to cbt
    if 'tenisintegrado' in url.lower():
        # FPT SP uses fpt.tenisintegrado.com.br — check URL subdomain first
        if 'fpt.tenisintegrado' in url.lower():
            return 'fpt'
        # Check source_name for FCT/FMT/FPT hint
        sname = (edition.source_name or '').upper()
        if 'FCT' in sname:
            return 'fct'
        if 'FMT' in sname:
            return 'fmt'
        if 'FPT' in sname:
            return 'fpt'
        # Check raw_payload host field
        payload = edition.raw_payload or {}
        host = str(payload.get('host', '')).lower()
        if 'fct' in host:
            return 'fct'
        if 'fmt' in host:
            return 'fmt'
        if 'fpt' in host:
            return 'fpt'
        # Default for tenisintegrado when no distinguishing hint: cbt (most common)
        return 'cbt'

    # 4. source_name text hint
    sname_upper = (edition.source_name or '').upper()
    for key, src in _CIRCUIT_TO_SOURCE.items():
        if key in sname_upper:
            return src

    return 'manual'


def _edition_source(edition: TournamentEdition) -> str:
    """Wrapper kept for backward compat — delegates to infer_source_from_edition."""
    return infer_source_from_edition(edition)


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

    # 1b. source_url itself may already be an inscription/entries page
    # (e.g. FPT /Inscricao/InscricaoTorneio/ or tenisintegrado /torneio_painel_info/)
    if source_url and any(p in source_url.lower() for p in _ENTRY_LINK_PATTERNS):
        entries_url = source_url
        return entries_url, ranking_url, candidates

    # 2. CBT/Tenisintegrado: check raw_payload + extract tournament ID
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
        m_eid = re.match(r'(?:cbt|fct|fmt):(\d+)', edition.external_id or '')
        if not m_eid:
            # Also try extracting from URL: /torneio_painel_info/index/<id>
            m_eid = re.search(r'/(?:torneio_painel_info|torneio)/(?:index/)?(\d+)', source_url)
        if m_eid:
            tid = m_eid.group(1)
            ti_candidates = [
                f'https://www.tenisintegrado.com.br/torneio_painel_info/index/{tid}',
                f'https://www.tenisintegrado.com.br/torneio/{tid}/inscricoes',
                f'https://www.tenisintegrado.com.br/torneio/{tid}',
            ]
            candidates.extend(ti_candidates)
            if not entries_url:
                entries_url = ti_candidates[0]

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
        .select_related('tournament', 'data_source')   # data_source needed for connector_key
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
    _editions_to_update = []
    for edition in qs[:limit * 3]:
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

        parser_avail = bool(get_parser(source))
        parser_limit = get_limitation(source) if source != 'manual' else (
            get_limitation(infer_source_from_url(edition.official_source_url))
            or get_limitation('manual')
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
            'parser_available': parser_avail,
            'parser_limitation': parser_limit,
        })

        # Persist computed sync fields to model (bulk-update below to avoid N+1 saves)
        _editions_to_update.append({
            'id': edition.id,
            'entries_source_url': entries_url[:500] if entries_url else '',
            'candidate_entry_links': candidate_links[:5],
            'needs_sync': needs_sync,
            'sync_priority': priority,
            'parser_available': parser_avail,
            'parser_limitation': (parser_limit or '')[:300],
        })
        # Note: source is already inferred — 'manual' only when truly unrecognised

    results.sort(
        key=lambda r: (-r['sync_priority'], r['entry_close_at'] or now.replace(year=2099)),
    )

    # Bulk-persist computed sync fields back to the model (fire-and-forget, non-blocking)
    if _editions_to_update:
        try:
            _bulk_update_sync_fields(_editions_to_update)
        except Exception as exc:
            logger.warning('federation_sync_targets: bulk sync field update failed: %s', exc)

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

    source_requested = (request.data.get('source') or 'manual').strip().lower()
    html_or_text = (request.data.get('html_or_text') or '').strip()
    source_url = (request.data.get('source_url') or '').strip()

    # Auto-detect source from URL when source=manual but URL indicates a known federation
    source_detected = source_requested
    if source_requested == 'manual' and source_url:
        inferred = infer_source_from_url(source_url)
        if inferred:
            source_detected = inferred
            logger.info(
                'parse-entries: source_requested=manual but URL suggests %s (%s) — using %s parser',
                inferred, source_url[:80], inferred,
            )
        elif 'tenisintegrado' in source_url.lower():
            source_detected = 'cbt'   # default for tenisintegrado ambiguity

    source = source_detected   # parser uses detected source

    parser = get_parser(source)
    if not parser:
        return Response({
            'entries': [],
            'parser_warning': True,
            'warning_message': (
                f'Source "{source}" não tem parser. '
                f'Fontes: {", ".join(sorted(["cosat","cbt","fbt","fpt","fct","manual"]))}'
            ),
            'confidence': 'low',
            'source_requested': source_requested,
            'source_detected': source_detected,
            'parser_used': None,
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

    entries = result.get('entries', [])
    count = len(entries)
    parser_warning = result.get('parser_warning', False)
    confidence = result.get('confidence', 'low')
    warning_message = result.get('warning_message', '')

    # Count entries with synthetic (deterministic) external_id — colons indicate auto-generated
    # Format: "source:name-slug:category-slug" — distinct from real federation IDs
    synthetic_count = sum(
        1 for e in entries
        if (e.get('player_external_id') or '').startswith(f'{source}:')
    )

    # Normalize warnings: always a list for n8n consistency
    warnings_list = [warning_message] if warning_message else []

    # Determine if auto-fetch was used (parser fetched data from source_url, no html input)
    html_empty = not (html_or_text or '').strip()
    _source_supports_auto_fetch = supports_auto_fetch(source)
    auto_fetch_used = (
        html_empty
        and _source_supports_auto_fetch
        and bool(source_url)
    )
    # Auto-fetch succeeded when it was used and the parser returned real entries
    auto_fetch_succeeded = (
        auto_fetch_used
        and count > 0
        and not parser_warning
        and confidence != 'low'
    )

    # Quality gate — n8n uses can_save to decide whether to proceed to import
    reasons_no_save = []
    if count == 0:
        reasons_no_save.append('entries vazio — nenhum inscrito extraído')
    if parser_warning:
        reasons_no_save.append('parser_warning ativo — fonte sem lista nominal acessível')
    if confidence == 'low':
        reasons_no_save.append('confidence=low — dados insuficientes para importação automática')
    # html_or_text empty is only a blocker when auto-fetch was NOT used successfully.
    # For sources with auto-fetch (e.g. CBT), empty html is expected and valid.
    if html_empty and not auto_fetch_succeeded:
        reasons_no_save.append('html_or_text vazio — nenhum conteúdo para parsear')

    quality_gate = {
        'can_save': len(reasons_no_save) == 0,
        'reasons': reasons_no_save,
        'entries_count': count,
        'synthetic_ids_count': synthetic_count,
        'confidence': confidence,
        'parser_warning': parser_warning,
    }

    result.update({
        'count': count,
        'source_url': source_url,
        'source_requested': source_requested,
        'source_detected': source_detected,
        'parser_used': source_detected,
        'supports_auto_fetch': _source_supports_auto_fetch,
        'auto_fetch_used': auto_fetch_used,
        'warnings': warnings_list,
        'quality_gate': quality_gate,
    })
    return Response(result)
