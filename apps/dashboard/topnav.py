"""Premium top navigation — workspace branding, quick actions, notifications."""

from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_label
from apps.dashboard.notification_service import (
    get_user_notifications,
    serialize_notification,
    sync_user_notifications,
    unread_notification_count,
)
from apps.dashboard.staff_services import staff_queryset_for, user_notification_url
from apps.organizations.models import Department, Organization


def _user_initials(user: User) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    letters = "".join(p[0].upper() for p in parts if p)
    if letters:
        return letters[:2]
    uname = (user.username or user.email or "U").strip()
    return uname[:2].upper()


def _workspace_titles(user: User) -> tuple[str, str]:
    role = user.role
    org = user.organization
    if role == User.Role.SUPER_ADMIN:
        return "HRMS Platform", "Super Admin Workspace"
    if org:
        subtitle = f"{role_display_label(user)} Workspace"
        return org.name, subtitle
    return "HRMS Platform", role_display_label(user)


def _profile_subtitle(user: User) -> str:
    if user.role == User.Role.SUPER_ADMIN:
        return "System Owner"
    if user.organization:
        return user.organization.name
    return role_display_label(user)


def _quick_create_items(user: User) -> list[dict]:
    role = user.role
    items: list[dict] = []

    if role == User.Role.SUPER_ADMIN:
        items.extend(
            [
                {
                    "label": "Create Organization",
                    "icon": "building-2",
                    "url": reverse("dashboard:super_organization_create"),
                },
                {
                    "label": "Create User",
                    "icon": "user-plus",
                    "url": reverse("dashboard:super_users"),
                },
                {
                    "label": "Create Plan",
                    "icon": "layers",
                    "url": reverse("dashboard:plans:create"),
                },
            ]
        )
    elif role in (User.Role.ADMIN, User.Role.HR):
        items.extend(
            [
                {
                    "label": "Create Employee",
                    "icon": "user-plus",
                    "url": reverse("dashboard:staff_create"),
                },
                {
                    "label": "Create Department",
                    "icon": "git-branch",
                    "url": reverse("dashboard:departments"),
                },
            ]
        )
        if role == User.Role.ADMIN:
            items.insert(
                0,
                {
                    "label": "Create User",
                    "icon": "users",
                    "url": reverse("dashboard:staff_create"),
                },
            )
    return items


def _profile_menu_items(user: User) -> list[dict]:
    items = [
        {"label": "My Profile", "icon": "user", "url": reverse("accounts:profile")},
        {"label": "Settings", "icon": "settings", "url": reverse("dashboard:settings")},
        {"label": "Security", "icon": "shield", "url": reverse("dashboard:settings")},
    ]
    if user.role == User.Role.SUPER_ADMIN:
        items.append(
            {
                "label": "Audit Logs",
                "icon": "scroll-text",
                "url": reverse("dashboard:financials:audit"),
            }
        )
    else:
        items.append(
            {
                "label": "Audit Logs",
                "icon": "scroll-text",
                "url": reverse("dashboard:storage:file_audits"),
            }
        )
    items.append({"label": "Logout", "icon": "log-out", "url": reverse("accounts:logout"), "is_logout": True})
    return items


def build_topnav(user: User) -> dict:
    if not user.is_authenticated:
        return {}

    platform_title, workspace_subtitle = _workspace_titles(user)
    sync_user_notifications(user)
    notification_rows = get_user_notifications(user, sync=False)
    notifications = [serialize_notification(n) for n in notification_rows]
    unread = unread_notification_count(user, sync=False)

    return {
        "platform_title": platform_title,
        "workspace_subtitle": workspace_subtitle,
        "role_label": role_display_label(user),
        "profile_subtitle": _profile_subtitle(user),
        "user_initials": _user_initials(user),
        "display_name": user.display_name or user.username,
        "quick_create": _quick_create_items(user),
        "profile_menu": _profile_menu_items(user),
        "notifications": notifications,
        "notification_count": unread,
        "unread_count": unread,
        "notifications_api_url": reverse("dashboard:notifications_list"),
        "notifications_read_all_url": reverse("dashboard:notifications_read_all"),
        "search_api_url": reverse("dashboard:global_search"),
        "is_super_admin": user.role == User.Role.SUPER_ADMIN,
    }


def global_search(user: User, query: str, *, limit: int = 12) -> list[dict]:
    q = (query or "").strip()
    if len(q) < 2:
        return []

    results: list[dict] = []
    role = user.role

    if role == User.Role.SUPER_ADMIN:
        orgs = Organization.objects.filter(
            Q(name__icontains=q) | Q(organization_code__icontains=q) | Q(official_email__icontains=q)
        ).order_by("name")[:limit]
        for org in orgs:
            results.append(
                {
                    "label": org.name,
                    "group": "Organizations",
                    "icon": "building-2",
                    "url": reverse("dashboard:super_organization_detail", kwargs={"pk": org.pk}),
                    "meta": org.organization_code,
                }
            )

        users = User.objects.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        ).select_related("organization")[:limit]
        for u in users:
            results.append(
                {
                    "label": u.display_name or u.username,
                    "group": "Users",
                    "icon": "user",
                    "url": reverse("dashboard:super_user_edit", kwargs={"pk": u.pk}),
                    "meta": u.get_role_display(),
                }
            )

        from apps.subscriptions.models import Plan

        plans = Plan.objects.filter(Q(name__icontains=q) | Q(slug__icontains=q)).order_by("sort_order")[:limit]
        for plan in plans:
            results.append(
                {
                    "label": plan.name,
                    "group": "Plans",
                    "icon": "layers",
                    "url": reverse("dashboard:plans:detail", kwargs={"pk": plan.pk}),
                    "meta": plan.slug,
                }
            )
    elif user.organization_id:
        org = user.organization
        staff = staff_queryset_for(user).filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )[:limit]
        for u in staff:
            results.append(
                {
                    "label": u.display_name or u.username,
                    "group": "Employees",
                    "icon": "user",
                    "url": user_notification_url(user, u),
                    "meta": u.get_role_display(),
                }
            )

        depts = Department.objects.filter(organization=org, name__icontains=q).order_by("name")[:limit]
        for dept in depts:
            results.append(
                {
                    "label": dept.name,
                    "group": "Departments",
                    "icon": "git-branch",
                    "url": reverse("dashboard:departments") + f"?edit={dept.pk}",
                    "meta": dept.code or "Department",
                }
            )

    return results[:limit]
