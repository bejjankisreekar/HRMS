"""Validate organization subscription on tenant routes."""

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization


class SubscriptionPlanMiddleware:
    """Block inactive/suspended org users from app routes (except login/logout)."""

    EXEMPT_PREFIXES = (
        "/accounts/",
        "/admin/",
        "/dashboard/super",
        "/dashboard/superadmin/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        if user.role == User.Role.SUPER_ADMIN:
            return self.get_response(request)

        org = user.organization
        if not org:
            return self.get_response(request)

        if not org.is_active or org.subscription_status in (
            Organization.SubscriptionStatus.EXPIRED,
            Organization.SubscriptionStatus.CANCELED,
        ):
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"error": "Organization subscription inactive. Contact your administrator."},
                    status=403,
                )
            return redirect(reverse("accounts:login"))

        return self.get_response(request)
