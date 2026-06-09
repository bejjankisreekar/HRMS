"""
Default feature keys and plan menu definitions.

Seeded into the database via `seed_plan_features` — editable later from Super Admin
without code changes.

Three plans: Basic, Professional, Growth.
"""

from __future__ import annotations

# ── Feature catalog (key → metadata) ───────────────────────────────────────

FEATURE_CATALOG: dict[str, dict] = {
    "dashboard": {"name": "Dashboard", "category": "core"},
    "employees": {"name": "Employees", "category": "core"},
    "departments": {"name": "Departments", "category": "core"},
    "attendance": {"name": "Attendance", "category": "core"},
    "leave": {"name": "Leave Management", "category": "core"},
    "payroll_basic": {"name": "Basic Payroll", "category": "payroll"},
    "payroll_advanced": {"name": "Advanced Payroll", "category": "payroll"},
    "holidays": {"name": "Holidays", "category": "core"},
    "announcements": {"name": "Announcements", "category": "core"},
    "employee_self_service": {"name": "Employee Self Service", "category": "core"},
    "reports_basic": {"name": "Basic Reports", "category": "reports"},
    "reports_advanced": {"name": "Advanced Reports", "category": "reports"},
    "custom_reports": {"name": "Custom Reports", "category": "reports"},
    "org_settings": {"name": "Organization Settings", "category": "admin"},
    "performance": {"name": "Performance Management", "category": "talent"},
    "documents": {"name": "Employee Documents", "category": "core"},
    "shifts": {"name": "Shift Management", "category": "attendance"},
    "expenses": {"name": "Expense Claims", "category": "finance"},
    "org_hierarchy": {"name": "Organization Hierarchy", "category": "structure"},
    "grades": {"name": "Grade Management", "category": "structure"},
    "designations": {"name": "Designation Management", "category": "structure"},
    "analytics_basic": {"name": "Basic Analytics", "category": "analytics"},
    "analytics_advanced": {"name": "Advanced Analytics", "category": "analytics"},
    "assets": {"name": "Asset Management", "category": "operations"},
    "projects": {"name": "Project Management", "category": "operations"},
    "tasks": {"name": "Task Management", "category": "operations"},
    "timesheets": {"name": "Timesheets", "category": "operations"},
    "workflows": {"name": "Workflow Automation", "category": "automation"},
    "audit_logs": {"name": "Audit Logs", "category": "security"},
    "api_access": {"name": "API Access", "category": "integrations"},
    "mobile_app": {"name": "Mobile App Access", "category": "integrations"},
    "biometric": {"name": "Biometric Integration", "category": "integrations"},
    "helpdesk": {"name": "Helpdesk / Tickets", "category": "support"},
    "multi_branch": {"name": "Multi Branch", "category": "advanced"},
    "multi_company": {"name": "Multi Company", "category": "advanced"},
    "lms": {"name": "Learning Management", "category": "advanced"},
    "compliance": {"name": "Compliance Center", "category": "advanced"},
    "workforce_planning": {"name": "Workforce Planning", "category": "advanced"},
    "succession": {"name": "Succession Planning", "category": "advanced"},
    "security_center": {"name": "Security Center", "category": "advanced"},
    "sso": {"name": "SSO Authentication", "category": "advanced"},
    "custom_roles": {"name": "Custom Roles & Permissions", "category": "advanced"},
    "ai_analytics": {"name": "AI Analytics", "category": "advanced"},
    "executive_dashboard": {"name": "Executive Dashboard", "category": "advanced"},
    "integrations": {"name": "Integrations Hub", "category": "integrations"},
    "white_label": {"name": "White Label Branding", "category": "advanced"},
}

PLAN_FEATURES: dict[str, list[str]] = {
    "basic": [
        "dashboard",
        "employees",
        "departments",
        "attendance",
        "leave",
        "payroll_basic",
        "holidays",
        "announcements",
        "employee_self_service",
        "reports_basic",
        "org_settings",
    ],
    "professional": [
        "dashboard",
        "employees",
        "departments",
        "attendance",
        "leave",
        "payroll_basic",
        "payroll_advanced",
        "holidays",
        "announcements",
        "employee_self_service",
        "reports_basic",
        "reports_advanced",
        "org_settings",
        "performance",
        "documents",
        "shifts",
        "expenses",
        "org_hierarchy",
        "grades",
        "designations",
        "analytics_basic",
    ],
    "growth": [],
}

_growth_extra = [
    "assets",
    "projects",
    "tasks",
    "timesheets",
    "workflows",
    "audit_logs",
    "api_access",
    "mobile_app",
    "biometric",
    "analytics_advanced",
    "custom_reports",
    "helpdesk",
    "integrations",
    "multi_branch",
    "multi_company",
    "lms",
    "compliance",
    "workforce_planning",
    "succession",
    "security_center",
    "sso",
    "custom_roles",
    "ai_analytics",
    "executive_dashboard",
    "white_label",
]
PLAN_FEATURES["growth"] = list(
    dict.fromkeys(PLAN_FEATURES["professional"] + _growth_extra)
)

PLAN_LIMITS: dict[str, dict] = {
    "basic": {"employee_limit": 50, "storage_limit_mb": 5120},
    "professional": {"employee_limit": 250, "storage_limit_mb": 20480},
    "growth": {"employee_limit": None, "storage_limit_mb": None},
}

# Menu item tuple: label, icon, url_name, feature_key, query, active_views, roles
MenuDef = tuple[str, str, str, str, str, tuple[str, ...], tuple[str, ...]]

ADMIN_MENUS: dict[str, list[MenuDef]] = {
    "basic": [
        ("Dashboard", "layout-dashboard", "dashboard:starter_admin", "dashboard", "", ("dashboard:starter_admin", "dashboard:home"), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list", "dashboard:staff_create", "dashboard:staff_detail", "dashboard:staff_edit"), ("ADMIN", "HR")),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Payroll", "wallet", "payroll:management", "payroll_basic", "", ("payroll:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Holidays", "calendar-days", "dashboard:work_calendar", "holidays", "", ("dashboard:work_calendar", "leaves:management"), ("ADMIN", "HR")),
        ("Announcements", "megaphone", "dashboard:settings", "announcements", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Reports", "bar-chart-3", "attendance:reports", "reports_basic", "", ("attendance:reports", "dashboard:attendance_report"), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
    ],
    "professional": [
        ("Dashboard", "layout-dashboard", "dashboard:professional_admin", "dashboard", "", ("dashboard:professional_admin", "dashboard:home"), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list", "dashboard:staff_create", "dashboard:staff_detail", "dashboard:staff_edit"), ("ADMIN", "HR")),
        ("Grades & Hierarchy", "network", "dashboard:grades:hub", "grades", "", ("dashboard:grades:hub", "dashboard:grades:list"), ("ADMIN",)),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Shift Management", "calendar-clock", "shifts:management", "shifts", "", ("shifts:management", "dashboard:attendance_shifts", "dashboard:attendance_settings"), ("ADMIN", "HR")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Payroll", "wallet", "payroll:management", "payroll_advanced", "", ("payroll:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Expenses", "receipt", "dashboard:settings", "expenses", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Performance", "target", "dashboard:settings", "performance", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Documents", "folder-open", "dashboard:settings", "documents", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Holidays", "calendar-days", "dashboard:work_calendar", "holidays", "", ("dashboard:work_calendar", "leaves:management"), ("ADMIN", "HR")),
        ("Announcements", "megaphone", "dashboard:settings", "announcements", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Reports", "file-bar-chart", "attendance:reports", "reports_advanced", "", ("attendance:reports",), ("ADMIN",)),
        ("Analytics", "line-chart", "attendance:reports", "analytics_basic", "", ("attendance:reports",), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
    ],
    "growth": [
        ("Executive Dashboard", "layout-dashboard", "dashboard:professional_admin", "executive_dashboard", "", ("dashboard:professional_admin",), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        ("Workforce Management", "users-round", "dashboard:staff_list", "workforce_planning", "", ("dashboard:staff_list",), ("ADMIN",)),
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list",), ("ADMIN", "HR")),
        ("Tasks", "check-square", "dashboard:settings", "tasks", "", ("dashboard:settings",), ("HR",)),
        ("Assets", "package", "dashboard:settings", "assets", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Learning Management", "graduation-cap", "dashboard:settings", "lms", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Grades & Hierarchy", "network", "dashboard:grades:hub", "grades", "", ("dashboard:grades:hub",), ("ADMIN",)),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Shift Management", "calendar-clock", "shifts:management", "shifts", "", ("shifts:management",), ("ADMIN", "HR")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Payroll", "wallet", "payroll:management", "payroll_advanced", "", ("payroll:management",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Expenses", "receipt", "dashboard:settings", "expenses", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Performance", "target", "dashboard:settings", "performance", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Workforce Planning", "trending-up", "dashboard:settings", "workforce_planning", "", ("dashboard:settings",), ("ADMIN",)),
        ("Succession Planning", "git-branch", "dashboard:settings", "succession", "", ("dashboard:settings",), ("ADMIN",)),
        ("Compliance Center", "shield-check", "dashboard:settings", "compliance", "", ("dashboard:settings",), ("ADMIN",)),
        ("Documents", "folder-open", "dashboard:settings", "documents", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Helpdesk", "life-buoy", "dashboard:settings", "helpdesk", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Workflows", "workflow", "dashboard:settings", "workflows", "", ("dashboard:settings",), ("ADMIN",)),
        ("Reports", "file-bar-chart", "attendance:reports", "custom_reports", "", ("attendance:reports",), ("ADMIN",)),
        ("Analytics Hub", "brain", "attendance:reports", "ai_analytics", "", ("attendance:reports",), ("ADMIN",)),
        ("Audit Logs", "clipboard-list", "dashboard:settings", "audit_logs", "", ("dashboard:settings",), ("ADMIN",)),
        ("Integrations", "plug", "dashboard:settings", "integrations", "", ("dashboard:settings",), ("ADMIN",)),
        ("Security Center", "lock", "dashboard:settings", "security_center", "", ("dashboard:settings",), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
    ],
}

ADDON_FEATURE_KEYS: dict[str, list[str]] = {
    "performance": ["performance"],
    "workflow-automation": ["workflows"],
    "asset-management": ["assets"],
    "project-management": ["projects", "tasks"],
    "lms": ["lms"],
    "helpdesk": ["helpdesk"],
    "api-access": ["api_access"],
    "biometric": ["biometric"],
    "custom-branding": ["white_label"],
    "audit-logs": ["audit_logs"],
    "ai-analytics": ["ai_analytics", "analytics_advanced"],
    "payroll-advanced": ["payroll_advanced"],
    "whatsapp": ["integrations"],
    "multi-branch": ["multi_branch"],
}

FEATURE_MIN_PLAN: dict[str, str] = {}
for _slug in ("basic", "professional", "growth"):
    for _key in PLAN_FEATURES[_slug]:
        FEATURE_MIN_PLAN.setdefault(_key, _slug)
