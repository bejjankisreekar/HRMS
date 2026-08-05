import uuid

from django.conf import settings
from django.db import models


class Rule(models.Model):
    """A configurable IF <conditions> THEN <actions> business rule.

    ``conditions`` is a list of AND-groups combined with OR:
    ``[[{"field": "employee.department", "operator": "EQUALS", "value": "IT"}, ...], ...]``.
    ``actions`` is an ordered list: ``[{"type": "ADD_LEAVE", "params": {...}}, ...]``.
    Storing both as JSON (rather than normalized tables) is what lets an org
    configure a brand new rule with zero code changes or deploys.
    """

    class Trigger(models.TextChoices):
        ATTENDANCE_MARKED = "ATTENDANCE_MARKED", "Attendance marked"
        LEAVE_REQUESTED = "LEAVE_REQUESTED", "Leave requested"
        SCHEDULED = "SCHEDULED", "Scheduled (batch)"
        MANUAL = "MANUAL", "Manual only"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"
        DRAFT = "DRAFT", "Draft"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="rules",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    trigger_event = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.MANUAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    priority = models.IntegerField(default=100, help_text="Lower number runs first.")
    conditions = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list, blank=True)
    is_test_mode = models.BooleanField(
        default=False,
        help_text="When on, the rule evaluates and logs but actions never mutate real data.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rules_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rules_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "created_at"]
        indexes = [
            models.Index(fields=["organization", "trigger_event", "status"], name="rule_org_trigger_status_idx"),
            models.Index(fields=["organization", "priority"], name="rule_org_priority_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_trigger_event_display()})"


class RuleExecutionLog(models.Model):
    """One row per rule evaluated against a subject — the "execution log"."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="rule_execution_logs",
    )
    rule = models.ForeignKey(
        Rule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_logs",
    )
    rule_name_snapshot = models.CharField(max_length=150, blank=True)
    trigger_event = models.CharField(max_length=20, choices=Rule.Trigger.choices)
    subject_type = models.CharField(max_length=32, blank=True)
    subject_id = models.CharField(max_length=64, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    matched = models.BooleanField(default=False)
    is_test_run = models.BooleanField(default=False)
    actions_result = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="rule_exec_org_created_idx"),
            models.Index(fields=["rule", "-created_at"], name="rule_exec_rule_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rule_name_snapshot} · {'matched' if self.matched else 'no match'} · {self.created_at}"


class RuleAuditLog(models.Model):
    """Audit trail for rule CRUD/lifecycle actions (mirrors PayrollAuditLog / TeamActionAuditLog)."""

    class Action(models.TextChoices):
        CREATED = "CREATED", "Rule created"
        UPDATED = "UPDATED", "Rule updated"
        ENABLED = "ENABLED", "Rule enabled"
        DISABLED = "DISABLED", "Rule disabled"
        DELETED = "DELETED", "Rule deleted"
        PRIORITY_CHANGED = "PRIORITY_CHANGED", "Rule priority changed"
        TESTED = "TESTED", "Rule tested (dry run)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="rule_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rule_actions_performed",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    object_id = models.UUIDField(null=True, blank=True, help_text="PK of the affected rule.")
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="rule_audit_org_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.summary}"


class RuleApprovalRequest(models.Model):
    """Generic approval to-do created by a CREATE_APPROVAL rule action.

    No generic approval model exists in this codebase today (only the
    leave-specific ``LeaveApproval``), so this is a small, purpose-built one
    for rule-driven approvals of arbitrary subjects.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="rule_approval_requests",
    )
    rule = models.ForeignKey(
        Rule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    subject_type = models.CharField(max_length=32, blank=True)
    subject_id = models.CharField(max_length=64, blank=True)
    requested_for = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rule_approvals_requested_for",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rule_approvals_to_review",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Approval for {self.subject_type}:{self.subject_id} ({self.status})"
