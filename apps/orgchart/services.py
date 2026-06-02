"""Organization tree data, layouts, filters, and hierarchy updates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.hierarchy import build_forest, org_active_users, tree_users_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.leaves.models import LeaveBalance, LeaveRequest
from apps.orgchart.models import HierarchyChangeLog, Team, TeamMembership
from apps.organizations.models import Department, Organization


@dataclass
class OrgTreeFilters:
    department: str = ""
    branch: str = ""
    manager: str = ""
    status: str = ""
    team: str = ""
    designation: str = ""
    q: str = ""
    view: str = "hierarchy"

    @classmethod
    def from_request(cls, request) -> OrgTreeFilters:
        g = request.GET
        return cls(
            department=(g.get("department") or "").strip(),
            branch=(g.get("branch") or "").strip(),
            manager=(g.get("manager") or "").strip(),
            status=(g.get("status") or "").strip(),
            team=(g.get("team") or "").strip(),
            designation=(g.get("designation") or "").strip(),
            q=(g.get("q") or "").strip(),
            view=(g.get("view") or "hierarchy").strip() or "hierarchy",
        )


def can_edit_hierarchy(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR)


def _department_color(dept_id) -> str:
    palette = (
        "#8b5cf6",
        "#22d3ee",
        "#34d399",
        "#f472b6",
        "#fbbf24",
        "#60a5fa",
        "#fb7185",
        "#a3e635",
    )
    if not dept_id:
        return "#64748b"
    return palette[hash(str(dept_id)) % len(palette)]


def users_on_leave_today(user_ids: list) -> set:
    if not user_ids:
        return set()
    today = timezone.localdate()
    return set(
        LeaveRequest.objects.filter(
            user_id__in=user_ids,
            status=LeaveRequest.Status.APPROVED,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list("user_id", flat=True)
    )


def employment_status(user: User, on_leave_ids: set) -> tuple[str, str]:
    if not user.is_active:
        return "inactive", "Inactive"
    if user.pk in on_leave_ids:
        return "on_leave", "On Leave"
    return "active", "Active"


def can_manage_org_chart(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR)


def apply_filters(qs: QuerySet[User], filters: OrgTreeFilters) -> QuerySet[User]:
    if filters.department:
        qs = qs.filter(department_id=filters.department)
    if filters.branch:
        qs = qs.filter(work_location__iexact=filters.branch)
    if filters.manager:
        qs = qs.filter(reporting_manager_id=filters.manager)
    if filters.status == "active":
        qs = qs.filter(is_active=True)
    elif filters.status == "inactive":
        qs = qs.filter(is_active=False)
    if filters.designation:
        qs = qs.filter(designation__icontains=filters.designation)
    if filters.team:
        member_ids = TeamMembership.objects.filter(team_id=filters.team).values_list("user_id", flat=True)
        qs = qs.filter(pk__in=member_ids)
    if filters.q:
        qs = qs.filter(
            Q(first_name__icontains=filters.q)
            | Q(last_name__icontains=filters.q)
            | Q(employee_id__icontains=filters.q)
            | Q(email__icontains=filters.q)
            | Q(designation__icontains=filters.q)
        )
    return qs


def user_team_name(user: User) -> str:
    m = (
        TeamMembership.objects.filter(user_id=user.pk, team__is_active=True)
        .select_related("team")
        .first()
    )
    return m.team.name if m else ""


def serialize_employee_node(
    user: User,
    *,
    parent_id: str | None = None,
    on_leave_ids: set | None = None,
) -> dict[str, Any]:
    mgr = user.reporting_manager
    initials = "".join(p[0].upper() for p in user.display_name.split()[:2]) or "?"
    role_colors = {
        User.Role.ADMIN: "#8b5cf6",
        User.Role.HR: "#22d3ee",
        User.Role.EMPLOYEE: "#6366f1",
    }
    leave_set = on_leave_ids or set()
    status_key, status_label = employment_status(user, leave_set)
    dept_color = _department_color(user.department_id)
    return {
        "id": str(user.pk),
        "parentId": parent_id,
        "name": user.display_name,
        "employeeId": user.employee_id or "—",
        "designation": user.designation or user.get_role_display(),
        "department": user.department_name or "Unassigned",
        "departmentId": str(user.department_id) if user.department_id else None,
        "departmentColor": dept_color,
        "role": user.role,
        "roleColor": role_colors.get(user.role, "#6366f1"),
        "branch": user.work_location or "",
        "email": user.email,
        "phone": user.phone or "",
        "managerId": str(mgr.pk) if mgr else None,
        "managerName": mgr.display_name if mgr else "",
        "teamName": user_team_name(user),
        "initials": initials,
        "avatar": user.profile_picture.url if user.profile_picture else None,
        "online": user.is_active and status_key != "inactive",
        "status": status_key,
        "statusLabel": status_label,
        "directReports": user.direct_reports.filter(is_active=True).count(),
    }


def _flat_from_forest(forest, parent_id: str | None = None, on_leave_ids: set | None = None) -> list[dict]:
    rows: list[dict] = []
    for node in forest:
        rows.append(serialize_employee_node(node.user, parent_id=parent_id, on_leave_ids=on_leave_ids))
        rows.extend(_flat_from_forest(node.children, parent_id=str(node.user.pk), on_leave_ids=on_leave_ids))
    return rows


def build_department_view(users: list[User], on_leave_ids: set | None = None) -> list[dict]:
    """Department parent nodes with employees nested under dept heads."""
    by_dept: dict[str, list[User]] = defaultdict(list)
    for u in users:
        key = str(u.department_id) if u.department_id else "_none"
        by_dept[key].append(u)

    rows: list[dict] = []
    for dept_key, members in sorted(by_dept.items(), key=lambda x: (x[0] == "_none", x[1][0].department_name if x[1] else "")):
        dept_node_id = f"dept-{dept_key}"
        dept_name = members[0].department_name if members and dept_key != "_none" else "Unassigned"
        rows.append(
            {
                "id": dept_node_id,
                "parentId": None,
                "name": dept_name,
                "employeeId": "",
                "designation": "Department",
                "department": dept_name,
                "departmentId": dept_key if dept_key != "_none" else None,
                "role": "DEPT",
                "roleColor": "#a78bfa",
                "branch": "",
                "email": "",
                "phone": "",
                "managerId": None,
                "managerName": "",
                "teamName": "",
                "initials": dept_name[:2].upper(),
                "avatar": None,
                "online": True,
                "directReports": len(members),
                "isDepartment": True,
            }
        )
        forest = build_forest(members)
        for subtree in forest:
            rows.append(serialize_employee_node(subtree.user, parent_id=dept_node_id, on_leave_ids=on_leave_ids))
            rows.extend(_flat_from_forest(subtree.children, parent_id=str(subtree.user.pk), on_leave_ids=on_leave_ids))
    return rows


def build_team_view(users: list[User], on_leave_ids: set | None = None) -> list[dict]:
    """Team lead nodes with members (uses Team model or manager squads)."""
    team_leads = [u for u in users if any(c.reporting_manager_id == u.pk for c in users)]
    if not team_leads:
        return _flat_from_forest(build_forest(users), on_leave_ids=on_leave_ids)

    rows: list[dict] = []
    covered: set = set()

    for lead in sorted(team_leads, key=lambda u: u.display_name.lower()):
        squad = [u for u in users if u.reporting_manager_id == lead.pk]
        if not squad:
            continue
        team_node_id = f"team-{lead.pk}"
        rows.append(
            {
                "id": team_node_id,
                "parentId": None,
                "name": f"{lead.display_name}'s team",
                "employeeId": "",
                "designation": "Team",
                "department": lead.department_name,
                "departmentId": str(lead.department_id) if lead.department_id else None,
                "role": "TEAM",
                "roleColor": "#22d3ee",
                "branch": lead.work_location or "",
                "email": "",
                "phone": "",
                "managerId": None,
                "managerName": lead.display_name,
                "teamName": user_team_name(lead),
                "initials": "TM",
                "avatar": None,
                "online": True,
                "directReports": len(squad) + 1,
                "isTeam": True,
            }
        )
        rows.append(serialize_employee_node(lead, parent_id=team_node_id, on_leave_ids=on_leave_ids))
        covered.add(lead.pk)
        for m in squad:
            rows.append(serialize_employee_node(m, parent_id=str(lead.pk), on_leave_ids=on_leave_ids))
            covered.add(m.pk)

    for u in users:
        if u.pk not in covered:
            rows.append(serialize_employee_node(u, parent_id=None, on_leave_ids=on_leave_ids))
    return rows


def build_branch_view(users: list[User], on_leave_ids: set | None = None) -> list[dict]:
    by_branch: dict[str, list[User]] = defaultdict(list)
    for u in users:
        by_branch[u.work_location or "Main office"].append(u)

    rows: list[dict] = []
    for branch, members in sorted(by_branch.items()):
        branch_id = f"branch-{branch.replace(' ', '-').lower()[:40]}"
        rows.append(
            {
                "id": branch_id,
                "parentId": None,
                "name": branch,
                "employeeId": "",
                "designation": "Branch",
                "department": "",
                "departmentId": None,
                "role": "BRANCH",
                "roleColor": "#34d399",
                "branch": branch,
                "email": "",
                "phone": "",
                "managerId": None,
                "managerName": "",
                "teamName": "",
                "initials": branch[:2].upper(),
                "avatar": None,
                "online": True,
                "directReports": len(members),
                "isBranch": True,
            }
        )
        forest = build_forest(members)
        for subtree in forest:
            rows.append(serialize_employee_node(subtree.user, parent_id=branch_id, on_leave_ids=on_leave_ids))
            rows.extend(_flat_from_forest(subtree.children, parent_id=str(subtree.user.pk), on_leave_ids=on_leave_ids))
    return rows


def build_matrix_view(users: list[User], on_leave_ids: set | None = None) -> list[dict]:
    """Reporting hierarchy plus dotted peer links (same dept + level)."""
    rows = _flat_from_forest(build_forest(users), on_leave_ids=on_leave_ids)
  # matrix links built separately
    return rows


def build_chart_data(users: list[User], view_mode: str) -> dict[str, Any]:
    user_ids = [u.pk for u in users]
    on_leave_ids = users_on_leave_today(user_ids)
    view = view_mode if view_mode in VIEW_MODES else "hierarchy"
    if view == "department":
        nodes = build_department_view(users, on_leave_ids)
    elif view == "team":
        nodes = build_team_view(users, on_leave_ids)
    elif view == "branch":
        nodes = build_branch_view(users, on_leave_ids)
    elif view in ("reporting", "hierarchy", "matrix"):
        nodes = _flat_from_forest(build_forest(users), on_leave_ids=on_leave_ids)
    else:
        nodes = _flat_from_forest(build_forest(users), on_leave_ids=on_leave_ids)

    matrix_links: list[dict] = []
    if view == "matrix":
        by_dept_level: dict[tuple, list[User]] = defaultdict(list)
        user_map = {u.pk: u for u in users}
        for u in users:
            depth = _manager_depth(u, user_map)
            key = (u.department_id, depth, u.role)
            by_dept_level[key].append(u)
        for peers in by_dept_level.values():
            if len(peers) < 2:
                continue
            for i, a in enumerate(peers):
                for b in peers[i + 1 :]:
                    matrix_links.append({"source": str(a.pk), "target": str(b.pk), "dotted": True})

    return {"nodes": nodes, "matrixLinks": matrix_links, "view": view, "onLeaveCount": len(on_leave_ids)}


VIEW_MODES = ("hierarchy", "department", "team", "reporting", "branch", "matrix")


def _manager_depth(user: User, user_map: dict) -> int:
    depth = 0
    mgr = user.reporting_manager
    seen = set()
    while mgr and mgr.pk in user_map and mgr.pk not in seen:
        seen.add(mgr.pk)
        depth += 1
        mgr = mgr.reporting_manager
    return depth


def max_reporting_depth(users: list[User]) -> int:
    user_map = {u.pk: u for u in users}
    return max((_manager_depth(u, user_map) for u in users), default=0)


def span_of_control_stats(users: list[User]) -> dict[str, Any]:
    pks = [u.pk for u in users]
    if not pks:
        return {"avg": 0, "max": 0}
    counts = list(
        User.objects.filter(pk__in=pks)
        .annotate(
            report_count=Count("direct_reports", filter=Q(direct_reports__is_active=True))
        )
        .values_list("report_count", flat=True)
    )
    if not counts:
        return {"avg": 0, "max": 0}
    return {"avg": round(sum(counts) / len(counts), 1), "max": max(counts)}


def get_tree_queryset(viewer: User, filters: OrgTreeFilters) -> QuerySet[User]:
    return get_tree_queryset_for_org(viewer.organization, viewer, filters)


def get_tree_queryset_for_org(
    organization: Organization,
    viewer: User,
    filters: OrgTreeFilters,
) -> QuerySet[User]:
    if viewer.role == User.Role.SUPER_ADMIN:
        qs = org_active_users(organization)
    else:
        qs = tree_users_for(viewer)
    qs = apply_filters(qs, filters)
    return qs.select_related("reporting_manager", "department", "work_shift").prefetch_related(
        "direct_reports", "team_memberships__team"
    )


def filter_options(organization: Organization) -> dict[str, Any]:
    base = org_active_users(organization)
    departments = Department.objects.filter(organization=organization, is_active=True).order_by("name")
    branches = list(
        base.exclude(work_location="")
        .values_list("work_location", flat=True)
        .distinct()
        .order_by("work_location")
    )
    managers = base.filter(direct_reports__isnull=False).distinct().order_by("first_name", "last_name")
    designations = list(
        base.exclude(designation="")
        .values_list("designation", flat=True)
        .distinct()
        .order_by("designation")[:50]
    )
    teams = Team.objects.filter(organization=organization, is_active=True).order_by("name")
    return {
        "departments": departments,
        "branches": branches,
        "managers": managers,
        "designations": designations,
        "teams": teams,
        "view_modes": [
            ("hierarchy", "Hierarchy view"),
            ("department", "Department view"),
            ("team", "Team view"),
            ("reporting", "Reporting structure"),
            ("branch", "Branch-wise view"),
            ("matrix", "Matrix organization"),
        ],
    }


def employee_detail_payload(employee: User, viewer: User) -> dict[str, Any]:
    today = timezone.localdate()
    month_start = today.replace(day=1)

    attendance_qs = AttendanceRecord.objects.filter(
        user=employee,
        date__gte=month_start,
        date__lte=today,
    )
    present = attendance_qs.filter(status=AttendanceRecord.Status.PRESENT).count()
    absent = attendance_qs.filter(status=AttendanceRecord.Status.ABSENT).count()
    late = attendance_qs.filter(status=AttendanceRecord.Status.HALF_DAY).count()

    balances = LeaveBalance.objects.filter(user=employee, year=today.year).select_related("leave_type")
    leave_rows = [
        {
            "type": b.leave_type.name,
            "used": float(b.used_days),
            "total": float(b.allocated_days),
        }
        for b in balances
    ]

    reports = list(
        employee.direct_reports.filter(is_active=True)
        .select_related("department")[:12]
        .values("pk", "first_name", "last_name", "designation", "employee_id")
    )
    for r in reports:
        r["name"] = f"{r.pop('first_name', '')} {r.pop('last_name', '')}".strip()
        r["id"] = str(r.pop("pk"))

    chain = []
    mgr = employee.reporting_manager
    seen = set()
    while mgr and mgr.pk not in seen:
        seen.add(mgr.pk)
        chain.append({"id": str(mgr.pk), "name": mgr.display_name, "designation": mgr.designation or ""})
        mgr = mgr.reporting_manager

    shift_name = employee.work_shift.name if employee.work_shift_id else "—"

    on_leave = employee.pk in users_on_leave_today([employee.pk])
    status_key, status_label = employment_status(employee, {employee.pk} if on_leave else set())

    peers = []
    if employee.reporting_manager_id:
        peer_qs = org_active_users(employee.organization).filter(
            reporting_manager_id=employee.reporting_manager_id
        ).exclude(pk=employee.pk)[:8]
        peers = [_mini_card(u) for u in peer_qs]

    quick_actions: list[dict[str, str]] = []
    if can_manage_org_chart(viewer):
        from django.urls import reverse

        quick_actions = [
            {"label": "Staff directory", "url": reverse("dashboard:staff_list"), "icon": "users"},
            {"label": "Attendance", "url": reverse("dashboard:attendance"), "icon": "calendar-check"},
            {"label": "Leave", "url": reverse("leaves:management"), "icon": "palmtree"},
            {"label": "Payroll", "url": reverse("payroll:management"), "icon": "wallet"},
        ]
    elif viewer.role == User.Role.EMPLOYEE and employee.pk == viewer.pk:
        from django.urls import reverse

        quick_actions = [
            {"label": "My profile", "url": reverse("accounts:profile"), "icon": "user"},
            {"label": "Attendance", "url": reverse("dashboard:attendance"), "icon": "calendar-check"},
            {"label": "Leave", "url": reverse("leaves:management"), "icon": "palmtree"},
        ]

    return {
        "id": str(employee.pk),
        "name": employee.display_name,
        "employeeId": employee.employee_id or "—",
        "email": employee.email,
        "phone": employee.phone or "",
        "designation": employee.designation or employee.get_role_display(),
        "department": employee.department_name or "—",
        "branch": employee.work_location or "—",
        "role": employee.get_role_display(),
        "managerName": employee.reporting_manager.display_name if employee.reporting_manager_id else "—",
        "managerId": str(employee.reporting_manager_id) if employee.reporting_manager_id else None,
        "teamName": user_team_name(employee),
        "shift": shift_name,
        "dateOfJoining": employee.date_of_joining.isoformat() if employee.date_of_joining else None,
        "avatar": employee.profile_picture.url if employee.profile_picture else None,
        "initials": "".join(p[0].upper() for p in employee.display_name.split()[:2]) or "?",
        "status": status_key,
        "statusLabel": status_label,
        "reportingChain": chain,
        "directReports": reports,
        "peers": peers,
        "attendanceSummary": {
            "present": present,
            "absent": absent,
            "late": late,
            "period": f"{month_start.strftime('%b %Y')}",
        },
        "leaveBalances": leave_rows,
        "performanceRating": "—",
        "projects": [],
        "canEdit": can_edit_hierarchy(viewer),
        "quickActions": quick_actions,
        "profileUrl": None,
    }


def validate_manager_change(employee: User, new_manager: User | None, org: Organization) -> str | None:
    if employee.role == User.Role.ADMIN and new_manager:
        return "Organization admins cannot report to another manager."
    if new_manager and new_manager.organization_id != org.pk:
        return "Manager must belong to the same organization."
    if new_manager and new_manager.pk == employee.pk:
        return "An employee cannot report to themselves."
    if new_manager:
        walk = new_manager
        seen = {employee.pk}
        while walk:
            if walk.pk in seen:
                return "This change would create a circular reporting line."
            seen.add(walk.pk)
            walk = walk.reporting_manager
    return None


@transaction.atomic
def update_reporting_manager(
    *,
    employee: User,
    new_manager: User | None,
    changed_by: User,
    note: str = "",
) -> HierarchyChangeLog:
    prev = employee.reporting_manager
    employee.reporting_manager = new_manager
    employee.save(update_fields=["reporting_manager"])
    return HierarchyChangeLog.objects.create(
        organization=employee.organization,
        employee=employee,
        previous_manager=prev,
        new_manager=new_manager,
        changed_by=changed_by,
        note=note or "Updated from org chart",
    )


def department_heatmap(users: list[User]) -> list[dict[str, Any]]:
    counts: dict[str, dict] = {}
    for u in users:
        name = u.department_name or "Unassigned"
        key = str(u.department_id) if u.department_id else "_none"
        if key not in counts:
            counts[key] = {"name": name, "count": 0, "color": _department_color(u.department_id)}
        counts[key]["count"] += 1
    return sorted(counts.values(), key=lambda x: -x["count"])


def employee_focus_context(viewer: User, users: list[User]) -> dict[str, Any]:
    """Manager, peers, and subordinates for employee-centric UI."""
    user_map = {u.pk: u for u in users}
    if viewer.pk not in user_map:
        return {"manager": None, "peers": [], "subordinates": [], "selfId": str(viewer.pk)}

    me = user_map[viewer.pk]
    mgr = me.reporting_manager
    manager_card = None
    if mgr and mgr.pk in user_map:
        manager_card = _mini_card(mgr)

    peers = []
    if me.reporting_manager_id:
        for u in users:
            if u.reporting_manager_id == me.reporting_manager_id and u.pk != me.pk:
                peers.append(_mini_card(u))

    subordinates = [_mini_card(u) for u in users if u.reporting_manager_id == me.pk]

    return {
        "manager": manager_card,
        "peers": peers[:12],
        "subordinates": subordinates[:24],
        "selfId": str(me.pk),
    }


def _mini_card(user: User) -> dict[str, str]:
    initials = "".join(p[0].upper() for p in user.display_name.split()[:2]) or "?"
    return {
        "id": str(user.pk),
        "name": user.display_name,
        "designation": user.designation or user.get_role_display(),
        "department": user.department_name or "",
        "initials": initials,
        "avatar": user.profile_picture.url if user.profile_picture else "",
    }


def export_chart_csv(nodes: list[dict]) -> list[list[str]]:
    header = ["ID", "Name", "Employee ID", "Designation", "Department", "Manager", "Branch", "Team"]
    rows = [header]
    for n in nodes:
        if n.get("isDepartment") or n.get("isTeam") or n.get("isBranch"):
            continue
        rows.append(
            [
                n.get("id", ""),
                n.get("name", ""),
                n.get("employeeId", ""),
                n.get("designation", ""),
                n.get("department", ""),
                n.get("managerName", ""),
                n.get("branch", ""),
                n.get("teamName", ""),
            ]
        )
    return rows
