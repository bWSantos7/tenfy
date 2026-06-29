import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Alert, DevicePushToken, PushSubscription, UserAlertPreference
from apps.watchlist.models import WatchlistItem
from apps.tournaments.models import TournamentEdition, TournamentChangeEvent

logger = logging.getLogger('apps.alerts')

# Erros de push permanentes (configuração) — não adianta reagendar a task.
_PERMANENT_PUSH_ERRORS = {'no_vapid_key', 'pywebpush_not_installed'}


def _get_parents_of(user):
    """Return dicts with parent and child info for active ParentChild links."""
    from apps.accounts.models import ParentChild
    return list(
        ParentChild.objects
        .filter(child=user, is_active=True)
        .values('parent__id', 'parent__email',
                'parent__full_name', 'child__full_name', 'child__email')
    )


def _notify_parents(item, kind, title, body, dedup_base, payload=None):
    """
    For each active parent of item.user, create an in-app and/or push alert
    with the child's name prepended to the title.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for row in _get_parents_of(item.user):
        parent = User.objects.get(pk=row['parent__id'])
        child_name = row['child__full_name'] or row['child__email']
        parent_title = f'{child_name} — {title}'
        prefs = UserAlertPreference.get_or_create_defaults(parent)
        if not prefs.in_app_enabled and not prefs.push_enabled:
            continue
        dedup_parent = f'{dedup_base}:parent:{parent.pk}'
        if prefs.in_app_enabled:
            _create_alert(
                user=parent, edition=item.edition,
                kind=kind, channel=Alert.CHANNEL_IN_APP,
                title=parent_title, body=body,
                payload=payload or {},
                dedup_key=dedup_parent + ':app',
            )
        if prefs.push_enabled:
            _create_alert(
                user=parent, edition=item.edition,
                kind=kind, channel=Alert.CHANNEL_PUSH,
                title=parent_title, body=body,
                payload=payload or {},
                dedup_key=dedup_parent + ':push',
            )

# Human-readable labels for tournament field names shown in change alerts
_FIELD_LABELS: dict[str, str] = {
    'entry_close_at':   'Prazo de inscrição',
    'start_date':       'Data de início',
    'end_date':         'Data de término',
    'venue':            'Local',
    'venue_name':       'Local',
    'city':             'Cidade',
    'state':            'Estado',
    'status':           'Status',
    'title':            'Nome do torneio',
    'max_participants': 'Vagas',
    'price':            'Valor da inscrição',
    'draws_url':        'Link das chaves',
    'official_source_url': 'Link oficial',
    'category':         'Categoria',
    'surface':          'Superfície',
}

_STATUS_LABELS: dict[str, str] = {
    'open':          'Aberto',
    'closing_soon':  'Fechando em breve',
    'closed':        'Encerrado',
    'finished':      'Finalizado',
    'canceled':      'Cancelado',
    'upcoming':      'Em breve',
}


def _fmt_value(field_name: str, value) -> str:
    """Format a raw field value into a user-friendly string."""
    if value is None:
        return 'não informado'
    v = str(value)
    # ISO datetime → Brazilian format. Uses stdlib zoneinfo (Django 5 native) so it
    # never depends on the optional pytz package being installed.
    if 'T' in v and ('+' in v or 'Z' in v or len(v) > 16):
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            local = dt.astimezone(ZoneInfo('America/Sao_Paulo'))
            return local.strftime('%d/%m/%Y às %H:%M')
        except Exception:
            pass
    # ISO date only → dd/mm/yyyy
    if len(v) == 10 and v[4] == '-' and v[7] == '-':
        try:
            from datetime import datetime
            dt = datetime.strptime(v, '%Y-%m-%d')
            return dt.strftime('%d/%m/%Y')
        except Exception:
            pass
    # Status labels
    if field_name == 'status':
        return _STATUS_LABELS.get(v, v)
    return v


def _build_change_body(field_changes: dict) -> str:
    """Convert raw field_changes dict into user-friendly Portuguese text."""
    lines = []
    for field_name, change in (field_changes or {}).items():
        label = _FIELD_LABELS.get(field_name, field_name.replace('_', ' ').title())
        if isinstance(change, dict):
            old_val = _fmt_value(field_name, change.get('old'))
            new_val = _fmt_value(field_name, change.get('new'))
            lines.append(f'{label} alterado para {new_val} (era {old_val})')
        elif isinstance(change, str) and ' → ' in change:
            parts = change.split(' → ', 1)
            old_val = _fmt_value(field_name, parts[0].strip())
            new_val = _fmt_value(field_name, parts[1].strip())
            lines.append(f'{label} alterado para {new_val} (era {old_val})')
        else:
            lines.append(f'{label}: {_fmt_value(field_name, change)}')
    return '\n'.join(lines) if lines else 'Mudanças detectadas na fonte oficial.'


def _alert_path(alert) -> str:
    """Caminho no app web aberto ao tocar na notificação."""
    if alert.edition_id:
        return f'/torneios/{alert.edition_id}'
    return '/alertas'


def _send_web_push(subscriptions, alert, data):
    """Envia Web Push (pywebpush/VAPID). Retorna (enviados, erros). Ausência de VAPID/
    pywebpush não derruba o alerta — apenas pula este canal."""
    from django.conf import settings
    vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    vapid_claims_email = getattr(settings, 'VAPID_CLAIMS_EMAIL', settings.DEFAULT_FROM_EMAIL)
    if not vapid_private_key:
        logger.warning('VAPID_PRIVATE_KEY not configured — web push skipped')
        return 0, ['no_vapid_key']

    try:
        from pywebpush import webpush
        import json as _json
        payload = _json.dumps({'title': alert.title, 'body': alert.body, 'data': data})
    except ImportError:
        return 0, ['pywebpush_not_installed']

    sent = 0
    errors = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={'sub': f'mailto:{vapid_claims_email}'},
            )
            sent += 1
        except Exception as exc:
            errors.append(str(exc)[:100])
            logger.warning('Web push failed for sub %s: %s', sub.id, exc)
            if '410' in str(exc):
                sub.delete()
    return sent, errors


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_push_alert(self, alert_id: int):
    """Envia a notificação push de um Alert por dois canais: push nativo (Expo, app
    iOS/Android) e Web Push (navegador). Sucesso se ao menos um canal entregar."""
    try:
        alert = Alert.objects.select_related('user').get(pk=alert_id)
    except Alert.DoesNotExist:
        logger.warning('Alert %s not found', alert_id)
        return

    web_subs = list(PushSubscription.objects.filter(user=alert.user))
    device_tokens = list(DevicePushToken.objects.filter(user=alert.user))
    if not web_subs and not device_tokens:
        alert.status = Alert.STATUS_FAILED
        alert.error = 'no_push_target'
        alert.save(update_fields=['status', 'error', 'updated_at'])
        return

    sent = 0
    errors = []
    data = {'alert_id': alert.id, 'kind': alert.kind, 'path': _alert_path(alert)}

    # Canal nativo (Expo) — app iOS/Android
    if device_tokens:
        try:
            from .expo_push import send_expo_push_messages
            n, invalid, expo_errors = send_expo_push_messages(
                [t.token for t in device_tokens], alert.title, alert.body, data,
            )
            sent += n
            errors.extend(expo_errors)
            if invalid:
                DevicePushToken.objects.filter(token__in=invalid).delete()
        except Exception as exc:  # noqa: BLE001
            errors.append(f'expo:{str(exc)[:80]}')
            logger.warning('Expo push failed for alert %s: %s', alert_id, exc)

    # Canal web (navegador)
    if web_subs:
        sent_web, web_errors = _send_web_push(web_subs, alert, data)
        sent += sent_web
        errors.extend(web_errors)

    if sent > 0:
        alert.status = Alert.STATUS_SENT
        alert.dispatched_at = timezone.now()
        alert.save(update_fields=['status', 'dispatched_at', 'updated_at'])
    else:
        alert.status = Alert.STATUS_FAILED
        alert.error = '; '.join(errors)[:300] or 'push_failed'
        # Só reagenda em falha transitória. Erros de configuração permanentes
        # (sem VAPID, lib ausente) nunca terão sucesso — não vale gastar retries.
        transient = [e for e in errors if e not in _PERMANENT_PUSH_ERRORS]
        alert.save(update_fields=['status', 'error', 'updated_at'])
        if transient:
            raise self.retry(exc=Exception(alert.error))


def _create_alert(user, edition, kind, channel, title, body='', payload=None, dedup_key=''):
    if dedup_key and Alert.objects.filter(user=user, dedup_key=dedup_key).exists():
        return None
    alert = Alert.objects.create(
        user=user,
        edition=edition,
        kind=kind,
        channel=channel,
        title=title,
        body=body,
        payload=payload or {},
        dedup_key=dedup_key,
    )
    # Email channel removed — only push and in-app are dispatched
    if channel == Alert.CHANNEL_PUSH:
        send_push_alert.delay(alert.id)
    else:
        alert.status = Alert.STATUS_SENT
        alert.dispatched_at = timezone.now()
        alert.save(update_fields=['status', 'dispatched_at', 'updated_at'])
    return alert


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def dispatch_deadline_alerts(self):
    """
    For every watchlist item whose user wants deadline alerts,
    send a notification when entry_close_at falls within D-N windows.
    """
    import pytz
    brasilia = pytz.timezone('America/Sao_Paulo')

    now = timezone.now()
    today_brasilia = now.astimezone(brasilia).date()
    created = 0

    qs = (
        WatchlistItem.objects
        .select_related('user', 'edition', 'edition__tournament__organization')
        .filter(alert_on_deadline=True, edition__entry_close_at__isnull=False)
        .filter(edition__entry_close_at__gt=now)
    )
    for item in qs:
        prefs = UserAlertPreference.get_or_create_defaults(item.user)
        if not prefs.in_app_enabled and not prefs.push_enabled:
            continue
        days_list = prefs.deadline_days or [7, 2, 0]

        close_local = item.edition.entry_close_at.astimezone(brasilia)
        close_date = close_local.date()
        days_until = (close_date - today_brasilia).days

        for d in days_list:
            if days_until != d:
                continue

            dedup = f'deadline:{item.edition_id}:{d}:{today_brasilia}'
            title = (
                f'{item.edition.title} — inscrições encerram hoje!'
                if d == 0
                else f'{item.edition.title} — faltam {d} dia{"s" if d != 1 else ""} para o fechamento'
            )
            body = (
                f'O prazo de inscrição encerra em '
                f'{close_local.strftime("%d/%m/%Y às %H:%M")} '
                f'(horário de Brasília).'
            )

            # In-app notification
            if prefs.in_app_enabled:
                _create_alert(
                    user=item.user, edition=item.edition,
                    kind=Alert.KIND_DEADLINE, channel=Alert.CHANNEL_IN_APP,
                    title=title, body=body,
                    payload={'days_before': d},
                    dedup_key=dedup + ':app',
                )
                created += 1

            # Push notification
            if prefs.push_enabled:
                _create_alert(
                    user=item.user, edition=item.edition,
                    kind=Alert.KIND_DEADLINE, channel=Alert.CHANNEL_PUSH,
                    title=title, body=body,
                    payload={'days_before': d},
                    dedup_key=dedup + ':push',
                )
                created += 1

            # Notify parent(s) of this child watcher
            _notify_parents(
                item=item,
                kind=Alert.KIND_DEADLINE,
                title=title,
                body=body,
                dedup_base=dedup,
                payload={'days_before': d},
            )

    logger.info('Dispatched %d deadline alerts', created)
    return created


# Event types that generate system-level noise and should NOT notify athletes/parents
_SKIP_EVENT_TYPES = {
    TournamentChangeEvent.EVENT_OTHER,   # surface / title / withdrawal_deadline minor updates
    TournamentChangeEvent.EVENT_CREATED, # new tournament indexed — not a change alert
}

# For EVENT_STATUS, only these transitions are meaningful for athletes
_NOTIFY_STATUSES = {'canceled', 'draws_published', 'closed', 'closing_soon'}

# Human-readable titles for status-based alerts
_STATUS_TITLES = {
    'canceled':      '{title} — torneio cancelado',
    'draws_published': '{title} — chaves publicadas',
    'closed':        '{title} — inscrições encerradas',
    'closing_soon':  '{title} — inscrições encerrando em breve',
}


def _should_dispatch(event: TournamentChangeEvent) -> bool:
    """Return True only for change events that are genuinely relevant to athletes."""
    # System/minor events: suppress entirely
    if event.event_type in _SKIP_EVENT_TYPES:
        return False

    # Status alerts only for meaningful transitions
    if event.event_type == TournamentChangeEvent.EVENT_STATUS:
        field = event.field_changes.get('status', {})
        new_status = field.get('new', '') if isinstance(field, dict) else str(field)
        return new_status in _NOTIFY_STATUSES

    # Deadline alerts only when entry_close_at (signup deadline) actually changed
    # Changing entry_open_at alone is low-value noise
    if event.event_type == TournamentChangeEvent.EVENT_DEADLINE:
        return 'entry_close_at' in event.field_changes

    # All other classified events (date, price, draws, canceled) are relevant
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_change_alert(self, edition_id: int, event_id: int):
    """Fan-out: notify every watcher of an edition when a change event is recorded."""
    try:
        edition = TournamentEdition.objects.get(pk=edition_id)
        event = TournamentChangeEvent.objects.get(pk=event_id)
    except (TournamentEdition.DoesNotExist, TournamentChangeEvent.DoesNotExist):
        return 0
    except Exception as exc:
        raise self.retry(exc=exc)

    # Gate: skip events that are not meaningful for athlete/parent notification
    if not _should_dispatch(event):
        logger.debug('dispatch_change_alert: skipping event_type=%s edition=%s', event.event_type, edition_id)
        return 0

    created = 0
    watchers = WatchlistItem.objects.filter(edition=edition).select_related('user')
    for item in watchers:
        prefs = UserAlertPreference.get_or_create_defaults(item.user)

        # Determine kind and title based on event type
        if event.event_type == TournamentChangeEvent.EVENT_DRAWS:
            if not item.alert_on_draws or not prefs.draws_enabled:
                continue
            kind = Alert.KIND_DRAWS
            title = f'{edition.title} — chaves publicadas'
        elif event.event_type == TournamentChangeEvent.EVENT_CANCELED:
            kind = Alert.KIND_CANCELED
            title = f'{edition.title} — torneio cancelado'
        elif event.event_type == TournamentChangeEvent.EVENT_STATUS:
            if not item.alert_on_changes or not prefs.changes_enabled:
                continue
            kind = Alert.KIND_CHANGE
            field = event.field_changes.get('status', {})
            new_status = field.get('new', '') if isinstance(field, dict) else str(field)
            title = _STATUS_TITLES.get(new_status, f'{edition.title} — status alterado').format(title=edition.title)
        else:
            if not item.alert_on_changes or not prefs.changes_enabled:
                continue
            kind = Alert.KIND_CHANGE
            title = f'{edition.title} — dados alterados ({event.get_event_type_display()})'

        # Human-readable body — no raw field names exposed to users
        body = _build_change_body(event.field_changes)

        # Dedup key: edition + event_type + today's date
        # Using event_id caused duplicates when multiple ingestion runs detected
        # the same change and created multiple TournamentChangeEvent records.
        import pytz
        today_brt = timezone.now().astimezone(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d')
        dedup = f'{kind}:{edition_id}:{event.event_type}:{today_brt}'

        if prefs.in_app_enabled:
            a = _create_alert(
                user=item.user, edition=edition,
                kind=kind, channel=Alert.CHANNEL_IN_APP,
                title=title, body=body,
                payload={'event_id': event_id, 'field_changes': event.field_changes},
                dedup_key=dedup + ':app',
            )
            if a:
                created += 1

        if prefs.push_enabled:
            _create_alert(
                user=item.user, edition=edition,
                kind=kind, channel=Alert.CHANNEL_PUSH,
                title=title, body=body,
                payload={'event_id': event_id},
                dedup_key=dedup + ':push',
            )

        # Notify parent(s) of this child watcher
        _notify_parents(
            item=item,
            kind=kind,
            title=title,
            body=body,
            dedup_base=dedup,
            payload={'event_id': event_id},
        )

    return created
