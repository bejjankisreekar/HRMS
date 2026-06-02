"""Dashboard notifications for leave workflow."""

from __future__ import annotations

from apps.accounts.models import User
from apps.dashboard.notification_service import (
    _leave_notification_payload,
    dismiss_notifications_by_prefix,
    upsert_dashboard_notification,
)
from apps.leaves.models import LeaveApproval, LeaveRequest


def _submission_recipients(leave_request: LeaveRequest) -> list[User]:
    """Users who should be notified when a leave request is submitted."""
    employee = leave_request.user
    org = employee.organization
    if not org:
        return []

    recipients: dict[int, User] = {}

    first_pending = (
        leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING)
        .order_by("step")
        .select_related("approver")
        .first()
    )
    if first_pending and first_pending.approver_id and first_pending.approver_id != employee.pk:
        recipients[first_pending.approver_id] = first_pending.approver

    if employee.role == User.Role.EMPLOYEE:
        for hr in User.objects.filter(organization=org, role=User.Role.HR, is_active=True):
            if hr.pk != employee.pk:
                recipients[hr.pk] = hr

    return list(recipients.values())


def _notify_user(user: User, leave_request: LeaveRequest, *, force_unread: bool = True) -> None:
    payload = _leave_notification_payload(user, leave_request)
    upsert_dashboard_notification(user, force_unread=force_unread, **payload)


def notify_leave_submitted(leave_request: LeaveRequest) -> None:
    if leave_request.status != LeaveRequest.Status.PENDING:
        return
    for user in _submission_recipients(leave_request):
        _notify_user(user, leave_request)


def notify_leave_next_approver(leave_request: LeaveRequest) -> None:
    if leave_request.status != LeaveRequest.Status.PENDING:
        return
    first_pending = (
        leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING)
        .order_by("step")
        .select_related("approver")
        .first()
    )
    if first_pending and first_pending.approver:
        _notify_user(first_pending.approver, leave_request)


def dismiss_leave_notifications(leave_request: LeaveRequest) -> None:
    dismiss_notifications_by_prefix(f"leave:{leave_request.pk}:")
