from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    AddOnCatalog,
    FinancialAuditLog,
    Invoice,
    OrganizationAddOn,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
)
from apps.subscriptions.services.billing import get_or_create_subscription, organization_billing_rows


def _decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by delta calendar months."""
    month_index = (year * 12 + (month - 1)) + delta
    return month_index // 12, (month_index % 12) + 1


def _month_range(year: int, month: int) -> tuple[date, date]:
    """Inclusive start, exclusive end for a calendar month."""
    start = _month_start(year, month)
    next_y, next_m = _shift_month(year, month, 1)
    return start, _month_start(next_y, next_m)


def compute_mrr() -> Decimal:
    total = Decimal("0")
    for sub in Subscription.objects.filter(
        status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)
    ).select_related("plan"):
        total += sub.monthly_bill_inr
    return total.quantize(Decimal("0.01"))


def compute_arr() -> Decimal:
    return (compute_mrr() * 12).quantize(Decimal("0.01"))


def get_executive_kpis() -> dict:
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    paid_total = _decimal(
        Payment.objects.filter(status=PaymentStatus.PAID).aggregate(s=Sum("amount_inr"))["s"]
    )
    pending_payments = Payment.objects.filter(status=PaymentStatus.PENDING).count()
    failed_payments = Payment.objects.filter(status=PaymentStatus.FAILED).count()
    active_subs = Subscription.objects.filter(status=SubscriptionStatus.ACTIVE).count()
    trial_orgs = Organization.objects.filter(
        subscription_status=Organization.SubscriptionStatus.TRIAL
    ).count()
    expired_orgs = Organization.objects.filter(
        subscription_status=Organization.SubscriptionStatus.EXPIRED
    ).count()
    addon_revenue = Decimal("0")
    for oa in OrganizationAddOn.objects.filter(is_active=True).select_related("addon", "organization"):
        addon_revenue += oa.monthly_cost_inr

    mrr = compute_mrr()
    prev_mrr = _estimate_prev_mrr()
    growth = Decimal("0")
    if prev_mrr > 0:
        growth = ((mrr - prev_mrr) / prev_mrr * 100).quantize(Decimal("0.1"))

    churn_rate = _churn_rate()
    profit_margin = Decimal("72.5")  # placeholder until COGS tracked

    return {
        "mrr": mrr,
        "arr": compute_arr(),
        "total_revenue": paid_total,
        "pending_payments": pending_payments,
        "failed_payments": failed_payments,
        "active_subscriptions": active_subs,
        "expired_organizations": expired_orgs,
        "trial_organizations": trial_orgs,
        "addon_revenue": addon_revenue.quantize(Decimal("0.01")),
        "profit_margin": profit_margin,
        "growth_percent": growth,
        "churn_rate": churn_rate,
        "month_payments": _decimal(
            Payment.objects.filter(status=PaymentStatus.PAID, paid_at__gte=month_start).aggregate(
                s=Sum("amount_inr")
            )["s"]
        ),
    }


def _estimate_prev_mrr() -> Decimal:
    """Approximate prior-month MRR from paid invoices."""
    today = timezone.localdate()
    prev_y, prev_m = _shift_month(today.year, today.month, -1)
    start, end = _month_range(prev_y, prev_m)
    total = _decimal(
        Invoice.objects.filter(
            status=Invoice.Status.PAID,
            paid_at__date__gte=start,
            paid_at__date__lt=end,
        ).aggregate(s=Sum("amount_inr"))["s"]
    )
    return total if total > 0 else compute_mrr() * Decimal("0.92")


def _churn_rate() -> Decimal:
    total = Organization.objects.count()
    if not total:
        return Decimal("0")
    churned = Organization.objects.filter(
        subscription_status__in=(
            Organization.SubscriptionStatus.CANCELED,
            Organization.SubscriptionStatus.EXPIRED,
        )
    ).count()
    return (Decimal(churned) / Decimal(total) * 100).quantize(Decimal("0.1"))


def revenue_chart_months(months: int = 12) -> dict:
    labels = []
    values = []
    today = timezone.localdate()
    for i in range(months - 1, -1, -1):
        y, m = _shift_month(today.year, today.month, -i)
        start, end = _month_range(y, m)
        labels.append(start.strftime("%b %Y"))
        total = _decimal(
            Payment.objects.filter(
                status=PaymentStatus.PAID,
                paid_at__date__gte=start,
                paid_at__date__lt=end,
            ).aggregate(s=Sum("amount_inr"))["s"]
        )
        values.append(float(total))
    return {"labels": labels, "values": values}


def subscription_growth_chart(months: int = 12) -> dict:
    labels = []
    active = []
    trial = []
    today = timezone.localdate()
    for i in range(months - 1, -1, -1):
        y, m = _shift_month(today.year, today.month, -i)
        start, end = _month_range(y, m)
        labels.append(start.strftime("%b %Y"))
        active.append(
            Subscription.objects.filter(
                status=SubscriptionStatus.ACTIVE,
                created_at__date__lt=end,
            ).count()
        )
        trial.append(
            Subscription.objects.filter(
                status=SubscriptionStatus.TRIAL,
                created_at__date__lt=end,
            ).count()
        )
    return {"labels": labels, "active": active, "trial": trial}


def plan_revenue_breakdown() -> list[dict]:
    rows = []
    for plan in Plan.objects.filter(is_active=True).annotate(
        sub_count=Count("subscriptions")
    ):
        mrr = Decimal("0")
        for sub in plan.subscriptions.filter(status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)):
            mrr += sub.monthly_bill_inr
        rows.append(
            {
                "name": plan.name,
                "slug": plan.slug,
                "subscribers": plan.sub_count,
                "mrr": float(mrr),
            }
        )
    return sorted(rows, key=lambda x: -x["mrr"])


def payment_success_rates() -> dict:
    total = Payment.objects.count()
    if not total:
        return {"success": 100, "failed": 0, "pending": 0}
    paid = Payment.objects.filter(status=PaymentStatus.PAID).count()
    failed = Payment.objects.filter(status=PaymentStatus.FAILED).count()
    pending = Payment.objects.filter(status=PaymentStatus.PENDING).count()
    return {
        "success": round(paid / total * 100, 1),
        "failed": round(failed / total * 100, 1),
        "pending": round(pending / total * 100, 1),
    }


def get_financial_dashboard_context() -> dict:
    kpis = get_executive_kpis()
    return {
        "kpis": kpis,
        "revenue_chart": revenue_chart_months(),
        "subscription_chart": subscription_growth_chart(),
        "plan_breakdown": plan_revenue_breakdown(),
        "payment_rates": payment_success_rates(),
        "recent_payments": Payment.objects.select_related("organization").order_by("-created_at")[:8],
        "recent_invoices": Invoice.objects.select_related("organization").order_by("-created_at")[:8],
        "recent_audit": FinancialAuditLog.objects.select_related("organization", "actor").order_by("-created_at")[
            :10
        ],
        "ai_insights": _ai_insights(kpis),
        "automation_placeholders": _automation_status(),
    }


def get_revenue_analytics_context() -> dict:
    kpis = get_executive_kpis()
    return {
        "kpis": kpis,
        "revenue_chart": revenue_chart_months(18),
        "subscription_chart": subscription_growth_chart(18),
        "plan_breakdown": plan_revenue_breakdown(),
        "addon_sales": _addon_sales(),
        "trial_conversion": _trial_conversion(),
        "forecast": _revenue_forecast(),
    }


def get_subscriptions_page_context(filters: dict | None = None) -> dict:
    return {
        "rows": organization_billing_rows(filters),
        "plans": Plan.objects.filter(is_active=True),
        "addons": AddOnCatalog.objects.filter(is_active=True),
        "filters": filters or {},
    }


def get_usage_page_context() -> list[dict]:
    rows = []
    for org in Organization.objects.filter(is_active=True).order_by("name")[:100]:
        sub = getattr(org, "subscription", None)
        if not sub:
            sub = get_or_create_subscription(org)
        emp_count = User.objects.filter(organization=org, is_active=True).exclude(
            role=User.Role.SUPER_ADMIN
        ).count()
        emp_limit = sub.plan.employee_limit
        storage_used = UsageRecord.objects.filter(organization=org, metric="storage_mb").order_by(
            "-recorded_at"
        ).first()
        storage_used_val = storage_used.quantity if storage_used else 0
        storage_limit = sub.plan.storage_limit_mb or org.storage_limit_mb or 1024
        rows.append(
            {
                "organization": org,
                "plan": sub.plan,
                "employees": emp_count,
                "employee_limit": emp_limit,
                "employee_pct": min(100, int(emp_count / emp_limit * 100)) if emp_limit else 0,
                "storage_used_mb": storage_used_val,
                "storage_limit_mb": storage_limit,
                "storage_pct": min(100, int(storage_used_val / storage_limit * 100)) if storage_limit else 0,
                "branch_count": org.branch_count or 1,
                "branch_limit": sub.plan.branch_limit,
                "overusage": emp_limit and emp_count > emp_limit,
            }
        )
    return rows


def _addon_sales() -> list[dict]:
    return [
        {
            "name": addon.name,
            "count": OrganizationAddOn.objects.filter(addon=addon, is_active=True).count(),
            "mrr": float(addon.monthly_price_inr),
        }
        for addon in AddOnCatalog.objects.filter(is_active=True)
    ]


def _trial_conversion() -> dict:
    trials = Subscription.objects.filter(status=SubscriptionStatus.TRIAL).count()
    converted = Subscription.objects.filter(
        status=SubscriptionStatus.ACTIVE,
        metadata__converted_from_trial=True,
    ).count()
    total_trials = trials + converted or 1
    rate = round(converted / total_trials * 100, 1) if total_trials else 0
    return {"trials": trials, "converted": converted, "rate": rate}


def _revenue_forecast() -> dict:
    mrr = compute_mrr()
    labels = []
    values = []
    for i in range(1, 7):
        labels.append(f"M+{i}")
        values.append(float(mrr * Decimal(1.03) ** i))
    return {"labels": labels, "values": values}


def _ai_insights(kpis: dict) -> list[dict]:
    insights = []
    if kpis["churn_rate"] > 5:
        insights.append(
            {
                "icon": "alert-triangle",
                "title": "Elevated churn",
                "body": f"Churn is {kpis['churn_rate']}%. Review expired orgs and offer retention discounts.",
                "tone": "warning",
            }
        )
    if kpis["failed_payments"] > 0:
        insights.append(
            {
                "icon": "credit-card",
                "title": "Failed payments",
                "body": f"{kpis['failed_payments']} failed payment(s) need follow-up.",
                "tone": "warning",
            }
        )
    if kpis["trial_organizations"] > 5:
        insights.append(
            {
                "icon": "sparkles",
                "title": "Trial pipeline",
                "body": f"{kpis['trial_organizations']} organizations on trial — prime for conversion outreach.",
                "tone": "info",
            }
        )
    insights.append(
        {
            "icon": "brain",
            "title": "AI revenue insight (preview)",
            "body": "Predictive churn and smart pricing recommendations will appear here.",
            "tone": "info",
        }
    )
    return insights[:4]


def _automation_status() -> list[dict]:
    return [
        {"name": "Auto renewal", "status": "ready", "enabled": False},
        {"name": "Auto invoice generation", "status": "ready", "enabled": False},
        {"name": "Trial expiry emails", "status": "ready", "enabled": False},
        {"name": "Failed payment retries", "status": "ready", "enabled": False},
        {"name": "Auto suspension", "status": "ready", "enabled": False},
    ]
