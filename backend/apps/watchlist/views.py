import logging
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import WatchlistItem, TournamentResult
from .serializers import WatchlistItemSerializer, TournamentResultSerializer
from apps.tournaments.models import TournamentEdition

logger = logging.getLogger('apps.watchlist')


def _audit(user, action_name: str, resource_id: str, detail: str = ''):
    try:
        from apps.audit.models import AuditLog
        AuditLog.objects.create(
            actor=user,
            action=action_name,
            resource_type='watchlist',
            resource_id=resource_id,
            changes={'detail': detail},
        )
    except Exception as exc:
        logger.warning('Audit log failed: %s', exc)


class WatchlistViewSet(viewsets.ModelViewSet):
    serializer_class = WatchlistItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('user_status',)

    def _managed_child_ids(self):
        from apps.accounts.models import ParentChild
        return list(
            ParentChild.objects
            .filter(parent=self.request.user, is_active=True)
            .values_list('child_id', flat=True)
        )

    def get_queryset(self):
        user = self.request.user

        if user.role == 'parent':
            child_ids = self._managed_child_ids()
            # All IDs the parent is allowed to see: themselves + managed children
            allowed_ids = [user.id, *child_ids]

            requested_user_id = self.request.query_params.get('user_id')
            if requested_user_id:
                # ?user_id=X → return items for that specific user (if allowed)
                try:
                    requested_user_id_int = int(requested_user_id)
                except (TypeError, ValueError):
                    requested_user_id_int = None
                user_ids = [requested_user_id_int] if requested_user_id_int in allowed_ids else []
            else:
                # No filter: return ONLY the parent's own items.
                # Children's items are fetched via ?user_id=<child_id> individually.
                # This prevents duplication in list views.
                user_ids = [user.id]
        else:
            user_ids = [user.id]

        return (
            WatchlistItem.objects
            .filter(user_id__in=user_ids)
            .select_related('edition__tournament__organization', 'edition__venue', 'profile')
            .order_by('-created_at')
        )

    def get_object(self):
        """
        Allow parent users to retrieve (and PATCH/DELETE) items belonging to
        themselves OR any of their managed children, even though get_queryset
        only returns the parent's own items by default.
        """
        user = self.request.user
        if user.role == 'parent':
            child_ids = self._managed_child_ids()
            allowed_ids = [user.id, *child_ids]
            try:
                obj = (
                    WatchlistItem.objects
                    .select_related('edition__tournament__organization', 'edition__venue', 'profile')
                    .filter(user_id__in=allowed_ids)
                    .get(pk=self.kwargs['pk'])
                )
            except WatchlistItem.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound()
            self.check_object_permissions(self.request, obj)
            return obj
        return super().get_object()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        qs = self.get_queryset()
        today = timezone.now().date()
        upcoming = qs.filter(edition__start_date__gte=today)
        past = qs.filter(edition__end_date__lt=today)
        active_registrations = qs.filter(user_status=WatchlistItem.STATUS_REGISTERED).count()
        return Response({
            'total': qs.count(),
            'active_registrations': active_registrations,
            'upcoming': upcoming.count(),
            'past': past.count(),
            'by_status': {
                s[0]: qs.filter(user_status=s[0]).count()
                for s in WatchlistItem.STATUS_CHOICES
            },
        })

    @action(detail=True, methods=['post', 'patch', 'delete'], url_path='result')
    def save_result(self, request, pk=None):
        """Create or update the result for a completed watchlist item."""
        item = self.get_object()
        if request.method == 'DELETE':
            TournamentResult.objects.filter(watchlist_item=item).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        result_obj, _ = TournamentResult.objects.get_or_create(watchlist_item=item)
        ser = TournamentResultSerializer(result_obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        # Automatically mark item as completed when a result is saved
        if item.user_status != WatchlistItem.STATUS_COMPLETED:
            item.user_status = WatchlistItem.STATUS_COMPLETED
            item.save(update_fields=['user_status', 'updated_at'])
        return Response(ser.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle(self, request):
        """Toggle membership: if exists, remove; else create with defaults."""
        edition_id = request.data.get('edition_id')
        profile_id = request.data.get('profile_id')
        if not edition_id:
            return Response({'error': 'edition_id obrigatório'}, status=400)
        try:
            edition = TournamentEdition.objects.get(pk=edition_id)
        except TournamentEdition.DoesNotExist:
            return Response({'error': 'Edição não encontrada'}, status=404)
        owner = request.user
        if profile_id:
            from apps.players.models import PlayerProfile
            try:
                profile = PlayerProfile.objects.select_related('user').get(pk=profile_id)
            except PlayerProfile.DoesNotExist:
                return Response({'error': 'Perfil não encontrado'}, status=404)

            if request.user.role == 'parent':
                if profile.user_id not in self._managed_child_ids():
                    return Response(
                        {'detail': 'Este perfil não pertence a um dependente gerenciado por você.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                # WatchlistItem is created ONLY for the dependent's user.
                # The parent's agenda already shows all dependents' items via
                # get_queryset(allowed_ids) — no duplication needed.
                owner = profile.user
            elif profile.user_id != request.user.id:
                return Response(
                    {'detail': 'Este perfil não pertence ao usuário autenticado.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        item = WatchlistItem.objects.filter(user=owner, edition=edition).first()
        if item:
            item.delete()
            _audit(request.user, 'watchlist.remove', str(edition_id), f'Removed edition {edition_id} from watchlist')
            return Response({'watching': False, 'edition_id': edition_id})

        item = WatchlistItem.objects.create(
            user=owner,
            edition=edition,
            profile_id=profile_id,
        )
        _audit(request.user, 'watchlist.add', str(edition_id), f'Added edition {edition_id} to watchlist')
        return Response({
            'watching': True,
            'edition_id': edition_id,
            'item': WatchlistItemSerializer(item).data,
        }, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        _audit(self.request.user, 'watchlist.remove', str(instance.edition_id), f'Removed edition {instance.edition_id} from watchlist')
        instance.delete()

    def perform_update(self, serializer):
        old_status = serializer.instance.user_status
        saved = serializer.save()
        if saved.user_status != old_status:
            _audit(self.request.user, 'watchlist.status_change', str(saved.edition_id),
                   f'Status changed: {old_status} → {saved.user_status}')
