"""Lifecycle dashboard analytics."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.hierarchy import org_active_users
from apps.accounts.models import User
from apps.lifecycle.models import (
    AssetAllocation,
    ClearanceApproval,
    EmployeeDocument,
    OffboardingWorkflow,
    OnboardingTask,
    OnboardingWorkflow,
    OrientationSession,
)
from apps.lifecycle.services import LifecycleFilters, avg_onboarding_days
from apps.organizations.models import Department, Organization


def filter_options(org: Organization) -> dict[str, Any]:
    users = org_active_users(org)
    branches = sorted({u.work_location for u in users if u.work_location})
    return {
        "departments": Department.objects.filter(organization=org, is_active=True).order_by("name"),
        "branches": branches,
        "onboarding_statuses": OnboardingWorkflow.Status.choices,
        "offboarding_statuses": OffboardingWorkflow.Status.choices,
        "employees": users.filter(role__in=[User.Role.HR, User.Role.EMPLOYEE]).order_by("first_name"),
    }


def _onboarding_qs(org: Organization, filters: LifecycleFilters):
    qs = OnboardingWorkflow.objects.filter(organization=org).select_related(
        "user", "user__department"
    )
    if filters.department:
        qs = qs.filter(user__department_id=filters.department)
    if filters.branch:
        qs = qs.filter(Q(branch__iexact=filters.branch) | Q(user__work_location__iexact=filters.branch))
    if filters.workflow_status:
        qs = qs.filter(status=filters.workflow_status)
    if filters.joining_from:
        qs = qs.filter(joining_date__gte=filters.joining_from)
    if filters.joining_to:
        qs = qs.filter(joining_date__lte=filters.joining_to)
    return qs


def _offboarding_qs(org: Organization, filters: LifecycleFilters):
    qs = OffboardingWorkflow.objects.filter(organization=org).select_related(
        "user", "user__department"
    )
    if filters.department:
        qs = qs.filter(user__department_id=filters.department)
    if filters.branch:
        qs = qs.filter(user__work_location__iexact=filters.branch)
    if filters.workflow_status:
        qs = qs.filter(status=filters.workflow_status)
    if filters.exit_from:
        qs = qs.filter(last_working_day__gte=filters.exit_from)
    if filters.exit_to:
        qs = qs.filter(last_working_day__lte=filters.exit_to)
    return qs


def onboarding_summary(org: Organization, filters: LifecycleFilters) -> dict[str, Any]:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    qs = _onboarding_qs(org, filters)
    new_joiners = qs.filter(joining_date__gte=month_start).count()
    pending_tasks = OnboardingTask.objects.filter(
        onboarding__organization=org, status=OnboardingTask.Status.PENDING
    ).count()
    in_orientation = qs.filter(status=OnboardingWorkflow.Status.ORIENTATION).count()
    if not in_orientation:
        in_orientation = OrientationSession.objects.filter(
            onboarding__organization=org, completed=False, scheduled_at__date__gte=today
        ).values("onboarding").distinct().count()
    devices = AssetAllocation.objects.filter(
        organization=org, status=AssetAllocation.Status.ALLOCATED
    ).count()
    return {
        "new_joiners": new_joiners,
        "pending_tasks": pending_tasks,
        "in_orientation": in_orientation,
        "devices_allocated": devices,
        "exit_requests": OffboardingWorkflow.objects.filter(
            organization=org, status=OffboardingWorkflow.Status.REQUESTED
        ).count(),
        "pending_clearances": ClearanceApproval.objects.filter(
            offboarding__organization=org, status=ClearanceApproval.Status.PENDING
        ).count(),
        "completed_offboarding": OffboardingWorkflow.objects.filter(
            organization=org, status=OffboardingWorkflow.Status.COMPLETED
        ).count(),
        "avg_onboarding_days": avg_onboarding_days(org),
    }


def offboarding_summary(org: Organization, filters: LifecycleFilters) -> dict[str, Any]:
    base = onboarding_summary(org, filters)
    ob = _offboarding_qs(org, filters)
    base["exit_requests"] = ob.exclude(status=OffboardingWorkflow.Status.COMPLETED).count()
    base["pending_clearances"] = ClearanceApproval.objects.filter(
        offboarding__in=ob, status=ClearanceApproval.Status.PENDING
    ).count()
    base["completed_offboarding"] = ob.filter(status=OffboardingWorkflow.Status.COMPLETED).count()
    return base


def onboarding_charts(org: Organization, filters: LifecycleFilters) -> dict[str, Any]:
    qs = _onboarding_qs(org, filters)
    dept_map: dict[str, int] = {}
    for w in qs:
        name = w.user.department_name or "Unassigned"
        dept_map[name] = dept_map.get(name, 0) + 1
    labels = list(dept_map.keys())[:8]
    values = [dept_map[k] for k in labels]

    months = []
    counts = []
    today = timezone.localdate()
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        label = f"{y}-{m:02d}"
        months.append(label)
        counts.append(
            OnboardingWorkflow.objects.filter(
                organization=org, joining_date__year=y, joining_date__month=m
            ).count()
        )

    doc_pending = EmployeeDocument.objects.filter(
        onboarding__organization=org,
        verify_status__in=[
            EmployeeDocument.VerifyStatus.PENDING,
            EmployeeDocument.VerifyStatus.MISSING,
        ],
    ).count()
    doc_verified = EmployeeDocument.objects.filter(
        onboarding__organization=org, verify_status=EmployeeDocument.VerifyStatus.VERIFIED
    ).count()

    return {
        "joiningTrend": {"labels": months, "values": counts},
        "departmentHires": {"labels": labels, "values": values},
        "documentation": {"labels": ["Verified", "Pending"], "values": [doc_verified, doc_pending]},
        "completion": {
            "labels": ["Completed", "In progress"],
            "values": [
                qs.filter(status=OnboardingWorkflow.Status.COMPLETED).count(),
                qs.exclude(status=OnboardingWorkflow.Status.COMPLETED).count(),
            ],
        },
    }


def offboarding_charts(org: Organization, filters: LifecycleFilters) -> dict[str, Any]:
    qs = _offboarding_qs(org, filters)
    reasons: dict[str, int] = {}
    for w in qs:
        label = w.get_resignation_reason_display()
        reasons[label] = reasons.get(label, 0) + 1

    dept_map: dict[str, int] = {}
    for w in qs:
        name = w.user.department_name or "Unassigned"
        dept_map[name] = dept_map.get(name, 0) + 1

    return {
        "attritionTrend": onboarding_charts(org, filters)["joiningTrend"],
        "exitReasons": {
            "labels": list(reasons.keys())[:6],
            "values": list(reasons.values())[:6],
        },
        "departmentExits": {
            "labels": list(dept_map.keys())[:8],
            "values": list(dept_map.values())[:8],
        },
        "clearance": {
            "labels": ["Approved", "Pending"],
            "values": [
                ClearanceApproval.objects.filter(
                    offboarding__organization=org, status=ClearanceApproval.Status.APPROVED
                ).count(),
                ClearanceApproval.objects.filter(
                    offboarding__organization=org, status=ClearanceApproval.Status.PENDING
                ).count(),
            ],
        },
    }


def build_insights(org: Organization, *, mode: str = "onboarding") -> list[dict]:
    insights = []
    pending_docs = EmployeeDocument.objects.filter(
        onboarding__organization=org,
        verify_status=EmployeeDocument.VerifyStatus.MISSING,
    ).count()
    if pending_docs:
        insights.append(
            {
                "icon": "file-warning",
                "title": "Missing documents",
                "body": f"{pending_docs} document slot(s) still need upload or verification.",
                "tone": "warning",
            }
        )
    pending_tasks = OnboardingTask.objects.filter(
        onboarding__organization=org, status=OnboardingTask.Status.PENDING
    ).count()
    if pending_tasks:
        insights.append(
            {
                "icon": "list-todo",
                "title": "Onboarding tasks pending",
                "body": f"{pending_tasks} tasks awaiting completion across active workflows.",
                "tone": "info",
            }
        )
    pending_clear = ClearanceApproval.objects.filter(
        offboarding__organization=org, status=ClearanceApproval.Status.PENDING
    ).count()
    if pending_clear and mode == "offboarding":
        insights.append(
            {
                "icon": "shield-check",
                "title": "Clearances pending",
                "body": f"{pending_clear} department clearance(s) need approval before exit.",
                "tone": "warning",
            }
        )
    assets_out = AssetAllocation.objects.filter(
        organization=org, status=AssetAllocation.Status.ALLOCATED, offboarding__isnull=False
    ).count()
    if assets_out:
        insights.append(
            {
                "icon": "laptop",
                "title": "Assets to recover",
                "body": f"{assets_out} asset(s) marked for return during offboarding.",
                "tone": "warning",
            }
        )
    if not insights:
        insights.append(
            {
                "icon": "sparkles",
                "title": "Workflows on track",
                "body": "No critical bottlenecks detected in lifecycle pipelines.",
                "tone": "success",
            }
        )
    return insights[:6]


def onboarding_table_rows(org: Organization, filters: LifecycleFilters) -> list[dict]:
    rows = []
    for w in _onboarding_qs(org, filters)[:200]:
        pending = w.tasks.filter(status=OnboardingTask.Status.PENDING).count()
        rows.append(
            {
                "employee_id": w.user.employee_id or "—",
                "name": w.user.display_name,
                "department": w.user.department_name or "—",
                "joining_date": w.joining_date.isoformat(),
                "status": w.get_status_display(),
                "progress": w.progress_percent,
                "pending_tasks": pending,
                "branch": w.branch or w.user.work_location or "—",
                "workflow_id": str(w.pk),
            }
        )
    return rows


def offboarding_table_rows(org: Organization, filters: LifecycleFilters) -> list[dict]:
    rows = []
    for w in _offboarding_qs(org, filters)[:200]:
        cleared = w.clearances.filter(status=ClearanceApproval.Status.APPROVED).count()
        total_clear = w.clearances.count()
        rows.append(
            {
                "employee_id": w.user.employee_id or "—",
                "name": w.user.display_name,
                "department": w.user.department_name or "—",
                "last_day": w.last_working_day.isoformat(),
                "reason": w.get_resignation_reason_display(),
                "status": w.get_status_display(),
                "progress": w.progress_percent,
                "clearance": f"{cleared}/{total_clear}",
                "workflow_id": str(w.pk),
            }
        )
    return rows


def export_csv(rows: list[dict], headers: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r.get(h, "") for h in headers])
    return buf.getvalue().encode("utf-8")
