import uuid

from django.conf import settings
from django.db import models


class DashboardNotification(models.Model):
    """Per-user dashboard notification with read/unread state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_notifications",
    )
    source_key = models.CharField(max_length=120, db_index=True)
    title = models.CharField(max_length=255)
    message = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=500)
    icon = models.CharField(max_length=40, default="bell")
    notification_type = models.CharField(max_length=30, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_key"],
                name="unique_dashboard_notification_per_user_source",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({'read' if self.is_read else 'unread'})"
