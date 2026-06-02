"""Shared context builder for organization tree pages."""

from __future__ import annotations

import json

from django.urls import reverse

from apps.accounts.models import User
from apps.orgchart.analytics import build_insights, build_summary
from apps.orgchart.services import (
    OrgTreeFilters,
    build_chart_data,
    can_edit_hierarchy,
    can_manage_org_chart,
    department_heatmap,
    employee_focus_context,
    filter_options,
    get_tree_queryset,
    get_tree_queryset_for_org,
)
from apps.organizations.models import Organization


def _scope_label(user: User) -> str:
    if user.role == User.Role.SUPER_ADMIN:
        return "Platform-wide organization hierarchy"
    if user.role == User.Role.ADMIN:
        return "Organization Admin · full organization"
    if user.role == User.Role.HR:
        return "HR · your portfolio & reporting lines"
    return "Employee · your team, manager & peers"


def _page_meta(user: User) -> dict:
    if user.role == User.Role.SUPER_ADMIN:
        return {
            "title": "Global Organization Hierarchy",
            "subtitle": "Browse and analyze workforce structure across all organizations.",
            "icon": "globe-2",
        }
    if user.role == User.Role.EMPLOYEE:
        return {
            "title": "My Team & Organization",
            "subtitle": "Your reporting manager, peers, and team structure at a glance.",
            "icon": "users-round",
        }
    if user.role == User.Role.HR:
        return {
            "title": "Employee Hierarchy",
            "subtitle": "Manage reporting lines, teams, and organizational structure.",
            "icon": "git-branch",
        }
    return {
        "title": "Organization Structure",
        "subtitle": "Visualize reporting hierarchy, departments, teams, and relationships.",
        "icon": "network",
    }


def build_org_tree_context(request, *, organization: Organization | None = None) -> dict:
    user = request.user
    org = organization or user.organization
    filters = OrgTreeFilters.from_request(request)

    if user.role == User.Role.SUPER_ADMIN and org:
        users_qs = get_tree_queryset_for_org(org, user, filters)
    else:
        users_qs = get_tree_queryset(user, filters)

    users = list(users_qs)
    chart = build_chart_data(users, filters.view)
    emp_pk = "00000000-0000-0000-0000-000000000000"
    meta = _page_meta(user)

    focus_param = (request.GET.get("focus") or "").strip()
    focus_id = None
    if focus_param == "me":
        focus_id = str(user.pk)
    elif focus_param == "manager" and user.reporting_manager_id:
        focus_id = str(user.reporting_manager_id)
    elif focus_param and focus_param not in ("me", "manager"):
        focus_id = focus_param

    ctx = {
        "filters": filters,
        "filters_get": request.GET,
        "filter_options": filter_options(org),
        "summary": build_summary(users, org),
        "insights": build_insights(users, org),
        "department_heatmap": department_heatmap(users),
        "chart_json": json.dumps(chart),
        "tree_scope": _scope_label(user),
        "page_meta": meta,
        "can_manage": can_manage_org_chart(user),
        "can_edit_hierarchy": can_edit_hierarchy(user),
        "view_modes": filter_options(org)["view_modes"],
        "staff_create_url": reverse("dashboard:staff_create"),
        "departments_url": reverse("dashboard:departments"),
        "is_super_admin_view": user.role == User.Role.SUPER_ADMIN,
        "is_employee_view": user.role == User.Role.EMPLOYEE,
        "selected_organization": org,
        "focus_node_id": focus_id,
        "current_user_id": str(user.pk),
        "employee_focus": employee_focus_context(user, users) if user.role == User.Role.EMPLOYEE else None,
        "show_full_filters": user.role != User.Role.EMPLOYEE,
        "show_insights": user.role in (User.Role.ADMIN, User.Role.HR, User.Role.SUPER_ADMIN),
        "show_stats_extended": user.role in (User.Role.ADMIN, User.Role.HR, User.Role.SUPER_ADMIN),
        "api_employee_template": reverse(
            "dashboard:orgchart:api_employee", kwargs={"pk": emp_pk}
        ).replace(emp_pk, "__ID__"),
    }
    return ctx
