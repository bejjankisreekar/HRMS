import uuid

from django.conf import settings
from django.db import models


class TeamActionAuditLog(models.Model):
    """Immutable audit trail of actions a manager takes on their team.

    Lives in the shared (public) schema alongside the other audit logs
    (``accounts.StaffAuditLog`` / ``accounts.LoginAuditLog``); every row carries
    its ``organization`` so it is always scoped to one tenant.
    """

    class Action(models.TextChoices):
        LEAVE_APPROVE = "LEAVE_APPROVE", "Leave approved"
        LEAVE_REJECT = "LEAVE_REJECT", "Leave rejected"
        LEAVE_APPLY = "LEAVE_APPLY", "Leave applied"
        LEAVE_CANCEL = "LEAVE_CANCEL", "Leave cancelled"
        BALANCE_ADJUST = "BALANCE_ADJUST", "Leave balance adjusted"
        REGULARIZATION_APPROVE = "REGULARIZATION_APPROVE", "Attendance regularization approved"
        REGULARIZATION_REJECT = "REGULARIZATION_REJECT", "Attendance regularization rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="team_action_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_actions_performed",
        help_text="The manager who performed the action.",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_actions_received",
        help_text="The employee the action was taken on.",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    object_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="PK of the affected leave request / regularization request.",
    )
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "team action audit log"
        verbose_name_plural = "team action audit logs"
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="team_audit_org_created_idx"),
            models.Index(fields=["actor", "-created_at"], name="team_audit_actor_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.summary}"
