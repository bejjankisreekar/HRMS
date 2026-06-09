import uuid
from datetime import datetime, time

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class WorkShift(models.Model):
    """Organization work shift with start/end and late buffer (grace minutes)."""

    class ShiftType(models.TextChoices):
        GENERAL = "GENERAL", "General Shift"
        MORNING = "MORNING", "Morning Shift"
        EVENING = "EVENING", "Evening Shift"
        NIGHT = "NIGHT", "Night Shift"
        ROTATIONAL = "ROTATIONAL", "Rotational Shift"
        FLEXIBLE = "FLEXIBLE", "Flexible Shift"
        SPLIT = "SPLIT", "Split Shift"
        WFH = "WFH", "Work From Home Shift"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="work_shifts",
    )
    name = models.CharField(max_length=80)
    shift_code = models.CharField(max_length=20, blank=True)
    shift_type = models.CharField(
        max_length=20,
        choices=ShiftType.choices,
        default=ShiftType.GENERAL,
    )
    start_time = models.TimeField(default=time(9, 0))
    end_time = models.TimeField(default=time(18, 0))
    break_minutes = models.PositiveSmallIntegerField(default=60)
    grace_minutes = models.PositiveSmallIntegerField(
        default=15,
        help_text="Minutes after shift start before marking as late.",
    )
    weekly_off_days = models.CharField(
        max_length=20,
        blank=True,
        help_text="Comma-separated weekday numbers (0=Mon … 6=Sun).",
    )
    color = models.CharField(max_length=7, default="#8b5cf6")
    description = models.TextField(blank=True)
    branch = models.CharField(max_length=120, blank=True)
    night_allowance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, blank=True
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(is_default=True),
                name="unique_default_shift_per_org",
            ),
        ]

    def __str__(self) -> str:
        default = " (Default)" if self.is_default else ""
        return f"{self.name}{default}"

    @property
    def time_range_display(self) -> str:
        return f"{self.start_time.strftime('%I:%M %p').lstrip('0')} – {self.end_time.strftime('%I:%M %p').lstrip('0')}"

    @property
    def crosses_midnight(self) -> bool:
        return self.end_time <= self.start_time

    @property
    def scheduled_minutes(self) -> int:
        from datetime import datetime, timedelta

        start = datetime.combine(timezone.localdate(), self.start_time)
        end = datetime.combine(timezone.localdate(), self.end_time)
        if self.crosses_midnight:
            end += timedelta(days=1)
        mins = int((end - start).total_seconds() // 60) - int(self.break_minutes or 0)
        return max(mins, 0)

    @property
    def working_hours_display(self) -> str:
        mins = self.scheduled_minutes
        h, m = divmod(mins, 60)
        if h and m:
            return f"{h}h {m}m"
        return f"{h}h" if h else f"{m}m"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"
        HALF_DAY = "HALF_DAY", "Half day"
        LEAVE = "LEAVE", "On leave"
        WFH = "WFH", "Work from home"
        HOLIDAY = "HOLIDAY", "Holiday"
        WEEKEND_OFF = "WEEKEND_OFF", "Weekend Off"

    class AttendanceSource(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        WEB = "WEB", "Web portal"
        MOBILE = "MOBILE", "Mobile app"
        BIOMETRIC = "BIOMETRIC", "Biometric"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(default=0)
    attendance_source = models.CharField(
        max_length=20,
        choices=AttendanceSource.choices,
        default=AttendanceSource.WEB,
        blank=True,
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_attendance_per_user_day"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.date} · {self.status}"


class BreakRecord(models.Model):
    """Individual break session logged against an attendance record."""

    class BreakType(models.TextChoices):
        TEA      = "TEA",      "Tea break"
        LUNCH    = "LUNCH",    "Lunch break"
        PERSONAL = "PERSONAL", "Personal"
        OTHER    = "OTHER",    "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="break_records",
    )
    break_type = models.CharField(
        max_length=20,
        choices=BreakType.choices,
        default=BreakType.OTHER,
    )
    start_time  = models.DateTimeField()
    end_time    = models.DateTimeField(null=True, blank=True)
    note        = models.CharField(max_length=100, blank=True)
    marked_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="breaks_marked",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]

    def __str__(self) -> str:
        return f"{self.get_break_type_display()} · {self.attendance_record_id}"

    @property
    def duration_minutes(self) -> int | None:
        if not self.end_time:
            return None
        delta = self.end_time - self.start_time
        return max(0, int(delta.total_seconds() // 60))

    @property
    def is_ongoing(self) -> bool:
        return self.end_time is None


class AttendanceRegularizationRequest(models.Model):
    """Employee request to correct login/logout or status for a past day."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_regularizations",
    )
    date = models.DateField()
    requested_check_in = models.TimeField(null=True, blank=True)
    requested_check_out = models.TimeField(null=True, blank=True)
    requested_status = models.CharField(
        max_length=20,
        choices=AttendanceRecord.Status.choices,
        blank=True,
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_regularizations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["date", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.date} · {self.status}"
