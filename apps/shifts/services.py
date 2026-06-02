"""Shift scheduling business logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for, org_active_users
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, WorkShift
from apps.dashboard.attendance_utils import analyze_lateness, compute_working_hours, get_effective_shift
from apps.organizations.models import Organization
from apps.shifts.models import OvertimeRecord, ShiftAssignment, ShiftRotation, ShiftSwapRequest


@dataclass
class ShiftFilters:
    branch: str = ""
    department: str = ""
    team: str = ""
    employee: str = ""
    shift_type: str = ""
    status: str = ""
    date_from: date | None = None
    date_to: date | None = None
    calendar_view: str = "weekly"

    @classmethod
    def from_request(cls, request) -> ShiftFilters:
        g = request.GET
        today = timezone.localdate()
        df = g.get("from") or str(today - timedelta(days=today.weekday()))
        dt = g.get("to") or str(today + timedelta(days=6 - today.weekday()))
        try:
            date_from = date.fromisoformat(df)
        except ValueError:
            date_from = today - timedelta(days=today.weekday())
        try:
            date_to = date.fromisoformat(dt)
        except ValueError:
            date_to = date_from + timedelta(days=6)
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        return cls(
            branch=(g.get("branch") or "").strip(),
            department=(g.get("department") or "").strip(),
            team=(g.get("team") or "").strip(),
            employee=(g.get("employee") or "").strip(),
            shift_type=(g.get("shift_type") or "").strip(),
            status=(g.get("status") or "").strip(),
            date_from=date_from,
            date_to=date_to,
            calendar_view=(g.get("view") or "weekly").strip(),
        )


def schedulable_users(viewer: User) -> list[User]:
    if not viewer.organization_id:
        return []
    org = viewer.organization
    if viewer.role == User.Role.ADMIN:
        qs = org_active_users(org).filter(role__in=[User.Role.HR, User.Role.EMPLOYEE])
    elif viewer.role == User.Role.HR:
        qs = attendance_team_for(viewer)
    else:
        qs = User.objects.filter(pk=viewer.pk, is_active=True)
    return list(qs.select_related("department", "work_shift").order_by("first_name", "last_name"))


def apply_user_filters(users: list[User], filters: ShiftFilters) -> list[User]:
    out = users
    if filters.department:
        out = [u for u in out if str(u.department_id) == filters.department]
    if filters.branch:
        out = [u for u in out if (u.work_location or "").lower() == filters.branch.lower()]
    if filters.employee:
        out = [u for u in out if str(u.pk) == filters.employee]
    if filters.team:
        from apps.orgchart.models import TeamMembership

        ids = set(
            TeamMembership.objects.filter(team_id=filters.team).values_list("user_id", flat=True)
        )
        out = [u for u in out if u.pk in ids]
    return out


def get_assignment_for_user_date(user: User, on_date: date) -> ShiftAssignment | None:
    return (
        ShiftAssignment.objects.filter(user=user, date=on_date)
        .select_related("shift")
        .first()
    )


def effective_shift_for_date(user: User, on_date: date) -> WorkShift | None:
    assignment = get_assignment_for_user_date(user, on_date)
    if assignment:
        return assignment.shift
    return get_effective_shift(user)


@transaction.atomic
def bulk_assign_shift(
    *,
    organization: Organization,
    users: list[User],
    shift: WorkShift,
    on_date: date,
    assigned_by: User,
    notes: str = "",
) -> int:
    count = 0
    for user in users:
        obj, _ = ShiftAssignment.objects.update_or_create(
            user=user,
            date=on_date,
            defaults={
                "organization": organization,
                "shift": shift,
                "status": ShiftAssignment.Status.SCHEDULED,
                "assigned_by": assigned_by,
                "notes": notes,
            },
        )
        count += 1
    return count


def detect_conflicts(user: User, on_date: date, shift: WorkShift) -> list[str]:
    warnings: list[str] = []
    leave = AttendanceRecord.objects.filter(
        user=user, date=on_date, status=AttendanceRecord.Status.LEAVE
    ).exists()
    if leave:
        warnings.append("Employee is on leave this day.")
    prev = on_date - timedelta(days=1)
    prev_assign = get_assignment_for_user_date(user, prev)
    if prev_assign and prev_assign.shift.crosses_midnight:
        warnings.append("Previous day night shift may overlap rest period.")
    return warnings


@transaction.atomic
def auto_schedule_week(
    *,
    organization: Organization,
    users: list[User],
    week_start: date,
    assigned_by: User,
) -> int:
    """Assign each user their default/effective shift for Mon–Fri."""
    shifts = list(WorkShift.objects.filter(organization=organization, is_active=True))
    if not shifts:
        return 0
    default = next((s for s in shifts if s.is_default), shifts[0])
    count = 0
    for user in users:
        shift = get_effective_shift(user) or default
        for offset in range(7):
            d = week_start + timedelta(days=offset)
            if shift.weekly_off_days and str(d.weekday()) in shift.weekly_off_days.split(","):
                continue
            ShiftAssignment.objects.update_or_create(
                user=user,
                date=d,
                defaults={
                    "organization": organization,
                    "shift": shift,
                    "status": ShiftAssignment.Status.SCHEDULED,
                    "assigned_by": assigned_by,
                },
            )
            count += 1
    return count


@transaction.atomic
def apply_rotation(
    rotation: ShiftRotation,
    users: list[User],
    start_date: date,
    days: int,
) -> int:
    steps = list(rotation.steps.select_related("shift").order_by("step_order"))
    if not steps:
        return 0
    count = 0
    for user in users:
        for i in range(days):
            d = start_date + timedelta(days=i)
            step = steps[i % len(steps)]
            ShiftAssignment.objects.update_or_create(
                user=user,
                date=d,
                defaults={
                    "organization": rotation.organization,
                    "shift": step.shift,
                    "status": ShiftAssignment.Status.SCHEDULED,
                },
            )
            count += 1
    return count


@transaction.atomic
def approve_swap(swap: ShiftSwapRequest, reviewer: User) -> None:
    swap.status = ShiftSwapRequest.Status.APPROVED
    swap.reviewed_by = reviewer
    swap.reviewed_at = timezone.now()
    swap.save()
    ShiftAssignment.objects.update_or_create(
        user=swap.requester,
        date=swap.date,
        defaults={
            "organization": swap.organization,
            "shift": swap.requested_shift,
            "status": ShiftAssignment.Status.CONFIRMED,
            "assigned_by": reviewer,
        },
    )
    if swap.swap_with_id:
        ShiftAssignment.objects.update_or_create(
            user=swap.swap_with,
            date=swap.date,
            defaults={
                "organization": swap.organization,
                "shift": swap.current_shift,
                "status": ShiftAssignment.Status.CONFIRMED,
                "assigned_by": reviewer,
            },
        )


def clone_shift(shift: WorkShift) -> WorkShift:
    return WorkShift.objects.create(
        organization=shift.organization,
        name=f"{shift.name} (Copy)",
        shift_code=f"{shift.shift_code}-copy"[:20] if shift.shift_code else "",
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        break_minutes=shift.break_minutes,
        grace_minutes=shift.grace_minutes,
        weekly_off_days=shift.weekly_off_days,
        color=shift.color,
        description=shift.description,
        branch=shift.branch,
        night_allowance_percent=shift.night_allowance_percent,
        is_active=True,
        is_default=False,
    )


def sync_overtime_from_attendance(user: User, on_date: date) -> OvertimeRecord | None:
    from apps.dashboard.attendance_analytics import compute_overtime_minutes

    record = AttendanceRecord.objects.filter(user=user, date=on_date).first()
    shift = effective_shift_for_date(user, on_date)
    mins = compute_overtime_minutes(record, shift)
    if mins <= 0:
        return None
    ot, _ = OvertimeRecord.objects.update_or_create(
        user=user,
        date=on_date,
        defaults={
            "organization": user.organization,
            "minutes": mins,
            "status": OvertimeRecord.Status.PENDING,
        },
    )
    return ot


def build_weekly_grid(users: list[User], week_start: date) -> dict:
    days = [week_start + timedelta(days=i) for i in range(7)]
    rows = []
    for user in users:
        cells = []
        for d in days:
            assign = get_assignment_for_user_date(user, d)
            shift = assign.shift if assign else get_effective_shift(user)
            cells.append(
                {
                    "date": d.isoformat(),
                    "shift_id": str(shift.pk) if shift else None,
                    "shift_name": shift.name if shift else "—",
                    "shift_type": shift.shift_type if shift else "",
                    "color": shift.color if shift else "#64748b",
                    "assignment_id": str(assign.pk) if assign else None,
                }
            )
        rows.append(
            {
                "user_id": str(user.pk),
                "name": user.display_name,
                "employee_id": user.employee_id or "",
                "department": user.department_name,
                "cells": cells,
            }
        )
    return {"week_start": week_start.isoformat(), "days": [d.isoformat() for d in days], "rows": rows}
