"""Shift dashboard analytics, charts, and report rows."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, WorkShift
from apps.dashboard.attendance_utils import analyze_lateness, compute_working_hours, get_effective_shift
from apps.organizations.models import Department, Organization
from apps.shifts.models import OvertimeRecord, ShiftAssignment, ShiftSwapRequest
from apps.shifts.services import ShiftFilters, effective_shift_for_date, schedulable_users


def filter_options(org: Organization, viewer: User) -> dict[str, Any]:
    users = schedulable_users(viewer)
    branches = sorted({u.work_location for u in users if u.work_location})
    departments = Department.objects.filter(organization=org, is_active=True).order_by("name")
    shifts = WorkShift.objects.filter(organization=org, is_active=True).order_by("-is_default", "name")
    try:
        from apps.orgchart.models import Team

        teams = Team.objects.filter(organization=org, is_active=True).order_by("name")
    except Exception:
        teams = []
    return {
        "branches": branches,
        "departments": departments,
        "employees": users,
        "teams": teams,
        "shift_types": WorkShift.ShiftType.choices,
        "shifts": shifts,
    }


def build_summary(org: Organization, users: list[User], filters: ShiftFilters) -> dict[str, Any]:
    today = timezone.localdate()
    active_shifts = WorkShift.objects.filter(organization=org, is_active=True).count()
    user_ids = [u.pk for u in users]

    scheduled_today = ShiftAssignment.objects.filter(
        organization=org, date=today, user_id__in=user_ids
    ).count()
    if scheduled_today == 0 and user_ids:
        scheduled_today = len(user_ids)

    night_count = ShiftAssignment.objects.filter(
        organization=org,
        date=today,
        user_id__in=user_ids,
        shift__shift_type=WorkShift.ShiftType.NIGHT,
    ).count()
    if not night_count:
        night_count = sum(
            1
            for u in users
            if (get_effective_shift(u) and get_effective_shift(u).shift_type == WorkShift.ShiftType.NIGHT)
        )

    rotational = WorkShift.objects.filter(
        organization=org, shift_type=WorkShift.ShiftType.ROTATIONAL, is_active=True
    ).count()

    pending_swaps = ShiftSwapRequest.objects.filter(
        organization=org, status=ShiftSwapRequest.Status.PENDING
    ).count()

    ot_hours = (
        OvertimeRecord.objects.filter(
            organization=org,
            date__gte=filters.date_from,
            date__lte=filters.date_to,
            user_id__in=user_ids,
        ).aggregate(total=Sum("minutes"))["total"]
        or 0
    )

    present = AttendanceRecord.objects.filter(
        user_id__in=user_ids,
        date=today,
        status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.WFH],
    ).count()
    compliance = round((present / max(len(users), 1)) * 100, 1)

    assignments_in_range = ShiftAssignment.objects.filter(
        organization=org,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
        user_id__in=user_ids,
    ).count()
    days_in_range = (filters.date_to - filters.date_from).days + 1
    slots = max(len(users) * days_in_range, 1)
    coverage = round((assignments_in_range / slots) * 100, 1)

    return {
        "active_shifts": active_shifts,
        "scheduled_today": scheduled_today,
        "night_shift_employees": night_count,
        "rotational_shifts": rotational,
        "pending_swaps": pending_swaps,
        "overtime_hours": round(ot_hours / 60, 1),
        "compliance_rate": compliance,
        "coverage_rate": min(coverage, 100),
    }


def build_insights(org: Organization, users: list[User], summary: dict) -> list[dict]:
    insights = []
    if summary["pending_swaps"] > 0:
        insights.append(
            {
                "icon": "repeat",
                "title": "Pending shift swaps",
                "body": f"{summary['pending_swaps']} swap request(s) need manager approval.",
                "tone": "warning",
            }
        )
    if summary["coverage_rate"] < 70:
        insights.append(
            {
                "icon": "calendar-x",
                "title": "Low schedule coverage",
                "body": "Run auto-schedule to fill gaps in the weekly roster.",
                "tone": "warning",
            }
        )
    if summary["overtime_hours"] > 20:
        insights.append(
            {
                "icon": "clock",
                "title": "Overtime risk",
                "body": f"{summary['overtime_hours']}h overtime logged in this period. Review staffing levels.",
                "tone": "warning",
            }
        )
    night = WorkShift.objects.filter(organization=org, shift_type=WorkShift.ShiftType.NIGHT).count()
    if night:
        insights.append(
            {
                "icon": "moon",
                "title": "Night shift coverage",
                "body": "Monitor fatigue and cross-day attendance for overnight shifts.",
                "tone": "info",
            }
        )
    if summary["compliance_rate"] >= 90:
        insights.append(
            {
                "icon": "check-circle",
                "title": "Strong attendance compliance",
                "body": f"{summary['compliance_rate']}% of scheduled staff are present today.",
                "tone": "success",
            }
        )
    if not insights:
        insights.append(
            {
                "icon": "sparkles",
                "title": "Schedules look healthy",
                "body": "No major conflicts detected. Consider rotation templates for 24/7 teams.",
                "tone": "success",
            }
        )
    return insights[:6]


def build_charts(org: Organization, users: list[User], filters: ShiftFilters) -> dict[str, Any]:
    user_ids = [u.pk for u in users]
    dept_labels, dept_counts = [], []
    dept_map: dict[str, int] = {}
    for u in users:
        name = u.department_name or "Unassigned"
        dept_map[name] = dept_map.get(name, 0) + 1
    for k, v in sorted(dept_map.items(), key=lambda x: -x[1])[:8]:
        dept_labels.append(k)
        dept_counts.append(v)

    type_labels, type_counts = [], []
    for val, label in WorkShift.ShiftType.choices:
        c = ShiftAssignment.objects.filter(
            organization=org,
            shift__shift_type=val,
            date__gte=filters.date_from,
            date__lte=filters.date_to,
            user_id__in=user_ids,
        ).count()
        if c:
            type_labels.append(label)
            type_counts.append(c)

    ot_by_day = []
    d = filters.date_from
    while d <= filters.date_to:
        mins = (
            OvertimeRecord.objects.filter(organization=org, date=d, user_id__in=user_ids).aggregate(
                s=Sum("minutes")
            )["s"]
            or 0
        )
        ot_by_day.append({"date": d.strftime("%d %b"), "hours": round(mins / 60, 1)})
        d += timedelta(days=1)

    compliance_days = []
    d = filters.date_from
    while d <= filters.date_to and len(compliance_days) < 14:
        scheduled = ShiftAssignment.objects.filter(organization=org, date=d, user_id__in=user_ids).count()
        present = AttendanceRecord.objects.filter(
            user_id__in=user_ids,
            date=d,
            status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.WFH],
        ).count()
        rate = round((present / max(scheduled or len(users), 1)) * 100, 0)
        compliance_days.append({"date": d.strftime("%a"), "rate": rate})
        d += timedelta(days=1)

    return {
        "department": {"labels": dept_labels, "values": dept_counts},
        "shiftTypes": {"labels": type_labels, "values": type_counts},
        "overtimeTrend": ot_by_day,
        "compliance": compliance_days,
        "utilization": {
            "labels": ["Scheduled", "Open slots"],
            "values": [
                ShiftAssignment.objects.filter(
                    organization=org,
                    date__gte=filters.date_from,
                    date__lte=filters.date_to,
                    user_id__in=user_ids,
                ).count(),
                max(len(users) * ((filters.date_to - filters.date_from).days + 1), 1),
            ],
        },
    }


def table_rows(org: Organization, users: list[User], filters: ShiftFilters) -> list[dict]:
    rows = []
    d = filters.date_from
    while d <= filters.date_to:
        for user in users:
            assign = ShiftAssignment.objects.filter(user=user, date=d).select_related("shift").first()
            shift = assign.shift if assign else get_effective_shift(user)
            record = AttendanceRecord.objects.filter(user=user, date=d).first()
            late = analyze_lateness(record, shift, d) if record and shift else {}
            rows.append(
                {
                    "employee_id": user.employee_id or "—",
                    "employee_name": user.display_name,
                    "department": user.department_name or "—",
                    "shift_name": shift.name if shift else "—",
                    "shift_type": shift.get_shift_type_display() if shift else "—",
                    "shift_timing": shift.time_range_display if shift else "—",
                    "working_hours": shift.working_hours_display if shift else "—",
                    "attendance_status": record.get_status_display() if record else "—",
                    "overtime": "—",
                    "late_by": late.get("label", "—") if late else "—",
                    "weekly_off": shift.weekly_off_days if shift else "",
                    "schedule_status": assign.get_status_display() if assign else "Default",
                    "date": d.isoformat(),
                }
            )
        d += timedelta(days=1)
    return rows


def export_schedule_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Date",
            "Employee ID",
            "Name",
            "Department",
            "Shift",
            "Type",
            "Timing",
            "Hours",
            "Attendance",
            "Late",
            "Status",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["date"],
                r["employee_id"],
                r["employee_name"],
                r["department"],
                r["shift_name"],
                r["shift_type"],
                r["shift_timing"],
                r["working_hours"],
                r["attendance_status"],
                r["late_by"],
                r["schedule_status"],
            ]
        )
    return buf.getvalue().encode("utf-8")
