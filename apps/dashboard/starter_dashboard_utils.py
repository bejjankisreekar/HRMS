"""Data aggregation for the Starter Plan organization admin dashboard."""

from __future__ import annotations

import calendar
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.leaves.models import LeaveRequest
from apps.organizations.models import Department, Organization
from apps.payroll.models import PayrollRun

from .attendance_utils import enrich_attendance_row, get_team_attendance_rows, summarize_team_rows


def _month_range(months: int = 6):
    today = timezone.localdate()
    result = []
    y, m = today.year, today.month
    for _ in range(months):
        result.append((y, m))
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return list(reversed(result))


def get_starter_dashboard_context(admin: User) -> dict:
    org: Organization | None = admin.organization
    if not org:
        return {"empty_org": True}

    today = timezone.localdate()
    month_start = today.replace(day=1)

    org_users = User.objects.filter(organization=org).exclude(role=User.Role.SUPER_ADMIN)
    employees_qs = org_users.filter(role=User.Role.EMPLOYEE, is_active=True)
    total_employees = employees_qs.count()

    team_rows = get_team_attendance_rows(admin, today)
    att = summarize_team_rows(team_rows)
    present_today = att.get("present", 0)
    on_leave = att.get("leave", 0)

    pending_leave = 0
    if org.leave_management_enabled:
        pending_leave = LeaveRequest.objects.filter(
            user__organization=org,
            status=LeaveRequest.Status.PENDING,
        ).count()

    pending_requests = pending_leave

    monthly_payroll = Decimal("0")
    payroll_label = "Not processed"
    if org.payroll_enabled:
        run = PayrollRun.objects.filter(organization=org, year=today.year, month=today.month).first()
        if run:
            monthly_payroll = run.total_net
            payroll_label = run.get_status_display()
        else:
            payroll_label = "No run yet"

    kpis = {
        "total_employees": total_employees,
        "present_today": present_today,
        "on_leave": on_leave,
        "pending_requests": pending_requests,
        "monthly_payroll": monthly_payroll,
        "monthly_payroll_display": f"₹{monthly_payroll:,.0f}" if monthly_payroll else "—",
        "payroll_label": payroll_label,
        "attendance_rate": round((present_today / total_employees) * 100) if total_employees else 0,
    }

    # Attendance pie (today)
    wfh_count = half_count = 0
    for row in team_rows:
        record = row.get("record")
        if record:
            if record.status == AttendanceRecord.Status.WFH:
                wfh_count += 1
            elif record.status == AttendanceRecord.Status.HALF_DAY:
                half_count += 1

    attendance_chart = {
        "labels": ["Present", "Absent", "On leave", "WFH / Other"],
        "values": [
            att.get("present", 0),
            att.get("absent", 0),
            att.get("leave", 0),
            wfh_count + half_count + att.get("other", 0),
        ],
    }

    # Department distribution
    dept_rows = list(
        Department.objects.filter(organization=org, is_active=True)
        .annotate(
            headcount=Count(
                "members",
                filter=Q(members__role=User.Role.EMPLOYEE, members__is_active=True),
            )
        )
        .order_by("-headcount", "name")[:8]
    )
    unassigned = employees_qs.filter(department__isnull=True).count()
    dept_labels = [d.name for d in dept_rows]
    dept_values = [d.headcount for d in dept_rows]
    if unassigned:
        dept_labels.append("Unassigned")
        dept_values.append(unassigned)

    department_chart = {"labels": dept_labels or ["No departments"], "values": dept_values or [0]}

    # Payroll bar — last 6 months
    months = _month_range(6)
    payroll_labels = [calendar.month_abbr[m] for _, m in months]
    payroll_values = []
    for y, m in months:
        run = PayrollRun.objects.filter(organization=org, year=y, month=m).first()
        payroll_values.append(float(run.total_net) if run else 0)

    payroll_chart = {"labels": payroll_labels, "values": payroll_values}

    # Leave trends — requests per month (last 6 months)
    six_months_ago = today - timedelta(days=180)
    leave_by_month = (
        LeaveRequest.objects.filter(user__organization=org, applied_at__date__gte=six_months_ago)
        .annotate(month=TruncMonth("applied_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    leave_map = {}
    for row in leave_by_month:
        if row["month"]:
            leave_map[(row["month"].year, row["month"].month)] = row["count"]
    leave_labels = payroll_labels[:]
    leave_values = [leave_map.get((y, m), 0) for y, m in months]

    leave_chart = {"labels": leave_labels, "values": leave_values}

    # Employee growth — cumulative by month
    growth_values = []
    for y, m in months:
        end = today.replace(year=y, month=m, day=calendar.monthrange(y, m)[1])
        count = org_users.filter(
            role=User.Role.EMPLOYEE,
            is_active=True,
            date_joined__date__lte=end,
        ).count()
        growth_values.append(count)

    growth_chart = {"labels": payroll_labels, "values": growth_values}

    # Employee overview table
    employee_rows = []
    for row in team_rows[:12]:
        member = row.get("member")
        if not member:
            continue
        record = row.get("record")
        status = record.get_status_display() if record else "Unmarked"
        status_code = record.status if record else ""
        employee_rows.append(
            {
                "id": str(member.pk),
                "name": member.display_name,
                "department": member.department_name or "—",
                "status": "Active" if member.is_active else "Inactive",
                "attendance": status,
                "attendance_class": _attendance_class(status_code),
            }
        )

    # Activity feed
    activities = []

    for u in org_users.order_by("-date_joined")[:3]:
        activities.append(
            {
                "type": "employee",
                "icon": "user-plus",
                "color": "violet",
                "title": f"{u.display_name} joined the team",
                "meta": u.get_role_display(),
                "time": u.date_joined,
            }
        )

    if org.leave_management_enabled:
        for req in (
            LeaveRequest.objects.filter(user__organization=org)
            .select_related("user", "leave_type")
            .order_by("-applied_at")[:4]
        ):
            activities.append(
                {
                    "type": "leave",
                    "icon": "palmtree",
                    "color": "amber",
                    "title": f"{req.user.display_name} — {req.leave_type.name} request",
                    "meta": req.get_status_display(),
                    "time": req.applied_at,
                }
            )

    if att.get("unmarked", 0):
        activities.append(
            {
                "type": "attendance",
                "icon": "alert-circle",
                "color": "rose",
                "title": f"{att['unmarked']} employee(s) unmarked for today",
                "meta": "Attendance",
                "time": timezone.now(),
            }
        )

    for run in PayrollRun.objects.filter(organization=org).order_by("-created_at")[:2]:
        activities.append(
            {
                "type": "payroll",
                "icon": "wallet",
                "color": "emerald",
                "title": f"Payroll {run.period_label} — {run.get_status_display()}",
                "meta": f"₹{run.total_net:,.0f} net" if run.total_net else "Draft",
                "time": run.created_at,
            }
        )

    activities.sort(key=lambda a: a["time"], reverse=True)
    activities = activities[:8]

    charts = {
        "attendance": attendance_chart,
        "departments": department_chart,
        "payroll": payroll_chart,
        "leave": leave_chart,
        "growth": growth_chart,
    }

    return {
        "organization": org,
        "today": today,
        "kpis": kpis,
        "charts": charts,
        "employee_rows": employee_rows,
        "activities": activities,
        "has_employees": total_employees > 0,
        "has_payroll_data": any(v > 0 for v in payroll_values),
        "has_leave_data": any(v > 0 for v in leave_values),
        "has_activities": bool(activities),
        "features": {
            "leave_enabled": org.leave_management_enabled,
            "payroll_enabled": org.payroll_enabled,
        },
        "plan_label": "Starter",
    }


def _attendance_class(status: str | None) -> str:
    mapping = {
        "PRESENT": "present",
        "ABSENT": "absent",
        "LEAVE": "leave",
        "WFH": "wfh",
        "HALF_DAY": "half",
    }
    return mapping.get(status or "", "neutral")
