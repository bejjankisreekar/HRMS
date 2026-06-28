"""Login portal definitions for multi-role authentication UI."""

from __future__ import annotations

from apps.accounts.models import User

PORTAL_ORG_ADMIN = "admin"
PORTAL_HR = "hr"
PORTAL_EMPLOYEE = "employee"

# Backward-compatible alias used in forms and audit logs
PORTAL_ADMIN = PORTAL_ORG_ADMIN

DEFAULT_PORTAL = PORTAL_ORG_ADMIN

LOGIN_PORTALS = [
    {
        "id": PORTAL_ORG_ADMIN,
        "label": "Organization Admin",
        "title": "Organization Admin Portal",
        "subtitle": (
            "Company administration — manage employees, departments, payroll, "
            "attendance, and organization settings."
        ),
        "icon": "building-2",
        "accent": "violet",
        "features": [
            "Employee & department management",
            "Payroll & attendance oversight",
            "Organization reports & analytics",
            "Company settings & policies",
            "HR operations control",
        ],
        "preview_stats": [
            {"label": "Active employees", "value": "248", "delta": "+12 this month"},
            {"label": "Payroll status", "value": "On track", "delta": "Next run: 1 Jun"},
        ],
        # Super Admin uses this portal silently (not shown as a separate tab)
        "allowed_roles": {User.Role.SUPER_ADMIN, User.Role.ADMIN},
        "role_mismatch_message": (
            "This account is not authorized for the Organization Admin Portal. "
            "Managers / HR should use the Manager / HR portal; employees should use the Employee portal."
        ),
    },
    {
        "id": PORTAL_HR,
        "label": "Manager / HR",
        "title": "Manager / HR Portal",
        "subtitle": (
            "Team & HR operations — attendance, leave approvals, "
            "payroll assistance, and employee support."
        ),
        "icon": "users",
        "accent": "cyan",
        "features": [
            "Attendance management",
            "Leave approvals",
            "Payroll assistance",
            "Employee support",
        ],
        "preview_stats": [
            {"label": "Pending leave", "value": "12", "delta": "4 urgent"},
            {"label": "Open positions", "value": "8", "delta": "3 interviews today"},
        ],
        "allowed_roles": {User.Role.HR},
        "role_mismatch_message": (
            "This account is not authorized for the Manager / HR Portal. "
            "Organization Admins should use the Organization Admin portal; "
            "employees should use the Employee portal."
        ),
    },
    {
        "id": PORTAL_EMPLOYEE,
        "label": "Employee",
        "title": "Employee Portal",
        "subtitle": "Self-service for leave, attendance, payslips, and your profile.",
        "icon": "user-circle",
        "accent": "emerald",
        "features": [
            "Leave requests",
            "Attendance history",
            "Payslips & profile",
            "Self-service portal",
            "Documents & leave tracking",
        ],
        "preview_stats": [
            {"label": "Leave balance", "value": "14 days", "delta": "Earned leave"},
            {"label": "Last payslip", "value": "Apr 2026", "delta": "Available now"},
        ],
        "allowed_roles": {User.Role.EMPLOYEE},
        "role_mismatch_message": (
            "This account is not authorized for the Employee Portal. "
            "Organization Admins and Managers / HR should use their respective portals."
        ),
    },
]

SECURITY_BADGES = [
    ("shield-check", "Secure login"),
    ("lock", "Encrypted access"),
    ("key-round", "Role-based security"),
    ("clipboard-list", "Audit logging"),
    ("layers", "Multi-tenant architecture"),
]

HERO_STATS = [
    ("500+", "Companies"),
    ("50K+", "Employees managed"),
    ("99.9%", "Uptime SLA"),
    ("24/7", "Cloud availability"),
]


def get_portal(portal_id: str | None) -> dict:
    for portal in LOGIN_PORTALS:
        if portal["id"] == portal_id:
            return portal
    return LOGIN_PORTALS[0]


def get_login_page_context(selected_portal: str | None = None) -> dict:
    portal = get_portal(selected_portal or DEFAULT_PORTAL)
    return {
        "login_portals": LOGIN_PORTALS,
        "selected_portal": portal,
        "security_badges": SECURITY_BADGES,
        "hero_stats": HERO_STATS,
    }
