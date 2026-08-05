import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ShiftRotation(models.Model):
    """Rotational shift pattern for teams or departments."""

    class CycleUnit(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shift_rotations",
    )
    name = models.CharField(max_length=120)
    cycle_unit = models.CharField(max_length=10, choices=CycleUnit.choices, default=CycleUnit.WEEKLY)
    cycle_length = models.PositiveSmallIntegerField(default=3)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ShiftRotationStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rotation = models.ForeignKey(ShiftRotation, on_delete=models.CASCADE, related_name="steps")
    shift = models.ForeignKey("attendance.WorkShift", on_delete=models.CASCADE)
    step_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["rotation", "step_order"],
                name="unique_rotation_step_order",
            ),
        ]


class ShiftAssignment(models.Model):
    """Dated shift schedule entry (overrides default work_shift for a day)."""

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shift_assignments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shift_assignments",
    )
    shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.CharField(max_length=255, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_assigned",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "user__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="unique_shift_assignment_per_user_day",
            ),
        ]


class ShiftSwapRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shift_swap_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shift_swaps_requested",
    )
    swap_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shift_swaps_received",
    )
    date = models.DateField()
    current_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.CASCADE,
        related_name="swap_requests_from",
    )
    requested_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.CASCADE,
        related_name="swap_requests_to",
    )
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shift_swaps_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OvertimeRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="overtime_records",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="overtime_records",
    )
    date = models.DateField()
    minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_overtime_per_user_day"),
        ]


class ShiftChange(models.Model):
    """Audit record for every shift reassignment made by HR/Admin."""

    class Scope(models.TextChoices):
        WEEK = "WEEK", "This week"
        MONTH = "MONTH", "This month"
        CUSTOM = "CUSTOM", "Custom range"
        PERMANENT = "PERMANENT", "Entire employment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shift_changes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shift_changes",
    )
    old_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    new_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.CASCADE,
        related_name="shift_change_targets",
    )
    scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.PERMANENT)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="shift_changes_made",
    )
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ShiftApproval(models.Model):
    """Approval log for assignments / overtime."""

    class ApprovalType(models.TextChoices):
        ASSIGNMENT = "ASSIGNMENT", "Shift assignment"
        SWAP = "SWAP", "Shift swap"
        OVERTIME = "OVERTIME", "Overtime"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shift_approvals",
    )
    approval_type = models.CharField(max_length=20, choices=ApprovalType.choices)
    reference_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shift_approvals_reviewed",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
