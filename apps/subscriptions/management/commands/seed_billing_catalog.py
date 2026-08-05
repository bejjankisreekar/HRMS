"""Seed billing catalog — plans and add-ons."""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.organizations.models import Organization
from apps.subscriptions.models import AddOnCatalog, BillingSettings, Plan, Subscription
from apps.subscriptions.plan_defaults import DEFAULT_ADDONS, DEFAULT_PLANS


class Command(BaseCommand):
    help = "Seed SaaS billing plans and add-on catalog."

    def handle(self, *args, **options):
        billing_settings = BillingSettings.get_solo()
        for p in DEFAULT_PLANS:
            defaults = {
                **p,
                "yearly_price_inr": billing_settings.compute_yearly_price(p["monthly_price_inr"]),
                "is_active": True,
            }
            Plan.objects.update_or_create(slug=p["slug"], defaults=defaults)
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
        # Remap any legacy plan values to the current Basic / Professional / Growth set.
        Organization.objects.filter(subscription_plan="ENTERPRISE").update(
            subscription_plan=Organization.SubscriptionPlan.GROWTH
        )
        Organization.objects.filter(subscription_plan="PREMIUM").update(
            subscription_plan=Organization.SubscriptionPlan.PROFESSIONAL
        )
        Organization.objects.filter(subscription_plan__in=["FREE", "STARTER", ""]).exclude(
            subscription_plan__in=[c[0] for c in Organization.SubscriptionPlan.choices]
        ).update(subscription_plan=Organization.SubscriptionPlan.BASIC)
