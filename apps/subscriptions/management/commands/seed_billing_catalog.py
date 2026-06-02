"""Seed billing catalog — plans and add-ons."""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.organizations.models import Organization
from apps.subscriptions.models import AddOnCatalog, Plan, Subscription


DEFAULT_PLANS = [
    {
        "slug": "basic",
        "name": "Basic",
        "description": "Core HR for small teams.",
        "monthly_price_inr": Decimal("2000"),
        "yearly_price_inr": Decimal("19920"),
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
        "monthly_price_inr": Decimal("5000"),
        "yearly_price_inr": Decimal("49800"),
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
        "monthly_price_inr": Decimal("6000"),
        "yearly_price_inr": Decimal("59760"),
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


class Command(BaseCommand):
    help = "Seed SaaS billing plans and add-on catalog."

    def handle(self, *args, **options):
        for p in DEFAULT_PLANS:
            Plan.objects.update_or_create(slug=p["slug"], defaults={**p, "is_active": True})
            self.stdout.write(f"Plan: {p['name']}")

        for i, (slug, name, price, icon) in enumerate(DEFAULT_ADDONS):
            AddOnCatalog.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "monthly_price_inr": Decimal(price),
                    "icon": icon,
                    "sort_order": i,
                    "is_active": True,
                },
            )
            self.stdout.write(f"Add-on: {name}")

        self._retire_enterprise_plan()
        self.stdout.write(self.style.SUCCESS("Billing catalog seeded."))

    def _retire_enterprise_plan(self) -> None:
        growth = Plan.objects.filter(slug="growth").first()
        retired = Plan.objects.filter(slug="enterprise").first()
        if retired:
            if growth:
                Subscription.objects.filter(plan=retired).update(plan=growth)
            retired.is_active = False
            retired.save(update_fields=["is_active", "updated_at"])
            self.stdout.write(self.style.WARNING("Retired plan: Enterprise (migrated subscriptions to Growth)."))
        Organization.objects.filter(subscription_plan=Organization.SubscriptionPlan.ENTERPRISE).update(
            subscription_plan=Organization.SubscriptionPlan.PREMIUM
        )
