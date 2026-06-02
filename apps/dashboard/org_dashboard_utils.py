"""Live metrics for the organization admin dashboard."""

from __future__ import annotations

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import WorkShift
from apps.organizations.models import Department, Organization

from .attendance_utils import get_team_attendance_rows, summarize_team_rows


def get_org_admin_dashboard_data(admin: User) -> dict:
    org: Organization | None = admin.organization
    if not org:
        return {}

    today = timezone.localdate()
    month_start = today.replace(day=1)

    org_users = User.objects.filter(organization=org).exclude(role=User.Role.SUPER_ADMIN)
    active = org_users.filter(is_active=True)

    employees_qs = active.filter(role=User.Role.EMPLOYEE)
    staff_stats = {
        "employees": employees_qs.count(),
        "hr": active.filter(role=User.Role.HR).count(),
        "admins": active.filter(role=User.Role.ADMIN).count(),
        "total_active": active.count(),
        "inactive": org_users.filter(is_active=False).count(),
        "unassigned_hr": employees_qs.filter(assigned_hr__isnull=True).count(),
        "joined_this_month": org_users.filter(date_joined__date__gte=month_start).count(),
    }

    team_rows = get_team_attendance_rows(admin, today)
    today_attendance = summarize_team_rows(team_rows)
    today_attendance["date"] = today
    total = today_attendance["total"] or 0
    marked = total - today_attendance["unmarked"]
    today_attendance["marked"] = marked
    if total:
        today_attendance["present_pct"] = round((today_attendance["present"] / total) * 100)
    else:
        today_attendance["present_pct"] = 0

    shifts = WorkShift.objects.filter(organization=org)
    shift_stats = {
        "count": shifts.count(),
        "default": shifts.filter(is_default=True).first(),
        "unassigned_shift": employees_qs.filter(work_shift__isnull=True).count(),
    }

    department_breakdown = list(
        Department.objects.filter(organization=org, is_active=True)
        .annotate(
            count=Count(
                "members",
                filter=Q(members__role=User.Role.EMPLOYEE, members__is_active=True),
            )
        )
        .order_by("-count", "name")[:8]
    )

    recent_members = list(
        org_users.select_related("work_shift", "assigned_hr", "reporting_manager").order_by(
            "-date_joined"
        )[:6]
    )

    return {
        "organization": org,
        "staff": staff_stats,
        "today_attendance": today_attendance,
        "shifts": shift_stats,
        "department_breakdown": department_breakdown,
        "dept_label_plural": org.department_label_plural,
        "recent_members": recent_members,
        "features": {
            "leave_enabled": org.leave_management_enabled,
            "payroll_enabled": org.payroll_enabled,
            "payroll_cycle": org.get_payroll_cycle_display() if org.payroll_cycle else "",
        },
    }
