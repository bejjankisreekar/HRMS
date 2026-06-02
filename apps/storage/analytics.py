"""Storage analytics for Super Admin organization monitoring."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_for
from apps.organizations.models import Organization
from apps.storage.models import FileCategory, StorageAuditLog, StoredFile, UserStorageQuota
from apps.subscriptions.services.billing import get_or_create_subscription


def _bytes_to_gb(n: int) -> Decimal:
    return (Decimal(n) / Decimal(1024 ** 3)).quantize(Decimal("0.01"))


def _bytes_to_mb(n: int) -> Decimal:
    return (Decimal(n) / Decimal(1024 ** 2)).quantize(Decimal("0.01"))


def _format_size(n: int) -> str:
    gb = _bytes_to_gb(n)
    if gb >= Decimal("1"):
        return f"{gb} GB"
    return f"{_bytes_to_mb(n)} MB"


def _storage_limit_bytes(org: Organization) -> int:
    mb = org.storage_limit_mb
    sub = getattr(org, "subscription", None)
    if sub and sub.plan.storage_limit_mb:
        mb = sub.plan.storage_limit_mb
    if not mb:
        mb = 102400  # 100 GB default display
    return int(mb) * 1024 * 1024


def build_org_storage_context(organization: Organization) -> dict:
    files_qs = StoredFile.objects.filter(organization=organization, is_active=True)
    total_bytes = files_qs.aggregate(s=Sum("file_size_bytes"))["s"] or 0
    limit_bytes = _storage_limit_bytes(organization)
    remaining = max(limit_bytes - total_bytes, 0)
    usage_pct = min(100, int(total_bytes / limit_bytes * 100)) if limit_bytes else 0
    file_count = files_qs.count()

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)
    uploads_this_month = files_qs.filter(uploaded_at__gte=month_start).count()
    uploads_prev_month = files_qs.filter(
        uploaded_at__gte=prev_start, uploaded_at__lt=month_start
    ).count()
    growth = 0
    if uploads_prev_month:
        growth = round((uploads_this_month - uploads_prev_month) / uploads_prev_month * 100, 1)

    top_user_row = (
        files_qs.filter(uploaded_by__isnull=False)
        .values("uploaded_by")
        .annotate(total=Sum("file_size_bytes"))
        .order_by("-total")
        .first()
    )
    largest_consumer = "—"
    if top_user_row:
        u = User.objects.filter(pk=top_user_row["uploaded_by"]).first()
        if u:
            largest_consumer = f"{u.display_name} ({_format_size(top_user_row['total'])})"

    role_breakdown = []
    role_labels_map = {
        User.Role.ADMIN: "Organization Admin",
        User.Role.HR: "HR",
        User.Role.EMPLOYEE: "Employee",
    }
    for role in (User.Role.ADMIN, User.Role.HR, User.Role.EMPLOYEE):
        rb = files_qs.filter(uploader_role=role).aggregate(
            total=Sum("file_size_bytes"), cnt=Count("id"), last=Max("uploaded_at")
        )
        rb_bytes = rb["total"] or 0
        role_breakdown.append(
            {
                "role": role,
                "label": role_labels_map.get(role, role_display_for(role)),
                "bytes": rb_bytes,
                "size_label": _format_size(rb_bytes),
                "percent": round(rb_bytes / total_bytes * 100, 1) if total_bytes else 0,
                "file_count": rb["cnt"] or 0,
                "last_upload": rb["last"],
            }
        )

    user_rows = []
    for u in User.objects.filter(organization=organization).exclude(role=User.Role.SUPER_ADMIN):
        stats = files_qs.filter(uploaded_by=u).aggregate(
            total=Sum("file_size_bytes"),
            cnt=Count("id"),
            last=Max("uploaded_at"),
            largest=Max("file_size_bytes"),
        )
        largest_file = (
            files_qs.filter(uploaded_by=u).order_by("-file_size_bytes").values("file_name").first()
        )
        quota = UserStorageQuota.objects.filter(user=u).first()
        user_rows.append(
            {
                "user": u,
                "department": u.department_name or "—",
                "bytes": stats["total"] or 0,
                "size_label": _format_size(stats["total"] or 0),
                "file_count": stats["cnt"] or 0,
                "last_upload": stats["last"],
                "largest_file": largest_file["file_name"] if largest_file else "—",
                "largest_size": _format_size(stats["largest"] or 0),
                "uploads_restricted": quota.uploads_restricted if quota else False,
            }
        )
    user_rows.sort(key=lambda x: -x["bytes"])

    category_breakdown = []
    for cat, label in FileCategory.choices:
        cb = files_qs.filter(category=cat).aggregate(total=Sum("file_size_bytes"), cnt=Count("id"))
        if cb["total"]:
            category_breakdown.append(
                {
                    "category": cat,
                    "label": label,
                    "bytes": cb["total"],
                    "size_label": _format_size(cb["total"]),
                    "count": cb["cnt"],
                }
            )

    dept_breakdown = []
    for row in (
        files_qs.exclude(department_name="")
        .values("department_name")
        .annotate(total=Sum("file_size_bytes"), cnt=Count("id"))
        .order_by("-total")[:8]
    ):
        dept_breakdown.append(
            {
                "name": row["department_name"],
                "bytes": row["total"],
                "size_label": _format_size(row["total"]),
                "count": row["cnt"],
            }
        )

    upload_trend = _upload_trend(files_qs, months=6)
    duplicate_groups = (
        files_qs.exclude(content_hash="")
        .values("content_hash")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .count()
    )

    sub = get_or_create_subscription(organization)
    emp_count = User.objects.filter(organization=organization, is_active=True).exclude(
        role=User.Role.SUPER_ADMIN
    ).count()
    emp_limit = sub.plan.employee_limit or organization.max_users_allowed

    health_score, health_risks = _health_score(usage_pct, growth, duplicate_groups, uploads_this_month)
    insights = _insights(usage_pct, growth, duplicate_groups, total_bytes, limit_bytes)

    audit_logs = StorageAuditLog.objects.filter(organization=organization).select_related(
        "actor", "target_user"
    )[:15]

    large_files = files_qs.order_by("-file_size_bytes")[:12]
    org_files = list(
        files_qs.select_related("uploaded_by").order_by("-uploaded_at")[:100]
    )

    return {
        "storage": {
            "total_bytes": total_bytes,
            "total_label": _format_size(total_bytes),
            "limit_bytes": limit_bytes,
            "limit_label": _format_size(limit_bytes),
            "remaining_bytes": remaining,
            "remaining_label": _format_size(remaining),
            "usage_percent": usage_pct,
            "file_count": file_count,
            "upload_growth_percent": growth,
            "uploads_this_month": uploads_this_month,
            "largest_consumer": largest_consumer,
            "active_files": file_count,
            "cloud_usage_percent": usage_pct,
            "threshold": _threshold_level(usage_pct),
        },
        "role_breakdown": role_breakdown,
        "user_storage_rows": user_rows,
        "category_breakdown": category_breakdown,
        "dept_breakdown": dept_breakdown,
        "upload_trend_json": upload_trend,
        "role_chart_json": {
            "labels": [r["label"] for r in role_breakdown],
            "values": [float(r["bytes"]) for r in role_breakdown],
        },
        "category_chart_json": {
            "labels": [c["label"] for c in category_breakdown],
            "values": [float(c["bytes"]) for c in category_breakdown],
        },
        "dept_chart_json": {
            "labels": [d["name"] for d in dept_breakdown],
            "values": [float(d["bytes"]) for d in dept_breakdown],
        },
        "plan_limits": {
            "plan_name": sub.plan.name,
            "storage_used_label": _format_size(total_bytes),
            "storage_limit_label": _format_size(limit_bytes),
            "usage_percent": usage_pct,
            "employees": emp_count,
            "employee_limit": emp_limit or "Unlimited",
            "api_usage": "—",
            "active_sessions": User.objects.filter(
                organization=organization, is_active=True, last_login__gte=timezone.now() - timedelta(days=7)
            ).count(),
        },
        "health": {
            "score": health_score,
            "risks": health_risks,
        },
        "insights": insights,
        "audit_logs": audit_logs,
        "large_files": large_files,
        "org_files": org_files,
        "duplicate_groups": duplicate_groups,
    }


def _upload_trend(files_qs, months: int = 6) -> dict:
    from apps.subscriptions.services.analytics import _month_start, _shift_month

    today = timezone.localdate()
    labels, uploads, bytes_vals = [], [], []
    for i in range(months - 1, -1, -1):
        y, m = _shift_month(today.year, today.month, -i)
        start = _month_start(y, m)
        ny, nm = _shift_month(y, m, 1)
        end = _month_start(ny, nm)
        month_files = files_qs.filter(uploaded_at__date__gte=start, uploaded_at__date__lt=end)
        labels.append(start.strftime("%b %Y"))
        uploads.append(month_files.count())
        bytes_vals.append(float(month_files.aggregate(s=Sum("file_size_bytes"))["s"] or 0))
    return {"labels": labels, "uploads": uploads, "bytes": bytes_vals}


def _threshold_level(pct: int) -> str:
    if pct >= 90:
        return "critical"
    if pct >= 75:
        return "warning"
    return "ok"


def _health_score(usage_pct, growth, duplicates, uploads_month) -> tuple[int, list[str]]:
    score = 100
    risks = []
    if usage_pct >= 90:
        score -= 30
        risks.append("Storage critically full")
    elif usage_pct >= 75:
        score -= 15
        risks.append("Approaching storage limit")
    if growth > 50:
        score -= 10
        risks.append("Unusual upload spike")
    if duplicates > 3:
        score -= 8
        risks.append("Duplicate files detected")
    if uploads_month == 0 and usage_pct > 20:
        score -= 5
        risks.append("Inactive storage consumption")
    return max(score, 0), risks


def _insights(usage_pct, growth, duplicates, used, limit) -> list[dict]:
    items = []
    if usage_pct >= 85:
        items.append(
            {
                "icon": "alert-triangle",
                "title": "Storage almost full",
                "body": f"Organization is at {usage_pct}% capacity. Consider plan upgrade or cleanup.",
                "tone": "warning",
            }
        )
    if growth > 40:
        items.append(
            {
                "icon": "trending-up",
                "title": "Upload spike",
                "body": f"Monthly upload growth is {growth}%. Review large file uploads.",
                "tone": "warning",
            }
        )
    if duplicates:
        items.append(
            {
                "icon": "copy",
                "title": "Duplicate files",
                "body": f"{duplicates} duplicate hash group(s) found. Run cleanup to save space.",
                "tone": "info",
            }
        )
    items.append(
        {
            "icon": "sparkles",
            "title": "AI optimization (preview)",
            "body": "Smart cleanup and archival recommendations will appear here.",
            "tone": "info",
        }
    )
    return items[:4]


def build_platform_storage_context() -> dict:
    orgs = Organization.objects.filter(is_active=True)
    total_bytes = (
        StoredFile.objects.filter(is_active=True).aggregate(s=Sum("file_size_bytes"))["s"] or 0
    )
    top_orgs = []
    for org in orgs:
        b = (
            StoredFile.objects.filter(organization=org, is_active=True).aggregate(
                s=Sum("file_size_bytes")
            )["s"]
            or 0
        )
        if b:
            top_orgs.append({"organization": org, "bytes": b, "size_label": _format_size(b)})
    top_orgs.sort(key=lambda x: -x["bytes"])

    category_totals = []
    for cat, label in FileCategory.choices:
        cb = StoredFile.objects.filter(is_active=True, category=cat).aggregate(
            total=Sum("file_size_bytes"), cnt=Count("id")
        )
        if cb["total"]:
            category_totals.append(
                {"label": label, "size_label": _format_size(cb["total"]), "count": cb["cnt"]}
            )

    return {
        "total_label": _format_size(total_bytes),
        "total_bytes": total_bytes,
        "org_count": orgs.count(),
        "top_orgs": top_orgs[:15],
        "file_count": StoredFile.objects.filter(is_active=True).count(),
        "category_totals": category_totals,
        "forecast_placeholder": [
            {"month": "Jun 2026", "projected": _format_size(int(total_bytes * 1.08))},
            {"month": "Jul 2026", "projected": _format_size(int(total_bytes * 1.15))},
            {"month": "Aug 2026", "projected": _format_size(int(total_bytes * 1.22))},
        ],
    }
