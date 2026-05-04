from rest_framework import viewsets, serializers as rf_serializers
from apps.core.permissions import IsAdminOrReadOnly
from .models import Merchant, Offer, OfferTargeting


class MerchantSerializer(rf_serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ('id', 'name', 'slug', 'email', 'website_url', 'city', 'state', 'active', 'description')


class OfferSerializer(rf_serializers.ModelSerializer):
    merchant_name = rf_serializers.CharField(source='merchant.name', read_only=True)

    class Meta:
        model = Offer
        fields = (
            'id', 'merchant', 'merchant_name', 'title', 'description',
            'price_brl', 'link_url', 'active', 'valid_from', 'valid_to',
        )


class OfferTargetingSerializer(rf_serializers.ModelSerializer):
    class Meta:
        model = OfferTargeting
        fields = ('id', 'offer', 'city', 'state', 'tournament_edition')


class MerchantViewSet(viewsets.ModelViewSet):
    queryset = Merchant.objects.all()
    serializer_class = MerchantSerializer
    permission_classes = [IsAdminOrReadOnly]


class OfferViewSet(viewsets.ModelViewSet):
    queryset = Offer.objects.select_related('merchant').all()
    serializer_class = OfferSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('merchant', 'active')


class OfferTargetingViewSet(viewsets.ModelViewSet):
    queryset = OfferTargeting.objects.all()
    serializer_class = OfferTargetingSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ('city', 'state', 'tournament_edition')
