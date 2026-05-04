from django.conf import settings
from django.db import models
from apps.core.models import TimestampedModel


class AuditLog(TimestampedModel):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_OVERRIDE = 'override'
    ACTION_INGEST = 'ingest'
    ACTION_LOGIN = 'login'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Criação'),
        (ACTION_UPDATE, 'Atualização'),
        (ACTION_DELETE, 'Exclusão'),
        (ACTION_OVERRIDE, 'Override manual'),
        (ACTION_INGEST, 'Ingestão'),
        (ACTION_LOGIN, 'Login'),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='audit_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=60)
    diff = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'[{self.action}] {self.entity_type}:{self.entity_id} by {self.actor_id}'
