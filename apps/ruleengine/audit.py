"""Recorder for rule CRUD/lifecycle audit logs.

Mirrors ``apps.team.audit.record_team_action`` / ``apps.payroll.services.record_payroll_action``
so the audit trail is uniform across the codebase regardless of which app it lives in.
"""

from __future__ import annotations

from apps.accounts.models import User
from apps.team.audit import client_ip

from .models import RuleAuditLog


def record_rule_action(
    org,
    actor: User | None,
    action: str,
    summary: str,
    rule_id=None,
    *,
    request=None,
    **details,
) -> RuleAuditLog | None:
    """Persist one rule audit entry. Never raises into the caller's flow."""
    if not org:
        return None
    try:
        return RuleAuditLog.objects.create(
            organization=org,
            actor=actor,
            action=action,
            object_id=rule_id,
            summary=summary[:255],
            details=details or {},
            ip_address=client_ip(request),
        )
    except Exception:
        # Auditing must never break the primary action.
        return None
