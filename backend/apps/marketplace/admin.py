from django.contrib import admin
from .models import Merchant, Offer, OfferTargeting


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state', 'active')
    list_filter = ('active', 'state')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('title', 'merchant', 'price_brl', 'active', 'valid_from', 'valid_to')
    list_filter = ('active',)


@admin.register(OfferTargeting)
class OfferTargetingAdmin(admin.ModelAdmin):
    list_display = ('offer', 'city', 'state', 'tournament_edition')
