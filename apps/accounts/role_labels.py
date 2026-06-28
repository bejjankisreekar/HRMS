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

# Roles that are regular org members with full self-service (leave balances,
# attendance rows, payslips, appear in rosters). Use this instead of
# hard-coding [HR, EMPLOYEE] for "who is a staff member" membership lists.
STAFF_SELF_SERVICE_ROLES: tuple[str, ...] = (
    User.Role.HR,
    User.Role.EMPLOYEE,
)

# Non-management staff (managed by HR/Admin). Excludes HR itself.
MANAGED_STAFF_ROLES: tuple[str, ...] = (
    User.Role.EMPLOYEE,
)


def hr_label_for_org(organization) -> str:
    """Org-configured display name for the HR role; falls back to 'HR'.

    Accepts an ``Organization`` (or ``None``). Kept import-free of the
    organizations app so this module stays a low-level leaf.
    """
    if organization is None:
        return ROLE_DISPLAY_LABELS[User.Role.HR]
    return getattr(organization, "hr_label", None) or "HR"


def role_display_label(user: User) -> str:
    """Human-readable role name for authenticated users.

    HR uses the user's organization's configured label (e.g. Manager,
    Team Leader); all other roles use the canonical labels.
    """
    if user.role == User.Role.HR:
        return hr_label_for_org(getattr(user, "organization", None))
    return ROLE_DISPLAY_LABELS.get(user.role, user.get_role_display())


def role_display_for(role: str, organization=None) -> str:
    """Display label for a role string, org-aware for HR when an org is given."""
    if role == User.Role.HR and organization is not None:
        return hr_label_for_org(organization)
    return ROLE_DISPLAY_LABELS.get(role, role)
