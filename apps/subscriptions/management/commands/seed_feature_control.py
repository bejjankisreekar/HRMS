"""Seed modules, pages, navigation, fields, workflows, role permissions, and dependencies."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.subscriptions.models import (
    FeatureDefinition,
    FeatureModule,
    FeatureRolePermission,
    FeatureType,
    FieldDefinition,
    MenuAudience,
    NavigationItem,
    PageDefinition,
    Plan,
    PlanMenuItem,
)
from apps.subscriptions.plan_catalog import ADMIN_MENUS, FEATURE_CATALOG

MODULES = [
    ("hr_core", "HR Core", "users", 1),
    ("payroll", "Payroll", "wallet", 2),
    ("performance", "Performance", "target", 3),
    ("attendance", "Attendance", "calendar-check", 4),
    ("leave", "Leave Management", "palmtree", 5),
    ("lms", "LMS", "graduation-cap", 6),
    ("assets", "Asset Management", "package", 7),
    ("projects", "Project Management", "folder-kanban", 8),
    ("analytics", "Analytics", "bar-chart-3", 9),
    ("automation", "Workflow Automation", "git-branch", 10),
    ("advanced", "Advanced", "building-2", 11),
]

MODULE_FEATURE_MAP = {
    "core": "hr_core",
    "payroll": "payroll",
    "talent": "performance",
    "attendance": "attendance",
    "operations": "projects",
    "analytics": "analytics",
    "automation": "automation",
    "advanced": "advanced",
    "security": "advanced",
    "integrations": "advanced",
    "support": "hr_core",
    "finance": "payroll",
    "structure": "hr_core",
    "admin": "hr_core",
    "reports": "analytics",
}

PAGES = [
    ("staff_list", "Employee List", "dashboard:staff_list", "employees"),
    ("staff_create", "Employee Create", "dashboard:staff_create", "employees"),
    ("staff_edit", "Employee Edit", "dashboard:staff_edit", "employees"),
    ("attendance", "Attendance", "dashboard:attendance", "attendance"),
    ("payroll", "Payroll", "payroll:management", "payroll_basic"),
    ("shifts", "Shift Management", "shifts:management", "shifts"),
    ("departments", "Departments", "dashboard:departments", "departments"),
    ("settings", "Organization Settings", "dashboard:settings", "org_settings"),
    ("reports", "Reports", "attendance:reports", "reports_basic"),
]

FIELDS = [
    ("salary", "Salary Field", "employee_form", "employees"),
    ("bank_details", "Bank Details", "employee_form", "employees"),
    ("emergency_contact", "Emergency Contact", "employee_form", "employees"),
    ("aadhaar", "Aadhaar", "employee_form", "employees"),
    ("pan", "PAN", "employee_form", "employees"),
]

WORKFLOWS = [
    ("approval_workflow", "Approval Workflow", ["employees"]),
    ("multi_level_approval", "Multi-Level Approval", ["approval_workflow"]),
    ("auto_escalation", "Auto Escalation", ["multi_level_approval"]),
]

DEPENDENCIES = {
    "payroll_basic": ["employees", "attendance"],
    "payroll_advanced": ["employees", "attendance", "payroll_basic"],
    "payroll_growth": ["employees", "attendance", "payroll_basic", "payroll_advanced"],
    "performance": ["employees"],
    "shifts": ["attendance"],
    "projects": ["employees"],
    "tasks": ["projects"],
    "workflows": ["employees"],
    "multi_level_approval": ["workflows"],
}


class Command(BaseCommand):
    help = "Seed master feature control catalog (modules, pages, nav, fields, roles)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding modules…")
        module_objs = {}
        for key, name, icon, order in MODULES:
            obj, _ = FeatureModule.objects.update_or_create(
                key=key, defaults={"name": name, "icon": icon, "sort_order": order, "is_globally_enabled": True, "is_active": True}
            )
            module_objs[key] = obj

        self.stdout.write("Linking features to modules + dependencies…")
        for key, meta in FEATURE_CATALOG.items():
            mod_key = MODULE_FEATURE_MAP.get(meta.get("category", ""), "hr_core")
            FeatureDefinition.objects.filter(key=key).update(
                module=module_objs.get(mod_key),
                category=meta.get("category", ""),
                depends_on=DEPENDENCIES.get(key, []),
                is_globally_enabled=True,
            )

        for key, name, url, feat_key in PAGES:
            feat = FeatureDefinition.objects.filter(key=feat_key).first()
            PageDefinition.objects.update_or_create(
                key=key,
                defaults={"name": name, "url_name": url, "feature": feat, "is_globally_enabled": True},
            )

        self.stdout.write("Seeding workflow features…")
        for key, name, deps in WORKFLOWS:
            FeatureDefinition.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "feature_type": FeatureType.WORKFLOW,
                    "depends_on": deps,
                    "is_globally_enabled": True,
                    "is_active": True,
                },
            )

        self.stdout.write("Seeding field definitions…")
        for key, name, form_ctx, feat_key in FIELDS:
            feat = FeatureDefinition.objects.filter(key=feat_key).first()
            FieldDefinition.objects.update_or_create(
                key=key,
                defaults={"name": name, "form_context": form_ctx, "feature": feat, "is_globally_visible": key not in ("aadhaar", "pan")},
            )

        self.stdout.write("Seeding role permissions…")
        for feat in FeatureDefinition.objects.filter(is_active=True):
            for role, default in (
                ("ADMIN", True),
                ("HR", True),
                ("EMPLOYEE", feat.key in ("attendance", "leave", "payroll_basic", "payroll_growth", "employee_self_service", "dashboard")),
            ):
                FeatureRolePermission.objects.update_or_create(
                    feature=feat, role=role, defaults={"is_allowed": default}
                )

        self.stdout.write("Syncing navigation items from plan menus…")
        NavigationItem.objects.all().delete()
        for slug, menus in ADMIN_MENUS.items():
            plan = Plan.objects.filter(slug=slug).first()
            if not plan:
                continue
            for order, row in enumerate(menus):
                label, icon, url_name, feature_key, query, active_views, roles, *rest = row
                group_label = rest[0] if rest else ""
                for role in roles:
                    NavigationItem.objects.create(
                        plan=plan,
                        label=label,
                        icon=icon,
                        url_name=url_name,
                        query_string=query or "",
                        feature_key=feature_key or "",
                        group_label=group_label,
                        sort_order=order,
                        is_visible=True,
                        audience=role,
                        active_views=list(active_views),
                        keywords=[label.lower()],
                    )

        self.stdout.write(self.style.SUCCESS("Feature control catalog seeded."))
