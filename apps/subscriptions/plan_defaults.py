"""Canonical seed values for billing plans and add-ons.

Single source of truth for default pricing. Live pricing is edited via the
Super Admin Plans UI (writes straight to the Plan/AddOnCatalog DB rows) —
these constants only matter for seeding a fresh database and as the
last-resort fallback in `services.billing.get_or_create_subscription`.
"""

from __future__ import annotations

from decimal import Decimal

DEFAULT_PLANS = [
    {
        "slug": "basic",
        "name": "Basic",
        "description": "Core HR for small teams.",
        "monthly_price_inr": Decimal("1999"),
        "employee_limit": 50,
        "branch_limit": 1,
        "storage_limit_mb": 5120,
        "trial_days": 14,
        "sort_order": 1,
    },
    {
        "slug": "professional",
        "name": "Professional",
        "description": "Payroll, performance, and analytics.",
        "monthly_price_inr": Decimal("4999"),
        "employee_limit": 250,
        "branch_limit": 3,
        "storage_limit_mb": 20480,
        "trial_days": 14,
        "sort_order": 2,
    },
    {
        "slug": "growth",
        "name": "Growth",
        "description": "Full platform — multi-branch, advanced analytics, compliance, and unlimited scale.",
        "monthly_price_inr": Decimal("5999"),
        "employee_limit": None,
        "branch_limit": None,
        "storage_limit_mb": None,
        "trial_days": 14,
        "sort_order": 3,
    },
]

DEFAULT_ADDONS = [
    ("ai-analytics", "AI Analytics", 1999, "brain"),
    ("payroll-advanced", "Payroll Advanced", 999, "wallet"),
    ("performance", "Performance Management", 1299, "target"),
    ("lms", "LMS", 899, "graduation-cap"),
    ("asset-management", "Asset Management", 799, "package"),
    ("api-access", "API Access", 1999, "code-2"),
    ("whatsapp", "WhatsApp Integration", 799, "message-circle"),
    ("biometric", "Biometric Integration", 999, "fingerprint"),
    ("custom-branding", "Custom Branding", 1499, "palette"),
    ("multi-branch", "Multi Branch", 2499, "building-2"),
    ("audit-logs", "Audit Logs", 599, "clipboard-list"),
    ("helpdesk", "Helpdesk", 699, "life-buoy"),
    ("project-management", "Project Management", 1199, "folder-kanban"),
]


def get_default_plan(slug: str) -> dict:
    return next(p for p in DEFAULT_PLANS if p["slug"] == slug)
