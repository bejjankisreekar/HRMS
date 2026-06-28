"""Sync system events into per-user dashboard notifications."""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_for
from apps.dashboard.models import DashboardNotification
from apps.dashboard.staff_services import staff_queryset_for, user_notification_url
from apps.organizations.models import Organization


def _meta_label(dt) -> str:
    if not dt:
        return ""
    return timesince(dt, timezone.now()) + " ago"


def upsert_dashboard_notification(
    user: User,
    *,
    source_key: str,
    title: str,
    message: str,
    url: str,
    icon: str = "bell",
    notification_type: str = "",
    created_at=None,
    force_unread: bool = False,
) -> DashboardNotification:
    """Create or update a notification row for one user."""
    notif, created = DashboardNotification.objects.get_or_create(
        user=user,
        source_key=source_key,
        defaults={
            "title": title,
            "message": message,
            "url": url,
            "icon": icon,
            "notification_type": notification_type,
            "is_read": False,
        },
    )
    if not created:
        notif.title = title
        notif.message = message
        notif.url = url
        notif.icon = icon
        notif.notification_type = notification_type
        update_fields = ["title", "message", "url", "icon", "notification_type"]
        if force_unread:
            notif.is_read = False
            notif.read_at = None
            update_fields.extend(["is_read", "read_at"])
        notif.save(update_fields=update_fields)
    if created and created_at:
        DashboardNotification.objects.filter(pk=notif.pk).update(created_at=created_at)
    return notif


def dismiss_notifications_by_prefix(source_prefix: str) -> int:
    return DashboardNotification.objects.filter(source_key__startswith=source_prefix).delete()[0]


def _send_email_notification(user: User, *, title: str, message: str, url: str, **_kwargs) -> None:
    """Email delivery seam.

    Intentionally a no-op for now — the notification system is designed to grow
    an email channel without changing call sites. Wire an actual transport here
    (Django ``send_mail`` / a task queue) when email notifications are enabled.
    """
    # TODO(notifications): deliver email when the email channel is enabled.
    return None


def send_notification(user: User, *, channels: tuple[str, ...] = ("in_app",), **payload):
    """Dispatch a notification to one user across the requested channels.

    Channels:
      * ``in_app`` — persists a :class:`DashboardNotification` (active today).
      * ``email``  — routed through :func:`_send_email_notification` (stub today).

    Unknown channels are ignored so new channels can be added incrementally.
    """
    result = None
    if "in_app" in channels:
        force_unread = payload.pop("force_unread", False)
        result = upsert_dashboard_notification(user, force_unread=force_unread, **payload)
    if "email" in channels:
        _send_email_notification(
            user,
            title=payload.get("title", ""),
            message=payload.get("message", ""),
            url=payload.get("url", ""),
        )
    return result


def _leave_notification_payload(user: User, leave_request, *, created_at=None) -> dict:
    employee = leave_request.user
    return {
        "source_key": f"leave:{leave_request.pk}:{user.pk}",
        "title": f"Leave request: {employee.display_name or employee.username}",
        "message": (
            f"{leave_request.leave_type.name} · "
            f"{leave_request.start_date:%d %b} – {leave_request.end_date:%d %b %Y} · "
            f"{leave_request.total_days} day(s)"
        ),
        "url": reverse("leaves:management") + "?status=PENDING",
        "icon": "palmtree",
        "notification_type": "leave",
        "created_at": created_at or leave_request.applied_at,
    }


def _pending_leave_candidates(user: User, org: Organization) -> list[dict]:
    from apps.leaves.models import LeaveApproval, LeaveRequest

    candidates: list[dict] = []
    seen_keys: set[str] = set()

    pending_as_approver = (
        LeaveApproval.objects.filter(
            approver=user,
            status=LeaveApproval.StepStatus.PENDING,
            leave_request__status=LeaveRequest.Status.PENDING,
            leave_request__user__organization=org,
        )
        .select_related("leave_request", "leave_request__user", "leave_request__leave_type")
        .order_by("-leave_request__applied_at")
    )
    for approval in pending_as_approver:
        req = approval.leave_request
        first_pending = (
            req.approvals.filter(status=LeaveApproval.StepStatus.PENDING).order_by("step").first()
        )
        if not first_pending or first_pending.approver_id != user.pk:
            continue
        payload = _leave_notification_payload(user, req)
        if payload["source_key"] not in seen_keys:
            candidates.append(payload)
            seen_keys.add(payload["source_key"])

    if user.role == User.Role.HR:
        employee_pending = (
            LeaveRequest.objects.filter(
                user__organization=org,
                user__role=User.Role.EMPLOYEE,
                status=LeaveRequest.Status.PENDING,
            )
            .select_related("user", "leave_type")
            .order_by("-applied_at")[:15]
        )
        for req in employee_pending:
            payload = _leave_notification_payload(user, req)
            if payload["source_key"] not in seen_keys:
                candidates.append(payload)
                seen_keys.add(payload["source_key"])

    return candidates


def _notification_candidates(user: User) -> list[dict]:
    """Build notification payloads from recent platform activity."""
    candidates: list[dict] = []

    try:
        if user.role == User.Role.SUPER_ADMIN:
            for org in Organization.objects.order_by("-created_at")[:5]:
                candidates.append(
                    {
                        "source_key": f"org:{org.pk}",
                        "title": f"New organization: {org.name}",
                        "message": f"Workspace {org.organization_code} was provisioned",
                        "url": reverse("dashboard:super_organization_detail", kwargs={"pk": org.pk}),
                        "icon": "building-2",
                        "notification_type": "org",
                        "created_at": org.created_at,
                    }
                )

            for u in User.objects.exclude(role=User.Role.SUPER_ADMIN).order_by("-date_joined")[:5]:
                candidates.append(
                    {
                        "source_key": f"user:{u.pk}",
                        "title": f"New user: {u.display_name or u.username}",
                        "message": u.get_role_display(),
                        "url": reverse("dashboard:super_user_edit", kwargs={"pk": u.pk}),
                        "icon": "user-plus",
                        "notification_type": "user",
                        "created_at": u.date_joined,
                    }
                )

            from apps.subscriptions.models import FinancialAuditLog

            for log in FinancialAuditLog.objects.filter(
                action=FinancialAuditLog.Action.PLAN_CHANGE
            ).select_related("organization")[:5]:
                candidates.append(
                    {
                        "source_key": f"fin:{log.pk}",
                        "title": log.summary,
                        "message": "Plan upgrade or change",
                        "url": reverse("dashboard:financials:audit"),
                        "icon": "credit-card",
                        "notification_type": "plan",
                        "created_at": log.created_at,
                    }
                )

            from apps.subscriptions.models import FeatureControlAuditLog

            for log in FeatureControlAuditLog.objects.order_by("-created_at")[:5]:
                candidates.append(
                    {
                        "source_key": f"feat:{log.pk}",
                        "title": log.summary,
                        "message": "System activity",
                        "url": reverse("dashboard:financials:audit"),
                        "icon": "activity",
                        "notification_type": "activity",
                        "created_at": log.created_at,
                    }
                )
        elif user.organization_id:
            org = user.organization
            staff_qs = staff_queryset_for(user).order_by("-date_joined")[:5]
            for u in staff_qs:
                candidates.append(
                    {
                        "source_key": f"member:{u.pk}",
                        "title": f"New member: {u.display_name or u.username}",
                        "message": role_display_for(u.role, org),
                        "url": user_notification_url(user, u),
                        "icon": "user-plus",
                        "notification_type": "user",
                        "created_at": u.date_joined,
                    }
                )
            candidates.extend(_pending_leave_candidates(user, org))
    except Exception:
        pass

    candidates.sort(key=lambda c: c.get("created_at") or timezone.now(), reverse=True)
    return candidates[:12]


def sync_user_notifications(user: User) -> None:
    """Upsert notification rows for the current user from platform activity."""
    candidates = _notification_candidates(user)
    valid_keys = {item["source_key"] for item in candidates}
    for item in candidates:
        created_at = item.get("created_at") or timezone.now()
        notif, created = DashboardNotification.objects.get_or_create(
            user=user,
            source_key=item["source_key"],
            defaults={
                "title": item["title"],
                "message": item["message"],
                "url": item["url"],
                "icon": item["icon"],
                "notification_type": item["notification_type"],
            },
        )
        if not created:
            DashboardNotification.objects.filter(pk=notif.pk).update(
                title=item["title"],
                message=item["message"],
                url=item["url"],
                icon=item["icon"],
                notification_type=item["notification_type"],
            )
        if created and created_at:
            DashboardNotification.objects.filter(pk=notif.pk).update(created_at=created_at)

    DashboardNotification.objects.filter(user=user).exclude(source_key__in=valid_keys).delete()


def serialize_notification(notif: DashboardNotification) -> dict:
    return {
        "id": str(notif.pk),
        "title": notif.title,
        "message": notif.message,
        "meta": _meta_label(notif.created_at),
        "url": notif.url,
        "icon": notif.icon,
        "type": notif.notification_type,
        "is_read": notif.is_read,
        "read_at": notif.read_at.isoformat() if notif.read_at else None,
        "created_at": notif.created_at.isoformat(),
    }


def get_user_notifications(user: User, *, sync: bool = True) -> list[DashboardNotification]:
    if sync:
        sync_user_notifications(user)
    return list(DashboardNotification.objects.filter(user=user).order_by("-created_at")[:20])


def unread_notification_count(user: User, *, sync: bool = False) -> int:
    if sync:
        sync_user_notifications(user)
    return DashboardNotification.objects.filter(user=user, is_read=False).count()


def mark_notification_read(user: User, notification_id) -> DashboardNotification | None:
    notif = DashboardNotification.objects.filter(user=user, pk=notification_id).first()
    if not notif:
        return None
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=["is_read", "read_at"])
    return notif


def mark_all_notifications_read(user: User) -> int:
    now = timezone.now()
    return DashboardNotification.objects.filter(user=user, is_read=False).update(is_read=True, read_at=now)
