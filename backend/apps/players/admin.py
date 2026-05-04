from django.contrib import admin
from .models import PlayerProfile, PlayerCategory, PlayerProfileCategory


@admin.register(PlayerCategory)
class PlayerCategoryAdmin(admin.ModelAdmin):
    list_display = ('taxonomy', 'code', 'label_ptbr', 'gender_scope', 'min_age', 'max_age', 'class_level')
    list_filter = ('taxonomy', 'gender_scope', 'class_level')
    search_fields = ('code', 'label_ptbr')


class PlayerProfileCategoryInline(admin.TabularInline):
    model = PlayerProfileCategory
    extra = 0


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'birth_year', 'gender', 'home_state', 'competitive_level', 'is_primary')
    list_filter = ('competitive_level', 'home_state', 'gender', 'is_primary')
    search_fields = ('display_name', 'user__email')
    inlines = [PlayerProfileCategoryInline]
