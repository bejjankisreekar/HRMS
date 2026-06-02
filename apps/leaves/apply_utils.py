"""Apply leave page — context, preview, and validation helpers."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from apps.accounts.hierarchy import org_active_users
from apps.accounts.models import User
from apps.attendance.work_calendar import (
    calendar_preview,
    get_holidays_between,
    is_weekend,
    is_working_day,
)
from apps.leaves.models import Holiday, LeaveBalance, LeaveRequest, LeaveType

from .services import calculate_leave_days, get_balance, has_overlapping_leave
from .approval_policy import preview_approval_chain


def leave_request_reference(req: LeaveRequest) -> str:
    year = req.applied_at.year if req.applied_at else date.today().year
    short = str(req.pk).replace("-", "")[:6].upper()
    return f"LV-{year}-{short}"


def leave_type_policy_hint(leave_type: LeaveType) -> str:
    parts: list[str] = []
    if leave_type.annual_quota is not None:
        parts.append(f"Annual quota: {leave_type.annual_quota} day(s).")
    if leave_type.requires_attachment:
        parts.append("Supporting document recommended (optional).")
    if not leave_type.is_paid:
        parts.append("Unpaid leave — may affect payroll.")
    if leave_type.carry_forward_max and leave_type.carry_forward_max > 0:
        parts.append(f"Carry forward up to {leave_type.carry_forward_max} day(s).")
    return " ".join(parts) if parts else "Follow your organization leave policy."


def serialize_balance(balance: LeaveBalance) -> dict:
    lt = balance.leave_type
    total = balance.allocated + balance.carried_forward
    used_pct = 0
    if total > 0:
        used_pct = min(int((balance.used / total) * 100), 100)
    remaining = balance.remaining
    return {
        "id": str(lt.pk),
        "name": lt.name,
        "code": lt.code,
        "color": lt.color or "#6366f1",
        "remaining": float(remaining),
        "remaining_display": f"{remaining:.1f}".rstrip("0").rstrip("."),
        "allocated": float(total),
        "used": float(balance.used),
        "used_pct": used_pct,
        "is_paid": lt.is_paid,
        "requires_attachment": lt.requires_attachment,
        "policy_hint": leave_type_policy_hint(lt),
    }


def team_on_leave_count(user: User, start: date, end: date) -> list[dict]:
    """Peers with overlapping approved/pending leave in date range."""
    if not user.organization_id or not user.reporting_manager_id:
        return []

    peers = org_active_users(user.organization).filter(
        reporting_manager_id=user.reporting_manager_id,
    ).exclude(pk=user.pk)

    peer_ids = list(peers.values_list("pk", flat=True))
    if not peer_ids:
        return []

    overlapping = (
        LeaveRequest.objects.filter(
            user_id__in=peer_ids,
            status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
            start_date__lte=end,
            end_date__gte=start,
        )
        .select_related("user", "leave_type")
        .order_by("start_date")[:10]
    )

    return [
        {
            "name": r.user.display_name,
            "leave_type": r.leave_type.name,
            "start": r.start_date.isoformat(),
            "end": r.end_date.isoformat(),
            "status": r.get_status_display(),
        }
        for r in overlapping
    ]


def build_apply_preview(
    user: User,
    *,
    leave_type_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    half_day: str = LeaveRequest.HalfDay.NONE,
) -> dict:
    org = user.organization
    warnings: list[str] = []
    total_days = Decimal("0")
    remaining_after = None
    leave_type = None

    if leave_type_id:
        leave_type = LeaveType.objects.filter(pk=leave_type_id, organization=org, is_active=True).first()

    if start and end:
        if end < start:
            warnings.append("End date must be on or after start date.")
        else:
            total_days = calculate_leave_days(
                start,
                end,
                organization=org,
                half_day=half_day,
                branch=user.work_location or "",
                user=user,
            )
            if total_days <= 0:
                warnings.append("No working days in selected range (weekends/holidays excluded).")

            if has_overlapping_leave(user, start, end):
                warnings.append("These dates overlap with an existing leave request.")

            holidays = get_holidays_between(org, start, end, user.work_location or "")
            if holidays:
                warnings.append(f"{len(holidays)} holiday(s) in range — excluded from leave count.")

            current = start
            while current <= end:
                if not is_working_day(org, current, user=user, branch=user.work_location or ""):
                    if is_weekend(org, current, user) and not holidays:
                        pass
                current += timedelta(days=1)

            if leave_type and leave_type.is_paid and leave_type.annual_quota is not None:
                bal = get_balance(user, leave_type)
                remaining_after = float(bal.remaining - total_days)
                if remaining_after < 0:
                    warnings.append(
                        f"Insufficient balance. You have {bal.remaining} day(s) remaining for {leave_type.name}."
                    )

            if leave_type and leave_type.requires_attachment and total_days >= 2:
                warnings.append(
                    f"{leave_type.name}: you may attach a supporting document (optional)."
                )

    team = team_on_leave_count(user, start, end) if start and end else []

    return {
        "total_days": float(total_days),
        "total_days_display": f"{total_days:.1f}".rstrip("0").rstrip(".") or "0",
        "remaining_after": remaining_after,
        "warnings": warnings,
        "team_on_leave": team,
        "team_on_leave_count": len(team),
    }


def get_apply_leave_context(user: User) -> dict:
    org = user.organization
    year = date.today().year
    today = date.today()

    balances_qs = (
        user.leave_balances.filter(year=year)
        .select_related("leave_type")
        .filter(leave_type__is_active=True)
        .order_by("leave_type__sort_order", "leave_type__name")
    )
    balance_cards = [serialize_balance(b) for b in balances_qs]

    leave_types = list(
        LeaveType.objects.filter(organization=org, is_active=True).order_by("sort_order", "name")
    )

    holidays = list(
        Holiday.objects.filter(organization=org, date__gte=today - timedelta(days=30))
        .order_by("date")[:90]
    )
    holiday_dates = [h.date.isoformat() for h in holidays]

    cal_year = today.year
    cal_month = today.month

    manager = user.reporting_manager
    drafts = list(
        LeaveRequest.objects.filter(user=user, status=LeaveRequest.Status.DRAFT)
        .select_related("leave_type")
        .order_by("-updated_at")[:5]
    )

    return {
        "balance_cards": balance_cards,
        "leave_types_json": [
            {
                "id": str(lt.pk),
                "name": lt.name,
                "color": lt.color,
                "requires_attachment": lt.requires_attachment,
                "is_paid": lt.is_paid,
                "policy_hint": leave_type_policy_hint(lt),
            }
            for lt in leave_types
        ],
        "approval_chain": preview_approval_chain(user),
        "manager_name": manager.display_name if manager else "Not assigned",
        "manager_designation": manager.designation_label if manager else "",
        "holiday_dates": holiday_dates,
        "calendar_weeks": calendar_preview(org, cal_year, cal_month, user=user),
        "cal_year": cal_year,
        "cal_month": cal_month,
        "drafts": drafts,
        "today": today,
    }
