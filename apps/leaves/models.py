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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="leave_types",
    )
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40)
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
        return self.allocated + self.carried_forward - self.used

    def __str__(self) -> str:
        return f"{self.user_id} · {self.leave_type.code} · {self.year}"


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
