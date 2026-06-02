"""Canonical HRMS role display labels and hierarchy.

Four distinct login types — never conflate Organization Admin with HR:

    Super Admin  →  platform / SaaS owner (global)
    Organization Admin  →  company owner / tenant admin (one org)
    HR  →  HR staff within an organization
    Employee  →  self-service only
"""

from __future__ import annotations

from apps.accounts.models import User

# Display names shown in UI (sidebar, profile, breadcrumbs, etc.)
ROLE_DISPLAY_LABELS: dict[str, str] = {
    User.Role.SUPER_ADMIN: "Super Admin",
    User.Role.ADMIN: "Organization Admin",
    User.Role.HR: "HR",
    User.Role.EMPLOYEE: "Employee",
}

# Ordered from highest to lowest privilege
ROLE_HIERARCHY: tuple[str, ...] = (
    User.Role.SUPER_ADMIN,
    User.Role.ADMIN,
    User.Role.HR,
    User.Role.EMPLOYEE,
)


def role_display_label(user: User) -> str:
    """Human-readable role name for authenticated users."""
    return ROLE_DISPLAY_LABELS.get(user.role, user.get_role_display())


def role_display_for(role: str) -> str:
    return ROLE_DISPLAY_LABELS.get(role, role)
