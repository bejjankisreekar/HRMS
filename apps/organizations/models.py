import calendar as _calendar
import uuid

from django.db import models

_MONTH_CHOICES = [(i, _calendar.month_name[i]) for i in range(1, 13)]


class Organization(models.Model):
    class SubscriptionStatus(models.TextChoices):
        TRIAL = "TRIAL", "Trial"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past Due"
        CANCELED = "CANCELED", "Canceled"
        INACTIVE = "INACTIVE", "Inactive"
        EXPIRED = "EXPIRED", "Expired"

    class OrganizationType(models.TextChoices):
        COMPANY = "COMPANY", "Company / Corporate"
        RETAIL = "RETAIL", "Retail"
        WHOLESALE = "WHOLESALE", "Wholesale"
        RESTAURANT = "RESTAURANT", "Restaurant / Food Service"
        HOSPITAL = "HOSPITAL", "Hospital"
        CLINIC = "CLINIC", "Clinic / Healthcare"
        HOTEL = "HOTEL", "Hotel / Hospitality"
        MANUFACTURING = "MANUFACTURING", "Manufacturing"
        IT_SERVICES = "IT_SERVICES", "IT / Software Services"
        CONSTRUCTION = "CONSTRUCTION", "Construction"
        LOGISTICS = "LOGISTICS", "Logistics / Transport"
        SCHOOL = "SCHOOL", "School"
        COLLEGE = "COLLEGE", "College"
        UNIVERSITY = "UNIVERSITY", "University"
        NGO = "NGO", "NGO / Non-profit"
        GOVERNMENT = "GOVERNMENT", "Government"
        OTHER = "OTHER", "Other"

    class OrganizationSize(models.TextChoices):
        SMALL = "SMALL", "Small"
        MEDIUM = "MEDIUM", "Medium"
        LARGE = "LARGE", "Large"
        ENTERPRISE = "ENTERPRISE", "Enterprise"

    class SubscriptionPlan(models.TextChoices):
        BASIC = "BASIC", "Basic"
        PROFESSIONAL = "PROFESSIONAL", "Professional"
        GROWTH = "GROWTH", "Growth"

    class OnboardingStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    class RevenueRange(models.TextChoices):
        UNDER_10L = "UNDER_10L", "Under 10L"
        L10_50 = "L10_50", "10L - 50L"
        L50_1CR = "L50_1CR", "50L - 1Cr"
        ABOVE_1CR = "ABOVE_1CR", "Above 1Cr"

    class AttendanceType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        BIOMETRIC = "BIOMETRIC", "Biometric"
        HYBRID = "HYBRID", "Hybrid"

    class AttendanceMode(models.TextChoices):
        TIME_BASED = "TIME_BASED", "Time-Based"
        STATUS_BASED = "STATUS_BASED", "Status-Based"

    class PayrollCycle(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        BIWEEKLY = "BIWEEKLY", "Bi-weekly"
        MONTHLY = "MONTHLY", "Monthly"

    class PayrollLopPolicy(models.TextChoices):
        ASSUME_PRESENT = "ASSUME_PRESENT", "Assume present (pay full unless explicitly absent)"
        STRICT = "STRICT", "Strict proration (pay by present ÷ working days)"

    class AbsentAttendancePolicy(models.TextChoices):
        NONE = "NONE", "No auto-deduction"
        LEAVE = "LEAVE", "Deduct from a leave balance"
        LOP = "LOP", "Deduct as Loss of Pay (LOP)"

    class WeekStartDay(models.TextChoices):
        MONDAY = "MONDAY", "Monday"
        SUNDAY = "SUNDAY", "Sunday"

    class DateFormat(models.TextChoices):
        DD_MM_YYYY = "DD/MM/YYYY", "DD/MM/YYYY"
        MM_DD_YYYY = "MM/DD/YYYY", "MM/DD/YYYY"
        YYYY_MM_DD = "YYYY-MM-DD", "YYYY-MM-DD"

    class WeekendPolicy(models.TextChoices):
        SAT_SUN = "SAT_SUN", "Saturday & Sunday (2 days)"
        SUN_ONLY = "SUN_ONLY", "Sunday only (1 day)"
        CUSTOM = "CUSTOM", "Custom fixed days"
        ROTATING_WEEKLY = "ROTATING_WEEKLY", "Rotating weekly"
        ROTATING_MONTHLY = "ROTATING_MONTHLY", "Rotating monthly"
        SHIFT_BASED = "SHIFT_BASED", "Per shift / employee schedule"

    class BoardType(models.TextChoices):
        CBSE = "CBSE", "CBSE"
        ICSE = "ICSE", "ICSE"
        STATE = "STATE", "State Board"
        IB = "IB", "IB"
        OTHER = "OTHER", "Other"

    class CompanyType(models.TextChoices):
        PRIVATE = "PRIVATE", "Private Limited"
        PUBLIC = "PUBLIC", "Public Limited"
        LLP = "LLP", "LLP"
        PROPRIETORSHIP = "PROPRIETORSHIP", "Proprietorship"
        NGO = "NGO", "NGO"
        OTHER = "OTHER", "Other"

    class HearAboutUs(models.TextChoices):
        GOOGLE = "GOOGLE", "Google Search"
        SOCIAL = "SOCIAL", "Social Media"
        REFERRAL = "REFERRAL", "Referral"
        ADS = "ADS", "Advertisement"
        OTHER = "OTHER", "Other"

    class ExpectedGrowth(models.TextChoices):
        SAME = "SAME", "No change"
        GROW_10 = "GROW_10", "Up to 10%"
        GROW_25 = "GROW_25", "10-25%"
        GROW_50 = "GROW_50", "25-50%"
        GROW_100 = "GROW_100", "50%+"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    organization_code = models.CharField(max_length=8, unique=True, null=True, blank=True)
    schema_name = models.CharField(max_length=63, unique=True, null=True, blank=True)

    organization_type = models.CharField(
        max_length=32, choices=OrganizationType.choices, default=OrganizationType.COMPANY, blank=True
    )
    organization_type_other = models.CharField(
        max_length=120, blank=True, help_text="Specify when type is Other"
    )
    industry = models.CharField(max_length=120, blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="org_logos/", blank=True, null=True)
    website = models.URLField(blank=True)
    established_year = models.PositiveSmallIntegerField(blank=True, null=True)
    employee_count = models.PositiveIntegerField(blank=True, null=True)
    organization_size = models.CharField(max_length=20, choices=OrganizationSize.choices, blank=True)
    annual_revenue_range = models.CharField(max_length=20, choices=RevenueRange.choices, blank=True)

    official_email = models.EmailField(blank=True)
    support_email = models.EmailField(blank=True)
    official_phone = models.CharField(max_length=30, blank=True)
    alternate_phone = models.CharField(max_length=30, blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)

    country = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    area = models.CharField(max_length=120, blank=True)
    street_address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    timezone = models.CharField(max_length=64, blank=True, default="Asia/Kolkata")
    currency = models.CharField(max_length=16, blank=True, default="INR")
    language = models.CharField(max_length=16, blank=True, default="en")
    date_format = models.CharField(max_length=20, choices=DateFormat.choices, blank=True)
    attendance_type = models.CharField(max_length=20, choices=AttendanceType.choices, blank=True)
    payroll_cycle = models.CharField(max_length=20, choices=PayrollCycle.choices, blank=True)
    week_start_day = models.CharField(max_length=20, choices=WeekStartDay.choices, blank=True)
    financial_year_start = models.DateField(blank=True, null=True)
    fy_start_month = models.PositiveSmallIntegerField(
        default=4,
        choices=_MONTH_CHOICES,
        help_text="Financial year start month (1=January … 12=December). Default: April (4).",
    )
    shift_enabled = models.BooleanField(default=False)
    biometric_enabled = models.BooleanField(default=False)
    hr_self_in_mark_attendance = models.BooleanField(
        default=False,
        help_text="When enabled, HR users appear in the mark-attendance table and can edit their own times.",
    )
    attendance_mode = models.CharField(
        max_length=20,
        choices=AttendanceMode.choices,
        default=AttendanceMode.TIME_BASED,
        help_text=(
            "TIME_BASED: HR/Admin record check-in/out times (hours, late, overtime auto-calculated). "
            "STATUS_BASED: attendance is marked with status values only (P/A/L/HD/H/WO), no time tracking."
        ),
    )
    hr_role_display_name = models.CharField(
        max_length=50,
        default="HR",
        blank=True,
        help_text=(
            "Label shown wherever a user's role appears as 'HR' (e.g. Manager, Team Leader, "
            "Supervisor). Display only — the stored role and permissions are unchanged."
        ),
    )
    weekend_policy = models.CharField(
        max_length=20,
        choices=WeekendPolicy.choices,
        default=WeekendPolicy.SAT_SUN,
        blank=True,
    )
    weekend_custom_days = models.CharField(
        max_length=20,
        blank=True,
        default="5,6",
        help_text="Comma-separated weekday numbers (0=Mon … 6=Sun) for CUSTOM policy.",
    )
    rotating_off_anchor = models.DateField(
        blank=True,
        null=True,
        help_text="Start date for rotating weekly off cycles.",
    )
    rotating_off_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {"off_days": [5,6]} per cycle step.',
    )
    holidays_exclude_optional = models.BooleanField(
        default=True,
        help_text="When enabled, optional holidays are not auto-excluded from leave/working-day counts.",
    )
    leave_approval_require_manager = models.BooleanField(
        default=True,
        help_text="Reporting manager must approve leave before the next step.",
    )
    leave_approval_require_hr = models.BooleanField(
        default=True,
        help_text="HR must approve leave (assigned HR, or any HR if unassigned).",
    )
    leave_approval_require_admin = models.BooleanField(
        default=True,
        help_text="Organization admin must give final approval.",
    )
    leave_auto_approve_without_manager = models.BooleanField(
        default=True,
        help_text=(
            "When the approval chain resolves no approvers (e.g. employee has no "
            "reporting manager and no other steps are enabled), auto-approve the "
            "request. When disabled, the request is routed to HR (or the admin) "
            "instead of being auto-approved. Default preserves legacy behavior."
        ),
    )
    leave_management_enabled = models.BooleanField(default=True)
    payroll_enabled = models.BooleanField(default=True)
    payroll_lop_policy = models.CharField(
        max_length=20,
        choices=PayrollLopPolicy.choices,
        default=PayrollLopPolicy.ASSUME_PRESENT,
        help_text=(
            "How unmarked attendance affects pay when running payroll. "
            "ASSUME_PRESENT pays full salary unless a day is explicitly marked absent; "
            "STRICT prorates pay by present ÷ working days."
        ),
    )

    absent_attendance_policy = models.CharField(
        max_length=10,
        choices=AbsentAttendancePolicy.choices,
        default=AbsentAttendancePolicy.NONE,
        help_text=(
            "When an employee is marked Absent, automatically deduct from a leave balance "
            "or record it as Loss of Pay. 'No auto-deduction' leaves balances untouched."
        ),
    )
    absent_leave_type_priorities = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Ordered list of LeaveType PKs (strings). When an employee is absent, "
            "the system deducts from the first type that has remaining balance, then "
            "cascades to the next if that one is exhausted."
        ),
    )

    subscription_plan = models.CharField(
        max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.BASIC, blank=True
    )
    trial_start_date = models.DateTimeField(blank=True, null=True)
    trial_end_date = models.DateTimeField(blank=True, null=True)
    max_users_allowed = models.PositiveIntegerField(blank=True, null=True)
    storage_limit_mb = models.PositiveIntegerField(blank=True, null=True)
    subscription_status = models.CharField(
        max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL
    )
    onboarding_status = models.CharField(
        max_length=20, choices=OnboardingStatus.choices, default=OnboardingStatus.PENDING, blank=True
    )

    how_did_you_hear_about_us = models.CharField(max_length=30, choices=HearAboutUs.choices, blank=True)
    expected_employee_growth = models.CharField(max_length=20, choices=ExpectedGrowth.choices, blank=True)
    current_hrms_used = models.CharField(max_length=120, blank=True)
    pain_points = models.JSONField(blank=True, default=list)
    required_modules = models.JSONField(blank=True, default=list)
    onboarding_notes = models.TextField(blank=True)

    board_type = models.CharField(max_length=20, choices=BoardType.choices, blank=True)
    total_students = models.PositiveIntegerField(blank=True, null=True)
    total_teachers = models.PositiveIntegerField(blank=True, null=True)
    classes_available = models.PositiveIntegerField(blank=True, null=True)
    transport_enabled = models.BooleanField(default=False)
    hostel_enabled = models.BooleanField(default=False)
    library_enabled = models.BooleanField(default=False)

    gst_number = models.CharField(max_length=30, blank=True)
    tax_number = models.CharField(max_length=120, blank=True)
    registration_number = models.CharField(max_length=120, blank=True)
    company_type = models.CharField(max_length=20, choices=CompanyType.choices, blank=True)
    departments_count = models.PositiveIntegerField(blank=True, null=True)
    branch_count = models.PositiveIntegerField(blank=True, null=True)

    signup_ip = models.GenericIPAddressField(blank=True, null=True)
    signup_device = models.CharField(max_length=120, blank=True)
    signup_browser = models.CharField(max_length=120, blank=True)

    code = models.SlugField(max_length=50, unique=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        ident = self.organization_code or self.code or "ORG"
        return f"{self.name} ({ident})"

    def department_labels(self) -> tuple[str, str]:
        """Singular and plural labels for department-like units (varies by industry)."""
        mapping = {
            self.OrganizationType.SCHOOL: ("Subject", "Subjects"),
            self.OrganizationType.COLLEGE: ("Department", "Departments"),
            self.OrganizationType.UNIVERSITY: ("Department", "Departments"),
            self.OrganizationType.RESTAURANT: ("Level / station", "Levels / stations"),
            self.OrganizationType.HOTEL: ("Department", "Departments"),
            self.OrganizationType.HOSPITAL: ("Department", "Departments"),
            self.OrganizationType.CLINIC: ("Department", "Departments"),
            self.OrganizationType.MANUFACTURING: ("Department", "Departments"),
            self.OrganizationType.RETAIL: ("Department", "Departments"),
            self.OrganizationType.IT_SERVICES: ("Department", "Departments"),
        }
        return mapping.get(self.organization_type, ("Department", "Departments"))

    @property
    def hr_label(self) -> str:
        """Org-configured display name for the HR role; falls back to 'HR'."""
        return (self.hr_role_display_name or "").strip() or "HR"

    @property
    def department_label(self) -> str:
        return self.department_labels()[0]

    @property
    def department_label_plural(self) -> str:
        return self.department_labels()[1]


class FinancialYear(models.Model):
    """A user-created financial year record for an organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="financial_years",
    )
    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Auto-generated if left blank (e.g. 'FY 2025-26').",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="The default FY selected when no session choice is active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "start_date"],
                name="unique_fy_start_date_per_org",
            ),
        ]

    def _auto_label(self) -> str:
        sy, ey = self.start_date.year, self.end_date.year
        return f"FY {sy}" if sy == ey else f"FY {sy}-{str(ey)[2:]}"

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = self._auto_label()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.label

    def as_dict(self) -> dict:
        """Return a dict compatible with the existing FY context shape."""
        return {
            "id": str(self.id),
            "start_year": self.start_date.year,
            "end_year": self.end_date.year,
            "label": self.label,
            "date_from": self.start_date,
            "date_to": self.end_date,
            "is_active": self.is_active,
            "is_default": self.is_default,
        }


class Department(models.Model):
    """Admin-defined unit: departments, school subjects, restaurant levels, etc."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_department_name_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name
