"""Organization feature control — Super Admin views."""

from __future__ import annotations

import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.organizations.models import Organization
from apps.subscriptions.models import FeatureCategory, FeatureDefinition, FeatureControlAuditLog, OrganizationLimit
from apps.subscriptions.services.entitlements import get_org_plan
from apps.subscriptions.services.feature_control import get_org_limits, invalidate_org_entitlements, log_feature_action
from apps.subscriptions.services.org_features import (
    build_org_feature_categories,
    bulk_set_all,
    bulk_set_category,
    get_org_feature_summary,
    reset_org_to_plan_defaults,
    set_org_feature_enabled,
)


class OrganizationFeatureControlView(SuperAdminRequiredMixin, TemplateView):
    template_name = "dashboard/superadmin/org_feature_control.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = get_object_or_404(Organization, pk=self.kwargs["pk"])
        ctx["organization"] = org
        ctx["plan"] = get_org_plan(org)
        ctx["summary"] = get_org_feature_summary(org)
        ctx["feature_categories"] = build_org_feature_categories(org)
        ctx["addons"] = list(org.billing_addons.filter(is_active=True).select_related("addon"))
        ctx["limits"] = _org_limits_context(org, ctx["plan"])
        return ctx


def _org_limits_context(org: Organization, plan) -> dict:
    try:
        override = org.feature_limits
    except OrganizationLimit.DoesNotExist:
        override = None
    effective = get_org_limits(org)
    fields = ("employee_limit", "storage_limit_mb", "branch_limit")
    rows = []
    labels = {
        "employee_limit": "Employee limit",
        "storage_limit_mb": "Storage limit (MB)",
        "branch_limit": "Branch limit",
    }
    for field in fields:
        plan_val = getattr(plan, field, None) if plan else None
        override_val = getattr(override, field, None) if override else None
        rows.append(
            {
                "field": field,
                "label": labels[field],
                "plan": plan_val,
                "override": override_val,
                "effective": effective.get(field),
            }
        )
    return {"rows": rows}


class OrganizationFeatureAPIView(SuperAdminRequiredMixin, View):
    def post(self, request, pk):
        org = get_object_or_404(Organization, pk=pk)
        if request.content_type and "application/json" in request.content_type:
            try:
                data = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        else:
            data = request.POST.dict()

        action = data.get("action", "")

        try:
            if action == "toggle":
                feat = get_object_or_404(FeatureDefinition, pk=data.get("feature_id"))
                enabled = data.get("enabled") in (True, "true", "1", 1)
                set_org_feature_enabled(
                    org=org,
                    feature=feat,
                    enabled=enabled,
                    actor=request.user,
                    reason=data.get("reason", ""),
                    request=request,
                )
                return JsonResponse({"ok": True, "feature_key": feat.key, "enabled": enabled})

            if action == "bulk_category":
                cat = get_object_or_404(FeatureCategory, pk=data.get("category_id"))
                enabled = data.get("enabled") in (True, "true", "1", 1)
                count = bulk_set_category(org=org, category=cat, enabled=enabled, actor=request.user, request=request)
                return JsonResponse({"ok": True, "count": count})

            if action == "bulk_all":
                enabled = data.get("enabled") in (True, "true", "1", 1)
                count = bulk_set_all(org=org, enabled=enabled, actor=request.user, request=request)
                return JsonResponse({"ok": True, "count": count})

            if action == "reset_plan":
                count = reset_org_to_plan_defaults(org=org, actor=request.user, request=request)
                messages.success(request, f"Reset {count} override(s) to plan defaults.")
                if data.get("redirect"):
                    return redirect("dashboard:super_organization_features", pk=org.pk)
                return JsonResponse({"ok": True, "count": count})

            if action == "update_limit":
                field = data.get("field", "employee_limit")
                if field not in ("employee_limit", "storage_limit_mb", "branch_limit"):
                    return JsonResponse({"ok": False, "error": "Invalid field"}, status=400)
                raw = str(data.get("value", "")).strip()
                limits, _ = OrganizationLimit.objects.get_or_create(organization=org)
                old_val = getattr(limits, field)
                if raw.lower() in ("", "reset", "clear", "null", "none"):
                    new_val = None
                else:
                    try:
                        new_val = int(raw)
                        if new_val < 0:
                            raise ValueError
                    except ValueError:
                        return JsonResponse(
                            {"ok": False, "error": "Enter a positive number or leave empty to use plan default"},
                            status=400,
                        )
                setattr(limits, field, new_val)
                limits.save(update_fields=[field, "updated_at"])
                invalidate_org_entitlements(org)
                effective = get_org_limits(org)
                log_feature_action(
                    actor=request.user,
                    action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
                    organization=org,
                    summary=f"Updated {field.replace('_', ' ')} for {org.name}",
                    old_value={field: old_val},
                    new_value={field: new_val},
                    request=request,
                )
                return JsonResponse(
                    {
                        "ok": True,
                        "field": field,
                        "override": new_val,
                        "effective": effective.get(field),
                    }
                )

            if action == "reset_limits":
                OrganizationLimit.objects.filter(organization=org).delete()
                invalidate_org_entitlements(org)
                log_feature_action(
                    actor=request.user,
                    action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
                    organization=org,
                    summary=f"Cleared all limit overrides for {org.name}",
                    request=request,
                )
                return JsonResponse({"ok": True})

        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        return JsonResponse({"ok": False, "error": "Unknown action"}, status=400)
