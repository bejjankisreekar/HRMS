"""Dashboard notifications for leave workflow."""

from __future__ import annotations

from django.urls import reverse

from apps.accounts.models import User
from apps.dashboard.notification_service import (
    _leave_notification_payload,
    dismiss_notifications_by_prefix,
    send_notification,
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


def notify_leave_decision(leave_request: LeaveRequest, *, approved: bool, actor: User | None = None) -> None:
    """Notify the employee that their leave request was approved or rejected.

    Sent over the in-app channel today; the email channel is wired through the
    same ``send_notification`` seam and can be enabled later without touching
    this call site.
    """
    employee = leave_request.user
    if not employee:
        return
    verb = "approved" if approved else "rejected"
    lt = leave_request.leave_type
    send_notification(
        employee,
        channels=("in_app", "email"),
        source_key=f"leave-decision:{leave_request.pk}",
        title=f"Leave {verb}",
        message=(
            f"Your {lt.name} request "
            f"({leave_request.start_date:%d %b} – {leave_request.end_date:%d %b %Y}) "
            f"was {verb}"
            + (f" by {actor.display_name}" if actor else "")
            + "."
        ),
        url=reverse("leaves:management"),
        icon="check-circle" if approved else "x-circle",
        notification_type="leave",
        force_unread=True,
    )


def notify_leave_cancelled(leave_request: LeaveRequest) -> None:
    """Notify approvers with a pending step that the employee cancelled."""
    employee = leave_request.user
    pending_approvers = (
        leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING)
        .exclude(approver=None)
        .select_related("approver")
    )
    for step in pending_approvers:
        if step.approver_id == employee.pk:
            continue
        send_notification(
            step.approver,
            channels=("in_app", "email"),
            source_key=f"leave-cancelled:{leave_request.pk}:{step.approver_id}",
            title="Leave request cancelled",
            message=(
                f"{employee.display_name} cancelled their {leave_request.leave_type.name} "
                f"request ({leave_request.start_date:%d %b} – {leave_request.end_date:%d %b %Y})."
            ),
            url=reverse("leaves:management"),
            icon="x-circle",
            notification_type="leave",
            force_unread=True,
        )


def dismiss_leave_notifications(leave_request: LeaveRequest) -> None:
    dismiss_notifications_by_prefix(f"leave:{leave_request.pk}:")
