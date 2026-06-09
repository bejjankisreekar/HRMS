import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        ADMIN = "ADMIN", "Organization Admin"
        HR = "HR", "HR"
        EMPLOYEE = "EMPLOYEE", "Employee"

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"
        PREFER_NOT = "PREFER_NOT", "Prefer not to say"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "FULL_TIME", "Full-time"
        PART_TIME = "PART_TIME", "Part-time"
        CONTRACT = "CONTRACT", "Contract"
        INTERN = "INTERN", "Intern"

    class WorkMode(models.TextChoices):
        ONSITE = "ONSITE", "On-site"
        REMOTE = "REMOTE", "Remote"
        HYBRID = "HYBRID", "Hybrid"

    class MaritalStatus(models.TextChoices):
        SINGLE = "SINGLE", "Single"
        MARRIED = "MARRIED", "Married"
        DIVORCED = "DIVORCED", "Divorced"
        WIDOWED = "WIDOWED", "Widowed"
        OTHER = "OTHER", "Other"

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        PROBATION = "PROBATION", "Probation"
        NOTICE = "NOTICE", "Notice period"
        SUSPENDED = "SUSPENDED", "Suspended"
        TERMINATED = "TERMINATED", "Terminated"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Account
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    username = models.SlugField(max_length=50, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)

    # Employee / HR profile
    employee_id = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    blood_group = models.CharField(max_length=10, blank=True)
    marital_status = models.CharField(max_length=20, choices=MaritalStatus.choices, blank=True)
    nationality = models.CharField(max_length=80, blank=True)

    alternate_phone = models.CharField(max_length=30, blank=True)
    personal_email = models.EmailField(blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    emergency_contact_relation = models.CharField(max_length=60, blank=True)

    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    designation = models.CharField(max_length=120, blank=True)
    job_grade = models.ForeignKey(
        "grades.Grade",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    org_designation = models.ForeignKey(
        "grades.Designation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="holders",
    )
    business_unit = models.CharField(max_length=120, blank=True)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, blank=True)
    date_of_joining = models.DateField(blank=True, null=True)
    reporting_manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    assigned_hr = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_assigned_employees",
    )
    work_shift = models.ForeignKey(
        "attendance.WorkShift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_users",
    )
    work_location = models.CharField(max_length=120, blank=True)
    work_mode = models.CharField(max_length=20, choices=WorkMode.choices, blank=True)

    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_holder = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=40, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    aadhaar_number = models.CharField(max_length=20, blank=True)

    internal_notes = models.TextField(blank=True)

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    profile_picture = models.ImageField(upload_to="profile_pictures/", blank=True, null=True)

    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    otp_verified = models.BooleanField(default=False)
    terms_accepted = models.BooleanField(default=False)
    privacy_policy_accepted = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee_id"],
                condition=~models.Q(employee_id=""),
                name="unique_employee_id_per_org",
            ),
        ]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        if full:
            return full
        if self.username:
            return self.username
        if self.email and "@" in self.email:
            return self.email.split("@", 1)[0]
        return self.email or "User"

    @property
    def department_name(self) -> str:
        return self.department.name if self.department_id else ""

    @property
    def grade_name(self) -> str:
        return self.job_grade.name if self.job_grade_id else ""

    @property
    def designation_label(self) -> str:
        if self.org_designation_id:
            return self.org_designation.name
        return self.designation or ""

    @property
    def choice_label(self) -> str:
        """Label for dropdowns: First Last (username)."""
        full = f"{self.first_name} {self.last_name}".strip()
        if full and self.username:
            return f"{full} ({self.username})"
        if full:
            return full
        if self.username:
            return self.username
        return self.display_name

    def __str__(self) -> str:
        return self.choice_label


class LoginAuditLog(models.Model):
    """Immutable record of login attempts for security auditing."""

    class Portal(models.TextChoices):
        ADMIN = "admin", "Organization Admin Portal"
        HR = "hr", "HR Portal"
        EMPLOYEE = "employee", "Employee Portal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_audit_logs",
    )
    username_attempt = models.CharField(max_length=255)
    portal = models.CharField(max_length=20, choices=Portal.choices)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "login audit log"
        verbose_name_plural = "login audit logs"

    def __str__(self) -> str:
        status = "success" if self.success else "failed"
        return f"{self.username_attempt} · {self.portal} · {status}"


class StaffAuditLog(models.Model):
    """Audit trail for staff management actions within an organization."""

    class Action(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        DELETE = "DELETE", "Deleted"
        DEACTIVATE = "DEACTIVATE", "Deactivated"
        ACTIVATE = "ACTIVATE", "Activated"
        STATUS_CHANGE = "STATUS_CHANGE", "Status changed"
        BULK = "BULK", "Bulk action"
        PASSWORD_RESET = "PASSWORD_RESET", "Password reset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="staff_audit_logs",
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_audit_entries",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_actions_performed",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.summary
