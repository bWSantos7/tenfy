from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from .models import AuditLog


@shared_task
def cleanup_old_logs(days: int = 180):
    """Remove audit logs older than N days (default 180)."""
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
    return deleted
