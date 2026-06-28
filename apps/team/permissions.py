"""DRF permissions for the manager team API."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.hierarchy import is_manager


class IsManagerOrTeamLead(BasePermission):
    """Allow only authenticated org members who manage a team.

    ``is_manager`` is True for the MANAGER role OR any user with active direct
    reports (preserving pre-role behavior). Object-level scoping to the
    manager's own reports is enforced in each view's queryset.
    """

    message = "You must be a manager with direct reports to access team data."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "organization_id", None)
            and is_manager(user)
        )
