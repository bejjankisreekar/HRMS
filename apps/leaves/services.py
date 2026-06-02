"""Leave business logic: types, balances, days calculation, approvals."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for
from apps.accounts.models import User
from apps.organizations.models import Organization

from .approval_policy import build_approval_chain_steps
from .models import Holiday, LeaveApproval, LeaveBalance, LeaveRequest, LeaveType
from .notifications import dismiss_leave_notifications, notify_leave_next_approver, notify_leave_submitted

# code, name, color, annual_days, carry_forward, gender, is_paid
DEFAULT_LEAVE_TYPES = [
    ("sick-leave", "Sick Leave", "#f87171", "12", False, "ALL", True),
    ("casual-leave", "Casual Leave", "#38bdf8", "12", False, "ALL", True),
    ("earned-leave", "Earned Leave", "#2dd4bf", "15", True, "ALL", True),
    ("annual-leave", "Annual Leave", "#0ea5e9", "18", True, "ALL", True),
    ("maternity-leave", "Maternity Leave", "#f472b6", "180", False, "FEMALE", True),
    ("paternity-leave", "Paternity Leave", "#60a5fa", "15", False, "MALE", True),
    ("work-from-home", "Work From Home", "#5eead4", "24", False, "ALL", True),
    ("comp-off", "Comp-Off", "#14b8a6", "10", False, "ALL", True),
    ("bereavement-leave", "Bereavement Leave", "#94a3b8", "5", False, "ALL", True),
    ("optional-holiday", "Optional Holiday", "#fbbf24", "2", False, "ALL", True),
    ("marriage-leave", "Marriage Leave", "#fb7185", "7", False, "ALL", True),
    ("loss-of-pay", "Loss of Pay (LOP)", "#ef4444", "365", False, "ALL", False),
    ("unpaid-leave", "Unpaid Leave", "#64748b", "30", False, "ALL", False),
]


def _parse_leave_type_row(row: tuple) -> dict:
    return {
        "code": row[0],
        "name": row[1],
        "color": row[2],
        "quota": Decimal(row[3]),
        "carry": row[4] if len(row) > 4 else False,
        "gender": row[5] if len(row) > 5 else LeaveType.GenderEligibility.ALL,
        "is_paid": row[6] if len(row) > 6 else True,
    }


def ensure_leave_types(organization: Organization) -> list[LeaveType]:
    """Create any missing default leave types; do not overwrite existing quotas."""
    result = []
    for i, row in enumerate(DEFAULT_LEAVE_TYPES):
        p = _parse_leave_type_row(row)
        lt, created = LeaveType.objects.get_or_create(
            organization=organization,
            code=p["code"],
            defaults={
                "name": p["name"],
                "color": p["color"],
                "annual_quota": p["quota"],
                "carry_forward_max": Decimal("5") if p["carry"] else Decimal("0"),
                "accrual_monthly": p["carry"],
                "gender_eligibility": p["gender"],
                "is_paid": p["is_paid"],
                "sort_order": i,
                "is_active": True,
            },
        )
        result.append(lt)
    return list(LeaveType.objects.filter(organization=organization, is_active=True).order_by("sort_order"))


def ensure_org_leave_setup(organization: Organization) -> None:
    """Seed all leave types and balances for every active HR/employee in the org."""
    ensure_leave_types(organization)
    staff = User.objects.filter(
        organization=organization,
        is_active=True,
        role__in=[User.Role.HR, User.Role.EMPLOYEE],
    )
    for member in staff:
        ensure_balances_for_user(member)


def leave_team_for(user: User):
    """Users whose leave requests the viewer can see/manage."""
    if user.role == User.Role.ADMIN:
        return User.objects.filter(
            organization=user.organization,
            is_active=True,
            role__in=[User.Role.HR, User.Role.EMPLOYEE],
        ).select_related("department", "reporting_manager")
    if user.role == User.Role.HR:
        return attendance_team_for(user).select_related("department", "reporting_manager")
    return User.objects.filter(pk=user.pk).select_related("department", "reporting_manager")


def get_holidays_between(
    organization: Organization,
    start: date,
    end: date,
    branch: str = "",
) -> set[date]:
    from apps.attendance.work_calendar import get_holidays_between as _wc_holidays

    return _wc_holidays(organization, start, end, branch)


def calculate_leave_days(
    start: date,
    end: date,
    *,
    organization: Organization,
    half_day: str = LeaveRequest.HalfDay.NONE,
    branch: str = "",
    exclude_weekends: bool = True,
    user: User | None = None,
) -> Decimal:
    from apps.attendance.work_calendar import is_working_day

    if end < start:
        return Decimal("0")

    if start == end and half_day != LeaveRequest.HalfDay.NONE:
        if exclude_weekends and not is_working_day(organization, start, user=user, branch=branch):
            return Decimal("0")
        return Decimal("0.5")

    days = Decimal("0")
    holidays = get_holidays_between(organization, start, end, branch) if not exclude_weekends else set()
    current = start
    while current <= end:
        if exclude_weekends:
            if not is_working_day(organization, current, user=user, branch=branch):
                current += timedelta(days=1)
                continue
        elif current in holidays:
            current += timedelta(days=1)
            continue
        days += Decimal("1")
        current += timedelta(days=1)
    return days


def _allocated_for_type(leave_type: LeaveType) -> Decimal:
    if leave_type.annual_quota is None:
        return Decimal("0")
    return leave_type.annual_quota


def ensure_balances_for_user(user: User, year: int | None = None) -> None:
    year = year or timezone.localdate().year
    if not user.organization_id:
        return
    for lt in LeaveType.objects.filter(organization=user.organization, is_active=True):
        if lt.gender_eligibility != LeaveType.GenderEligibility.ALL:
            if lt.gender_eligibility == LeaveType.GenderEligibility.MALE and user.gender != User.Gender.MALE:
                continue
            if lt.gender_eligibility == LeaveType.GenderEligibility.FEMALE and user.gender != User.Gender.FEMALE:
                continue
        LeaveBalance.objects.get_or_create(
            user=user,
            leave_type=lt,
            year=year,
            defaults={"allocated": _allocated_for_type(lt)},
        )


def sync_org_staff_balances(organization: Organization, leave_type: LeaveType | None = None) -> None:
    """Create/update balance rows for all HR/employees when policies are added."""
    year = timezone.localdate().year
    staff = User.objects.filter(
        organization=organization,
        is_active=True,
        role__in=[User.Role.HR, User.Role.EMPLOYEE],
    )
    types = [leave_type] if leave_type else LeaveType.objects.filter(organization=organization, is_active=True)
    for member in staff:
        for lt in types:
            bal, created = LeaveBalance.objects.get_or_create(
                user=member,
                leave_type=lt,
                year=year,
                defaults={"allocated": _allocated_for_type(lt)},
            )
            if not created and leave_type and leave_type.annual_quota is not None:
                bal.allocated = leave_type.annual_quota
                bal.save(update_fields=["allocated"])


def get_balance(user: User, leave_type: LeaveType, year: int | None = None) -> LeaveBalance:
    year = year or timezone.localdate().year
    ensure_balances_for_user(user, year)
    bal, _ = LeaveBalance.objects.get_or_create(
        user=user,
        leave_type=leave_type,
        year=year,
        defaults={"allocated": _allocated_for_type(leave_type)},
    )
    return bal


def has_overlapping_leave(user: User, start: date, end: date, exclude_pk=None) -> bool:
    qs = LeaveRequest.objects.filter(
        user=user,
        status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
        start_date__lte=end,
        end_date__gte=start,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def create_approval_chain(leave_request: LeaveRequest) -> None:
    user = leave_request.user
    LeaveApproval.objects.filter(leave_request=leave_request).delete()

    chain = build_approval_chain_steps(user)
    for step_num, (_role_key, label, approver) in enumerate(chain, start=1):
        LeaveApproval.objects.create(
            leave_request=leave_request,
            step=step_num,
            step_label=label,
            approver=approver,
            status=LeaveApproval.StepStatus.PENDING,
        )

    if not chain:
        LeaveApproval.objects.create(
            leave_request=leave_request,
            step=1,
            step_label="Auto-approved",
            approver=None,
            status=LeaveApproval.StepStatus.APPROVED,
            acted_at=timezone.now(),
        )
        _finalize_approval(leave_request, None, "")


def _finalize_approval(leave_request: LeaveRequest, approver: User | None, comment: str) -> None:
    leave_request.status = LeaveRequest.Status.APPROVED
    leave_request.reviewed_by = approver
    leave_request.reviewed_at = timezone.now()
    leave_request.review_comment = comment
    leave_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_comment", "updated_at"])
    bal = get_balance(leave_request.user, leave_request.leave_type)
    bal.used += leave_request.total_days
    bal.save(update_fields=["used"])


@transaction.atomic
def submit_leave_request(
    *,
    user: User,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    half_day: str,
    reason: str,
    emergency_contact: str = "",
    attachment=None,
    as_draft: bool = False,
) -> tuple[LeaveRequest | None, str]:
    if not user.organization_id:
        return None, "No organization."
    if end_date < start_date:
        return None, "End date must be on or after start date."
    if has_overlapping_leave(user, start_date, end_date):
        return None, "Leave dates overlap with an existing request."

    total = calculate_leave_days(
        start_date,
        end_date,
        organization=user.organization,
        half_day=half_day,
        branch=user.work_location or "",
        user=user,
    )
    if total <= 0:
        return None, "No working days in selected range (weekends/holidays excluded)."

    if not as_draft and leave_type.is_paid:
        if leave_type.annual_quota is None:
            return None, f"{leave_type.name} has no annual quota set. Contact your admin."
        bal = get_balance(user, leave_type)
        if bal.remaining < total:
            return None, f"Insufficient balance. Remaining: {bal.remaining} day(s)."
    elif not as_draft:
        get_balance(user, leave_type)

    status = LeaveRequest.Status.DRAFT if as_draft else LeaveRequest.Status.PENDING
    req = LeaveRequest.objects.create(
        user=user,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        total_days=total,
        half_day=half_day,
        reason=reason,
        emergency_contact=emergency_contact,
        attachment=attachment,
        status=status,
    )
    if not as_draft:
        create_approval_chain(req)
        if req.status == LeaveRequest.Status.APPROVED:
            return req, "Leave request auto-approved."
        notify_leave_submitted(req)
        return req, "Leave request submitted for approval."
    return req, "Draft saved."


@transaction.atomic
def approve_leave(leave_request: LeaveRequest, approver: User, comment: str = "") -> str:
    if leave_request.status != LeaveRequest.Status.PENDING:
        return "Request is not pending."

    step = (
        leave_request.approvals.filter(approver=approver, status=LeaveApproval.StepStatus.PENDING)
        .order_by("step")
        .first()
    )
    if not step and approver.role in (User.Role.ADMIN, User.Role.HR):
        step = leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING).order_by("step").first()

    if step:
        step.status = LeaveApproval.StepStatus.APPROVED
        step.comment = comment
        step.acted_at = timezone.now()
        step.save(update_fields=["status", "comment", "acted_at"])

    pending = leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING).exists()
    if not pending:
        dismiss_leave_notifications(leave_request)
        _finalize_approval(leave_request, approver, comment)
        return "Leave approved."
    notify_leave_next_approver(leave_request)
    return "Approved at your step. Awaiting next approver."


@transaction.atomic
def reject_leave(leave_request: LeaveRequest, approver: User, comment: str = "") -> str:
    if leave_request.status != LeaveRequest.Status.PENDING:
        return "Request is not pending."
    leave_request.status = LeaveRequest.Status.REJECTED
    leave_request.reviewed_by = approver
    leave_request.reviewed_at = timezone.now()
    leave_request.review_comment = comment
    leave_request.save()
    leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING).update(
        status=LeaveApproval.StepStatus.REJECTED,
        acted_at=timezone.now(),
        comment=comment,
    )
    dismiss_leave_notifications(leave_request)
    return "Leave rejected."


@transaction.atomic
def cancel_leave(leave_request: LeaveRequest, user: User) -> str:
    if leave_request.user_id != user.pk and user.role not in (User.Role.ADMIN, User.Role.HR):
        return "Not allowed."
    if leave_request.status not in (LeaveRequest.Status.PENDING, LeaveRequest.Status.DRAFT):
        return "Only pending or draft requests can be cancelled."
    if leave_request.status == LeaveRequest.Status.APPROVED:
        bal = get_balance(leave_request.user, leave_request.leave_type)
        bal.used = max(Decimal("0"), bal.used - leave_request.total_days)
        bal.save(update_fields=["used"])
    leave_request.status = LeaveRequest.Status.CANCELLED
    leave_request.save(update_fields=["status", "updated_at"])
    dismiss_leave_notifications(leave_request)
    return "Leave cancelled."
