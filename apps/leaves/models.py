import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class LeaveType(models.Model):
    """Organization leave type with policy settings."""

    class GenderEligibility(models.TextChoices):
        ALL = "ALL", "All employees"
        MALE = "MALE", "Male only"
        FEMALE = "FEMALE", "Female only"

    class ApplicableTo(models.TextChoices):
        ALL = "ALL", "All employees"
        DEPARTMENT = "DEPARTMENT", "Specific departments"
        DESIGNATION = "DESIGNATION", "Specific designations"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="leave_types",
    )
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default="#8b5cf6")
    annual_quota = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Annual days allowed; leave empty until configured.",
    )
    carry_forward_max = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    accrual_monthly = models.BooleanField(
        default=False,
        help_text="Accrue quota monthly instead of yearly lump sum.",
    )
    gender_eligibility = models.CharField(
        max_length=10,
        choices=GenderEligibility.choices,
        default=GenderEligibility.ALL,
    )
    applicable_to = models.CharField(
        max_length=20,
        choices=ApplicableTo.choices,
        default=ApplicableTo.ALL,
        help_text="Which employees may use this leave type.",
    )
    applicable_departments = models.ManyToManyField(
        "organizations.Department",
        blank=True,
        related_name="leave_types",
    )
    applicable_designations = models.ManyToManyField(
        "grades.Designation",
        blank=True,
        related_name="leave_types",
    )
    requires_attachment = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_leave_type_code_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def is_applicable_to(self, user) -> bool:
        """Whether this leave type is available to the given employee.

        Checks gender eligibility and the All/Department/Designation scope.
        """
        # Only filter by gender when the user has one recorded (legacy behavior).
        if self.gender_eligibility != self.GenderEligibility.ALL and user.gender:
            if self.gender_eligibility == self.GenderEligibility.MALE and user.gender != "MALE":
                return False
            if self.gender_eligibility == self.GenderEligibility.FEMALE and user.gender != "FEMALE":
                return False
        if self.applicable_to == self.ApplicableTo.DEPARTMENT:
            if not user.department_id:
                return False
            return self.applicable_departments.filter(pk=user.department_id).exists()
        if self.applicable_to == self.ApplicableTo.DESIGNATION:
            if not user.org_designation_id:
                return False
            return self.applicable_designations.filter(pk=user.org_designation_id).exists()
        return True


class Holiday(models.Model):
    class HolidayType(models.TextChoices):
        NATIONAL = "NATIONAL", "National"
        COMPANY = "COMPANY", "Company"
        OPTIONAL = "OPTIONAL", "Optional"
        FESTIVAL = "FESTIVAL", "Festival"
        REGIONAL = "REGIONAL", "Regional"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="holidays",
    )
    name = models.CharField(max_length=120)
    date = models.DateField()
    holiday_type = models.CharField(
        max_length=20,
        choices=HolidayType.choices,
        default=HolidayType.COMPANY,
    )
    branch = models.CharField(max_length=120, blank=True, help_text="Blank = all branches")
    is_optional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "date", "name"],
                name="unique_holiday_per_org_date_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.date})"


class LeaveBalance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_balances",
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="balances")
    year = models.PositiveSmallIntegerField()
    allocated = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0"))
    used = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0"))
    adjusted = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0"),
        help_text="Manual HR/Admin adjustment (positive or negative).",
    )
    carried_forward = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "leave_type", "year"],
                name="unique_leave_balance_per_user_type_year",
            ),
        ]

    @property
    def remaining(self) -> Decimal:
        return self.allocated + self.carried_forward + self.adjusted - self.used

    def __str__(self) -> str:
        return f"{self.user_id} · {self.leave_type.code} · {self.year}"


class AttendanceLeaveDeduction(models.Model):
    """Tracks automatic leave-balance deductions triggered by absent attendance records.

    Multiple rows per AttendanceRecord are allowed when the deduction splits across
    several leave types in the priority chain. Deleting all rows for a record_id
    reverses the full deduction (the service handles balance updates).
    """

    attendance_record_id = models.UUIDField(
        db_index=True,
        help_text="PK of the AttendanceRecord that triggered this deduction.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_leave_deductions",
    )
    leave_balance = models.ForeignKey(
        LeaveBalance,
        on_delete=models.CASCADE,
        related_name="attendance_deductions",
    )
    days = models.DecimalField(max_digits=4, decimal_places=1)
    attendance_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attendance_date"]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.attendance_date} · -{self.days}d"


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class HalfDay(models.TextChoices):
        NONE = "NONE", "Full day(s)"
        FIRST_HALF = "FIRST_HALF", "First half"
        SECOND_HALF = "SECOND_HALF", "Second half"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    total_days = models.DecimalField(max_digits=5, decimal_places=1)
    half_day = models.CharField(max_length=20, choices=HalfDay.choices, default=HalfDay.NONE)
    reason = models.TextField()
    attachment = models.FileField(upload_to="leave_attachments/", blank=True, null=True)
    emergency_contact = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    applied_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applied_at"]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.leave_type.code} · {self.start_date}"

    @property
    def current_stage_label(self) -> str:
        """Human stage, e.g. 'Pending — Manager approval', derived from the chain.

        Iterates ``approvals.all()`` so a ``prefetch_related("approvals")`` on the
        queryset avoids per-row queries (approvals are ordered by step).
        """
        if self.status != self.Status.PENDING:
            return self.get_status_display()
        first_pending = next(
            (a for a in self.approvals.all() if a.status == LeaveApproval.StepStatus.PENDING),
            None,
        )
        if first_pending and first_pending.step_label:
            return f"Pending — {first_pending.step_label}"
        return self.get_status_display()


class LeaveApproval(models.Model):
    class StepStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SKIPPED = "SKIPPED", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    leave_request = models.ForeignKey(
        LeaveRequest,
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_approval_steps",
    )
    step = models.PositiveSmallIntegerField(help_text="1=Manager, 2=HR, 3=Final")
    step_label = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=StepStatus.choices, default=StepStatus.PENDING)
    comment = models.TextField(blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["step"]
