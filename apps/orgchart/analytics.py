"""Organization chart summary metrics and AI-style insights."""

from __future__ import annotations

from typing import Any

from django.db.models import Count

from apps.accounts.hierarchy import build_forest, org_active_users
from apps.accounts.models import User
from apps.orgchart.services import max_reporting_depth, span_of_control_stats
from apps.organizations.models import Department, Organization


def open_positions_count(organization: Organization) -> int:
    return 0


def build_summary(users: list[User], organization: Organization) -> dict[str, Any]:
    dept_ids = {u.department_id for u in users if u.department_id}
    managers = (
        User.objects.filter(pk__in=[u.pk for u in users])
        .annotate(rc=Count("direct_reports"))
        .filter(rc__gt=0)
        .count()
    )
    team_leads = sum(
        1
        for u in users
        if u.direct_reports.filter(is_active=True).count() >= 2
    )
    span = span_of_control_stats(users)
    return {
        "total_employees": len(users),
        "total_departments": len(dept_ids),
        "managers_count": managers,
        "team_leads_count": team_leads,
        "open_positions": open_positions_count(organization),
        "reporting_depth": max_reporting_depth(users),
        "span_avg": span["avg"],
        "span_max": span["max"],
    }


def build_insights(users: list[User], organization: Organization) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    if not users:
        insights.append(
            {
                "icon": "users",
                "title": "Build your org chart",
                "body": "Add employees and assign reporting managers to visualize your hierarchy.",
                "tone": "info",
            }
        )
        return insights

    span = span_of_control_stats(users)
    overloaded = (
        User.objects.filter(pk__in=[u.pk for u in users])
        .annotate(rc=Count("direct_reports"))
        .filter(rc__gt=8)
        .count()
    )
    if overloaded:
        insights.append(
            {
                "icon": "alert-triangle",
                "title": "Reporting overload detected",
                "body": f"{overloaded} manager(s) have more than 8 direct reports. Consider adding team leads.",
                "tone": "warning",
            }
        )

    depth = max_reporting_depth(users)
    if depth > 5:
        insights.append(
            {
                "icon": "layers",
                "title": "Deep hierarchy",
                "body": f"Reporting depth is {depth} levels. Flattening may improve decision speed.",
                "tone": "warning",
            }
        )

    dept_counts: dict[str, int] = {}
    for u in users:
        name = u.department_name or "Unassigned"
        dept_counts[name] = dept_counts.get(name, 0) + 1
    if dept_counts:
        largest = max(dept_counts, key=dept_counts.get)
        smallest = min(dept_counts, key=dept_counts.get)
        if largest != smallest and dept_counts[largest] > dept_counts[smallest] * 3:
            insights.append(
                {
                    "icon": "pie-chart",
                    "title": "Workforce imbalance",
                    "body": f"{largest} is significantly larger than {smallest}. Review hiring distribution.",
                    "tone": "info",
                }
            )

    unassigned = sum(1 for u in users if not u.reporting_manager_id and u.role != User.Role.ADMIN)
    roots = len(build_forest(users))
    if unassigned > 1 or roots > 2:
        insights.append(
            {
                "icon": "git-branch",
                "title": "Multiple hierarchy roots",
                "body": "Several employees lack a reporting manager. Align to a single leadership tree where possible.",
                "tone": "info",
            }
        )

    if span["max"] > 0 and span["avg"] < 2:
        insights.append(
            {
                "icon": "trending-up",
                "title": "Lean management layers",
                "body": "Average span of control is low. Managers may have capacity for broader teams.",
                "tone": "success",
            }
        )

    open_pos = open_positions_count(organization)
    if open_pos:
        insights.append(
            {
                "icon": "briefcase",
                "title": "Workforce planning",
                "body": "Review department headcount and reporting structure for upcoming growth.",
                "tone": "info",
            }
        )

    if not insights:
        insights.append(
            {
                "icon": "sparkles",
                "title": "Healthy structure",
                "body": "No major bottlenecks detected. Hierarchy depth and spans look balanced.",
                "tone": "success",
            }
        )
    return insights[:6]


def build_global_platform_summary() -> dict[str, int]:
    orgs = Organization.objects.filter(is_active=True)
    users = User.objects.filter(organization__in=orgs, is_active=True).exclude(
        role=User.Role.SUPER_ADMIN
    )
    return {
        "organizations": orgs.count(),
        "employees": users.count(),
        "departments": Department.objects.filter(organization__in=orgs, is_active=True).count(),
        "managers": users.filter(direct_reports__isnull=False).distinct().count(),
    }
