"""Role-based sidebar navigation configuration.

Reorder the left nav by editing the *_NAV_ORDER lists below.
Each string must match a label defined in the matching *_nav_catalog() function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from django.urls import reverse

from apps.accounts.role_labels import role_display_label
from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.subscriptions.services.entitlements import get_org_plan, get_plan_menu_items, plan_has_menu_items

# =============================================================================
# SIDEBAR ORDER — edit these lists to change nav order (top → bottom)
# =============================================================================

SUPER_ADMIN_NAV_ORDER = [
    "Overview",
    "Organizations",
    "All users",
    "Global hierarchy",
    "Organization tree",
    "Plan features",
    "Financials",
    "Storage analytics",
    "Profile",
]

# Static (non-DB) fallback breakdown of the Payroll sidebar section — used only
# for orgs without seeded plan menus (see _dynamic_groups; real orgs use that path).
PAYROLL_ADMIN_LABELS = [
    "Payroll Dashboard", "Salary Structures", "Salary Components", "Employee Salary",
    "Payroll Cycles", "Payroll Runs", "Payslips", "Tax Management", "Form 16",
    "PF & ESI", "Professional Tax", "Loans & Advances", "Reimbursements",
    "Bonuses & Incentives", "Overtime", "Deductions", "Salary Revisions",
    "Arrears", "Final Settlement", "Payroll Reports", "Payroll Settings",
]
PAYROLL_EMPLOYEE_LABELS = [
    "Payroll Dashboard", "My Salary", "Payslips", "Form 16", "Loans & Advances", "Reimbursements",
]

# Org-Admin sidebar = core pages only. Everything else is reached from Settings.
ADMIN_NAV_ORDER = [
    "Dashboard",
    "Staff management",
    "Staff attendance",
    "Leave management",
    *PAYROLL_ADMIN_LABELS,
    "Compliance Reports",
    "HR Analytics",
    "Analytics",
    "Rule Engine",
    "Organization settings",
]

HR_NAV_ORDER = [
    "HR Analytics",
    "Team analytics",
    "Organization tree",
    "Team structure",
    "Reporting matrix",
    "My team",
    "My attendance",
    "Staff attendance",
    "Leave management",
    "Work calendar",
    "Shift management",
    *PAYROLL_ADMIN_LABELS,
    "Onboarding",
    "Offboarding",
    "Rule Engine",
    "Settings",
    "My profile",
]

EMPLOYEE_NAV_ORDER = [
    "Dashboard",
    "My team",
    "Reporting manager",
    "Department tree",
    "My profile",
    "Attendance",
    "Leave requests",
    "Payroll Dashboard",
    "My Salary",
    "Payslips",
    "Loans & Advances",
    "Reimbursements",
    "Settings",
]

# Shown to employees who lead a team (have active direct reports).
TEAM_LEAD_NAV_ORDER = [
    "Team members",
    "Team attendance",
    "Leave approvals",
    "Attendance regularizations",
]

# =============================================================================


def get_hrms_role_label(user: User) -> str:
    if not user.is_authenticated:
        return ""
    return role_display_label(user)


def _normalize_path(path: str) -> str:
    return (path or "").rstrip("/") or "/"


@dataclass
class SidebarItem:
    label: str
    icon: str
    url_name: str = ""
    url: str = "#"
    active_views: tuple[str, ...] = ()
    badge: str = ""
    roles: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    is_active: bool = False
    group_label: str = ""


@dataclass
class SidebarGroup:
    id: str
    title: str
    items: list[SidebarItem] = field(default_factory=list)
    roles: tuple[str, ...] = ()
    collapsible: bool = False


def _url(name: str, **kwargs) -> str:
    try:
        return reverse(name, kwargs=kwargs)
    except Exception:
        return "#"


def _item(
    label: str,
    icon: str,
    url_name: str,
    active_views: Sequence[str],
    roles: Sequence[str],
    badge: str = "",
    keywords: Sequence[str] = (),
    query: str = "",
    group: str = "",
) -> SidebarItem:
    views = tuple(active_views) if active_views else (url_name,)
    kw = keywords or (label.lower(),)
    url = _url(url_name)
    if query:
        url = f"{url}?{query}"
    return SidebarItem(
        label=label,
        icon=icon,
        url_name=url_name,
        url=url,
        active_views=views,
        badge=badge,
        roles=tuple(roles),
        keywords=tuple(kw),
        group_label=group,
    )


def _payroll_nav_catalog(roles: Sequence[str], *, employee: bool = False) -> dict[str, SidebarItem]:
    """Static-fallback breakdown of the Payroll sidebar section (see PAYROLL_ADMIN_LABELS /
    PAYROLL_EMPLOYEE_LABELS). Mirrors apps.subscriptions.plan_catalog's payroll rows —
    used only for orgs without seeded plan menus (_dynamic_groups covers real orgs)."""
    g = "Payroll"
    if employee:
        return {
            "Payroll Dashboard": _item("Payroll Dashboard", "layout-dashboard", "payroll:dashboard", ("payroll:dashboard", "payroll:management"), roles, group=g),
            "Payslips": _item("Payslips", "file-text", "payroll:payslips", ("payroll:payslips",), roles, group=g),
            "Form 16": _item("Form 16", "file-badge", "payroll:form16", ("payroll:form16",), roles, group=g),
            "Loans & Advances": _item("Loans & Advances", "hand-coins", "payroll:loans", ("payroll:loans",), roles, group=g),
            "Reimbursements": _item("Reimbursements", "receipt", "payroll:reimbursements", ("payroll:reimbursements",), roles, group=g),
        }
    return {
        "Payroll Dashboard": _item("Payroll Dashboard", "layout-dashboard", "payroll:dashboard", ("payroll:dashboard", "payroll:management"), roles, group=g),
        "Salary Structures": _item("Salary Structures", "layers", "payroll:salary_structures", ("payroll:salary_structures", "payroll:salary_structures_bulk"), roles, group=g),
        "Salary Components": _item("Salary Components", "puzzle", "payroll:components", ("payroll:components",), roles, group=g),
        "Employee Salary": _item("Employee Salary", "user-cog", "payroll:salary_structures", ("payroll:salary_structures", "payroll:employee_financials"), roles, group=g),
        "Payroll Cycles": _item("Payroll Cycles", "repeat", "payroll:cycles", ("payroll:cycles",), roles, group=g),
        "Payroll Runs": _item("Payroll Runs", "play-circle", "payroll:runs", ("payroll:runs",), roles, group=g),
        "Payslips": _item("Payslips", "file-text", "payroll:payslips", ("payroll:payslips",), roles, group=g),
        "Tax Management": _item("Tax Management", "percent", "payroll:tax_management", ("payroll:tax_management",), roles, group=g),
        "Form 16": _item("Form 16", "file-badge", "payroll:form16", ("payroll:form16",), roles, group=g),
        "PF & ESI": _item("PF & ESI", "shield-check", "payroll:compliance", ("payroll:compliance",), roles, query="report=pf", group=g),
        "Professional Tax": _item("Professional Tax", "landmark", "payroll:compliance", ("payroll:compliance",), roles, query="report=pt", group=g),
        "Loans & Advances": _item("Loans & Advances", "hand-coins", "payroll:loans", ("payroll:loans",), roles, group=g),
        "Reimbursements": _item("Reimbursements", "receipt", "payroll:reimbursements", ("payroll:reimbursements",), roles, group=g),
        "Bonuses & Incentives": _item("Bonuses & Incentives", "gift", "payroll:bonuses", ("payroll:bonuses",), roles, group=g),
        "Overtime": _item("Overtime", "clock", "payroll:overtime", ("payroll:overtime",), roles, group=g),
        "Deductions": _item("Deductions", "minus-circle", "payroll:deductions", ("payroll:deductions",), roles, group=g),
        "Salary Revisions": _item("Salary Revisions", "trending-up", "payroll:revisions", ("payroll:revisions",), roles, group=g),
        "Arrears": _item("Arrears", "git-commit", "payroll:arrears", ("payroll:arrears",), roles, group=g),
        "Final Settlement": _item("Final Settlement", "log-out", "payroll:final_settlement", ("payroll:final_settlement",), roles, group=g),
        "Payroll Reports": _item("Payroll Reports", "bar-chart-3", "payroll:reports", ("payroll:reports", "payroll:report"), roles, group=g),
        "Payroll Settings": _item("Payroll Settings", "settings", "payroll:settings", ("payroll:settings",), roles, group=g),
    }


def _slugify_group(label: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in label.lower()).strip("-") or "group"


def _bucket_items_into_groups(
    items: Sequence[SidebarItem],
    group_roles: Sequence[str],
) -> list[SidebarGroup]:
    """Split a flat item list into the main flat group plus one collapsible
    SidebarGroup per distinct non-blank `group_label` (order of first appearance)."""
    main_items: list[SidebarItem] = []
    grouped: dict[str, list[SidebarItem]] = {}
    group_order: list[str] = []
    for item in items:
        if item.group_label:
            if item.group_label not in grouped:
                grouped[item.group_label] = []
                group_order.append(item.group_label)
            grouped[item.group_label].append(item)
        else:
            main_items.append(item)

    groups = [
        SidebarGroup(id="nav", title="", roles=tuple(group_roles), items=main_items)
    ]
    for label in group_order:
        groups.append(
            SidebarGroup(
                id=_slugify_group(label),
                title=label,
                roles=tuple(group_roles),
                items=grouped[label],
                collapsible=True,
            )
        )
    return groups


def _groups_from_order(
    order: Sequence[str],
    catalog: dict[str, SidebarItem],
    group_roles: Sequence[str],
) -> list[SidebarGroup]:
    """Build nav groups from an ordered label list + item catalog — items sharing
    a `group_label` are split into their own collapsible section."""
    items: list[SidebarItem] = []
    for label in order:
        item = catalog.get(label)
        if item is not None:
            items.append(item)
    return _bucket_items_into_groups(items, group_roles)


def _owns_destination(item: SidebarItem) -> int:
    """How strong an item's claim is on its own URL.

    Several features have no page of their own yet and link to a shared landing page
    (Settings) as a placeholder. Those claim only the landing route, while the feature
    that actually owns the page also claims its sub-routes. Ranking by the number of
    claimed routes therefore keeps the real owner and drops the placeholders.
    """
    return len(item.active_views)


def _dedupe_items_by_url(groups: list[SidebarGroup]) -> list[SidebarGroup]:
    """Keep one nav entry per URL so the sidebar shows unique destinations.

    Where several entries share a URL, the one that owns the destination wins rather
    than whichever happened to sort first — otherwise a placeholder can stand in for a
    page it does not represent, and take that page's active highlight with it.
    """
    best_by_url: dict[str, SidebarItem] = {}
    for group in groups:
        for item in group.items:
            if not item.url or item.url == "#":
                continue
            incumbent = best_by_url.get(item.url)
            if incumbent is None or _owns_destination(item) > _owns_destination(incumbent):
                best_by_url[item.url] = item

    seen: set[str] = set()
    result: list[SidebarGroup] = []
    for group in groups:
        unique_items: list[SidebarItem] = []
        for item in group.items:
            if not item.url or item.url == "#" or item.url in seen:
                continue
            if best_by_url[item.url] is not item:
                continue
            seen.add(item.url)
            unique_items.append(item)
        if unique_items:
            result.append(
                SidebarGroup(
                    id=group.id,
                    title=group.title,
                    items=unique_items,
                    roles=group.roles,
                    collapsible=group.collapsible,
                )
            )
    return result


def _set_single_active(
    groups: list[SidebarGroup],
    current_view: str,
    current_path: str = "",
) -> None:
    """Highlight exactly one item — the best match for the current route."""
    for group in groups:
        for item in group.items:
            item.is_active = False

    if not current_view and not current_path:
        return

    norm_path = _normalize_path(current_path)
    best: SidebarItem | None = None
    best_score = -1

    for group in groups:
        for item in group.items:
            score = -1
            if item.url and item.url != "#":
                norm_url = _normalize_path(item.url)
                if norm_path == norm_url:
                    score = 1100
                elif norm_path.startswith(norm_url + "/"):
                    score = 1050 - len(norm_url)

            if current_view == item.url_name:
                score = max(score, 1000)
            elif current_view in item.active_views:
                view_score = 800 - len(item.active_views)
                if item.active_views and current_view == item.active_views[0]:
                    view_score += 40
                score = max(score, view_score)

            if score > best_score:
                best_score = score
                best = item

    if best:
        best.is_active = True


def build_sidebar_menu(user: User, current_view: str, current_path: str = "") -> dict:
    role = user.role if user.is_authenticated else ""

    if role == User.Role.SUPER_ADMIN:
        groups = _super_admin_groups()
    elif role == User.Role.ADMIN:
        groups = _admin_groups(user)
    elif role == User.Role.HR:
        groups = _hr_groups(user)
    else:
        groups = _employee_groups(user)

    groups = _dedupe_items_by_url(groups)
    _set_single_active(groups, current_view, current_path)

    flat_search = []
    for g in groups:
        for item in g.items:
            flat_search.append(
                {
                    "label": item.label,
                    "url": item.url,
                    "icon": item.icon,
                    "group": g.title,
                    "keywords": " ".join(item.keywords),
                }
            )

    nav_accent = ""
    if current_view in ("attendance:reports", "attendance:reports_employee"):
        nav_accent = "analytics"

    return {
        "groups": groups,
        "search_items": flat_search,
        "role_label": get_hrms_role_label(user),
        "is_super": role == User.Role.SUPER_ADMIN,
        "nav_accent": nav_accent,
    }


# ── Item catalogs (link targets, icons, active routes) ────────────────────────


def _super_admin_nav_catalog() -> dict[str, SidebarItem]:
    r = (User.Role.SUPER_ADMIN,)
    return {
        "Overview": _item("Overview", "layout-dashboard", "dashboard:super", ("dashboard:super",), r),
        "Organizations": _item(
            "Organizations",
            "building-2",
            "dashboard:super_organizations",
            (
                "dashboard:super_organizations",
                "dashboard:super_organization_detail",
                "dashboard:super_organization_edit",
                "dashboard:super_organization_create",
                "dashboard:super_organization_delete",
                "dashboard:storage:hub",
                "dashboard:storage:resources",
                "dashboard:storage:file_audits",
                "dashboard:storage:usage",
            ),
            r,
        ),
        "All users": _item(
            "All users",
            "users",
            "dashboard:super_users",
            (
                "dashboard:super_users",
                "dashboard:super_user_edit",
                "dashboard:super_user_delete",
            ),
            r,
        ),
        "Global hierarchy": _item(
            "Global hierarchy",
            "globe-2",
            "dashboard:super_org_global",
            ("dashboard:super_org_global", "dashboard:super_org_tree"),
            r,
        ),
        "Organization tree": _item(
            "Organization tree",
            "git-branch",
            "dashboard:super_org_tree",
            ("dashboard:super_org_tree",),
            r,
        ),
        "Plan features": _item(
            "Plan features",
            "table-2",
            "dashboard:plans:matrix",
            (
                "dashboard:plans:matrix",
                "dashboard:plans:detail",
            ),
            r,
        ),
        "Financials": _item(
            "Financials",
            "indian-rupee",
            "dashboard:financials:hub",
            (
                "dashboard:financials:hub",
                "dashboard:financials:subscriptions",
                "dashboard:financials:plans",
                "dashboard:financials:addons",
                "dashboard:financials:payments",
                "dashboard:financials:invoices",
                "dashboard:financials:analytics",
                "dashboard:financials:usage",
                "dashboard:financials:audit",
            ),
            r,
        ),
        "Storage analytics": _item(
            "Storage analytics",
            "hard-drive",
            "dashboard:storage:hub",
            (
                "dashboard:storage:hub",
                "dashboard:storage:resources",
                "dashboard:storage:file_audits",
                "dashboard:storage:usage",
            ),
            r,
        ),
        "Profile": _item("Profile", "user", "accounts:profile", ("accounts:profile",), r),
    }


def _admin_nav_catalog(user: User | None) -> dict[str, SidebarItem]:
    ar = (User.Role.ADMIN,)
    hr = (User.Role.ADMIN, User.Role.HR)
    all_org = (User.Role.ADMIN, User.Role.HR, User.Role.EMPLOYEE)

    dash_url = _admin_dashboard_url_name(user) if user else "dashboard:starter_admin"
    dash_views = (
        "dashboard:starter_admin",
        "dashboard:professional_admin",
        "dashboard:org_admin",
        "dashboard:home",
    )

    return {
        "Dashboard": SidebarItem(
            label="Dashboard",
            icon="layout-dashboard",
            url_name=dash_url,
            url=_url(dash_url),
            active_views=dash_views,
            roles=ar,
            keywords=("dashboard", "overview", "home"),
        ),
        "HR Analytics": _item(
            "HR Analytics",
            "chart-no-axes-combined",
            "dashboard:hr_analytics",
            ("dashboard:hr_analytics", "dashboard:hr_analytics_data"),
            ar,
            keywords=("hr analytics", "people analytics", "attrition", "headcount",
                      "retention", "workforce", "diversity", "scorecard"),
        ),
        "Analytics": _item(
            "Analytics",
            "bar-chart-3",
            "dashboard:analytics",
            (
                "dashboard:analytics",
                "dashboard:analytics_data",
                "attendance:reports",
                "attendance:reports_employee",
                "dashboard:attendance_report",
            ),
            ar,
            keywords=("analytics", "reports", "insights", "charts", "graphs"),
        ),
        "Organization tree": _item(
            "Organization tree",
            "git-branch",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            ar,
        ),
        "Team structure": _item(
            "Team structure",
            "users-round",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            ar,
            keywords=("team", "structure", "hierarchy"),
            query="view=team",
        ),
        "Reporting matrix": _item(
            "Reporting matrix",
            "layout-grid",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            ar,
            keywords=("matrix", "reporting"),
            query="view=matrix",
        ),
        "Staff management": _item(
            "Staff management",
            "users",
            "dashboard:staff_list",
            (
                "dashboard:staff_list",
                "dashboard:staff_create",
                "dashboard:staff_detail",
                "dashboard:staff_edit",
            ),
            hr,
        ),
        "My attendance": _item(
            "My attendance",
            "user-check",
            "dashboard:attendance",
            ("dashboard:attendance",),
            all_org,
        ),
        "Staff attendance": _item(
            "Staff attendance",
            "calendar-check",
            "dashboard:attendance_team",
            ("dashboard:attendance_team",),
            hr,
        ),
        "Digital Register": _item(
            "Digital Register",
            "book-open",
            "dashboard:digital_register",
            ("dashboard:digital_register",),
            hr,
            keywords=("register", "muster", "attendance book", "ledger", "monthly"),
        ),
        "Leave management": _item(
            "Leave management",
            "palmtree",
            "leaves:management",
            ("leaves:management",),
            all_org,
        ),
        "Work calendar": _item(
            "Work calendar",
            "calendar-days",
            "dashboard:work_calendar",
            ("dashboard:work_calendar",),
            hr,
            keywords=("weekend", "holiday", "calendar", "working days"),
        ),
        "Shift management": _item(
            "Shift management",
            "calendar-clock",
            "shifts:management",
            ("shifts:management",),
            hr,
        ),
        **_payroll_nav_catalog(hr),
        "Onboarding": _item(
            "Onboarding",
            "user-plus",
            "lifecycle:onboarding",
            ("lifecycle:onboarding",),
            hr,
        ),
        "Offboarding": _item(
            "Offboarding",
            "user-minus",
            "lifecycle:offboarding",
            ("lifecycle:offboarding",),
            hr,
        ),
        "Compliance Reports": _item(
            "Compliance Reports",
            "shield-check",
            "payroll:compliance",
            ("payroll:compliance",),
            ar,
            keywords=("pf", "esi", "tds", "professional tax", "form 16", "statutory", "filing", "compliance"),
        ),
        "Rule Engine": _item(
            "Rule Engine",
            "sliders-horizontal",
            "ruleengine:management",
            (
                "ruleengine:management",
                "ruleengine:builder_create",
                "ruleengine:builder_edit",
                "ruleengine:test",
                "ruleengine:logs",
            ),
            hr,
            keywords=("rules", "automation", "workflow", "conditions", "actions", "policy"),
        ),
        "Organization settings": _item(
            "Organization settings",
            "building",
            "dashboard:settings",
            ("dashboard:settings", "dashboard:departments"),
            ar,
            keywords=("organization", "roles", "permissions", "integrations", "departments"),
        ),
        "Grades & hierarchy": _item(
            "Grades & hierarchy",
            "network",
            "dashboard:grades:hub",
            (
                "dashboard:grades:hub",
                "dashboard:grades:list",
                "dashboard:grades:designations",
                "dashboard:grades:hierarchy",
                "dashboard:grades:career",
            ),
            ar,
            keywords=("grade", "designation", "hierarchy", "level", "promotion"),
        ),
        "Work shifts": _item(
            "Work shifts",
            "clock",
            "dashboard:attendance_shifts",
            ("dashboard:attendance_shifts",),
            ar,
        ),
        "My profile": _item(
            "My profile",
            "user",
            "accounts:profile",
            ("accounts:profile",),
            ar,
        ),
    }


def _hr_nav_catalog() -> dict[str, SidebarItem]:
    hr = (User.Role.HR,)
    all_org = (User.Role.HR, User.Role.EMPLOYEE)
    return {
        "HR Analytics": _item(
            "HR Analytics",
            "chart-no-axes-combined",
            "dashboard:hr_analytics",
            ("dashboard:hr_analytics", "dashboard:hr_analytics_data"),
            hr,
            keywords=("hr analytics", "people analytics", "attrition", "headcount",
                      "retention", "workforce", "diversity", "scorecard"),
        ),
        "Team analytics": _item(
            "Team analytics",
            "bar-chart-3",
            "dashboard:analytics",
            (
                "dashboard:analytics",
                "attendance:reports",
                "attendance:reports_employee",
                "dashboard:attendance_report",
            ),
            hr,
        ),
        "Organization tree": _item(
            "Organization tree",
            "git-branch",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            hr,
        ),
        "Team structure": _item(
            "Team structure",
            "users-round",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            hr,
            query="view=team",
        ),
        "Reporting matrix": _item(
            "Reporting matrix",
            "layout-grid",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            hr,
            query="view=matrix",
        ),
        "My team": _item(
            "My team",
            "users",
            "dashboard:staff_list",
            ("dashboard:staff_list", "dashboard:staff_create"),
            hr,
        ),
        "My attendance": _item(
            "My attendance",
            "user-check",
            "dashboard:attendance",
            ("dashboard:attendance",),
            hr,
        ),
        "Staff attendance": _item(
            "Staff attendance",
            "calendar-check",
            "dashboard:attendance_team",
            ("dashboard:attendance_team",),
            hr,
        ),
        "Digital Register": _item(
            "Digital Register",
            "book-open",
            "dashboard:digital_register",
            ("dashboard:digital_register",),
            hr,
            keywords=("register", "muster", "attendance book", "ledger", "monthly"),
        ),
        "Leave management": _item(
            "Leave management",
            "palmtree",
            "leaves:management",
            ("leaves:management",),
            all_org,
        ),
        "Work calendar": _item(
            "Work calendar",
            "calendar-days",
            "dashboard:work_calendar",
            ("dashboard:work_calendar",),
            hr,
            keywords=("weekend", "holiday", "calendar", "working days"),
        ),
        "Shift management": _item(
            "Shift management",
            "calendar-clock",
            "shifts:management",
            ("shifts:management",),
            hr,
        ),
        **_payroll_nav_catalog(hr),
        "Onboarding": _item(
            "Onboarding",
            "user-plus",
            "lifecycle:onboarding",
            ("lifecycle:onboarding",),
            hr,
        ),
        "Offboarding": _item(
            "Offboarding",
            "user-minus",
            "lifecycle:offboarding",
            ("lifecycle:offboarding",),
            hr,
        ),
        "Rule Engine": _item(
            "Rule Engine",
            "sliders-horizontal",
            "ruleengine:management",
            (
                "ruleengine:management",
                "ruleengine:builder_create",
                "ruleengine:builder_edit",
                "ruleengine:test",
                "ruleengine:logs",
            ),
            hr,
            keywords=("rules", "automation", "workflow", "conditions", "actions", "policy"),
        ),
        "Settings": _item(
            "Settings",
            "settings",
            "dashboard:settings",
            ("dashboard:settings",),
            hr,
        ),
        "My profile": _item(
            "My profile",
            "user",
            "accounts:profile",
            ("accounts:profile",),
            hr,
        ),
    }


def _employee_nav_catalog() -> dict[str, SidebarItem]:
    em = (User.Role.EMPLOYEE,)
    return {
        "Dashboard": _item(
            "Dashboard",
            "layout-dashboard",
            "dashboard:employee",
            ("dashboard:employee", "dashboard:home"),
            em,
        ),
        "My team": _item(
            "My team",
            "users-round",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            em,
            query="view=team&focus=me",
        ),
        "Reporting manager": _item(
            "Reporting manager",
            "user-check",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            em,
            query="focus=manager",
        ),
        "Department tree": _item(
            "Department tree",
            "git-branch",
            "dashboard:orgchart:tree",
            ("dashboard:orgchart:tree",),
            em,
            query="view=department",
        ),
        "My profile": _item("My profile", "user", "accounts:profile", ("accounts:profile",), em),
        "Attendance": _item(
            "My attendance",
            "calendar-check",
            "dashboard:attendance",
            ("dashboard:attendance",),
            em,
        ),
        "Leave requests": _item(
            "Leave requests",
            "palmtree",
            "leaves:management",
            ("leaves:management",),
            em,
        ),
        **_payroll_nav_catalog(em, employee=True),
        "Settings": _item(
            "Settings",
            "settings",
            "dashboard:settings",
            ("dashboard:settings",),
            em,
        ),
    }


def _team_lead_nav_catalog() -> dict[str, SidebarItem]:
    em = (User.Role.EMPLOYEE,)
    return {
        "Team members": _item(
            "Team members",
            "users",
            "dashboard:team_members",
            ("dashboard:team_members",),
            em,
            keywords=("team", "directory", "reports", "members"),
        ),
        "Team attendance": _item(
            "Team attendance",
            "calendar-check",
            "dashboard:team_attendance",
            ("dashboard:team_attendance", "dashboard:team_attendance_export"),
            em,
        ),
        "Leave approvals": _item(
            "Leave approvals",
            "check-circle",
            "dashboard:team_leave_approvals",
            ("dashboard:team_leave_approvals", "dashboard:team_leave_decision"),
            em,
            keywords=("approve", "leave", "approvals"),
        ),
        "Attendance regularizations": _item(
            "Attendance regularizations",
            "clock",
            "dashboard:team_regularizations",
            ("dashboard:team_regularizations", "dashboard:team_regularization_decision"),
            em,
            keywords=("regularization", "correction", "attendance"),
        ),
    }


def _team_lead_group() -> SidebarGroup:
    catalog = _team_lead_nav_catalog()
    return SidebarGroup(
        id="team",
        title="My team",
        roles=(User.Role.EMPLOYEE,),
        items=[catalog[label] for label in TEAM_LEAD_NAV_ORDER if label in catalog],
    )


def _super_admin_groups() -> list[SidebarGroup]:
    return _groups_from_order(
        SUPER_ADMIN_NAV_ORDER,
        _super_admin_nav_catalog(),
        (User.Role.SUPER_ADMIN,),
    )


_DASHBOARD_HOME_VIEWS: dict[str, frozenset[str]] = {
    User.Role.SUPER_ADMIN: frozenset({"dashboard:super", "dashboard:home"}),
    User.Role.ADMIN: frozenset(
        {
            "dashboard:starter_admin",
            "dashboard:professional_admin",
            "dashboard:org_admin",
            "dashboard:home",
        }
    ),
    User.Role.HR: frozenset({"dashboard:attendance_team", "dashboard:home"}),
    User.Role.EMPLOYEE: frozenset({"dashboard:employee", "dashboard:home"}),
}


def get_dashboard_home_url(user: User) -> str:
    if not user.is_authenticated:
        return "/"
    role = user.role
    if role == User.Role.SUPER_ADMIN:
        return _url("dashboard:super")
    if role == User.Role.ADMIN:
        return _url(_admin_dashboard_url_name(user))
    if role == User.Role.HR:
        return _url("dashboard:attendance_team")
    return _url("dashboard:employee")


def is_dashboard_home_view(user: User, view_name: str) -> bool:
    if not user.is_authenticated or not view_name:
        return False
    return view_name in _DASHBOARD_HOME_VIEWS.get(user.role, frozenset())


def _admin_dashboard_url_name(user: User) -> str:
    # One unified admin dashboard for every plan (Basic/Professional/Growth).
    return "dashboard:professional_admin"


def _sidebar_item_from_menu_row(row) -> SidebarItem:
    views = tuple(row.active_views) if row.active_views else (row.url_name,)
    kw = tuple(row.keywords) if row.keywords else (row.label.lower(),)
    url = _url(row.url_name)
    if row.query_string:
        url = f"{url}?{row.query_string}"
    return SidebarItem(
        label=row.label,
        icon=row.icon,
        url_name=row.url_name,
        url=url,
        active_views=views,
        roles=(row.audience,),
        keywords=kw,
        group_label=getattr(row, "group_label", "") or "",
    )


def _dynamic_groups(user: User, group_roles: Sequence[str]) -> list[SidebarGroup] | None:
    org = user.organization
    if not org:
        return None
    plan = get_org_plan(org)
    if not plan or not plan_has_menu_items(plan):
        return None
    db_items = get_plan_menu_items(org, user.role)
    if not db_items:
        return None
    items = [_sidebar_item_from_menu_row(row) for row in db_items]
    return _bucket_items_into_groups(items, group_roles)


def _admin_groups(user: User | None = None) -> list[SidebarGroup]:
    if user and user.organization_id:
        dynamic = _dynamic_groups(user, (User.Role.ADMIN,))
        if dynamic:
            return dynamic
    return _groups_from_order(
        ADMIN_NAV_ORDER,
        _admin_nav_catalog(user),
        (User.Role.ADMIN,),
    )


def _hr_groups(user: User | None = None) -> list[SidebarGroup]:
    if user and user.organization_id:
        dynamic = _dynamic_groups(user, (User.Role.HR,))
        if dynamic:
            return dynamic
    return _groups_from_order(
        HR_NAV_ORDER,
        _hr_nav_catalog(),
        (User.Role.HR,),
    )


def _ensure_employee_dashboard_item(groups: list[SidebarGroup]) -> None:
    """Plan-driven nav may omit the ESS dashboard — always show it first for employees."""
    dashboard = _employee_nav_catalog()["Dashboard"]
    for group in groups:
        if any(item.url_name == dashboard.url_name for item in group.items):
            return
    if groups:
        groups[0].items.insert(0, dashboard)


def _employee_groups(user: User | None = None) -> list[SidebarGroup]:
    if user and user.organization_id:
        dynamic = _dynamic_groups(user, (User.Role.EMPLOYEE,))
        if dynamic:
            _ensure_employee_dashboard_item(dynamic)
            _append_team_lead_group(dynamic, user)
            return dynamic
    groups = _groups_from_order(
        EMPLOYEE_NAV_ORDER,
        _employee_nav_catalog(),
        (User.Role.EMPLOYEE,),
    )
    _append_team_lead_group(groups, user)
    return groups


def _append_team_lead_group(groups: list[SidebarGroup], user: User | None) -> None:
    """Employees with active direct reports also get team-management links."""
    from apps.accounts.hierarchy import has_direct_reports

    if user and user.organization_id and has_direct_reports(user):
        groups.append(_team_lead_group())
