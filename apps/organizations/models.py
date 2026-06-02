import uuid

from django.db import models


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
        FREE = "FREE", "Free"
        BASIC = "BASIC", "Basic"
        PREMIUM = "PREMIUM", "Premium"
        ENTERPRISE = "ENTERPRISE", "Enterprise"

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

    class PayrollCycle(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        BIWEEKLY = "BIWEEKLY", "Bi-weekly"
        MONTHLY = "MONTHLY", "Monthly"

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
    shift_enabled = models.BooleanField(default=False)
    biometric_enabled = models.BooleanField(default=False)
    hr_self_in_mark_attendance = models.BooleanField(
        default=False,
        help_text="When enabled, HR users appear in the mark-attendance table and can edit their own times.",
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
    leave_management_enabled = models.BooleanField(default=True)
    payroll_enabled = models.BooleanField(default=True)

    subscription_plan = models.CharField(
        max_length=20, choices=SubscriptionPlan.choices, default=SubscriptionPlan.FREE, blank=True
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
    def department_label(self) -> str:
        return self.department_labels()[0]

    @property
    def department_label_plural(self) -> str:
        return self.department_labels()[1]


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
