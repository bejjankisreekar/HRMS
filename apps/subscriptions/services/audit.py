from __future__ import annotations

from apps.subscriptions.models import FinancialAuditLog


def log_financial_action(
    *,
    actor,
    action: str,
    summary: str,
    organization=None,
    details: dict | None = None,
    request=None,
) -> FinancialAuditLog:
    ip = None
    if request:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get(
            "REMOTE_ADDR"
        )
    return FinancialAuditLog.objects.create(
        actor=actor,
        organization=organization,
        action=action,
        summary=summary[:255],
        details=details or {},
        ip_address=ip,
    )
