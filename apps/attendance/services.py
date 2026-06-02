"""Attendance regularization and employee summary helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest

from apps.dashboard.attendance_analytics import compute_overtime_minutes, record_working_minutes
from apps.dashboard.attendance_utils import (
    analyze_lateness,
    combine_date_and_time,
    get_effective_shift,
)


def submit_regularization(
    user: User,
    *,
    on_date,
    reason: str,
    requested_check_in=None,
    requested_check_out=None,
    requested_status: str = "",
) -> AttendanceRegularizationRequest:
    if not reason.strip():
        raise ValueError("Please provide a reason for the correction request.")
    if not requested_check_in and not requested_check_out and not requested_status:
        raise ValueError("Enter at least a check-in time, check-out time, or status.")

    pending = AttendanceRegularizationRequest.objects.filter(
        user=user,
        date=on_date,
        status=AttendanceRegularizationRequest.Status.PENDING,
    ).exists()
    if pending:
        raise ValueError("You already have a pending correction request for this date.")

    return AttendanceRegularizationRequest.objects.create(
        user=user,
        date=on_date,
        requested_check_in=requested_check_in,
        requested_check_out=requested_check_out,
        requested_status=requested_status or "",
        reason=reason.strip(),
    )


def _can_review_request(reviewer: User, req: AttendanceRegularizationRequest) -> bool:
    from apps.accounts.hierarchy import can_review_attendance_corrections

    if not can_review_attendance_corrections(reviewer):
        return False
    if reviewer.role == User.Role.ADMIN:
        return req.user.organization_id == reviewer.organization_id
    if reviewer.role == User.Role.HR:
        emp = req.user
        return emp.organization_id == reviewer.organization_id and (
            emp.role == User.Role.EMPLOYEE and emp.assigned_hr_id == reviewer.pk
            or emp.pk == reviewer.pk
        )
    return req.user.reporting_manager_id == reviewer.pk


def approve_regularization(reviewer: User, req: AttendanceRegularizationRequest, comment: str = "") -> None:
    if req.status != AttendanceRegularizationRequest.Status.PENDING:
        raise ValueError("This request is no longer pending.")
    if not _can_review_request(reviewer, req):
        raise ValueError("You cannot approve this request.")

    record, _ = AttendanceRecord.objects.get_or_create(
        user=req.user,
        date=req.date,
        defaults={"status": AttendanceRecord.Status.PRESENT},
    )
    update_fields = ["updated_at"]
    if req.requested_check_in:
        record.check_in = combine_date_and_time(req.date, req.requested_check_in.strftime("%H:%M"))
        record.status = AttendanceRecord.Status.PRESENT
        update_fields.extend(["check_in", "status"])
    if req.requested_check_out:
        record.check_out = combine_date_and_time(req.date, req.requested_check_out.strftime("%H:%M"))
        update_fields.append("check_out")
    if req.requested_status:
        record.status = req.requested_status
        update_fields.append("status")
    record.save(update_fields=list(dict.fromkeys(update_fields)))

    req.status = AttendanceRegularizationRequest.Status.APPROVED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.review_comment = comment.strip()
    req.applied_at = timezone.now()
    req.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_comment",
            "applied_at",
            "updated_at",
        ]
    )


def reject_regularization(reviewer: User, req: AttendanceRegularizationRequest, comment: str = "") -> None:
    if req.status != AttendanceRegularizationRequest.Status.PENDING:
        raise ValueError("This request is no longer pending.")
    if not _can_review_request(reviewer, req):
        raise ValueError("You cannot reject this request.")

    req.status = AttendanceRegularizationRequest.Status.REJECTED
    req.reviewed_by = reviewer
    req.reviewed_at = timezone.now()
    req.review_comment = comment.strip()
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_comment", "updated_at"])


def pending_corrections_for(reviewer: User):
    from apps.accounts.hierarchy import correction_requests_for_reviewer

    return correction_requests_for_reviewer(reviewer).filter(
        status=AttendanceRegularizationRequest.Status.PENDING,
    )


def build_employee_attendance_stats(user: User, date_from, date_to) -> dict:
    records = list(
        AttendanceRecord.objects.filter(user=user, date__gte=date_from, date__lte=date_to)
    )
    present = absent = late = leave = wfh = half_day = 0
    total_work_mins = 0
    total_ot_mins = 0

    for rec in records:
        if rec.status == AttendanceRecord.Status.PRESENT:
            present += 1
        elif rec.status == AttendanceRecord.Status.ABSENT:
            absent += 1
        elif rec.status == AttendanceRecord.Status.LEAVE:
            leave += 1
        elif rec.status == AttendanceRecord.Status.WFH:
            wfh += 1
        elif rec.status == AttendanceRecord.Status.HALF_DAY:
            half_day += 1

        shift = get_effective_shift(user)
        lateness = analyze_lateness(rec, shift, rec.date)
        if lateness.get("is_late"):
            late += 1
        total_work_mins += record_working_minutes(rec)
        total_ot_mins += compute_overtime_minutes(rec, shift)

    from apps.dashboard.attendance_utils import format_total_minutes

    org = user.organization
    if org:
        from apps.attendance.work_calendar import count_working_days

        total_days = max(
            count_working_days(org, date_from, date_to, user=user, branch=user.work_location or ""),
            1,
        )
    else:
        total_days = max((date_to - date_from).days + 1, 1)
    marked = present + absent + leave + wfh + half_day
    on_time = max(present - late, 0)
    attendance_rate = round(((present + wfh + half_day * 0.5) / total_days) * 100, 1)
    punctuality_rate = round((on_time / max(present, 1)) * 100, 1) if present else 0.0
    late_rate = round((late / max(present, 1)) * 100, 1) if present else 0.0

    return {
        "present": present,
        "absent": absent,
        "late": late,
        "leave": leave,
        "wfh": wfh,
        "half_day": half_day,
        "working_hours": format_total_minutes(total_work_mins),
        "overtime": format_total_minutes(total_ot_mins),
        "total_days": total_days,
        "marked_days": marked,
        "on_time": on_time,
        "attendance_rate": attendance_rate,
        "punctuality_rate": punctuality_rate,
        "late_rate": late_rate,
    }


def period_bounds(anchor_date, period: str) -> tuple:
    if period == "week":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end = start + timedelta(days=6)
        return start, end
    if period == "month":
        start = anchor_date.replace(day=1)
        if anchor_date.month == 12:
            end = anchor_date.replace(day=31)
        else:
            end = (anchor_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return start, end
    return anchor_date, anchor_date
