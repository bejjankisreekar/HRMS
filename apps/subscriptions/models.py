"""Subscription & billing models — SaaS financial center."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class BillingInterval(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    YEARLY = "YEARLY", "Yearly"


class SubscriptionStatus(models.TextChoices):
    TRIAL = "TRIAL", "Trial"
    ACTIVE = "ACTIVE", "Active"
    PAST_DUE = "PAST_DUE", "Past due"
    SUSPENDED = "SUSPENDED", "Suspended"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"


class PaymentMethod(models.TextChoices):
    RAZORPAY = "RAZORPAY", "Razorpay"
    STRIPE = "STRIPE", "Stripe"
    PAYPAL = "PAYPAL", "PayPal"
    UPI = "UPI", "UPI"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
    MANUAL = "MANUAL", "Manual / offline"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    PARTIAL_REFUND = "PARTIAL_REFUND", "Partial refund"


class Plan(models.Model):
    """Catalog plan — managed from Super Admin Financials."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    monthly_price_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    yearly_price_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    per_employee_price_inr = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Optional per-employee surcharge"
    )
    setup_fee_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    employee_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Null = unlimited")
    branch_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Null = unlimited")
    storage_limit_mb = models.PositiveIntegerField(null=True, blank=True)
    trial_days = models.PositiveSmallIntegerField(default=14)
    feature_flags = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    features_json = models.JSONField(default=list, blank=True)
    stripe_price_monthly_id = models.CharField(max_length=120, blank=True)
    stripe_price_yearly_id = models.CharField(max_length=120, blank=True)
    razorpay_plan_monthly_id = models.CharField(max_length=120, blank=True)
    razorpay_plan_yearly_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def monthly_mrr_contribution(self) -> Decimal:
        return self.monthly_price_inr


class BillingSettings(models.Model):
    """Platform-wide billing config — single row (id=1). Edited from Super Admin."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    yearly_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("17"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billing settings"
        verbose_name_plural = "Billing settings"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "BillingSettings":
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def compute_yearly_price(self, monthly_price_inr: Decimal) -> Decimal:
        """Yearly price = monthly × 12, discounted by yearly_discount_percent, rounded to the nearest rupee."""
        factor = (Decimal("100") - self.yearly_discount_percent) / Decimal("100")
        yearly = Decimal(monthly_price_inr) * 12 * factor
        return yearly.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class Coupon(models.Model):
    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=255, blank=True)
    percent_off = models.PositiveSmallIntegerField(null=True, blank=True)
    amount_off_inr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    redemption_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.code


class FeatureModule(models.Model):
    """Top-level HRMS module grouping (HR Core, Payroll, Recruitment, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, default="box")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_globally_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class FeatureType(models.TextChoices):
    FEATURE = "FEATURE", "Feature"
    PAGE = "PAGE", "Page"
    FIELD = "FIELD", "Field"
    WORKFLOW = "WORKFLOW", "Workflow"


class MenuAudience(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    HR = "HR", "HR"
    EMPLOYEE = "EMPLOYEE", "Employee"


class FeatureCategory(models.Model):
    """UI grouping for organization feature control (Core HR, Attendance, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="folder")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Feature categories"

    def __str__(self) -> str:
        return self.name


class FeatureDefinition(models.Model):
    """Platform feature catalog — gates modules, routes, and sidebar items."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    module = models.ForeignKey(
        FeatureModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="features",
    )
    display_category = models.ForeignKey(
        FeatureCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="features",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    feature_type = models.CharField(max_length=20, choices=FeatureType.choices, default=FeatureType.FEATURE)
    category = models.CharField(max_length=40, blank=True)
    icon = models.CharField(max_length=40, blank=True, default="circle")
    description = models.TextField(blank=True)
    url_names = models.JSONField(
        default=list,
        blank=True,
        help_text="Django URL names gated by this feature (for upgrade prompts).",
    )
    path_prefix = models.CharField(
        max_length=120,
        blank=True,
        help_text="URL path prefix blocked when disabled, e.g. /recruitment/",
    )
    api_path_prefix = models.CharField(
        max_length=120,
        blank=True,
        help_text="API path prefix blocked when disabled, e.g. /api/recruitment/",
    )
    depends_on = models.JSONField(
        default=list,
        blank=True,
        help_text="Feature keys that must be enabled before this feature can be enabled.",
    )
    is_globally_enabled = models.BooleanField(
        default=True,
        help_text="When False, feature is disabled platform-wide regardless of plan.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class PageDefinition(models.Model):
    """Individual pages/views controllable from Super Admin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    url_name = models.CharField(max_length=120)
    feature = models.ForeignKey(
        FeatureDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pages",
    )
    module = models.ForeignKey(
        FeatureModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pages",
    )
    is_globally_enabled = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class FieldDefinition(models.Model):
    """Form field visibility control."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    form_context = models.CharField(max_length=80, blank=True, help_text="e.g. employee_form")
    feature = models.ForeignKey(
        FeatureDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fields",
    )
    is_globally_visible = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["form_context", "sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class FeatureRolePermission(models.Model):
    """Role-based feature access within an organization."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Organization Admin"
        HR = "HR", "HR"
        EMPLOYEE = "EMPLOYEE", "Employee"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name="role_permissions")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_allowed = models.BooleanField(default=True)

    class Meta:
        unique_together = [("feature", "role")]
        ordering = ["feature__sort_order", "role"]

    def __str__(self) -> str:
        return f"{self.feature.key} · {self.role}"


class OrganizationFeatureOverride(models.Model):
    """Per-organization feature enable/disable — highest priority when set."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="feature_overrides",
    )
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name="org_overrides")
    is_enabled = models.BooleanField()
    reason = models.CharField(max_length=255, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feature_overrides_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("organization", "feature")]

    def __str__(self) -> str:
        state = "enabled" if self.is_enabled else "disabled"
        return f"{self.organization} · {self.feature.key} · {state}"


class OrganizationLimit(models.Model):
    """Per-organization resource limits — overrides plan defaults when set."""

    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="feature_limits",
    )
    employee_limit = models.PositiveIntegerField(null=True, blank=True)
    storage_limit_mb = models.PositiveIntegerField(null=True, blank=True)
    branch_limit = models.PositiveIntegerField(null=True, blank=True)
    admin_limit = models.PositiveIntegerField(null=True, blank=True)
    hr_limit = models.PositiveIntegerField(null=True, blank=True)
    api_limit_daily = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Limits · {self.organization}"


class NavigationItem(models.Model):
    """Master navigation catalog — plan-scoped or global."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        "Plan",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="navigation_items",
        help_text="Null = global default navigation template.",
    )
    label = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="circle")
    url_name = models.CharField(max_length=120)
    query_string = models.CharField(max_length=200, blank=True)
    feature_key = models.CharField(max_length=60, blank=True)
    group_label = models.CharField(
        max_length=40, blank=True,
        help_text="When set, items sharing this label render as a collapsible sidebar section instead of a flat item.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    audience = models.CharField(max_length=20, choices=MenuAudience.choices, default=MenuAudience.ADMIN)
    active_views = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "label"]
        indexes = [
            models.Index(fields=["plan", "audience", "sort_order"]),
        ]

    def __str__(self) -> str:
        plan_label = self.plan.name if self.plan_id else "Global"
        return f"{plan_label} · {self.label}"


class OrganizationNavigationOverride(models.Model):
    """Hide/show or reorder nav items for a specific organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="nav_overrides",
    )
    navigation_item = models.ForeignKey(
        NavigationItem,
        on_delete=models.CASCADE,
        related_name="org_overrides",
    )
    is_visible = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("organization", "navigation_item")]


class OrganizationFieldOverride(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="field_overrides",
    )
    field = models.ForeignKey(FieldDefinition, on_delete=models.CASCADE, related_name="org_overrides")
    is_visible = models.BooleanField()

    class Meta:
        unique_together = [("organization", "field")]


class FeatureControlAuditLog(models.Model):
    class Action(models.TextChoices):
        GLOBAL_ENABLE = "GLOBAL_ENABLE", "Global enable"
        GLOBAL_DISABLE = "GLOBAL_DISABLE", "Global disable"
        PLAN_ENABLE = "PLAN_ENABLE", "Plan enable"
        PLAN_DISABLE = "PLAN_DISABLE", "Plan disable"
        ORG_OVERRIDE = "ORG_OVERRIDE", "Organization override"
        ORG_OVERRIDE_CLEAR = "ORG_OVERRIDE_CLEAR", "Organization override cleared"
        NAV_UPDATE = "NAV_UPDATE", "Navigation updated"
        PAGE_UPDATE = "PAGE_UPDATE", "Page updated"
        MODULE_UPDATE = "MODULE_UPDATE", "Module updated"
        ADDON_TOGGLE = "ADDON_TOGGLE", "Add-on toggled"
        LIMIT_UPDATE = "LIMIT_UPDATE", "Limit updated"
        ROLE_PERMISSION = "ROLE_PERMISSION", "Role permission updated"
        FIELD_UPDATE = "FIELD_UPDATE", "Field visibility updated"
        BULK_ACTION = "BULK_ACTION", "Bulk action"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feature_control_logs",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    feature_key = models.CharField(max_length=80, blank=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feature_control_logs",
    )
    plan = models.ForeignKey("Plan", null=True, blank=True, on_delete=models.SET_NULL)
    summary = models.CharField(max_length=255)
    old_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} · {self.summary}"


class PlanFeature(models.Model):
    """Features included in a subscription plan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey("Plan", on_delete=models.CASCADE, related_name="plan_features")
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name="plan_assignments")
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = [("plan", "feature")]
        ordering = ["feature__sort_order", "feature__name"]

    def __str__(self) -> str:
        return f"{self.plan.name} · {self.feature.name}"


class PlanMenuItem(models.Model):
    """Database-driven sidebar navigation per plan."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey("Plan", on_delete=models.CASCADE, related_name="menu_items")
    label = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="circle")
    url_name = models.CharField(max_length=120)
    query_string = models.CharField(max_length=200, blank=True)
    feature_key = models.CharField(max_length=60, blank=True)
    group_label = models.CharField(
        max_length=40, blank=True,
        help_text="When set, items sharing this label render as a collapsible sidebar section instead of a flat item.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    audience = models.CharField(max_length=20, choices=MenuAudience.choices, default=MenuAudience.ADMIN)
    active_views = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "label"]
        indexes = [
            models.Index(fields=["plan", "audience", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan.name} · {self.label}"


class AddOnCatalog(models.Model):
    """Platform add-on products."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    monthly_price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    setup_fee_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    per_employee_price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    trial_days = models.PositiveSmallIntegerField(default=0)
    feature_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="Feature keys unlocked when this add-on is purchased.",
    )
    is_active = models.BooleanField(default=True)
    icon = models.CharField(max_length=40, blank=True, default="puzzle")
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Subscription(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL)
    billing_interval = models.CharField(
        max_length=10, choices=BillingInterval.choices, default=BillingInterval.MONTHLY
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    suspended_at = models.DateTimeField(null=True, blank=True)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)
    discount_percent = models.PositiveSmallIntegerField(default=0)
    credit_balance_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stripe_subscription_id = models.CharField(max_length=120, blank=True)
    razorpay_subscription_id = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.organization} — {self.plan.name} ({self.status})"

    @property
    def monthly_bill_inr(self) -> Decimal:
        base = (
            self.plan.yearly_price_inr / 12
            if self.billing_interval == BillingInterval.YEARLY
            else self.plan.monthly_price_inr
        )
        addon_total = sum(a.monthly_cost_inr for a in self.organization_addons.filter(is_active=True))
        emp_count = self._employee_count()
        emp_charge = self.plan.per_employee_price_inr * emp_count
        subtotal = base + addon_total + emp_charge
        if self.discount_percent:
            subtotal *= Decimal(1) - Decimal(self.discount_percent) / Decimal(100)
        return max(subtotal - self.credit_balance_inr, Decimal("0"))

    def _employee_count(self) -> int:
        from apps.accounts.models import User

        return User.objects.filter(
            organization=self.organization, is_active=True
        ).exclude(role=User.Role.SUPER_ADMIN).count()


class OrganizationAddOn(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="billing_addons",
    )
    addon = models.ForeignKey(AddOnCatalog, on_delete=models.PROTECT, related_name="org_assignments")
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="organization_addons",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(default=timezone.now)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("organization", "addon")]

    @property
    def monthly_cost_inr(self) -> Decimal:
        if not self.is_active:
            return Decimal("0")
        base = self.addon.monthly_price_inr
        if self.addon.per_employee_price_inr:
            from apps.accounts.models import User

            count = User.objects.filter(
                organization=self.organization, is_active=True
            ).exclude(role=User.Role.SUPER_ADMIN).count()
            base += self.addon.per_employee_price_inr * count
        return base


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        OPEN = "OPEN", "Open"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"
        UNCOLLECTIBLE = "UNCOLLECTIBLE", "Uncollectible"
        WAIVED = "WAIVED", "Waived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="invoices")
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="invoices",
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(max_length=40, unique=True)
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    tax_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    line_items = models.JSONField(default=list, blank=True)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    due_date = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    stripe_invoice_id = models.CharField(max_length=120, blank=True)
    razorpay_invoice_id = models.CharField(max_length=120, blank=True)
    pdf_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.organization_id and self.subscription_id:
            self.organization_id = self.subscription.organization_id
        super().save(*args, **kwargs)

    @property
    def total_inr(self) -> Decimal:
        return self.amount_inr + self.tax_inr - self.discount_inr


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments", null=True, blank=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.MANUAL)
    reference_id = models.CharField(max_length=120, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    refund_amount_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunded_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_payments",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.organization} · ₹{self.amount_inr} · {self.status}"


class UsageRecord(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="usage_records",
        null=True,
        blank=True,
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="usage_records",
        null=True,
        blank=True,
    )
    metric = models.CharField(max_length=60)
    quantity = models.PositiveIntegerField(default=0)
    limit_value = models.PositiveIntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at"]


class FinancialAuditLog(models.Model):
    class Action(models.TextChoices):
        PLAN_CHANGE = "PLAN_CHANGE", "Plan change"
        SUBSCRIPTION_ACTIVATE = "SUBSCRIPTION_ACTIVATE", "Subscription activated"
        SUBSCRIPTION_SUSPEND = "SUBSCRIPTION_SUSPEND", "Subscription suspended"
        SUBSCRIPTION_RENEW = "SUBSCRIPTION_RENEW", "Subscription renewed"
        INVOICE_GENERATED = "INVOICE_GENERATED", "Invoice generated"
        INVOICE_WAIVED = "INVOICE_WAIVED", "Invoice waived"
        PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment recorded"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment failed"
        REFUND = "REFUND", "Refund"
        COUPON_APPLIED = "COUPON_APPLIED", "Coupon applied"
        CREDIT_ADDED = "CREDIT_ADDED", "Credit added"
        ADDON_ACTIVATED = "ADDON_ACTIVATED", "Add-on activated"
        ADDON_DEACTIVATED = "ADDON_DEACTIVATED", "Add-on deactivated"
        TRIAL_EXTENDED = "TRIAL_EXTENDED", "Trial extended"
        MANUAL_OVERRIDE = "MANUAL_OVERRIDE", "Manual override"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="financial_audit_logs",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="financial_audit_logs",
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} · {self.summary}"
