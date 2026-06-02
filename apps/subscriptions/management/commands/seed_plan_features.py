"""Seed feature catalog, plan features, navigation menus, and add-on feature keys."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.subscriptions.models import AddOnCatalog, FeatureDefinition, Plan, PlanFeature, PlanMenuItem
from apps.subscriptions.plan_catalog import (
    ADDON_FEATURE_KEYS,
    ADMIN_MENUS,
    FEATURE_CATALOG,
    PLAN_FEATURES,
    PLAN_LIMITS,
)


FEATURE_URL_NAMES: dict[str, list[str]] = {
    "shifts": ["shifts:management", "dashboard:attendance_shifts", "dashboard:attendance_settings"],
    "attendance": ["dashboard:attendance", "dashboard:attendance_corrections", "dashboard:attendance_team"],
    "leave": ["leaves:management", "leaves:apply"],
    "payroll_basic": ["payroll:management"],
    "payroll_advanced": ["payroll:management"],
    "departments": ["dashboard:departments"],
    "employees": ["dashboard:staff_list", "dashboard:staff_create", "dashboard:staff_detail", "dashboard:staff_edit"],
    "grades": ["dashboard:grades:hub", "dashboard:grades:list"],
    "reports_basic": ["attendance:reports", "dashboard:attendance_report"],
    "reports_advanced": ["attendance:reports"],
    "analytics_basic": ["attendance:reports"],
    "analytics_advanced": ["attendance:reports"],
    "custom_reports": ["attendance:reports"],
    "org_settings": ["dashboard:settings"],
    "dashboard": ["dashboard:starter_admin", "dashboard:professional_admin", "dashboard:home"],
    "employee_self_service": ["dashboard:employee"],
    "holidays": ["dashboard:work_calendar", "leaves:management"],
    "executive_dashboard": ["dashboard:professional_admin"],
}


class Command(BaseCommand):
    help = "Seed plan features, navigation menus, and add-on feature mappings."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding feature definitions…")
        feature_objs: dict[str, FeatureDefinition] = {}
        for i, (key, meta) in enumerate(FEATURE_CATALOG.items()):
            obj, _ = FeatureDefinition.objects.update_or_create(
                key=key,
                defaults={
                    "name": meta["name"],
                    "category": meta.get("category", ""),
                    "url_names": FEATURE_URL_NAMES.get(key, []),
                    "sort_order": i,
                    "is_active": True,
                },
            )
            feature_objs[key] = obj

        self.stdout.write("Updating plan limits…")
        for slug, limits in PLAN_LIMITS.items():
            Plan.objects.filter(slug=slug).update(
                employee_limit=limits["employee_limit"],
                storage_limit_mb=limits["storage_limit_mb"],
            )

        self.stdout.write("Assigning plan features…")
        for slug, keys in PLAN_FEATURES.items():
            plan = Plan.objects.filter(slug=slug).first()
            if not plan:
                self.stdout.write(self.style.WARNING(f"  Plan '{slug}' not found — run seed_billing_catalog first."))
                continue
            plan.feature_flags = {k: True for k in keys}
            plan.save(update_fields=["feature_flags", "updated_at"])
            for key in keys:
                feat = feature_objs.get(key)
                if not feat:
                    continue
                PlanFeature.objects.update_or_create(
                    plan=plan,
                    feature=feat,
                    defaults={"is_enabled": True},
                )
            PlanFeature.objects.filter(plan=plan).exclude(feature__key__in=keys).update(is_enabled=False)

        self.stdout.write("Seeding navigation menus…")
        for slug, menus in ADMIN_MENUS.items():
            plan = Plan.objects.filter(slug=slug).first()
            if not plan:
                continue
            PlanMenuItem.objects.filter(plan=plan).delete()
            for order, row in enumerate(menus):
                label, icon, url_name, feature_key, query, active_views, roles = row
                for role in roles:
                    PlanMenuItem.objects.create(
                        plan=plan,
                        label=label,
                        icon=icon,
                        url_name=url_name,
                        query_string=query or "",
                        feature_key=feature_key or "",
                        sort_order=order,
                        is_enabled=True,
                        audience=role,
                        active_views=list(active_views),
                        keywords=[label.lower()],
                    )

        self.stdout.write("Mapping add-on feature keys…")
        for slug, keys in ADDON_FEATURE_KEYS.items():
            AddOnCatalog.objects.filter(slug=slug).update(feature_keys=keys)

        missing_addons = [
            ("workflow-automation", "Workflow Automation", 999, "git-branch", ["workflows"]),
            ("compliance-center", "Compliance Center", 1499, "shield-check", ["compliance"]),
        ]
        for slug, name, price, icon, keys in missing_addons:
            AddOnCatalog.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "monthly_price_inr": price,
                    "icon": icon,
                    "feature_keys": keys,
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Plan features and navigation seeded."))
