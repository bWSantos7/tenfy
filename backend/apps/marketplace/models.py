from django.db import models
from apps.core.models import TimestampedModel
from apps.tournaments.models import TournamentEdition


class Merchant(TimestampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Offer(TimestampedModel):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='offers')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price_brl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    link_url = models.URLField()
    active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.merchant.name} - {self.title}'


class OfferTargeting(TimestampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='targetings')
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    tournament_edition = models.ForeignKey(
        TournamentEdition, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='offers'
    )

    class Meta:
        indexes = [
            models.Index(fields=['city']),
            models.Index(fields=['state']),
        ]
