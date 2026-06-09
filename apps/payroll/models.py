import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class SalaryComponent(models.Model):
    """Earning or deduction line used in salary structures and payslips."""

    class ComponentType(models.TextChoices):
        EARNING = "EARNING", "Earning"
        DEDUCTION = "DEDUCTION", "Deduction"

    class Category(models.TextChoices):
        BASIC = "BASIC", "Basic Salary"
        HRA = "HRA", "HRA"
        SPECIAL = "SPECIAL", "Special Allowance"
        MEDICAL = "MEDICAL", "Medical Allowance"
        TRAVEL = "TRAVEL", "Travel Allowance"
        BONUS = "BONUS", "Bonus"
        INCENTIVE = "INCENTIVE", "Incentives"
        OVERTIME = "OVERTIME", "Overtime"
        PF = "PF", "Provident Fund"
        ESI = "ESI", "ESI"
        PT = "PT", "Professional Tax"
        TAX = "TAX", "Income Tax"
        LOAN = "LOAN", "Loan Deduction"
        OTHER = "OTHER", "Other"

    class CalcType(models.TextChoices):
        FIXED = "FIXED", "Fixed amount"
        PCT_BASIC = "PCT_BASIC", "% of Basic"
        PCT_GROSS = "PCT_GROSS", "% of Gross"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="salary_components",
    )
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    component_type = models.CharField(max_length=12, choices=ComponentType.choices)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    calc_type = models.CharField(max_length=12, choices=CalcType.choices, default=CalcType.FIXED)
    default_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    default_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    is_taxable = models.BooleanField(default=True)
    is_statutory = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_salary_component_code_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SalaryStructure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="salary_structures",
    )
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_structures",
    )
    grade = models.CharField(max_length=40, blank=True)
    monthly_ctc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="INR")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_salary_structure_code_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SalaryStructureLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.CASCADE,
        related_name="structure_lines",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["structure", "component"],
                name="unique_structure_component_line",
            ),
        ]


class EmployeeSalary(models.Model):
    class SalaryType(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        HOURLY = "HOURLY", "Hourly"
        CONTRACT = "CONTRACT", "Contract"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="salary_profiles",
    )
    structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_assignments",
    )
    salary_type = models.CharField(
        max_length=12,
        choices=SalaryType.choices,
        default=SalaryType.MONTHLY,
    )
    monthly_ctc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("50000"))
    currency = models.CharField(max_length=3, default="INR")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-effective_from"]


class EmployeeSalaryComponent(models.Model):
    """Per-employee, editable salary line — fixed amount or a percentage."""

    class Mode(models.TextChoices):
        FIXED = "FIXED", "Fixed amount"
        PCT_CTC = "PCT_CTC", "% of CTC"
        PCT_BASIC = "PCT_BASIC", "% of Basic"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    salary = models.ForeignKey(
        EmployeeSalary, on_delete=models.CASCADE, related_name="components"
    )
    code = models.SlugField(max_length=40)
    label = models.CharField(max_length=80)
    kind = models.CharField(
        max_length=12, choices=SalaryComponent.ComponentType.choices,
        default=SalaryComponent.ComponentType.EARNING,
    )
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.FIXED)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["salary", "code"], name="unique_emp_component_code"),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.mode})"


class PayrollRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PROCESSING = "PROCESSING", "Processing"
        REVIEW = "REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"
        LOCKED = "LOCKED", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payroll_runs",
    )
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_bonus = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_reimbursements = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    employee_count = models.PositiveIntegerField(default=0)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs_processed",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year", "month"],
                name="unique_payroll_run_per_org_month",
            ),
        ]

    @property
    def period_label(self) -> str:
        import calendar

        return f"{calendar.month_name[self.month]} {self.year}"


class Payslip(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payslips",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payslips",
    )
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    reimbursements = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    overtime_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    leave_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    attendance_days = models.PositiveSmallIntegerField(default=0)
    working_days = models.PositiveSmallIntegerField(default=0)
    leave_days = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    payment_status = models.CharField(
        max_length=12,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    payment_date = models.DateField(null=True, blank=True)
    bank_reference = models.CharField(max_length=60, blank=True)
    payslip_number = models.CharField(max_length=40, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "user"],
                name="unique_payslip_per_run_user",
            ),
        ]
        ordering = ["user__first_name", "user__last_name"]


class PayslipLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    label = models.CharField(max_length=80)
    line_type = models.CharField(max_length=12, choices=SalaryComponent.ComponentType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "label"]


class TaxConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="tax_configs",
    )
    financial_year_start = models.DateField()
    regime = models.CharField(max_length=20, default="NEW")
    standard_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("75000"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-financial_year_start"]


class TaxSlab(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tax_config = models.ForeignKey(TaxConfiguration, on_delete=models.CASCADE, related_name="slabs")
    min_income = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    max_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["min_income"]


class Reimbursement(models.Model):
    class Category(models.TextChoices):
        TRAVEL = "TRAVEL", "Travel"
        FOOD = "FOOD", "Food"
        INTERNET = "INTERNET", "Internet / Mobile"
        MEDICAL = "MEDICAL", "Medical"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAID = "PAID", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reimbursements",
    )
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    receipt = models.FileField(upload_to="reimbursements/", blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reimbursements",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reimbursements_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EmployeeLoan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        DEFAULTED = "DEFAULTED", "Defaulted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="loans",
    )
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tenure_months = models.PositiveSmallIntegerField(default=12)
    emi_amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)


class PayrollApproval(models.Model):
    class Step(models.TextChoices):
        HR = "HR", "HR Approval"
        FINANCE = "FINANCE", "Finance Approval"
        DIRECTOR = "DIRECTOR", "Director Approval"

    class StepStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    step = models.CharField(max_length=12, choices=Step.choices)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=12, choices=StepStatus.choices, default=StepStatus.PENDING)
    comment = models.TextField(blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)


class SalaryRevision(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="salary_revisions",
    )
    previous_ctc = models.DecimalField(max_digits=12, decimal_places=2)
    new_ctc = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_revisions_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
