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
    "payroll_growth": {"name": "Complete Payroll Suite", "category": "payroll"},
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
    "payroll_growth",
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

# Menu item tuple: label, icon, url_name, feature_key, query, active_views, roles[, group_label]
# The 8th element (group_label) is optional — omit it for a flat top-level item.
MenuDef = tuple[str, str, str, str, str, tuple[str, ...], tuple[str, ...]]

# ── Payroll sidebar section — 21 items, tiered across Basic/Professional/Growth ──
_ADMIN_HR = ("ADMIN", "HR")
_EMPLOYEE = ("EMPLOYEE",)

# Basic tier: 8 items, visible to Admin/HR (+ Employee self-service subset).
_PAYROLL_BASIC_ADMIN: list[MenuDef] = [
    ("Payroll Dashboard", "layout-dashboard", "payroll:dashboard", "payroll_basic", "", ("payroll:dashboard", "payroll:management"), _ADMIN_HR, "Payroll"),
    ("Salary Structures", "layers", "payroll:salary_structures", "payroll_basic", "", ("payroll:salary_structures", "payroll:salary_structures_bulk"), _ADMIN_HR, "Payroll"),
    ("Salary Components", "puzzle", "payroll:components", "payroll_basic", "", ("payroll:components",), _ADMIN_HR, "Payroll"),
    ("Employee Salary", "user-cog", "payroll:salary_structures", "payroll_basic", "", ("payroll:salary_structures", "payroll:employee_financials"), _ADMIN_HR, "Payroll"),
    ("Payroll Cycles", "repeat", "payroll:cycles", "payroll_basic", "", ("payroll:cycles",), _ADMIN_HR, "Payroll"),
    ("Payroll Runs", "play-circle", "payroll:runs", "payroll_basic", "", ("payroll:runs",), _ADMIN_HR, "Payroll"),
    ("Payslips", "file-text", "payroll:payslips", "payroll_basic", "", ("payroll:payslips",), _ADMIN_HR, "Payroll"),
    ("Payroll Settings", "settings", "payroll:settings", "payroll_basic", "", ("payroll:settings",), _ADMIN_HR, "Payroll"),
]
_PAYROLL_BASIC_EMPLOYEE: list[MenuDef] = [
    ("Payroll Dashboard", "layout-dashboard", "payroll:dashboard", "payroll_basic", "", ("payroll:dashboard", "payroll:management"), _EMPLOYEE, "Payroll"),
    ("Payslips", "file-text", "payroll:payslips", "payroll_basic", "", ("payroll:payslips",), _EMPLOYEE, "Payroll"),
]

# Professional tier adds: statutory/tax + deductions + revisions + reports.
_PAYROLL_ADVANCED_ADMIN: list[MenuDef] = [
    ("Tax Management", "percent", "payroll:tax_management", "payroll_advanced", "", ("payroll:tax_management",), _ADMIN_HR, "Payroll"),
    ("PF & ESI", "shield-check", "payroll:compliance", "payroll_advanced", "report=pf", ("payroll:compliance",), _ADMIN_HR, "Payroll"),
    ("Professional Tax", "landmark", "payroll:compliance", "payroll_advanced", "report=pt", ("payroll:compliance",), _ADMIN_HR, "Payroll"),
    ("Deductions", "minus-circle", "payroll:deductions", "payroll_advanced", "", ("payroll:deductions",), _ADMIN_HR, "Payroll"),
    ("Salary Revisions", "trending-up", "payroll:revisions", "payroll_advanced", "", ("payroll:revisions",), _ADMIN_HR, "Payroll"),
    ("Payroll Reports", "bar-chart-3", "payroll:reports", "payroll_advanced", "", ("payroll:reports", "payroll:report"), _ADMIN_HR, "Payroll"),
]

# Growth tier adds: Form 16, loans, reimbursements, bonuses, overtime, arrears, final settlement.
_PAYROLL_GROWTH_ADMIN: list[MenuDef] = [
    ("Form 16", "file-badge", "payroll:form16", "payroll_growth", "", ("payroll:form16",), _ADMIN_HR, "Payroll"),
    ("Loans & Advances", "hand-coins", "payroll:loans", "payroll_growth", "", ("payroll:loans",), _ADMIN_HR, "Payroll"),
    ("Reimbursements", "receipt", "payroll:reimbursements", "payroll_growth", "", ("payroll:reimbursements",), _ADMIN_HR, "Payroll"),
    ("Bonuses & Incentives", "gift", "payroll:bonuses", "payroll_growth", "", ("payroll:bonuses",), _ADMIN_HR, "Payroll"),
    ("Overtime", "clock", "payroll:overtime", "payroll_growth", "", ("payroll:overtime",), _ADMIN_HR, "Payroll"),
    ("Arrears", "git-commit", "payroll:arrears", "payroll_growth", "", ("payroll:arrears",), _ADMIN_HR, "Payroll"),
    ("Final Settlement", "log-out", "payroll:final_settlement", "payroll_growth", "", ("payroll:final_settlement",), _ADMIN_HR, "Payroll"),
]
_PAYROLL_GROWTH_EMPLOYEE: list[MenuDef] = [
    ("Form 16", "file-badge", "payroll:form16", "payroll_growth", "", ("payroll:form16",), _EMPLOYEE, "Payroll"),
    ("Loans & Advances", "hand-coins", "payroll:loans", "payroll_growth", "", ("payroll:loans",), _EMPLOYEE, "Payroll"),
    ("Reimbursements", "receipt", "payroll:reimbursements", "payroll_growth", "", ("payroll:reimbursements",), _EMPLOYEE, "Payroll"),
]

PAYROLL_MENU_BASIC: list[MenuDef] = _PAYROLL_BASIC_ADMIN + _PAYROLL_BASIC_EMPLOYEE
PAYROLL_MENU_PROFESSIONAL: list[MenuDef] = PAYROLL_MENU_BASIC + _PAYROLL_ADVANCED_ADMIN
PAYROLL_MENU_GROWTH: list[MenuDef] = PAYROLL_MENU_PROFESSIONAL + _PAYROLL_GROWTH_ADMIN + _PAYROLL_GROWTH_EMPLOYEE

# Employee self-service links that were missing from the DB-seeded nav (only ever
# existed in sidebar_menu.py's static fallback, which real orgs with a seeded plan
# never use — see feedback-alpine-select-jsonscript / hrms-project-layout memory).
# Gated on "employee_self_service" (same key as the employee Dashboard row) so it's
# available on every plan tier, matching the static catalog's unconditional visibility.
_EMPLOYEE_ESS_EXTRA: list[MenuDef] = [
    ("My team", "users-round", "dashboard:orgchart:tree", "employee_self_service", "view=team&focus=me", ("dashboard:orgchart:tree",), _EMPLOYEE),
    ("Reporting manager", "user-check", "dashboard:orgchart:tree", "employee_self_service", "focus=manager", ("dashboard:orgchart:tree",), _EMPLOYEE),
    ("Department tree", "git-branch", "dashboard:orgchart:tree", "employee_self_service", "view=department", ("dashboard:orgchart:tree",), _EMPLOYEE),
    ("My profile", "user", "accounts:profile", "employee_self_service", "", ("accounts:profile",), _EMPLOYEE),
]
_EMPLOYEE_SETTINGS: MenuDef = (
    "Settings", "settings", "dashboard:settings", "employee_self_service", "", ("dashboard:settings",), _EMPLOYEE,
)

ADMIN_MENUS: dict[str, list[MenuDef]] = {
    "basic": [
        ("Dashboard", "layout-dashboard", "dashboard:starter_admin", "dashboard", "", ("dashboard:starter_admin", "dashboard:home"), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        *_EMPLOYEE_ESS_EXTRA,
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list", "dashboard:staff_create", "dashboard:staff_detail", "dashboard:staff_edit"), ("ADMIN", "HR")),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        *PAYROLL_MENU_BASIC,
        ("Holidays", "calendar-days", "dashboard:work_calendar", "holidays", "", ("dashboard:work_calendar", "leaves:management"), ("ADMIN", "HR")),
        ("Announcements", "megaphone", "dashboard:settings", "announcements", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Reports", "bar-chart-3", "attendance:reports", "reports_basic", "", ("attendance:reports", "dashboard:attendance_report"), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
        _EMPLOYEE_SETTINGS,
    ],
    "professional": [
        ("Dashboard", "layout-dashboard", "dashboard:professional_admin", "dashboard", "", ("dashboard:professional_admin", "dashboard:home"), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        *_EMPLOYEE_ESS_EXTRA,
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list", "dashboard:staff_create", "dashboard:staff_detail", "dashboard:staff_edit"), ("ADMIN", "HR")),
        ("Grades & Hierarchy", "network", "dashboard:grades:hub", "grades", "", ("dashboard:grades:hub", "dashboard:grades:list"), ("ADMIN",)),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Shift Management", "calendar-clock", "shifts:management", "shifts", "", ("shifts:management", "dashboard:attendance_shifts", "dashboard:attendance_settings"), ("ADMIN", "HR")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        *PAYROLL_MENU_PROFESSIONAL,
        ("Expenses", "receipt", "dashboard:settings", "expenses", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Performance", "target", "dashboard:settings", "performance", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Document Generator", "file-text", "documents:management", "documents", "", ("documents:management", "documents:template_create", "documents:template_edit", "documents:generate", "documents:generated_detail", "documents:audit"), ("ADMIN", "HR")),
        ("Holidays", "calendar-days", "dashboard:work_calendar", "holidays", "", ("dashboard:work_calendar", "leaves:management"), ("ADMIN", "HR")),
        ("Announcements", "megaphone", "dashboard:settings", "announcements", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Reports", "file-bar-chart", "attendance:reports", "reports_advanced", "", ("attendance:reports",), ("ADMIN",)),
        ("Analytics", "line-chart", "attendance:reports", "analytics_basic", "", ("attendance:reports",), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
        _EMPLOYEE_SETTINGS,
    ],
    "growth": [
        ("Executive Dashboard", "layout-dashboard", "dashboard:professional_admin", "executive_dashboard", "", ("dashboard:professional_admin",), ("ADMIN",)),
        ("Dashboard", "layout-dashboard", "dashboard:employee", "employee_self_service", "", ("dashboard:employee", "dashboard:home"), ("EMPLOYEE",)),
        *_EMPLOYEE_ESS_EXTRA,
        ("Workforce Management", "users-round", "dashboard:staff_list", "workforce_planning", "", ("dashboard:staff_list",), ("ADMIN",)),
        ("Employees", "users", "dashboard:staff_list", "employees", "", ("dashboard:staff_list",), ("ADMIN", "HR")),
        ("Tasks", "check-square", "dashboard:settings", "tasks", "", ("dashboard:settings",), ("HR",)),
        ("Assets", "package", "dashboard:settings", "assets", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Learning Management", "graduation-cap", "dashboard:settings", "lms", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Grades & Hierarchy", "network", "dashboard:grades:hub", "grades", "", ("dashboard:grades:hub",), ("ADMIN",)),
        ("Attendance", "calendar-check", "dashboard:attendance", "attendance", "", ("dashboard:attendance",), ("ADMIN", "HR", "EMPLOYEE")),
        ("Shift Management", "calendar-clock", "shifts:management", "shifts", "", ("shifts:management",), ("ADMIN", "HR")),
        ("Leave Management", "palmtree", "leaves:management", "leave", "", ("leaves:management",), ("ADMIN", "HR", "EMPLOYEE")),
        *PAYROLL_MENU_GROWTH,
        ("Expenses", "receipt", "dashboard:settings", "expenses", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Performance", "target", "dashboard:settings", "performance", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Workforce Planning", "trending-up", "dashboard:settings", "workforce_planning", "", ("dashboard:settings",), ("ADMIN",)),
        ("Succession Planning", "git-branch", "dashboard:settings", "succession", "", ("dashboard:settings",), ("ADMIN",)),
        ("Compliance Center", "shield-check", "dashboard:settings", "compliance", "", ("dashboard:settings",), ("ADMIN",)),
        ("Document Generator", "file-text", "documents:management", "documents", "", ("documents:management", "documents:template_create", "documents:template_edit", "documents:generate", "documents:generated_detail", "documents:audit"), ("ADMIN", "HR")),
        ("Helpdesk", "life-buoy", "dashboard:settings", "helpdesk", "", ("dashboard:settings",), ("ADMIN", "HR")),
        ("Workflows", "workflow", "dashboard:settings", "workflows", "", ("dashboard:settings",), ("ADMIN",)),
        ("Reports", "file-bar-chart", "attendance:reports", "custom_reports", "", ("attendance:reports",), ("ADMIN",)),
        ("Analytics Hub", "brain", "attendance:reports", "ai_analytics", "", ("attendance:reports",), ("ADMIN",)),
        ("Audit Logs", "clipboard-list", "dashboard:settings", "audit_logs", "", ("dashboard:settings",), ("ADMIN",)),
        ("Integrations", "plug", "dashboard:settings", "integrations", "", ("dashboard:settings",), ("ADMIN",)),
        ("Security Center", "lock", "dashboard:settings", "security_center", "", ("dashboard:settings",), ("ADMIN",)),
        ("Organization Settings", "building", "dashboard:settings", "org_settings", "", ("dashboard:settings", "dashboard:departments"), ("ADMIN",)),
        _EMPLOYEE_SETTINGS,
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
