"""Org hierarchy helpers: visibility by role and tree building."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet

from apps.accounts.models import User

if TYPE_CHECKING:
    from apps.organizations.models import Organization


def org_active_users(organization: Organization) -> QuerySet[User]:
    return (
        User.objects.filter(organization=organization, is_active=True)
        .exclude(role=User.Role.SUPER_ADMIN)
        .select_related("reporting_manager", "assigned_hr", "department")
    )


def staff_list_for(user: User) -> QuerySet[User]:
    """Users visible on the staff list page."""
    if not user.organization_id:
        return User.objects.none()
    base = org_active_users(user.organization)
    if user.role == User.Role.ADMIN:
        return base.order_by("role", "first_name", "last_name", "email")
    if user.role == User.Role.HR:
        return base.filter(role=User.Role.EMPLOYEE, assigned_hr=user).order_by(
            "first_name", "last_name", "employee_id"
        )
    return User.objects.none()


def tree_users_for(user: User) -> QuerySet[User]:
    """Users included in the org tree for the current viewer."""
    if not user.organization_id:
        return User.objects.none()
    org = user.organization
    base = org_active_users(org)

    if user.role == User.Role.ADMIN:
        return base.order_by("first_name", "last_name")

    if user.role == User.Role.HR:
        assigned = base.filter(role=User.Role.EMPLOYEE, assigned_hr=user)
        ids: set = set(assigned.values_list("pk", flat=True))
        ids.add(user.pk)
        # Include reporting chain among assigned employees + managers in org
        for emp in assigned.select_related("reporting_manager"):
            mgr = emp.reporting_manager
            while mgr and mgr.organization_id == org.pk:
                ids.add(mgr.pk)
                mgr = mgr.reporting_manager
        return base.filter(pk__in=ids).order_by("first_name", "last_name")

    # Employee: self, managers up, direct/indirect reports down
    ids = {user.pk}
    mgr = user.reporting_manager
    while mgr and mgr.organization_id == org.pk:
        ids.add(mgr.pk)
        mgr = mgr.reporting_manager

    def collect_reports(manager_id):
        for report in base.filter(reporting_manager_id=manager_id):
            if report.pk not in ids:
                ids.add(report.pk)
                collect_reports(report.pk)

    collect_reports(user.pk)

    # Peers (same manager) for team context
    if user.reporting_manager_id:
        peer_ids = base.filter(reporting_manager_id=user.reporting_manager_id).values_list(
            "pk", flat=True
        )
        ids.update(peer_ids)

    return base.filter(pk__in=ids).order_by("first_name", "last_name")


def org_tree_users(organization: Organization) -> QuerySet[User]:
    """Full active org roster for super-admin hierarchy views."""
    return org_active_users(organization).order_by("first_name", "last_name")


@dataclass
class TreeNode:
    user: User
    children: list[TreeNode] = field(default_factory=list)


def build_forest(users: QuerySet[User] | list[User]) -> list[TreeNode]:
    """Build one or more trees from reporting_manager links within the queryset."""
    user_list = list(users)
    by_id = {u.pk: u for u in user_list}
    children_map: dict = {pk: [] for pk in by_id}
    roots: list[User] = []

    for u in user_list:
        mgr_id = u.reporting_manager_id
        if mgr_id and mgr_id in by_id:
            children_map[mgr_id].append(u)
        else:
            roots.append(u)

    def make_node(u: User) -> TreeNode:
        kids = sorted(children_map.get(u.pk, []), key=lambda x: (x.display_name.lower(), str(x.pk)))
        return TreeNode(user=u, children=[make_node(c) for c in kids])

    roots.sort(key=lambda x: (x.display_name.lower(), str(x.pk)))
    return [make_node(r) for r in roots]


def manager_choices_qs(organization: Organization, exclude_pk=None) -> QuerySet[User]:
    qs = org_active_users(organization).filter(
        role__in=[User.Role.ADMIN, User.Role.HR, User.Role.EMPLOYEE],
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.order_by("role", "first_name", "last_name")


def hr_choices_qs(organization: Organization) -> QuerySet[User]:
    return org_active_users(organization).filter(role=User.Role.HR).order_by("first_name", "last_name")


def attendance_team_for(user: User) -> QuerySet[User]:
    """Users whose attendance the viewer can manage (admin / HR)."""
    if not user.organization_id:
        return User.objects.none()
    base = org_active_users(user.organization)
    if user.role == User.Role.ADMIN:
        return base.filter(
            role__in=[User.Role.HR, User.Role.EMPLOYEE]
        ).order_by("role", "first_name", "last_name")
    if user.role == User.Role.HR:
        return base.filter(
            Q(role=User.Role.EMPLOYEE, assigned_hr=user) | Q(pk=user.pk)
        ).order_by("first_name", "last_name")
    return User.objects.none()


def direct_reports_for(user: User) -> QuerySet[User]:
    if not user.organization_id:
        return User.objects.none()
    return org_active_users(user.organization).filter(reporting_manager=user).order_by(
        "first_name", "last_name"
    )


def has_direct_reports(user: User) -> bool:
    return direct_reports_for(user).exists()


def is_manager(user: User) -> bool:
    """Whether the user may access team-management features.

    True for any user with active direct reports — leading a team is a
    capability derived from the reporting hierarchy, not a role.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return has_direct_reports(user)


def attendance_visible_team_for(user: User) -> QuerySet[User]:
    """Users whose attendance the viewer can see (admin, HR, or direct manager)."""
    if can_manage_team_attendance(user):
        return attendance_team_for(user)
    if has_direct_reports(user):
        return direct_reports_for(user)
    return User.objects.none()


def can_view_team_attendance(user: User) -> bool:
    return can_manage_team_attendance(user) or has_direct_reports(user)


def can_review_attendance_corrections(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR) or has_direct_reports(user)


def correction_requests_for_reviewer(reviewer: User):
    from apps.attendance.models import AttendanceRegularizationRequest

    org = reviewer.organization
    if not org:
        return AttendanceRegularizationRequest.objects.none()
    qs = AttendanceRegularizationRequest.objects.filter(
        user__organization=org,
    ).select_related("user", "reviewed_by")
    if reviewer.role == User.Role.ADMIN:
        return qs
    if reviewer.role == User.Role.HR:
        return qs.filter(
            Q(user__assigned_hr=reviewer, user__role=User.Role.EMPLOYEE)
            | Q(user=reviewer)
        )
    return qs.filter(user__reporting_manager=reviewer)


def can_manage_team_attendance(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR)
