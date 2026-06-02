"""Employee self-service dashboard context."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.accounts.hierarchy import org_active_users, tree_users_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
from apps.attendance.services import build_employee_attendance_stats, period_bounds
from apps.dashboard.attendance_utils import (
    enrich_attendance_row,
    format_total_minutes,
    get_effective_shift,
    shift_timing_info,
)
from apps.dashboard.notification_service import get_user_notifications
from apps.leaves.models import Holiday, LeaveBalance, LeaveRequest
from apps.leaves.services import ensure_balances_for_user
from apps.lifecycle.models import EmployeeDocument, OnboardingTask
from apps.orgchart.services import employee_focus_context, user_team_name
from apps.payroll.models import Payslip, Reimbursement
from apps.payroll.services import get_active_salary


def _greeting(now=None) -> str:
    now = now or timezone.localtime()
    hour = now.hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _years_of_service(user: User, today: date) -> str:
    start = user.date_of_joining or (user.date_joined.date() if user.date_joined else None)
    if not start:
        return "—"
    years = today.year - start.year
    months = today.month - start.month
    if today.day < start.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    if years <= 0:
        return f"{max(months, 1)} mo" if months else "< 1 mo"
    if months:
        return f"{years} yr {months} mo"
    return f"{years} yr"


def _profile_completion(user: User) -> int:
    checks = [
        bool(user.first_name),
        bool(user.last_name),
        bool(user.email),
        bool(user.phone),
        bool(user.profile_picture),
        bool(user.employee_id),
        user.department_id is not None,
        bool(user.designation or user.org_designation_id),
        user.date_of_birth is not None,
        bool(user.emergency_contact_name),
        bool(user.emergency_contact_phone),
        bool(user.address_line or user.city),
        bool(user.bank_account_number),
        bool(user.pan_number),
    ]
    return round((sum(checks) / len(checks)) * 100)


def _count_weekdays(start: date, end: date) -> int:
    """Deprecated helper — use work calendar via org when available."""
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _mini_person(user: User | None) -> dict | None:
    if not user:
        return None
    initials = "".join(p[0].upper() for p in user.display_name.split()[:2]) or "?"
    return {
        "id": str(user.pk),
        "name": user.display_name,
        "employee_id": user.employee_id or "—",
        "designation": user.designation_label or user.get_role_display(),
        "department": user.department_name or "—",
        "initials": initials,
        "avatar": user.profile_picture.url if user.profile_picture else "",
    }


def _attendance_work_status(today_record, today_row: dict) -> dict:
    if not today_record:
        return {
            "label": "Awaiting mark",
            "detail": "HR records attendance",
            "variant": "neutral",
        }
    if today_record.check_in and not today_record.check_out:
        return {
            "label": "Checked In",
            "detail": today_row.get("login_time") or "—",
            "variant": "success",
        }
    if today_record.check_in and today_record.check_out:
        return {
            "label": "Checked Out",
            "detail": today_row.get("logout_time") or "—",
            "variant": "complete",
        }
    if today_row.get("is_marked"):
        return {
            "label": today_record.get_status_display(),
            "detail": today_row.get("login_time") or "",
            "variant": "info",
        }
    return {
        "label": "Awaiting mark",
        "detail": "HR records attendance",
        "variant": "neutral",
    }


def _serialize_leave_balance(balance: LeaveBalance) -> dict:
    lt = balance.leave_type
    remaining = balance.remaining
    total = balance.allocated + balance.carried_forward
    used_pct = 0
    if total > 0:
        used_pct = min(int((balance.used / total) * 100), 100)
    return {
        "name": lt.name,
        "code": lt.code,
        "color": lt.color or "#6366f1",
        "remaining": remaining,
        "remaining_display": f"{remaining:.1f}".rstrip("0").rstrip("."),
        "allocated": total,
        "used": balance.used,
        "used_pct": used_pct,
        "is_paid": lt.is_paid,
    }


def _company_events(user: User, today: date) -> list[dict]:
    """Birthdays and work anniversaries for department colleagues (next 14 days)."""
    events: list[dict] = []
    if not user.organization_id or not user.department_id:
        return events

    colleagues = org_active_users(user.organization).filter(department_id=user.department_id)
    horizon = today + timedelta(days=14)

    for colleague in colleagues[:80]:
        if colleague.date_of_birth:
            try:
                bday = colleague.date_of_birth.replace(year=today.year)
            except ValueError:
                bday = colleague.date_of_birth.replace(year=today.year, day=28)
            if bday < today:
                try:
                    bday = bday.replace(year=today.year + 1)
                except ValueError:
                    bday = bday.replace(year=today.year + 1, day=28)
            if today <= bday <= horizon:
                events.append(
                    {
                        "type": "birthday",
                        "type_label": "Birthday",
                        "name": colleague.display_name,
                        "date": bday,
                        "day": bday.strftime("%A"),
                        "icon": "cake",
                    }
                )

        join = colleague.date_of_joining
        if join and join.month == today.month and join.year < today.year:
            try:
                anniv = join.replace(year=today.year)
            except ValueError:
                anniv = join.replace(year=today.year, day=28)
            if today <= anniv <= horizon:
                years = today.year - join.year
                events.append(
                    {
                        "type": "anniversary",
                        "type_label": f"{years} yr anniversary",
                        "name": colleague.display_name,
                        "date": anniv,
                        "day": anniv.strftime("%A"),
                        "icon": "award",
                    }
                )

    events.sort(key=lambda e: e["date"])
    return events[:8]


def _performance_summary(month_stats: dict) -> dict:
    attendance_pct = float(month_stats.get("attendance_rate") or 0)
    score = min(round(attendance_pct / 20, 1), 5.0)
    goal_pct = min(int(attendance_pct), 100)
    return {
        "score": score,
        "score_display": f"{score}/5",
        "goal_completion": goal_pct,
        "review_status": "Not scheduled",
        "goals": [
            {"label": "Attendance target", "progress": goal_pct, "color": "#6366f1"},
            {"label": "Punctuality", "progress": int(month_stats.get("punctuality_rate") or 0), "color": "#10b981"},
        ],
    }


def _format_currency(amount) -> str:
    if amount is None:
        return "—"
    value = Decimal(str(amount))
    return f"₹{value:,.0f}"


def get_employee_dashboard_context(user: User) -> dict:
    today = timezone.localdate()
    month_start, month_end = period_bounds(today, "month")
    year = today.year

    today_record = AttendanceRecord.objects.filter(user=user, date=today).first()
    shift = get_effective_shift(user)
    today_row = enrich_attendance_row(user, today_record, today)
    month_stats = build_employee_attendance_stats(user, month_start, month_end)
    work_status = _attendance_work_status(today_record, today_row)

    break_mins = int(today_record.break_minutes or 0) if today_record else 0
    break_display = format_total_minutes(break_mins) if break_mins else "—"

    recent = list(AttendanceRecord.objects.filter(user=user).order_by("-date")[:7])
    recent_rows = [enrich_attendance_row(user, rec, rec.date) for rec in recent]

    ensure_balances_for_user(user, year)
    leave_balances_qs = (
        user.leave_balances.filter(year=year)
        .select_related("leave_type")
        .filter(leave_type__is_active=True)
        .order_by("leave_type__sort_order", "leave_type__name")
    )
    leave_balances = [_serialize_leave_balance(b) for b in leave_balances_qs]

    total_leave_remaining = sum(b["remaining"] for b in leave_balances)
    paid_leave_remaining = sum(b["remaining"] for b in leave_balances if b["is_paid"])

    pending_leave = LeaveRequest.objects.filter(
        user=user,
        status=LeaveRequest.Status.PENDING,
    ).count()

    pending_corrections = AttendanceRegularizationRequest.objects.filter(
        user=user,
        status=AttendanceRegularizationRequest.Status.PENDING,
    ).count()

    pending_leave_requests = list(
        LeaveRequest.objects.filter(user=user, status=LeaveRequest.Status.PENDING)
        .select_related("leave_type")
        .order_by("-applied_at")[:3]
    )
    upcoming_leaves = list(
        LeaveRequest.objects.filter(
            user=user,
            status=LeaveRequest.Status.APPROVED,
            end_date__gte=today,
        )
        .select_related("leave_type")
        .order_by("start_date")[:3]
    )

    org = user.organization
    upcoming_holidays = []
    if org:
        upcoming_holidays = list(
            Holiday.objects.filter(organization=org, date__gte=today)
            .order_by("date")[:5]
        )

    upcoming_holiday_count = 0
    if org:
        upcoming_holiday_count = Holiday.objects.filter(
            organization=org,
            date__gte=today,
            date__lte=month_end,
        ).count()

    latest_payslip = (
        Payslip.objects.filter(user=user)
        .select_related("payroll_run")
        .order_by("-payroll_run__year", "-payroll_run__month")
        .first()
    )
    active_salary = get_active_salary(user)

    expense_pending = Reimbursement.objects.filter(
        user=user, status=Reimbursement.Status.PENDING
    ).count()
    expense_approved = Reimbursement.objects.filter(
        user=user, status__in=[Reimbursement.Status.APPROVED, Reimbursement.Status.PAID]
    ).count()
    expense_rejected = Reimbursement.objects.filter(
        user=user, status=Reimbursement.Status.REJECTED
    ).count()

    pending_requests_total = pending_leave + pending_corrections + expense_pending

    users = list(tree_users_for(user))
    team = employee_focus_context(user, users)

    department_info = {
        "name": user.department_name or "—",
        "team_name": user_team_name(user) or "—",
        "member_count": 0,
    }
    if org and user.department_id:
        department_info["member_count"] = org_active_users(org).filter(
            department_id=user.department_id
        ).count()

    my_tasks = list(
        OnboardingTask.objects.filter(
            Q(assigned_to=user) | Q(onboarding__user=user),
            status__in=[OnboardingTask.Status.PENDING, OnboardingTask.Status.IN_PROGRESS],
        )
        .select_related("onboarding")
        .order_by("due_date", "-priority")[:6]
    )
    pending_tasks = sum(1 for t in my_tasks if t.status == OnboardingTask.Status.PENDING)

    my_documents = list(
        EmployeeDocument.objects.filter(onboarding__user=user)
        .exclude(file="")
        .order_by("-uploaded_at")[:8]
    )

    announcements = get_user_notifications(user, sync=True)[:6]

    company_events = _company_events(user, today)

    performance = _performance_summary(month_stats)
    if org:
        from apps.attendance.work_calendar import count_working_days

        working_days_month = count_working_days(
            org,
            month_start,
            min(today, month_end),
            user=user,
            branch=user.work_location or "",
        )
    else:
        working_days_month = _count_weekdays(month_start, min(today, month_end))

    manager = _mini_person(user.reporting_manager)
    profile_picture_url = user.profile_picture.url if user.profile_picture else ""

    last_login_display = "—"
    if user.last_login:
        last_login_display = timezone.localtime(user.last_login).strftime("%d %b %Y, %I:%M %p").lstrip("0")

    payroll_status = "—"
    if latest_payslip:
        payroll_status = latest_payslip.get_payment_status_display()

    ring_circ = round(2 * 3.14159 * 34, 1)
    ring_dash = round(ring_circ * _profile_completion(user) / 100, 1)

    return {
        "greeting": _greeting(),
        "profile_ring_circ": ring_circ,
        "profile_ring_dash": ring_dash,
        "today": today,
        "month_start": month_start,
        "month_end": month_end,
        "today_record": today_record,
        "today_row": today_row,
        "work_status": work_status,
        "break_display": break_display,
        "my_shift_timing": shift_timing_info(shift),
        "month_stats": month_stats,
        "recent_rows": recent_rows,
        "display_name": user.display_name,
        "employee_id": user.employee_id or "—",
        "designation_label": user.designation_label or "—",
        "department_name": user.department_name or "—",
        "profile_picture_url": profile_picture_url,
        "profile_initials": "".join(p[0].upper() for p in user.display_name.split()[:2]) or "?",
        "manager": manager,
        "years_of_service": _years_of_service(user, today),
        "profile_completion": _profile_completion(user),
        "emergency_contact": {
            "name": user.emergency_contact_name or "—",
            "phone": user.emergency_contact_phone or "—",
            "relation": user.emergency_contact_relation or "",
        },
        "last_login_display": last_login_display,
        "account_status": user.get_employment_status_display(),
        "kpi": {
            "attendance_rate": month_stats["attendance_rate"],
            "leave_balance": total_leave_remaining,
            "leave_balance_display": f"{total_leave_remaining:.1f}".rstrip("0").rstrip("."),
            "paid_leaves_remaining": paid_leave_remaining,
            "paid_leaves_display": f"{paid_leave_remaining:.1f}".rstrip("0").rstrip("."),
            "working_days": working_days_month,
            "pending_requests": pending_requests_total,
            "upcoming_holidays": upcoming_holiday_count,
            "performance_score": performance["score_display"],
            "years_of_service": _years_of_service(user, today),
        },
        "leave_balances": leave_balances,
        "pending_leave": pending_leave,
        "pending_corrections": pending_corrections,
        "pending_leave_requests": pending_leave_requests,
        "upcoming_leaves": upcoming_leaves,
        "upcoming_holidays": upcoming_holidays,
        "latest_payslip": latest_payslip,
        "active_salary": active_salary,
        "salary_display": _format_currency(active_salary.monthly_ctc if active_salary else None),
        "payroll_status": payroll_status,
        "expense_summary": {
            "pending": expense_pending,
            "approved": expense_approved,
            "rejected": expense_rejected,
        },
        "team": team,
        "department_info": department_info,
        "my_tasks": my_tasks,
        "pending_tasks": pending_tasks,
        "my_documents": my_documents,
        "announcements": announcements,
        "company_events": company_events,
        "performance": performance,
        "helpdesk_available": False,
        "training_available": False,
    }
