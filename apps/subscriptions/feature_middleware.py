"""Block routes and APIs when organization features are disabled."""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from apps.accounts.models import User
from apps.subscriptions.services.entitlements import get_upgrade_context, has_feature
from apps.subscriptions.services.feature_control import get_feature_for_url_name, is_page_enabled
from apps.subscriptions.services.org_features import feature_for_path


_EXEMPT_PREFIXES = (
    "/dashboard/super",
    "/dashboard/superadmin/",
    "/accounts/",
    "/admin/",
    "/static/",
    "/media/",
    "/dashboard/upgrade",
    "/dashboard/settings",
    "/api/auth/",
)


def _feature_blocked_response(request, org, feature_key, *, is_api: bool = False):
    role = getattr(request.user, "role", None)
    if is_api or "application/json" in (request.META.get("HTTP_ACCEPT") or ""):
        return JsonResponse(
            {
                "detail": "This feature is not enabled for your organization.",
                "feature": feature_key,
                "code": "feature_not_enabled",
            },
            status=403,
        )
    ctx = get_upgrade_context(org, feature_key)
    ctx["page_title"] = "Feature Not Enabled"
    ctx["is_not_enabled"] = True
    ctx["show_upgrade"] = feature_key in ctx.get("available_plans", []) or bool(ctx.get("required_plan"))
    return render(request, "dashboard/feature_not_enabled.html", ctx, status=403)


class FeatureGateMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        path = request.path or ""
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return None

        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None
        if getattr(user, "role", None) == User.Role.SUPER_ADMIN:
            return None
        org = getattr(user, "organization", None)
        if not org:
            return None

        role = getattr(user, "role", None)

        path_key, is_api = feature_for_path(path)
        if path_key and not has_feature(org, path_key, role):
            return _feature_blocked_response(request, org, path_key, is_api=is_api or path.startswith("/api/"))

        url_name = getattr(request.resolver_match, "url_name", None) if request.resolver_match else None
        namespace = getattr(request.resolver_match, "namespace", None) if request.resolver_match else None
        full_name = f"{namespace}:{url_name}" if namespace and url_name else url_name
        if not full_name:
            return None

        if not is_page_enabled(org, full_name, role):
            feature_key = get_feature_for_url_name(full_name) or "feature"
            return _feature_blocked_response(request, org, feature_key)

        feature_key = get_feature_for_url_name(full_name)
        if feature_key and not has_feature(org, feature_key, role):
            return _feature_blocked_response(request, org, feature_key)

        return None
