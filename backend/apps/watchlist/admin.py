from django.contrib import admin
from .models import WatchlistItem


@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'edition', 'user_status', 'created_at')
    list_filter = ('user_status',)
    search_fields = ('user__email', 'edition__title')
    autocomplete_fields = ('user', 'edition', 'profile')
