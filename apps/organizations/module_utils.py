"""Organization module flags (leave, payroll) vs subscription plan features."""

from __future__ import annotations

from apps.organizations.models import Organization
from apps.subscriptions.services.entitlements import has_feature

MODULE_PLAN_FEATURES = {
    "leave": "leave",
    "payroll": "payroll",
}

MODULE_ORG_FLAGS = {
    "leave": "leave_management_enabled",
    "payroll": "payroll_enabled",
}


def plan_includes_module(org: Organization | None, module: str, role: str | None = None) -> bool:
    if not org:
        return False
    return has_feature(org, MODULE_PLAN_FEATURES[module], role)


def module_enabled(org: Organization | None, module: str, role: str | None = None) -> bool:
    if not org or not plan_includes_module(org, module, role):
        return False
    return bool(getattr(org, MODULE_ORG_FLAGS[module]))


def sync_module_from_plan(org: Organization | None, module: str) -> bool:
    """Turn on the org module flag when the plan includes it but the flag is off."""
    if not org or not plan_includes_module(org, module):
        return False
    field = MODULE_ORG_FLAGS[module]
    if getattr(org, field):
        return False
    setattr(org, field, True)
    org.save(update_fields=[field, "updated_at"])
    return True


def ensure_module(org: Organization | None, module: str, role: str | None = None) -> tuple[bool, bool]:
    """Return (is_active, was_auto_enabled)."""
    synced = sync_module_from_plan(org, module)
    if synced and org:
        org.refresh_from_db(fields=[MODULE_ORG_FLAGS[module]])
    return module_enabled(org, module, role), synced
