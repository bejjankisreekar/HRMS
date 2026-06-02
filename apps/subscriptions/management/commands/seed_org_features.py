"""Seed organization feature control categories, hierarchy, and path prefixes."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.subscriptions.models import FeatureCategory, FeatureDefinition, FeatureType

CATEGORIES = [
    ("core_hr", "Core HR", "users", 1),
    ("attendance", "Attendance", "calendar-check", 2),
    ("leave", "Leave", "palmtree", 3),
    ("payroll", "Payroll", "wallet", 4),
    ("performance", "Performance", "target", 5),
    ("projects", "Projects", "folder-kanban", 6),
    ("assets", "Assets", "package", 7),
    ("learning", "Learning", "graduation-cap", 8),
    ("analytics", "Analytics", "bar-chart-3", 9),
    ("support", "Support", "life-buoy", 10),
    ("integrations", "Integrations", "plug", 11),
    ("advanced", "Advanced", "shield", 12),
]

# key, name, category_key, parent_key, icon, path_prefix, url_names, depends_on
FEATURES = [
    ("dashboard", "Dashboard", "core_hr", "", "layout-dashboard", "", ["dashboard:starter_admin", "dashboard:professional_admin"], []),
    ("employees", "Employees", "core_hr", "", "users", "/dashboard/staff/", ["dashboard:staff_list", "dashboard:staff_create"], []),
    ("departments", "Departments", "core_hr", "", "layers", "/dashboard/departments/", ["dashboard:departments"], []),
    ("designations", "Designations", "core_hr", "", "badge", "", [], []),
    ("grades", "Grades & Hierarchy", "core_hr", "", "network", "/dashboard/admin/grades/", ["dashboard:grades:hub"], []),
    ("attendance", "Attendance", "attendance", "", "calendar-check", "/dashboard/attendance/", ["dashboard:attendance"], []),
    ("shifts", "Shift Management", "attendance", "", "calendar-clock", "/shifts/", ["shifts:management"], ["attendance"]),
    ("holidays", "Holidays", "attendance", "", "calendar-days", "/dashboard/work-calendar/", ["dashboard:work_calendar", "leaves:management"], []),
    ("leave", "Leave Management", "leave", "", "palmtree", "/leave-management/", ["leaves:management", "leaves:apply"], []),
    ("payroll_basic", "Payroll", "payroll", "", "wallet", "/payroll/", ["payroll:management"], ["employees", "attendance"]),
    ("payslips", "Payslips", "payroll", "payroll_basic", "receipt", "/payroll/", ["payroll:management"], ["payroll_basic"]),
    ("performance", "Performance Reviews", "performance", "", "target", "", [], ["employees"]),
    ("performance_goals", "Goals", "performance", "performance", "flag", "", [], ["performance"]),
    ("performance_appraisals", "Appraisals", "performance", "performance", "clipboard-check", "", [], ["performance"]),
    ("projects", "Projects", "projects", "", "folder-kanban", "", [], ["employees"]),
    ("tasks", "Tasks", "projects", "projects", "check-square", "", [], ["projects"]),
    ("kanban", "Kanban Boards", "projects", "projects", "columns", "", [], ["projects"]),
    ("assets", "Asset Management", "assets", "", "package", "", [], []),
    ("lms", "LMS", "learning", "", "graduation-cap", "", [], []),
    ("reports_basic", "Reports", "analytics", "", "file-bar-chart", "/attendance/", ["attendance:reports"], []),
    ("analytics_basic", "Analytics", "analytics", "", "line-chart", "/attendance/", ["attendance:reports"], []),
    ("helpdesk", "Helpdesk", "support", "", "life-buoy", "", [], []),
    ("api_access", "API Access", "integrations", "", "code-2", "/api/", [], []),
    ("biometric", "Biometric Integration", "integrations", "", "fingerprint", "", [], []),
    ("integrations", "WhatsApp Integration", "integrations", "", "message-circle", "", [], []),
    ("audit_logs", "Audit Logs", "advanced", "", "clipboard-list", "", [], []),
    ("workflows", "Workflow Automation", "advanced", "", "git-branch", "", [], ["employees"]),
    ("multi_branch", "Multi Branch", "advanced", "", "building-2", "", [], []),
]


class Command(BaseCommand):
    help = "Seed organization feature control categories, hierarchy, and URL prefixes."

    @transaction.atomic
    def handle(self, *args, **options):
        cat_objs = {}
        for key, name, icon, order in CATEGORIES:
            obj, _ = FeatureCategory.objects.update_or_create(
                key=key, defaults={"name": name, "icon": icon, "sort_order": order, "is_active": True}
            )
            cat_objs[key] = obj

        parent_objs = {}
        for key, name, cat_key, parent_key, icon, path_prefix, url_names, depends in FEATURES:
            parent = parent_objs.get(parent_key) if parent_key else None
            feat, _ = FeatureDefinition.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "display_category": cat_objs.get(cat_key),
                    "parent": parent,
                    "icon": icon,
                    "path_prefix": path_prefix,
                    "url_names": url_names,
                    "depends_on": depends,
                    "feature_type": FeatureType.FEATURE,
                    "is_globally_enabled": True,
                    "is_active": True,
                },
            )
            parent_objs[key] = feat

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(cat_objs)} categories and {len(FEATURES)} org features."))
