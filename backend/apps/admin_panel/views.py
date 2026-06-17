"""
Admin panel: consolidated endpoints used by the admin web UI:
- Dashboard counters
- Review queue (low-confidence / recently changed / missing-link editions)
- User management (list, edit, delete)
- Statistics (time-series charts)
- Edition inline patch (manual override / confidence update)
- Data source management
"""
import re
import unicodedata
from datetime import timedelta, date
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsAdmin, IsSuperUser
from apps.tournaments.models import TournamentEdition
from apps.sources.models import DataSource, Organization
from apps.ingestion.models import IngestionRun
from apps.audit.models import AuditLog
from apps.alerts.models import Alert
from apps.tournaments.serializers import TournamentEditionListSerializer

User = get_user_model()


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def _audit(actor, action, entity_id, *, diff=None, reason='', request=None):
    """Write an admin AuditLog entry. Never let auditing break the operation."""
    try:
        AuditLog.objects.create(
            actor=actor,
            action=action,
            entity_type='user',
            entity_id=str(entity_id),
            diff=diff or {},
            reason=reason or '',
            ip_address=_client_ip(request) if request else None,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger('apps.admin_panel').exception('Audit write failed')


# ── Derived user info helpers ────────────────────────────────────────────────

_PLAN_ACTIVE_STATUSES = ('active', 'trial')


def _profile_type(user):
    """(code, friendly label) describing the user's profile for the admin UI."""
    from apps.accounts.models import ParentChild
    if user.is_superuser:
        return 'master', 'Master'
    if user.is_staff:
        return 'admin', 'Admin'
    if user.role == 'parent':
        return 'responsavel', 'Responsável'
    if user.role == 'coach':
        return 'treinador', 'Treinador'
    if user.role == 'player':
        is_dependent = getattr(user, '_dep_count', None)
        if is_dependent is None:
            is_dependent = ParentChild.objects.filter(child=user, is_active=True).exists()
        return ('dependente', 'Dependente') if is_dependent else ('jogador', 'Jogador')
    return user.role or 'user', (user.role or 'Usuário').capitalize()


def _plan_info(user):
    """Plan + subscription status summary; tolerant when there is no subscription."""
    try:
        sub = user.subscription
    except Exception:  # noqa: BLE001 — Subscription.DoesNotExist / not loaded
        return {
            'plan': None, 'plan_slug': None, 'plan_status': 'none',
            'plan_is_blocked': True, 'billing_period': None,
        }
    return {
        'plan': sub.plan.name if sub.plan_id else None,
        'plan_slug': sub.plan.slug if sub.plan_id else None,
        'plan_status': sub.status,
        'plan_is_blocked': sub.status not in _PLAN_ACTIVE_STATUSES,
        'billing_period': sub.billing_period,
    }


def _is_login_locked(user):
    from apps.accounts import security
    return security.is_locked(user)


def _serialize_user_row(user):
    """Compact row for the admin users list."""
    code, label = _profile_type(user)
    plan = _plan_info(user)
    return {
        'id': user.id,
        'email': user.email,
        'full_name': user.full_name,
        'phone': user.phone,
        'role': user.role,
        'profile_type': code,
        'profile_label': label,
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'is_login_locked': _is_login_locked(user),
        'email_verified': user.email_verified,
        'created_at': user.created_at,
        'last_login': user.last_login,
        **plan,
    }


class AdminUserWriteSerializer(serializers.ModelSerializer):
    """Admin-editable user fields. E-mail is writable here (admin override) with a
    uniqueness guard; role/active/staff are editable. Superuser flag is never set
    via the API."""
    class Meta:
        model = User
        fields = (
            'full_name', 'email', 'phone', 'role',
            'is_active', 'is_staff', 'email_verified', 'marketing_consent',
        )

    def validate_email(self, value):
        value = (value or '').strip().lower()
        qs = User.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Este e-mail já está em uso.')
        return value


@api_view(['GET'])
@permission_classes([IsAdmin])
def user_list(request):
    """List all users with optional search and derived plan/profile info."""
    qs = (
        User.objects
        .select_related('subscription__plan')
        .annotate(
            _dep_count=Count('parent_links', filter=Q(parent_links__is_active=True)),
        )
        .order_by('-created_at')
    )
    q = request.query_params.get('q', '').strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(full_name__icontains=q))
    return Response([_serialize_user_row(u) for u in qs])


@api_view(['POST'])
@permission_classes([IsAdmin])
def user_set_password(request, pk):
    """Admin: define nova senha para qualquer usuário."""
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    password = request.data.get('password', '').strip()
    if len(password) < 6:
        return Response({'detail': 'Senha deve ter pelo menos 6 caracteres.'}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(password)
    user.save(update_fields=['password'])
    _audit(request.user, AuditLog.ACTION_UPDATE, user.id,
           diff={'event': 'password_reset'},
           reason='Senha redefinida pelo administrador.', request=request)
    return Response({'detail': f'Senha do usuário {user.email} atualizada com sucesso.'})


def _sport_profile_payload(user):
    """Full sport-profile snapshot for admin audit (primary profile + extras)."""
    from apps.players.models import PlayerProfile, ExternalPlayerRanking
    from apps.players.parsers import extract_ti_id

    profiles = list(PlayerProfile.objects.filter(user=user).order_by('-is_primary', '-created_at'))
    if not profiles:
        return None
    primary = profiles[0]
    ti_id, _ = extract_ti_id(primary.external_ids or {})

    external_rankings = []
    if ti_id:
        external_rankings = list(
            ExternalPlayerRanking.objects
            .filter(ti_player_id=str(ti_id))
            .values('source', 'ranking_name', 'category_label', 'position', 'points', 'season')[:30]
        )

    def _fed(p):
        if p.federation_id and p.federation:
            return {'id': p.federation_id, 'name': p.federation.short_name or p.federation.name,
                    'uf': p.federation.state}
        return None

    return {
        'display_name': primary.display_name,
        'modality': primary.preferred_modality,
        'competitive_level': primary.competitive_level,
        'competitive_level_label': primary.get_competitive_level_display(),
        'birth_year': primary.birth_year,
        'birth_date': primary.birth_date,
        'age': primary.sporting_age,
        'gender': primary.gender,
        'gender_label': primary.get_gender_display() if primary.gender else '',
        'federation': _fed(primary),
        'home_state': primary.home_state,
        'home_city': primary.home_city,
        'travel_states': primary.travel_states,
        'dominant_hand': primary.dominant_hand,
        'ti_player_id': ti_id,
        'utr_singles': primary.utr_singles,
        'utr_doubles': primary.utr_doubles,
        'utr_profile_url': primary.utr_profile_url,
        'ti_rankings': primary.ti_rankings_cache or [],
        'external_rankings': external_rankings,
        'profiles_count': len(profiles),
    }


def _tournaments_payload(user):
    """Registrations / watchlist / results counts + recent samples for admin audit."""
    out = {'registered': [], 'watching': [], 'results': []}
    try:
        from apps.registrations.models import TournamentRegistration
        regs = (
            TournamentRegistration.objects
            .filter(profile__user=user)
            .select_related('edition__tournament')
            .order_by('-registered_at')[:30]
        )
        out['registered'] = [{
            'id': r.id,
            'edition': getattr(r.edition, 'title', '') or str(r.edition_id),
            'payment_status': r.payment_status,
            'is_withdrawn': r.is_withdrawn,
            'registered_at': r.registered_at,
        } for r in regs]
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.watchlist.models import WatchlistItem, TournamentResult
        items = (
            WatchlistItem.objects
            .filter(user=user)
            .select_related('edition__tournament')
            .order_by('-created_at')[:30]
        )
        out['watching'] = [{
            'id': w.id,
            'edition': getattr(w.edition, 'title', '') or str(w.edition_id),
            'user_status': w.user_status,
        } for w in items]
        results = (
            TournamentResult.objects
            .filter(watchlist_item__user=user)
            .order_by('-created_at')[:30]
        )
        out['results'] = [{
            'id': r.id,
            'category_played': r.category_played,
            'position': r.position,
            'wins': r.wins,
            'losses': r.losses,
        } for r in results]
    except Exception:  # noqa: BLE001
        pass
    return out


def _links_payload(user):
    """Responsáveis vinculados (se dependente) e dependentes vinculados (se responsável)."""
    from apps.accounts.models import ParentChild

    parents = (
        ParentChild.objects.filter(child=user, is_active=True)
        .select_related('parent')
    )
    children = (
        ParentChild.objects.filter(parent=user, is_active=True)
        .select_related('child')
    )

    def _u(u):
        return {'id': u.id, 'full_name': u.full_name, 'email': u.email, 'role': u.role}

    return {
        'responsibles': [{'link_id': l.id, **_u(l.parent)} for l in parents],
        'dependents': [{'link_id': l.id, **_u(l.child)} for l in children],
    }


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdmin])
def user_detail(request, pk):
    """GET full audit payload; PATCH editable fields; DELETE a user. Cannot act on
    your own account for PATCH/DELETE."""
    try:
        user = User.objects.select_related('subscription__plan').get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        from apps.accounts import security
        code, label = _profile_type(user)
        payload = {
            **_serialize_user_row(user),
            'consent_version': user.consent_version,
            'consented_at': user.consented_at,
            'last_login_ip': user.last_login_ip,
            'failed_login_attempts': user.failed_login_attempts,
            'login_locked_until': user.login_locked_until,
            'lock_seconds_remaining': security.seconds_remaining(user),
            'sport_profile': _sport_profile_payload(user),
            'tournaments': _tournaments_payload(user),
            'links': _links_payload(user),
        }
        return Response(payload)

    if user.pk == request.user.pk:
        return Response({'detail': 'Você não pode editar ou deletar sua própria conta aqui.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        if user.is_superuser:
            return Response({'detail': 'Não é possível deletar um superusuário.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import transaction
        from django.db.models import ProtectedError
        _audit(request.user, AuditLog.ACTION_DELETE, user.id,
               diff={'email': user.email}, reason='Usuário excluído pelo administrador.', request=request)
        try:
            with transaction.atomic():
                # Payment.user é PROTECT — remover os pagamentos antes da exclusão
                # (exclusão de conta é irreversível por design). As comissões
                # vinculadas ficam com payment=NULL (SET_NULL), preservando o ledger
                # do parceiro; a assinatura e os vínculos de família caem por CASCADE.
                user.payments.all().delete()
                user.delete()
        except ProtectedError:
            return Response(
                {'detail': 'Não foi possível excluir: o usuário possui registros vinculados que impedem a exclusão.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    ser = AdminUserWriteSerializer(user, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    before = {k: getattr(user, k) for k in ser.validated_data.keys()}
    ser.save(is_superuser=user.is_superuser)  # never promote to superuser via API
    after = {k: getattr(user, k) for k in ser.validated_data.keys()}
    _audit(request.user, AuditLog.ACTION_UPDATE, user.id,
           diff={'before': {k: str(v) for k, v in before.items()},
                 'after': {k: str(v) for k, v in after.items()}},
           reason='Dados de usuário atualizados pelo administrador.', request=request)
    return Response(_serialize_user_row(user))


@api_view(['POST'])
@permission_classes([IsAdmin])
def user_unlock_login(request, pk):
    """Release a login lock (clears the failed-attempt counter and lock)."""
    from apps.accounts import security
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    security.reset_attempts(user)
    _audit(request.user, AuditLog.ACTION_UPDATE, user.id,
           diff={'event': 'login_unlocked'}, reason='Login desbloqueado pelo administrador.', request=request)
    return Response({'detail': f'Login de {user.email} desbloqueado.'})


@api_view(['POST'])
@permission_classes([IsAdmin])
def user_set_plan(request, pk):
    """Admin: liberar/alterar o plano do usuário.

    Body: { "plan_slug": "individual|familia|tester" (opcional),
            "status": "active|pending|canceled|expired|unpaid|trial" (opcional) }
    - Cria a Subscription se não existir.
    - Plano Tester ativa imediatamente (sem Asaas), conforme regra do produto.
    Registra ator + timestamp no AuditLog.
    """
    from apps.billing.models import Plan, Subscription
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    plan_slug = (request.data.get('plan_slug') or '').strip().lower()
    new_status = (request.data.get('status') or '').strip().lower()

    if not plan_slug and not new_status:
        return Response({'detail': 'Informe plan_slug e/ou status.'}, status=status.HTTP_400_BAD_REQUEST)

    plan = None
    if plan_slug:
        try:
            plan = Plan.objects.get(slug=plan_slug)
        except Plan.DoesNotExist:
            return Response({'detail': f'Plano "{plan_slug}" não encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    valid_statuses = {s for s, _ in Subscription.STATUS_CHOICES}
    if new_status and new_status not in valid_statuses:
        return Response({'detail': f'Status inválido. Use um de: {", ".join(sorted(valid_statuses))}.'},
                        status=status.HTTP_400_BAD_REQUEST)

    sub, _created = Subscription.objects.get_or_create(
        user=user,
        defaults={'plan': plan or Plan.objects.get(slug=Plan.SLUG_INDIVIDUAL),
                  'status': Subscription.STATUS_PENDING},
    )
    before = {'plan': sub.plan.slug if sub.plan_id else None, 'status': sub.status}

    update_fields = []
    if plan is not None:
        sub.plan = plan
        update_fields.append('plan')
        # Tester ativa imediatamente (operacional, sem Asaas).
        if plan.slug == Plan.SLUG_TESTER and not new_status:
            new_status = Subscription.STATUS_ACTIVE
    if new_status:
        sub.status = new_status
        update_fields.append('status')
        if new_status == Subscription.STATUS_ACTIVE and not sub.start_date:
            sub.start_date = timezone.now().date()
            update_fields.append('start_date')

    if update_fields:
        sub.save(update_fields=list(set(update_fields)) + ['updated_at'])

    _audit(request.user, AuditLog.ACTION_UPDATE, user.id,
           diff={'event': 'plan_changed', 'before': before,
                 'after': {'plan': sub.plan.slug, 'status': sub.status}},
           reason='Plano/assinatura alterado pelo administrador.', request=request)
    return Response({'detail': f'Plano de {user.email} atualizado.', **_plan_info(user)})


@api_view(['POST'])
@permission_classes([IsAdmin])
def user_manage_link(request, pk):
    """Admin corrige vínculo responsável↔jogador/dependente.

    Body: { "action": "add"|"remove", "counterpart_id": <int>, "role": "parent"|"child" }
      - role="parent": counterpart é o RESPONSÁVEL de <pk> (pk é o jogador/dependente).
      - role="child":  counterpart é o DEPENDENTE de <pk> (pk é o responsável).
    A criação respeita a regra de limite de responsáveis (Área 5).
    """
    from django.core.exceptions import ValidationError as DjangoValidationError
    from apps.accounts.models import ParentChild
    from apps.accounts import services

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    action = (request.data.get('action') or '').strip().lower()
    role = (request.data.get('role') or '').strip().lower()
    counterpart_id = request.data.get('counterpart_id')

    if action not in ('add', 'remove') or role not in ('parent', 'child') or not counterpart_id:
        return Response({'detail': 'Parâmetros inválidos. Use action, role e counterpart_id.'},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        counterpart = User.objects.get(pk=counterpart_id)
    except User.DoesNotExist:
        return Response({'detail': 'Usuário contraparte não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    parent, child = (counterpart, user) if role == 'parent' else (user, counterpart)
    if parent.pk == child.pk:
        return Response({'detail': 'Responsável e dependente não podem ser o mesmo usuário.'},
                        status=status.HTTP_400_BAD_REQUEST)

    if action == 'add':
        try:
            services.assert_can_link_responsible(child, parent)
        except DjangoValidationError as exc:
            detail = exc.messages[0] if exc.messages else str(exc)
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
        link, created = ParentChild.objects.get_or_create(parent=parent, child=child, defaults={'is_active': True})
        if not link.is_active:
            link.is_active = True
            link.save(update_fields=['is_active'])
        _audit(request.user, AuditLog.ACTION_CREATE, child.id,
               diff={'event': 'link_added', 'parent_id': parent.id, 'child_id': child.id},
               reason='Vínculo responsável/dependente criado pelo administrador.', request=request)
        return Response({'detail': 'Vínculo criado.', 'link_id': link.id, 'links': _links_payload(user)})

    # remove
    link = ParentChild.objects.filter(parent=parent, child=child, is_active=True).first()
    if not link:
        return Response({'detail': 'Vínculo ativo não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
    link.is_active = False
    link.save(update_fields=['is_active'])
    _audit(request.user, AuditLog.ACTION_UPDATE, child.id,
           diff={'event': 'link_removed', 'parent_id': parent.id, 'child_id': child.id},
           reason='Vínculo responsável/dependente removido pelo administrador.', request=request)
    return Response({'detail': 'Vínculo removido.', 'links': _links_payload(user)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def dashboard(request):
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    editions_qs = TournamentEdition.objects.all()
    return Response({
        'counts': {
            'tournaments_total': editions_qs.count(),
            'tournaments_open': editions_qs.filter(status=TournamentEdition.STATUS_OPEN).count(),
            'tournaments_closing_soon': editions_qs.filter(
                status__in=[
                    TournamentEdition.STATUS_CLOSING_SOON,
                    TournamentEdition.STATUS_OPEN,
                ],
                entry_close_at__gt=now,
                entry_close_at__lt=now + timedelta(days=7),
            ).count(),
            'data_sources_enabled': DataSource.objects.filter(enabled=True).count(),
            'data_sources_total': DataSource.objects.count(),
            'manual_overrides': editions_qs.filter(is_manual_override=True).count(),
            'low_confidence': editions_qs.filter(
                data_confidence=TournamentEdition.CONFIDENCE_LOW
            ).count(),
            'missing_official_url': editions_qs.filter(
                Q(official_source_url='') | Q(official_source_url__isnull=True)
            ).count(),
        },
        'ingestion': {
            'runs_24h': IngestionRun.objects.filter(started_at__gte=last_24h).count(),
            'failed_24h': IngestionRun.objects.filter(
                started_at__gte=last_24h, status=IngestionRun.STATUS_FAILED
            ).count(),
            'partial_24h': IngestionRun.objects.filter(
                started_at__gte=last_24h, status=IngestionRun.STATUS_PARTIAL
            ).count(),
        },
        'alerts': {
            'total_7d': Alert.objects.filter(created_at__gte=last_7d).count(),
            'failed_7d': Alert.objects.filter(
                created_at__gte=last_7d, status=Alert.STATUS_FAILED
            ).count(),
        },
        'audit': {
            'actions_24h': AuditLog.objects.filter(created_at__gte=last_24h).count(),
        },
    })


@api_view(['GET'])
@permission_classes([IsAdmin])
def stats(request):
    """Platform statistics for charts."""
    now = timezone.now()
    days = int(request.query_params.get('days', 30))
    since = now - timedelta(days=days)

    # Daily new registrations
    reg_qs = (
        User.objects
        .filter(created_at__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    reg_by_day = {str(r['day']): r['count'] for r in reg_qs}
    all_days = [(since.date() + timedelta(days=i)).isoformat() for i in range(days + 1)]
    registrations = [{'date': d, 'registrations': reg_by_day.get(d, 0)} for d in all_days]

    # Users by role
    roles = (
        User.objects
        .values('role')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    role_labels = {'player': 'Jogador', 'coach': 'Treinador', 'parent': 'Pai/Resp.', 'admin': 'Admin'}
    users_by_role = [{'role': role_labels.get(r['role'], r['role']), 'count': r['count']} for r in roles]

    # Tournaments by status
    from apps.tournaments.models import TournamentEdition
    status_qs = (
        TournamentEdition.objects
        .values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    status_labels = {
        'open': 'Aberto', 'closing_soon': 'Fechando', 'closed': 'Encerrado',
        'in_progress': 'Em andamento', 'finished': 'Finalizado',
        'announced': 'Anunciado', 'canceled': 'Cancelado', 'unknown': 'Desconhecido',
        'draws_published': 'Chaves pub.',
    }
    tournaments_by_status = [
        {'status': status_labels.get(s['status'], s['status']), 'count': s['count']}
        for s in status_qs
    ]

    # Watchlist items by user_status
    from apps.watchlist.models import WatchlistItem
    wl_qs = (
        WatchlistItem.objects
        .values('user_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    wl_labels = {
        'none': 'Nenhum', 'intended': 'Pretende', 'registered_declared': 'Inscrito',
        'withdrawn': 'Desistiu', 'completed': 'Concluído',
    }
    watchlist_by_status = [
        {'status': wl_labels.get(w['user_status'], w['user_status']), 'count': w['count']}
        for w in wl_qs
    ]

    return Response({
        'registrations': registrations,
        'users_by_role': users_by_role,
        'tournaments_by_status': tournaments_by_status,
        'watchlist_by_status': watchlist_by_status,
        'totals': {
            'users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'new_users_period': User.objects.filter(created_at__gte=since).count(),
        },
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def review_queue(request):
    """Editions that need human curation."""
    from apps.tournaments.models import TournamentChangeEvent

    base_qs = TournamentEdition.objects.select_related(
        'tournament__organization', 'venue', 'data_source'
    ).prefetch_related('categories__normalized_category', 'links')

    low_conf = base_qs.filter(
        data_confidence=TournamentEdition.CONFIDENCE_LOW,
        is_manual_override=False,
    ).order_by('-fetched_at')[:20]

    no_link = base_qs.filter(
        Q(official_source_url='') | Q(official_source_url__isnull=True),
        is_manual_override=False,
    ).order_by('-fetched_at')[:20]

    cutoff = timezone.now() - timedelta(days=2)
    recent_ids = (
        TournamentChangeEvent.objects
        .filter(detected_at__gte=cutoff)
        .values_list('edition_id', flat=True)
        .distinct()[:20]
    )
    recently_changed = base_qs.filter(id__in=list(recent_ids)).order_by('-updated_at')

    return Response({
        'low_confidence': TournamentEditionListSerializer(low_conf, many=True).data,
        'missing_official_url': TournamentEditionListSerializer(no_link, many=True).data,
        'recently_changed': TournamentEditionListSerializer(recently_changed, many=True).data,
    })


class EditionPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'title', 'status', 'start_date', 'end_date',
            'entry_open_at', 'entry_close_at', 'official_source_url',
            'base_price_brl', 'data_confidence', 'is_manual_override', 'is_youth',
            'is_published',
        )
        read_only_fields = ('id',)


class AdminEditionListSerializer(serializers.ModelSerializer):
    """Compact list serializer for the admin editions tab.
    Includes is_published and curation flags so admin can see hidden items."""
    organization_short_name = serializers.CharField(source='tournament.organization.short_name', read_only=True)
    venue_city = serializers.CharField(source='venue.city', read_only=True, default='')
    venue_state = serializers.CharField(source='venue.state', read_only=True, default='')

    class Meta:
        model = TournamentEdition
        fields = (
            'id', 'title', 'status',
            'start_date', 'end_date', 'entry_close_at',
            'data_confidence', 'is_manual_override', 'is_youth', 'is_published',
            'official_source_url', 'source_name',
            'organization_short_name', 'venue_city', 'venue_state',
        )


@api_view(['GET'])
@permission_classes([IsSuperUser])
def admin_editions_list(request):
    """
    Admin-only listing of TournamentEdition that INCLUDES unpublished items.
    Supports query params:
      - q          → text search across title / org / venue
      - published  → 'true' | 'false' to filter; omit for all
      - youth_only → 'true' (default off — admin needs to see everything)
      - page_size  → default 30 (cap 200)
    """
    qs = (
        TournamentEdition.objects
        .select_related('tournament__organization', 'venue')
        .order_by('-start_date', '-id')
    )

    q = request.query_params.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(tournament__canonical_name__icontains=q)
            | Q(tournament__organization__short_name__icontains=q)
            | Q(venue__name__icontains=q)
            | Q(venue__city__icontains=q)
        )

    published = request.query_params.get('published')
    if published is not None:
        if published.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(is_published=True)
        elif published.lower() in ('0', 'false', 'no'):
            qs = qs.filter(is_published=False)

    if request.query_params.get('youth_only', 'false').lower() == 'true':
        qs = qs.filter(Q(is_youth=True) | Q(is_youth__isnull=True))

    try:
        page_size = min(int(request.query_params.get('page_size', 30)), 200)
    except ValueError:
        page_size = 30

    total = qs.count()
    items = qs[:page_size]
    return Response({
        'count': total,
        'results': AdminEditionListSerializer(items, many=True).data,
    })


class EditionCreateSerializer(serializers.ModelSerializer):
    """Serializer for manually creating a tournament edition in the admin panel."""
    circuit = serializers.CharField(required=True)
    venue_city = serializers.CharField(required=False, allow_blank=True)
    venue_state = serializers.CharField(required=False, allow_blank=True, max_length=2)

    class Meta:
        model = TournamentEdition
        fields = (
            'title', 'circuit', 'status', 'start_date', 'end_date',
            'entry_open_at', 'entry_close_at', 'official_source_url',
            'base_price_brl', 'is_youth',
            'venue_city', 'venue_state',
        )

    def create(self, validated_data):
        from apps.sources.models import Organization
        from apps.tournaments.models import Tournament, Venue
        city = validated_data.pop('venue_city', '')
        state = validated_data.pop('venue_state', '')
        circuit = validated_data.pop('circuit')

        # Get or create org for manual entries
        org, _ = Organization.objects.get_or_create(
            short_name=circuit,
            defaults={'name': circuit, 'type': 'platform'},
        )

        # Get or create the tournament identity
        title = validated_data.get('title', '')
        slug = re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()).strip('-')[:200]
        tournament, _ = Tournament.objects.get_or_create(
            canonical_slug=slug,
            defaults={'canonical_name': title, 'organization': org, 'circuit': circuit},
        )

        # Venue
        venue = None
        if city or state:
            venue, _ = Venue.objects.get_or_create(
                city=city, state=state,
                defaults={'name': f'{city} - {state}' if city and state else (city or state)},
            )

        # Note: `circuit` is part of the Tournament model (already set above
        # via Tournament.objects.get_or_create defaults), not TournamentEdition.
        edition = TournamentEdition.objects.create(
            tournament=tournament,
            venue=venue,
            source_name='manual',
            data_confidence=TournamentEdition.CONFIDENCE_HIGH,
            is_manual_override=True,
            season_year=validated_data.get('start_date', date.today()).year if validated_data.get('start_date') else date.today().year,
            **validated_data,
        )
        return edition


@api_view(['POST'])
@permission_classes([IsSuperUser])
def edition_create(request):
    """
    Manually create a tournament edition — for COSAT/ITF/UTR entries
    that cannot be fetched automatically due to connector blocks.
    """
    ser = EditionCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    edition = ser.save()
    from apps.tournaments.serializers import TournamentEditionListSerializer
    return Response(TournamentEditionListSerializer(edition).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def connector_status(request):
    """
    Return status of each registered connector — last run, last status,
    consecutive failures, and whether it's currently blocked (circuit open).
    """
    from django.core.cache import cache
    from apps.ingestion.connectors import registered_connectors

    result = []
    sources = {ds.connector_key: ds for ds in DataSource.objects.select_related('organization').all()}

    for key in sorted(registered_connectors().keys()):
        ds = sources.get(key)
        # Per-connector circuit breaker keys
        failures_key = f'connector:failures:{key}'
        open_key = f'connector:open:{key}'
        is_blocked = bool(cache.get(open_key))
        consecutive_failures = cache.get(failures_key, 0)

        result.append({
            'connector_key': key,
            'enabled': ds.enabled if ds else False,
            'source_name': ds.source_name if ds else key,
            'organization': ds.organization.short_name if ds else '—',
            'last_run_at': ds.last_run_at.isoformat() if ds and ds.last_run_at else None,
            'last_run_status': ds.last_run_status if ds else None,
            'is_blocked': is_blocked,
            'consecutive_failures': consecutive_failures,
            'action': 'Curar manualmente' if is_blocked else ('Ingerir' if ds and ds.enabled else 'Desativado'),
        })

    return Response(result)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def edition_patch(request, pk):
    """Inline admin edit for a TournamentEdition (manual override / curation)."""
    try:
        edition = TournamentEdition.objects.get(pk=pk)
    except TournamentEdition.DoesNotExist:
        return Response({'detail': 'Edição não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    ser = EditionPatchSerializer(edition, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    instance = ser.save(
        reviewed_at=timezone.now(),
        reviewed_by=request.user,
        is_manual_override=True,
    )
    # Return the patched fields (including is_published) plus list metadata.
    patched = EditionPatchSerializer(instance).data
    listed = TournamentEditionListSerializer(instance).data
    return Response({**listed, **patched})


class DataSourceSerializer(serializers.ModelSerializer):
    org_name = serializers.CharField(source='organization.short_name', read_only=True)

    class Meta:
        model = DataSource
        fields = (
            'id', 'organization', 'org_name', 'source_name', 'slug',
            'connector_key', 'source_type', 'base_url',
            'fetch_schedule_cron', 'priority', 'enabled',
            'legal_notes', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


@api_view(['GET'])
@permission_classes([IsSuperUser])
def data_sources_list(request):
    """List all data sources with optional filter by enabled status."""
    qs = DataSource.objects.select_related('organization').order_by('organization__short_name', 'priority')
    enabled = request.query_params.get('enabled')
    if enabled is not None:
        qs = qs.filter(enabled=enabled.lower() in ('1', 'true', 'yes'))
    return Response(DataSourceSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def execution_logs(request):
    """Return recent ingestion runs with timestamps, status, errors and service info."""
    limit = min(int(request.query_params.get('limit', 50)), 200)
    runs = (
        IngestionRun.objects
        .select_related('data_source__organization')
        .order_by('-started_at')[:limit]
    )
    data = []
    for run in runs:
        data.append({
            'id': run.id,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'duration_seconds': (
                int((run.finished_at - run.started_at).total_seconds())
                if run.finished_at and run.started_at else None
            ),
            'status': run.status,
            'service': run.data_source.source_name if run.data_source else 'manual',
            'organization': run.data_source.organization.short_name if run.data_source and run.data_source.organization else '—',
            'editions_found': run.items_fetched,
            'editions_created': run.items_created,
            'editions_updated': run.items_updated,
            'error': run.error_summary or '',
        })
    return Response(data)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def data_source_patch(request, pk):
    """Toggle or update a data source configuration."""
    try:
        source = DataSource.objects.get(pk=pk)
    except DataSource.DoesNotExist:
        return Response({'detail': 'Fonte não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    allowed_fields = {'enabled', 'fetch_schedule_cron', 'priority', 'legal_notes', 'base_url'}
    patch_data = {k: v for k, v in request.data.items() if k in allowed_fields}
    ser = DataSourceSerializer(source, data=patch_data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def debug_itf_sample(request):
    """
    GET /api/admin-panel/debug/itf-sample/?key=J-J100-GTM-2026-001
    Retorna um documento raw do MongoDB ITF para inspecionar o schema.
    Seguro: não modifica dados. Apenas staff pode acessar.
    """
    from apps.ingestion.connectors.itf_mongo import ItfMongoConnector
    key = request.query_params.get('key', '')
    conn = ItfMongoConnector()
    try:
        docs = conn.sample_raw(key=key, n=1)
        if not docs:
            return Response({'detail': 'Nenhum documento encontrado.', 'key': key})
        doc = docs[0]
        # Retorna apenas as chaves do documento (para ver o schema) + valores superficiais
        schema = {}
        for k, v in doc.items():
            if k == '_id':
                schema[k] = v
            elif isinstance(v, dict):
                schema[k] = {'_type': 'dict', '_keys': list(v.keys()), '_sample': str(v)[:100]}
            elif isinstance(v, list):
                schema[k] = {'_type': 'list', '_len': len(v), '_sample': str(v[:1])[:200]}
            else:
                schema[k] = v
        return Response({'key': key, 'fields': schema})
    finally:
        conn.close()


@api_view(['POST'])
@permission_classes([IsSuperUser])
def trigger_itf_sync(request):
    """
    POST /api/admin-panel/sync/itf/
    Dispara o sync ITF MongoDB → PostgreSQL imediatamente via Celery task.
    Requer ITF_MONGO_ENABLED=true no Railway.
    """
    from apps.ingestion.tasks import sync_itf_from_mongo_task
    task = sync_itf_from_mongo_task.delay()
    return Response({
        'detail': 'Sync ITF disparado em background.',
        'task_id': str(task.id),
        'hint': 'Acompanhe o resultado em /api/admin-panel/runs/ após ~1 minuto.',
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def trigger_db_cleanup(request):
    """
    POST /api/admin-panel/maintenance/cleanup/
    Executa cleanup_db --no-dry-run em background via Celery.
    Libera espaço removendo IngestionRun antigas, raw_payload, WebhookEvent e AuditLog obsoletos.
    """
    from apps.ingestion.tasks import cleanup_db_task
    task = cleanup_db_task.delay()
    return Response({
        'detail': 'Cleanup do banco disparado em background.',
        'task_id': str(task.id),
        'hint': 'Aguarde ~1-2 minutos. Verifique o volume Postgres após conclusão.',
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def trigger_cosat_sync(request):
    """
    POST /api/admin-panel/sync/cosat/
    Dispara o sync COSAT MongoDB → PostgreSQL imediatamente via Celery task.
    Requer COSAT_MONGO_ENABLED=true no Railway.
    """
    from apps.ingestion.tasks import sync_cosat_from_mongo_task
    task = sync_cosat_from_mongo_task.delay()
    return Response({
        'detail': 'Sync COSAT disparado em background.',
        'task_id': str(task.id),
        'hint': 'Acompanhe o resultado em /api/admin-panel/runs/ após ~1 minuto.',
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def ingestion_runs_list(request):
    """Recent ingestion runs (last 50)."""
    qs = (
        IngestionRun.objects
        .select_related('data_source__organization')
        .order_by('-started_at')[:50]
    )

    class RunSerializer(serializers.ModelSerializer):
        source_name = serializers.CharField(source='data_source.source_name', read_only=True)
        org_name = serializers.CharField(source='data_source.organization.short_name', read_only=True)

        class Meta:
            model = IngestionRun
            fields = (
                'id', 'source_name', 'org_name', 'status',
                'started_at', 'finished_at',
                'items_fetched', 'items_created', 'items_updated', 'changes_detected',
                'error_summary',
            )

    return Response(RunSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAdmin])
def waitlist_leads(request):
    """Lista (somente leitura) da tabela externa ``tenfy_waitlist_leads``.

    A tabela não é gerenciada pelo Django (criada por outro fluxo/landing).
    Consultamos direto via SQL, introspectando as colunas, para ser robusto ao
    esquema. Se a tabela não existir no banco padrão, retorna ``available=False``
    com um detalhe explicativo (sem quebrar o painel).
    """
    from django.db import connection

    TABLE = 'tenfy_waitlist_leads'
    try:
        limit = min(max(int(request.query_params.get('limit', 100)), 1), 500)
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(int(request.query_params.get('offset', 0)), 0)
    except (TypeError, ValueError):
        offset = 0

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                [TABLE],
            )
            columns = [row[0] for row in cur.fetchall()]
            if not columns:
                return Response({
                    'available': False,
                    'columns': [],
                    'results': [],
                    'count': 0,
                    'detail': 'Tabela tenfy_waitlist_leads não encontrada no banco.',
                })

            # Ordena pela coluna de data/criação quando existir; senão pela 1ª coluna.
            order_col = next(
                (c for c in ('created_at', 'inserted_at', 'createdAt', 'id') if c in columns),
                columns[0],
            )

            cur.execute('SELECT COUNT(*) FROM "{tbl}"'.format(tbl=TABLE))
            total = cur.fetchone()[0]

            cur.execute(
                'SELECT * FROM "{tbl}" ORDER BY "{col}" DESC LIMIT %s OFFSET %s'.format(
                    tbl=TABLE, col=order_col,
                ),
                [limit, offset],
            )
            result_cols = [c[0] for c in cur.description]
            results = []
            for row in cur.fetchall():
                item = {}
                for key, value in zip(result_cols, row):
                    if isinstance(value, (bytes, bytearray, memoryview)):
                        value = str(value)
                    item[key] = value
                results.append(item)
    except Exception as exc:  # noqa: BLE001 — diagnóstico amigável para o admin
        return Response({
            'available': False,
            'columns': [],
            'results': [],
            'count': 0,
            'detail': 'Erro ao consultar tenfy_waitlist_leads: {0}'.format(exc),
        })

    return Response({
        'available': True,
        'columns': result_cols,
        'results': results,
        'count': total,
        'limit': limit,
        'offset': offset,
    })
