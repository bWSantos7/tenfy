from django.conf import settings
from django.db import models
from apps.core.models import TimestampedModel
from apps.tournaments.models import TournamentEdition


class UserAlertPreference(TimestampedModel):
    """Global alert preferences for a user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alert_preference'
    )
    email_enabled = models.BooleanField(default=False)  # Email notifications disabled
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)

    deadline_days = models.JSONField(default=list,
                                     help_text='Days before close to notify, e.g. [7,2,0]')
    changes_enabled = models.BooleanField(default=True)
    draws_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f'AlertPrefs<{self.user.email}>'

    @classmethod
    def get_or_create_defaults(cls, user):
        obj, created = cls.objects.get_or_create(
            user=user,
            defaults={
                'deadline_days': [7, 2, 0],
            },
        )
        return obj


class Alert(TimestampedModel):
    KIND_DEADLINE = 'deadline'
    KIND_CHANGE = 'change'
    KIND_DRAWS = 'draws'
    KIND_CANCELED = 'canceled'
    KIND_OTHER = 'other'
    KIND_CHOICES = [
        (KIND_DEADLINE, 'Prazo se aproximando'),
        (KIND_CHANGE, 'Dados alterados'),
        (KIND_DRAWS, 'Chaves publicadas'),
        (KIND_CANCELED, 'Cancelado'),
        (KIND_OTHER, 'Outro'),
    ]

    CHANNEL_IN_APP = 'in_app'
    CHANNEL_EMAIL = 'email'
    CHANNEL_PUSH = 'push'
    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, 'In-app'),
        (CHANNEL_EMAIL, 'E-mail'),
        (CHANNEL_PUSH, 'Push'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_READ = 'read'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_SENT, 'Enviado'),
        (STATUS_FAILED, 'Falhou'),
        (STATUS_READ, 'Lido'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alerts'
    )
    edition = models.ForeignKey(
        TournamentEdition, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='alerts'
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    dispatched_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    # Deduplication key: "kind:edition:daysbefore" etc.
    dedup_key = models.CharField(max_length=200, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['kind']),
            models.Index(fields=['dedup_key']),
        ]

    def __str__(self):
        return f'[{self.kind}] {self.title} -> {self.user.email}'


class PushSubscription(TimestampedModel):
    """Stores a Web Push subscription for a user device."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_subscriptions'
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PushSub<{self.user.email}>'
