"""Login redirect resolution and audit logging."""

from __future__ import annotations

from django.urls import reverse

from apps.accounts.login_portals import (
    PORTAL_ADMIN,
    PORTAL_EMPLOYEE,
    PORTAL_HR,
    get_portal,
)
from apps.accounts.models import LoginAuditLog, User
from apps.organizations.models import Organization


def resolve_post_login_url(user: User, portal_id: str) -> str:
    """Return dashboard URL after successful portal-authenticated login."""
    if portal_id == PORTAL_ADMIN:
        if user.role == User.Role.SUPER_ADMIN:
            return reverse("dashboard:superadmin")
        org = user.organization
        if org and org.subscription_plan in (
            Organization.SubscriptionPlan.PREMIUM,
            Organization.SubscriptionPlan.ENTERPRISE,
        ):
            return reverse("dashboard:professional_admin")
        return reverse("dashboard:starter_admin")

    if portal_id == PORTAL_HR:
        return reverse("dashboard:attendance_team")

    if portal_id == PORTAL_EMPLOYEE:
        return reverse("dashboard:employee")

    return reverse("dashboard:home")


def user_allowed_for_portal(user: User, portal_id: str) -> bool:
    portal = get_portal(portal_id)
    return user.role in portal["allowed_roles"]


def log_login_attempt(
    *,
    request,
    portal_id: str,
    username_attempt: str,
    success: bool,
    user: User | None = None,
    failure_reason: str = "",
) -> None:
    meta = request.META
    LoginAuditLog.objects.create(
        user=user,
        username_attempt=username_attempt[:255],
        portal=portal_id,
        success=success,
        ip_address=_client_ip(meta),
        user_agent=(meta.get("HTTP_USER_AGENT") or "")[:500],
        failure_reason=failure_reason[:255],
    )


def _client_ip(meta: dict) -> str | None:
    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    remote = meta.get("REMOTE_ADDR")
    return remote[:45] if remote else None
