from django.conf import settings
from django.db import models
from apps.core.models import TimestampedModel
from apps.players.models import PlayerProfile
from apps.tournaments.models import TournamentEdition


class WatchlistItem(TimestampedModel):
    STATUS_NONE = 'none'
    STATUS_INTENDED = 'intended'
    STATUS_REGISTERED = 'registered_declared'
    STATUS_WITHDRAWN = 'withdrawn'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_NONE, 'Não iniciado'),
        (STATUS_INTENDED, 'Pretendo inscrever'),
        (STATUS_REGISTERED, 'Inscrito (auto-declarado)'),
        (STATUS_WITHDRAWN, 'Desisti'),
        (STATUS_COMPLETED, 'Concluído'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watchlist_items'
    )
    profile = models.ForeignKey(
        PlayerProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='watchlist_items'
    )
    edition = models.ForeignKey(
        TournamentEdition, on_delete=models.CASCADE, related_name='watchers'
    )
    user_status = models.CharField(max_length=25, choices=STATUS_CHOICES, default=STATUS_NONE)
    notes = models.TextField(blank=True)

    # Alert preferences (overrides global defaults)
    alert_on_deadline = models.BooleanField(default=True)
    alert_on_changes = models.BooleanField(default=True)
    alert_on_draws = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'edition')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['edition']),
        ]

    def __str__(self):
        return f'{self.user.email} ♥ {self.edition.title}'


class TournamentResult(TimestampedModel):
    """Records the outcome of a completed tournament participation."""
    watchlist_item = models.OneToOneField(
        WatchlistItem, on_delete=models.CASCADE, related_name='result'
    )
    category_played = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(null=True, blank=True, help_text='Final position (1 = winner)')
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Result: {self.watchlist_item}'
