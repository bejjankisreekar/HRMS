from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect

from apps.accounts.models import User


class OrganizationRequiredMixin(LoginRequiredMixin):
    """User must belong to an organization (tenant member)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role == User.Role.SUPER_ADMIN:
            messages.error(request, "Super Admins must use the platform console.")
            return redirect("dashboard:superadmin")
        if not request.user.organization_id:
            messages.error(request, "You must belong to an organization.")
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(OrganizationRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == User.Role.ADMIN

    def handle_no_permission(self):
        messages.error(self.request, "Only Organization Admins can access this page.")
        return redirect("dashboard:home")


class AdminOrHRRequiredMixin(OrganizationRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role in (User.Role.ADMIN, User.Role.HR)

    def handle_no_permission(self):
        messages.error(
            self.request,
            "Only Organization Admins and HR staff can access this page.",
        )
        return redirect("dashboard:home")


class TeamLeadRequiredMixin(OrganizationRequiredMixin, UserPassesTestMixin):
    """Anyone who may manage a team: a user with active direct reports."""

    def test_func(self):
        from apps.accounts.hierarchy import is_manager

        return is_manager(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "You do not manage a team.")
        return redirect("dashboard:home")


class SuperAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict views to platform super administrators."""

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and user.role == User.Role.SUPER_ADMIN

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("accounts:login")
        messages.error(self.request, "You do not have permission to access the platform console.")
        return redirect("dashboard:home")
