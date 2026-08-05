from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    AddOnCatalog,
    BillingInterval,
    BillingSettings,
    FinancialAuditLog,
    Invoice,
    OrganizationAddOn,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from apps.subscriptions.plan_defaults import get_default_plan
from apps.subscriptions.services.feature_control import invalidate_org_entitlements
from apps.subscriptions.services.audit import log_financial_action


def _next_invoice_number() -> str:
    year = timezone.localdate().year
    prefix = f"INV-{year}-"
    last = (
        Invoice.objects.filter(invoice_number__startswith=prefix)
        .order_by("-invoice_number")
        .values_list("invoice_number", flat=True)
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = Invoice.objects.count() + 1
    return f"{prefix}{seq:05d}"


def get_or_create_subscription(org: Organization) -> Subscription:
    sub = getattr(org, "subscription", None)
    if sub:
        return sub
    plan = Plan.objects.filter(is_active=True).order_by("sort_order").first()
    if not plan:
        basic = get_default_plan("basic")
        billing_settings = BillingSettings.get_solo()
        plan = Plan.objects.create(
            slug=basic["slug"],
            name=basic["name"],
            monthly_price_inr=basic["monthly_price_inr"],
            yearly_price_inr=billing_settings.compute_yearly_price(basic["monthly_price_inr"]),
            employee_limit=basic["employee_limit"],
        )
    now = timezone.now()
    return Subscription.objects.create(
        organization=org,
        plan=plan,
        status=SubscriptionStatus.TRIAL,
        trial_ends_at=now + timedelta(days=plan.trial_days),
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )


def sync_org_subscription_status(org: Organization) -> None:
    """Keep Organization.subscription_status in sync with billing Subscription."""
    sub = getattr(org, "subscription", None)
    if not sub:
        return
    mapping = {
        SubscriptionStatus.TRIAL: Organization.SubscriptionStatus.TRIAL,
        SubscriptionStatus.ACTIVE: Organization.SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE: Organization.SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.SUSPENDED: Organization.SubscriptionStatus.INACTIVE,
        SubscriptionStatus.CANCELLED: Organization.SubscriptionStatus.CANCELED,
        SubscriptionStatus.EXPIRED: Organization.SubscriptionStatus.EXPIRED,
    }
    org.subscription_status = mapping.get(sub.status, Organization.SubscriptionStatus.INACTIVE)
    org.save(update_fields=["subscription_status", "updated_at"])


@transaction.atomic
def upgrade_plan(*, org: Organization, plan: Plan, actor, billing_interval: str | None = None) -> Subscription:
    sub = get_or_create_subscription(org)
    old_plan = sub.plan.name
    sub.plan = plan
    if billing_interval:
        sub.billing_interval = billing_interval
    if sub.status in (SubscriptionStatus.TRIAL, SubscriptionStatus.EXPIRED):
        sub.status = SubscriptionStatus.ACTIVE
    sub.save()
    org.subscription_plan = _map_plan_to_org_field(plan.slug)
    org.save(update_fields=["subscription_plan", "updated_at"])
    sync_org_subscription_status(org)
    invalidate_org_entitlements(org)
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.PLAN_CHANGE,
        organization=org,
        summary=f"Plan changed from {old_plan} to {plan.name}",
        details={"plan_slug": plan.slug},
    )
    return sub


def _map_plan_to_org_field(slug: str) -> str:
    slug_map = {
        "basic": Organization.SubscriptionPlan.BASIC,
        "essential": Organization.SubscriptionPlan.BASIC,
        "professional": Organization.SubscriptionPlan.PROFESSIONAL,
        "growth": Organization.SubscriptionPlan.GROWTH,
        "business": Organization.SubscriptionPlan.GROWTH,
    }
    return slug_map.get(slug.lower(), Organization.SubscriptionPlan.BASIC)


def _org_field_to_plan_slug(subscription_plan: str) -> str:
    mapping = {
        Organization.SubscriptionPlan.BASIC: "basic",
        Organization.SubscriptionPlan.PROFESSIONAL: "professional",
        Organization.SubscriptionPlan.GROWTH: "growth",
    }
    return mapping.get(subscription_plan, "basic")


def plan_for_org_subscription_field(org: Organization) -> Plan | None:
    slug = _org_field_to_plan_slug(org.subscription_plan)
    return Plan.objects.filter(slug=slug, is_active=True).first()


@transaction.atomic
def sync_subscription_from_org_plan(
    *,
    org: Organization,
    actor=None,
    request=None,
    reset_features: bool = True,
) -> tuple[Plan | None, bool]:
    """Align billing Subscription with Organization.subscription_plan and refresh features."""
    plan = plan_for_org_subscription_field(org)
    if not plan:
        plan = Plan.objects.filter(is_active=True).order_by("sort_order").first()
    if not plan:
        return None, False

    sub = get_or_create_subscription(org)
    changed = sub.plan_id != plan.pk
    if changed:
        old_name = sub.plan.name
        sub.plan = plan
        sub.save(update_fields=["plan", "updated_at"])
        log_financial_action(
            actor=actor,
            action=FinancialAuditLog.Action.PLAN_CHANGE,
            organization=org,
            summary=f"Plan synced to {plan.name} for {org.name} (was {old_name})",
            details={"plan_slug": plan.slug, "source": "organization_subscription_plan"},
        )

    invalidate_org_entitlements(org)

    if changed and reset_features:
        from apps.subscriptions.models import OrganizationLimit
        from apps.subscriptions.services.org_features import reset_org_to_plan_defaults

        reset_org_to_plan_defaults(org=org, actor=actor, request=request)
        OrganizationLimit.objects.filter(organization=org).delete()
        update_fields = ["updated_at"]
        if plan.employee_limit is not None:
            org.max_users_allowed = plan.employee_limit
            update_fields.append("max_users_allowed")
        if plan.storage_limit_mb is not None:
            org.storage_limit_mb = plan.storage_limit_mb
            update_fields.append("storage_limit_mb")
        org.save(update_fields=update_fields)
        invalidate_org_entitlements(org)

    return plan, changed


@transaction.atomic
def suspend_subscription(*, org: Organization, actor) -> Subscription:
    sub = get_or_create_subscription(org)
    sub.status = SubscriptionStatus.SUSPENDED
    sub.suspended_at = timezone.now()
    sub.save(update_fields=["status", "suspended_at", "updated_at"])
    org.is_active = False
    org.save(update_fields=["is_active", "updated_at"])
    sync_org_subscription_status(org)
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.SUBSCRIPTION_SUSPEND,
        organization=org,
        summary=f"Subscription suspended for {org.name}",
    )
    return sub


@transaction.atomic
def activate_subscription(*, org: Organization, actor) -> Subscription:
    sub = get_or_create_subscription(org)
    sub.status = SubscriptionStatus.ACTIVE
    sub.suspended_at = None
    now = timezone.now()
    if not sub.current_period_end or sub.current_period_end < now:
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    sub.save()
    org.is_active = True
    org.save(update_fields=["is_active", "updated_at"])
    sync_org_subscription_status(org)
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.SUBSCRIPTION_ACTIVATE,
        organization=org,
        summary=f"Subscription activated for {org.name}",
    )
    return sub


@transaction.atomic
def extend_trial(*, org: Organization, days: int, actor) -> Subscription:
    sub = get_or_create_subscription(org)
    now = timezone.now()
    base = sub.trial_ends_at if sub.trial_ends_at and sub.trial_ends_at > now else now
    sub.trial_ends_at = base + timedelta(days=days)
    sub.status = SubscriptionStatus.TRIAL
    sub.save(update_fields=["trial_ends_at", "status", "updated_at"])
    sync_org_subscription_status(org)
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.TRIAL_EXTENDED,
        organization=org,
        summary=f"Trial extended by {days} days",
        details={"days": days},
    )
    return sub


@transaction.atomic
def add_credit(*, org: Organization, amount_inr: Decimal, actor, note: str = "") -> Subscription:
    sub = get_or_create_subscription(org)
    sub.credit_balance_inr += amount_inr
    sub.save(update_fields=["credit_balance_inr", "updated_at"])
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.CREDIT_ADDED,
        organization=org,
        summary=f"Credit ₹{amount_inr} added",
        details={"amount": str(amount_inr), "note": note},
    )
    return sub


@transaction.atomic
def apply_coupon(*, org: Organization, coupon_code: str, actor) -> Subscription:
    from apps.subscriptions.models import Coupon

    coupon = Coupon.objects.get(code__iexact=coupon_code.strip(), is_active=True)
    sub = get_or_create_subscription(org)
    sub.coupon = coupon
    if coupon.percent_off:
        sub.discount_percent = coupon.percent_off
    sub.save(update_fields=["coupon", "discount_percent", "updated_at"])
    coupon.redemption_count += 1
    coupon.save(update_fields=["redemption_count"])
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.COUPON_APPLIED,
        organization=org,
        summary=f"Coupon {coupon.code} applied",
    )
    return sub


@transaction.atomic
def generate_invoice(*, org: Organization, actor) -> Invoice:
    sub = get_or_create_subscription(org)
    now = timezone.now()
    amount = sub.monthly_bill_inr
    tax = (amount * Decimal("18") / Decimal("100")).quantize(Decimal("0.01"))
    period_end = sub.current_period_end or (now + timedelta(days=30))
    period_start = sub.current_period_start or now
    inv = Invoice.objects.create(
        subscription=sub,
        organization=org,
        invoice_number=_next_invoice_number(),
        amount_inr=amount,
        tax_inr=tax,
        status=Invoice.Status.OPEN,
        period_start=period_start,
        period_end=period_end,
        due_date=now + timedelta(days=7),
        line_items=[
            {"label": sub.plan.name, "amount": str(amount)},
        ],
    )
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.INVOICE_GENERATED,
        organization=org,
        summary=f"Invoice {inv.invoice_number} generated",
        details={"invoice_id": str(inv.pk), "amount": str(amount)},
    )
    return inv


@transaction.atomic
def record_manual_payment(
    *,
    org: Organization,
    amount_inr: Decimal,
    actor,
    invoice: Invoice | None = None,
    method: str = PaymentMethod.MANUAL,
    reference_id: str = "",
    notes: str = "",
) -> Payment:
    payment = Payment.objects.create(
        organization=org,
        invoice=invoice,
        amount_inr=amount_inr,
        status=PaymentStatus.PAID,
        method=method,
        reference_id=reference_id,
        paid_at=timezone.now(),
        recorded_by=actor,
        notes=notes,
    )
    if invoice:
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at"])
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.PAYMENT_RECORDED,
        organization=org,
        summary=f"Payment ₹{amount_inr} recorded",
        details={"payment_id": str(payment.pk)},
    )
    return payment


@transaction.atomic
def toggle_org_addon(*, org: Organization, addon: AddOnCatalog, active: bool, actor) -> OrganizationAddOn:
    sub = get_or_create_subscription(org)
    obj, _ = OrganizationAddOn.objects.get_or_create(
        organization=org,
        addon=addon,
        defaults={"subscription": sub, "is_active": active},
    )
    obj.is_active = active
    obj.subscription = sub
    if not active:
        obj.deactivated_at = timezone.now()
    obj.save()
    invalidate_org_entitlements(org)
    log_financial_action(
        actor=actor,
        action=FinancialAuditLog.Action.ADDON_ACTIVATED if active else FinancialAuditLog.Action.ADDON_DEACTIVATED,
        organization=org,
        summary=f"Add-on {addon.name} {'enabled' if active else 'disabled'}",
    )
    return obj


def organization_billing_rows(filters: dict | None = None) -> list[dict]:
    filters = filters or {}
    qs = Organization.objects.all().select_related("subscription__plan").prefetch_related("billing_addons__addon")
    status_filter = filters.get("status")
    if status_filter == "trial":
        qs = qs.filter(subscription_status=Organization.SubscriptionStatus.TRIAL)
    elif status_filter == "active":
        qs = qs.filter(subscription_status=Organization.SubscriptionStatus.ACTIVE, is_active=True)
    elif status_filter == "expired":
        qs = qs.filter(subscription_status=Organization.SubscriptionStatus.EXPIRED)
    elif status_filter == "suspended":
        qs = qs.filter(is_active=False)
    elif status_filter == "past_due":
        qs = qs.filter(subscription_status=Organization.SubscriptionStatus.PAST_DUE)
    elif status_filter == "growth":
        qs = qs.filter(subscription__plan__slug="growth")

    plan_filter = filters.get("plan")
    if plan_filter:
        qs = qs.filter(subscription__plan__slug=plan_filter)

    q = (filters.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(organization_code__icontains=q))

    rows = []
    for org in qs.order_by("name")[:200]:
        sub = getattr(org, "subscription", None)
        if not sub:
            sub = None
        emp_count = User.objects.filter(organization=org, is_active=True).exclude(
            role=User.Role.SUPER_ADMIN
        ).count()
        addons = list(org.billing_addons.filter(is_active=True).select_related("addon")[:5])
        last_inv = org.invoices.order_by("-created_at").first()
        payment_status = "—"
        if last_inv:
            payment_status = last_inv.get_status_display()
        rows.append(
            {
                "organization": org,
                "subscription": sub,
                "plan_name": sub.plan.name if sub else org.get_subscription_plan_display(),
                "status": sub.get_status_display() if sub else org.get_subscription_status_display(),
                "employee_count": emp_count,
                "monthly_bill": sub.monthly_bill_inr if sub else Decimal("0"),
                "renewal_date": sub.current_period_end if sub else None,
                "payment_status": payment_status,
                "addons": addons,
            }
        )
    return rows
