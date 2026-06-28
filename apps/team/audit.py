"""Recorder for manager team-action audit logs.

Used by both the server-rendered manager views and the DRF ``/api/team/``
endpoints so the audit trail is uniform regardless of entry point.
"""

from __future__ import annotations

from apps.accounts.models import User

from .models import TeamActionAuditLog


def client_ip(request) -> str | None:
    """Best-effort client IP, honoring a proxy's X-Forwarded-For header."""
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    remote = meta.get("REMOTE_ADDR")
    return (remote[:45] if remote else None)


def record_team_action(
    *,
    actor: User,
    action: str,
    target: User | None,
    summary: str,
    object_id=None,
    request=None,
    ip_address: str | None = None,
    **details,
) -> TeamActionAuditLog | None:
    """Persist one manager action. Never raises into the caller's flow."""
    org = getattr(actor, "organization", None)
    if not org:
        return None
    try:
        return TeamActionAuditLog.objects.create(
            organization=org,
            actor=actor,
            target_user=target,
            action=action,
            object_id=object_id,
            summary=summary[:255],
            details=details or {},
            ip_address=ip_address if ip_address is not None else client_ip(request),
        )
    except Exception:
        # Auditing must never break the primary action.
        return None
