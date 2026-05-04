from rest_framework import serializers
from .models import PlayerProfile, PlayerCategory, PlayerProfileCategory


class PlayerCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerCategory
        fields = (
            'id', 'taxonomy', 'code', 'label_ptbr',
            'gender_scope', 'min_age', 'max_age', 'class_level', 'description'
        )


class PlayerProfileCategorySerializer(serializers.ModelSerializer):
    category_detail = PlayerCategorySerializer(source='category', read_only=True)

    class Meta:
        model = PlayerProfileCategory
        fields = ('id', 'category', 'category_detail', 'is_primary', 'confidence')


class PlayerProfileSerializer(serializers.ModelSerializer):
    categories = PlayerProfileCategorySerializer(
        source='profile_categories', many=True, read_only=True
    )
    sporting_age = serializers.IntegerField(read_only=True)

    class Meta:
        model = PlayerProfile
        fields = (
            'id', 'display_name', 'birth_year', 'birth_date',
            'gender', 'home_state', 'home_city', 'travel_radius_km',
            'competitive_level', 'dominant_hand', 'tennis_class',
            'is_primary', 'external_ids', 'categories', 'sporting_age',
            'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at', 'sporting_age')

    def create(self, validated_data):
        user = self.context['request'].user
        if user.role == 'player' and PlayerProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                'Contas do tipo jogador podem manter apenas um perfil esportivo.'
            )
        # Ensure only one primary per user
        if validated_data.get('is_primary', True):
            PlayerProfile.objects.filter(user=user, is_primary=True).update(is_primary=False)
        return PlayerProfile.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        user = instance.user
        if validated_data.get('is_primary', False):
            PlayerProfile.objects.filter(user=user, is_primary=True).exclude(pk=instance.pk).update(is_primary=False)
        return super().update(instance, validated_data)

    def validate_birth_year(self, value):
        if value is None:
            return value
        from datetime import datetime
        cur = datetime.now().year
        if value < 1900 or value > cur:
            raise serializers.ValidationError('Ano de nascimento inválido.')
        return value

    def validate_home_state(self, value):
        if value and len(value) != 2:
            raise serializers.ValidationError('UF deve ter 2 caracteres.')
        return value.upper() if value else value
