from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from .models import Alert, PushSubscription, UserAlertPreference
from .serializers import AlertSerializer, UserAlertPreferenceSerializer


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('kind', 'channel', 'status')

    def get_queryset(self):
        return Alert.objects.filter(user=self.request.user).select_related('edition').order_by('-created_at')

    @action(detail=False, methods=['get'])
    def unread(self, request):
        qs = self.get_queryset().exclude(status=Alert.STATUS_READ)
        page = self.paginate_queryset(qs)
        ser = AlertSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(ser.data)
        return Response({'count': qs.count(), 'results': ser.data})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        now = timezone.now()
        n = self.get_queryset().exclude(status=Alert.STATUS_READ).update(
            status=Alert.STATUS_READ, read_at=now
        )
        return Response({'marked_read': n})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        a = self.get_object()
        a.status = Alert.STATUS_READ
        a.read_at = timezone.now()
        a.save(update_fields=['status', 'read_at', 'updated_at'])
        return Response(AlertSerializer(a).data)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def preferences(request):
    prefs = UserAlertPreference.get_or_create_defaults(request.user)
    if request.method == 'GET':
        return Response(UserAlertPreferenceSerializer(prefs).data)
    ser = UserAlertPreferenceSerializer(prefs, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)


@api_view(['POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def push_subscribe(request):
    """Register or unregister a Web Push subscription."""
    endpoint = (request.data.get('endpoint') or '').strip()
    if not endpoint:
        return Response({'detail': 'endpoint obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response({'detail': 'Inscrição removida.'}, status=status.HTTP_204_NO_CONTENT)

    keys = request.data.get('keys', {})
    p256dh = keys.get('p256dh', '')
    auth = keys.get('auth', '')
    if not p256dh or not auth:
        return Response({'detail': 'keys.p256dh e keys.auth são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

    sub, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': request.user,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
        },
    )
    # Ensure push_enabled on preferences
    prefs = UserAlertPreference.get_or_create_defaults(request.user)
    if not prefs.push_enabled:
        prefs.push_enabled = True
        prefs.save(update_fields=['push_enabled', 'updated_at'])

    return Response({'detail': 'Inscrição registrada.', 'created': created}, status=status.HTTP_200_OK)
