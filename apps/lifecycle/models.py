import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class OnboardingWorkflow(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        ORIENTATION = "ORIENTATION", "Orientation"
        COMPLETED = "COMPLETED", "Completed"
        ON_HOLD = "ON_HOLD", "On hold"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="onboarding_workflows",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding_workflows",
    )
    joining_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    welcome_sent = models.BooleanField(default=False)
    branch = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboardings_created",
    )

    class Meta:
        ordering = ["-joining_date"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_onboarding_per_user"),
        ]

    def __str__(self) -> str:
        return f"Onboarding · {self.user_id}"


class OffboardingWorkflow(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        CLEARANCE = "CLEARANCE", "Clearance in progress"
        SETTLEMENT = "SETTLEMENT", "Settlement"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class ResignationReason(models.TextChoices):
        BETTER_OPPORTUNITY = "BETTER_OPPORTUNITY", "Better opportunity"
        PERSONAL = "PERSONAL", "Personal reasons"
        RELOCATION = "RELOCATION", "Relocation"
        HEALTH = "HEALTH", "Health"
        RETIREMENT = "RETIREMENT", "Retirement"
        TERMINATION = "TERMINATION", "Termination"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="offboarding_workflows",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offboarding_workflows",
    )
    last_working_day = models.DateField()
    resignation_reason = models.CharField(
        max_length=30, choices=ResignationReason.choices, default=ResignationReason.OTHER
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offboardings_created",
    )

    class Meta:
        ordering = ["-last_working_day"]

    def __str__(self) -> str:
        return f"Offboarding · {self.user_id}"


class EmployeeDocument(models.Model):
    class DocType(models.TextChoices):
        AADHAAR = "AADHAAR", "Aadhaar / Passport"
        PAN = "PAN", "PAN Card"
        RESUME = "RESUME", "Resume"
        EDUCATION = "EDUCATION", "Educational certificates"
        EXPERIENCE = "EXPERIENCE", "Experience letters"
        BANK = "BANK", "Bank details"
        TAX = "TAX", "Tax documents"
        ADDRESS = "ADDRESS", "Address proof"
        PHOTO = "PHOTO", "Profile photo"
        OTHER = "OTHER", "Other"

    class VerifyStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"
        MISSING = "MISSING", "Missing"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    onboarding = models.ForeignKey(
        OnboardingWorkflow, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    file = models.FileField(upload_to="onboarding_documents/%Y/%m/", blank=True)
    verify_status = models.CharField(
        max_length=20, choices=VerifyStatus.choices, default=VerifyStatus.PENDING
    )
    expires_at = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_verified",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["doc_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["onboarding", "doc_type"],
                name="unique_doc_type_per_onboarding",
            ),
        ]


class OnboardingTask(models.Model):
    class Category(models.TextChoices):
        HR = "HR", "HR"
        IT = "IT", "IT"
        MANAGER = "MANAGER", "Manager"
        TEAM = "TEAM", "Team orientation"
        SECURITY = "SECURITY", "Security"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Done"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    onboarding = models.ForeignKey(
        OnboardingWorkflow, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.HR)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarding_tasks_assigned",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "priority"]


class AssetAllocation(models.Model):
    class AssetType(models.TextChoices):
        LAPTOP = "LAPTOP", "Laptop"
        ID_CARD = "ID_CARD", "ID card"
        EMAIL = "EMAIL", "Email account"
        SYSTEM_ACCESS = "SYSTEM_ACCESS", "System access"
        MOBILE = "MOBILE", "Mobile / SIM"
        ACCESSORY = "ACCESSORY", "Accessory"

    class Status(models.TextChoices):
        ALLOCATED = "ALLOCATED", "Allocated"
        RETURNED = "RETURNED", "Returned"
        DAMAGED = "DAMAGED", "Damaged"
        MISSING = "MISSING", "Missing"
        PENDING = "PENDING", "Pending"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="asset_allocations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asset_allocations"
    )
    onboarding = models.ForeignKey(
        OnboardingWorkflow,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assets",
    )
    offboarding = models.ForeignKey(
        "OffboardingWorkflow",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="asset_returns",
    )
    asset_type = models.CharField(max_length=20, choices=AssetType.choices)
    serial_number = models.CharField(max_length=80, blank=True)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    condition_notes = models.TextField(blank=True)
    allocated_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-allocated_at"]


class PolicyAcceptance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    onboarding = models.ForeignKey(
        OnboardingWorkflow, on_delete=models.CASCADE, related_name="policy_acceptances"
    )
    policy_name = models.CharField(max_length=120)
    policy_version = models.CharField(max_length=20, default="1.0")
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    signature_note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["onboarding", "policy_name"],
                name="unique_policy_per_onboarding",
            ),
        ]


class OrientationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    onboarding = models.ForeignKey(
        OnboardingWorkflow, on_delete=models.CASCADE, related_name="orientation_sessions"
    )
    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    completed = models.BooleanField(default=False)
    attended = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)


class ExitInterview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offboarding = models.OneToOneField(
        OffboardingWorkflow, on_delete=models.CASCADE, related_name="exit_interview"
    )
    feedback = models.TextField(blank=True)
    reason_detail = models.TextField(blank=True)
    hr_comments = models.TextField(blank=True)
    manager_comments = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=False)
    sentiment = models.CharField(max_length=20, blank=True)
    conducted_at = models.DateTimeField(null=True, blank=True)


class ClearanceApproval(models.Model):
    class Department(models.TextChoices):
        HR = "HR", "HR"
        IT = "IT", "IT"
        FINANCE = "FINANCE", "Finance"
        ADMIN = "ADMIN", "Admin"
        SECURITY = "SECURITY", "Security"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offboarding = models.ForeignKey(
        OffboardingWorkflow, on_delete=models.CASCADE, related_name="clearances"
    )
    department = models.CharField(max_length=20, choices=Department.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clearances_approved",
    )
    note = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["offboarding", "department"],
                name="unique_clearance_dept_per_offboarding",
            ),
        ]


class SettlementRecord(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offboarding = models.OneToOneField(
        OffboardingWorkflow, on_delete=models.CASCADE, related_name="settlement"
    )
    pending_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    leave_encashment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reimbursements = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlements_approved",
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class GeneratedLetter(models.Model):
    class LetterType(models.TextChoices):
        EXPERIENCE = "EXPERIENCE", "Experience letter"
        RELIEVING = "RELIEVING", "Relieving letter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offboarding = models.ForeignKey(
        OffboardingWorkflow, on_delete=models.CASCADE, related_name="letters"
    )
    letter_type = models.CharField(max_length=20, choices=LetterType.choices)
    content = models.TextField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="letters_generated",
    )
