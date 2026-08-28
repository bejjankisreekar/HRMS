import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from .payslip_formats import DEFAULT_PAYSLIP_FORMAT, payslip_format_choices


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
        EMPLOYER_PF = "EMPLOYER_PF", "Employer PF"
        ESI = "ESI", "ESI"
        PT = "PT", "Professional Tax"
        TAX = "TAX", "Income Tax"
        LOAN = "LOAN", "Loan Deduction"
        ADVANCE = "ADVANCE", "Salary Advance Recovery"
        NOTICE = "NOTICE", "Notice Period Recovery"
        LOP = "LOP", "Loss of Pay"
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
    grade = models.ForeignKey(
        "grades.Grade",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_structures",
    )
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
    employer_pf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Employer PF contribution (cost to company; not deducted from net).",
    )
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
    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "user"],
                name="unique_payslip_per_run_user",
            ),
        ]
        ordering = ["user__first_name", "user__last_name"]


class CompliancePayment(models.Model):
    """Tracks whether a statutory remittance (PF/ESI/TDS/PT) has been paid for a given period."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"

    REPORT_CHOICES = [
        ("pf", "PF"),
        ("esi", "ESI"),
        ("tds", "TDS"),
        ("pt", "Professional Tax"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="compliance_payments",
    )
    report_type = models.CharField(max_length=10, choices=REPORT_CHOICES)
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compliance_payments_marked",
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "report_type", "year", "month"],
                name="unique_compliance_payment",
            ),
        ]


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
    cess_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("4"),
        help_text="Health and education cess applied on top of computed tax.",
    )
    rebate_87a_income_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("700000"),
        help_text="Taxable income at or below this gets the 87A rebate. 0 disables it.",
    )
    rebate_87a_max = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("25000"),
        help_text="Maximum 87A rebate. Caps at the tax due.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-financial_year_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "financial_year_start", "regime"],
                name="unique_tax_config_per_org_fy_regime",
            ),
        ]


class TaxSlab(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tax_config = models.ForeignKey(TaxConfiguration, on_delete=models.CASCADE, related_name="slabs")
    min_income = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    max_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["min_income"]


class TaxRegime(models.TextChoices):
    OLD = "OLD", "Old regime"
    NEW = "NEW", "New regime"


class TaxDeclaration(models.Model):
    """One employee's investment declaration for one financial year.

    Only APPROVED declarations reduce taxable income — a submitted-but-unverified
    claim must not cut someone's TDS before HR has seen the proof.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="tax_declarations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tax_declarations",
    )
    financial_year_start = models.DateField(help_text="1 April of the FY this declaration covers.")
    regime = models.CharField(max_length=8, choices=TaxRegime.choices, default=TaxRegime.NEW)

    # Old-regime exemptions and deductions. Ignored under the new regime.
    hra_rent_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Total annual rent paid, for the HRA exemption.",
    )
    metro_city = models.BooleanField(
        default=False, help_text="HRA exemption is 50% of basic in metros, 40% elsewhere.",
    )
    section_80c = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="EPF, PPF, ELSS, life insurance, tuition fees, principal repayment.",
    )
    section_80d = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Health insurance premium — self, family and parents.",
    )
    section_80ccd_1b = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Additional NPS contribution.",
    )
    home_loan_interest = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Section 24(b) interest on a self-occupied house.",
    )
    other_exemptions = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Any other approved exemption (80E, 80G, …).",
    )
    other_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Income from other sources to include in the projection.",
    )

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tax_declarations_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-financial_year_start", "user__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "financial_year_start"],
                name="unique_tax_declaration_per_user_fy",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} — FY starting {self.financial_year_start}"

    @property
    def is_effective(self) -> bool:
        """Only an approved declaration may reduce taxable income."""
        return self.status == self.Status.APPROVED


class TaxComputation(models.Model):
    """Audit trail of what the engine decided for one employee in one month.

    Stored so a payslip's TDS can always be explained after the fact, and so the
    year-to-date catch-up has a record to read back.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="tax_computations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tax_computations",
    )
    payslip = models.OneToOneField(
        "Payslip",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="tax_computation",
    )
    financial_year_start = models.DateField()
    regime = models.CharField(max_length=8, choices=TaxRegime.choices, default=TaxRegime.NEW)

    projected_gross = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_exemptions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    annual_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    rebate_applied = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tds_paid_till_date = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    months_remaining = models.PositiveSmallIntegerField(default=12)
    monthly_tds = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    breakdown = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} — TDS {self.monthly_tds}"


class Form16Certificate(models.Model):
    """An issued Form 16 for one employee and one financial year.

    The figures are snapshotted at issue time rather than recomputed on read: a TDS
    certificate is a statement of what was actually deducted, and must not drift if
    a later payroll correction changes the underlying payslips.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="form16_certificates",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="form16_certificates",
    )
    financial_year_start = models.DateField()
    certificate_number = models.CharField(max_length=40, blank=True)

    gross_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_exemptions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    tds_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    balance_payable = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form16_certificates_issued",
    )

    class Meta:
        ordering = ["-financial_year_start", "user__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "financial_year_start"],
                name="unique_form16_per_user_fy",
            ),
        ]

    def __str__(self) -> str:
        return f"Form 16 {self.certificate_number or self.pk} — {self.user}"

    @property
    def fy_label(self) -> str:
        return f"{self.financial_year_start.year}-{str(self.financial_year_start.year + 1)[2:]}"


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
        PENDING = "PENDING", "Pending approval"
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        REJECTED = "REJECTED", "Rejected"
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
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    start_date = models.DateField(default=timezone.localdate)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loans_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
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


class EmployeeDeduction(models.Model):
    """Recurring/one-off recovery deducted during payroll (advance, notice, other)."""

    class Type(models.TextChoices):
        ADVANCE = "ADVANCE", "Salary Advance Recovery"
        NOTICE = "NOTICE", "Notice Period Recovery"
        OTHER = "OTHER", "Other Deduction"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payroll_deductions",
    )
    deduction_type = models.CharField(max_length=12, choices=Type.choices, default=Type.OTHER)
    label = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Per-cycle recovery amount.")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_deduction_type_display()} · {self.amount}"


class PayrollAuditLog(models.Model):
    """Audit trail for payroll/deduction activities within an organization."""

    class Action(models.TextChoices):
        PROCESSED = "PROCESSED", "Payroll processed"
        CALCULATED = "CALCULATED", "Deductions calculated"
        VIEWED = "VIEWED", "Deductions viewed"
        EXPORTED = "EXPORTED", "Report exported"
        GENERATED = "GENERATED", "Payslip generated"
        LOAN_APPROVED = "LOAN_APPROVED", "Loan approved"
        SETTINGS_UPDATED = "SETTINGS_UPDATED", "Payroll settings updated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payroll_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_actions_performed",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class PayrollCycleConfig(models.Model):
    """Per-org payroll cycle timing — one row per organization."""

    class Frequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        WEEKLY = "WEEKLY", "Weekly"
        BIWEEKLY = "BIWEEKLY", "Biweekly"
        SEMI_MONTHLY = "SEMI_MONTHLY", "Semi-monthly"
        CUSTOM = "CUSTOM", "Custom"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payroll_cycle_config",
    )
    frequency = models.CharField(max_length=15, choices=Frequency.choices, default=Frequency.MONTHLY)
    payroll_day = models.PositiveSmallIntegerField(
        default=25, help_text="Day of the month payroll is processed."
    )
    salary_day = models.PositiveSmallIntegerField(
        default=1, help_text="Day of the (following) month salary is credited."
    )
    attendance_cutoff_day = models.PositiveSmallIntegerField(default=20)
    leave_cutoff_day = models.PositiveSmallIntegerField(default=20)
    approval_deadline_day = models.PositiveSmallIntegerField(default=23)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Payroll cycle · {self.organization}"


class PayrollSettings(models.Model):
    """Per-org payroll behavior settings — one row per organization."""

    class RoundingRule(models.TextChoices):
        NONE = "NONE", "No rounding"
        NEAREST = "NEAREST", "Round to nearest rupee"
        UP = "UP", "Always round up"
        DOWN = "DOWN", "Always round down"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payroll_settings",
    )
    currency = models.CharField(max_length=3, default="INR")
    # Deductor identity printed on Form 16. TAN is mandatory on a TDS certificate.
    tan_number = models.CharField(
        max_length=15, blank=True, help_text="Employer's TAN, e.g. BLRA12345C. Required on Form 16."
    )
    employer_pan = models.CharField(max_length=15, blank=True, help_text="Employer's PAN.")
    deductor_name = models.CharField(
        max_length=150, blank=True, help_text="Name of the deductor as registered with TRACES. Defaults to the organization name."
    )
    decimal_precision = models.PositiveSmallIntegerField(default=2)
    rounding_rule = models.CharField(max_length=10, choices=RoundingRule.choices, default=RoundingRule.NEAREST)
    auto_payroll_enabled = models.BooleanField(default=False)
    payslip_email_enabled = models.BooleanField(default=True)
    approval_workflow_enabled = models.BooleanField(default=True)
    payslip_format = models.CharField(
        max_length=20,
        choices=payslip_format_choices,
        default=DEFAULT_PAYSLIP_FORMAT,
    )
    default_salary_structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Payroll settings · {self.organization}"
