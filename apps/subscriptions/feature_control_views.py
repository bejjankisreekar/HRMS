"""Master Feature Control Center — Super Admin views."""

from __future__ import annotations

import json

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    AddOnCatalog,
    FeatureControlAuditLog,
    FeatureDefinition,
    FeatureModule,
    FeatureRolePermission,
    FeatureType,
    FieldDefinition,
    MenuAudience,
    NavigationItem,
    OrganizationFeatureOverride,
    OrganizationLimit,
    PageDefinition,
    Plan,
    PlanFeature,
)
from apps.subscriptions.services.feature_control import (
    invalidate_org_entitlements,
    invalidate_org_entitlements_for_all,
    log_feature_action,
    set_global_feature,
    set_org_feature_override,
    set_plan_feature,
    validate_disable,
)


CONTROL_NAV = [
    ("hub", "Overview", "layout-dashboard", "dashboard:feature_control:hub"),
    ("global", "Global features", "toggle-right", "dashboard:feature_control:global"),
    ("modules", "Modules", "boxes", "dashboard:feature_control:modules"),
    ("pages", "Pages", "file", "dashboard:feature_control:pages"),
    ("navigation", "Navigation", "menu", "dashboard:feature_control:navigation"),
    ("roles", "Role permissions", "shield", "dashboard:feature_control:roles"),
    ("fields", "Field control", "form-input", "dashboard:feature_control:fields"),
    ("workflows", "Workflows", "git-branch", "dashboard:feature_control:workflows"),
    ("addons", "Add-ons", "puzzle", "dashboard:feature_control:addons"),
    ("audit", "Audit log", "clipboard-list", "dashboard:feature_control:audit"),
]


class FeatureControlMixin(SuperAdminRequiredMixin):
    section = "hub"

    def get_control_nav(self):
        current = self.section
        return [
            {"id": sid, "label": label, "icon": icon, "url": reverse(url), "active": sid == current}
            for sid, label, icon, url in CONTROL_NAV
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["control_nav"] = self.get_control_nav()
        ctx["control_section"] = self.section
        return ctx


class FeatureControlHubView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/hub.html"
    section = "hub"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stats"] = {
            "features": FeatureDefinition.objects.filter(is_active=True).count(),
            "modules": FeatureModule.objects.filter(is_active=True).count(),
            "pages": PageDefinition.objects.count(),
            "nav_items": NavigationItem.objects.count(),
            "plans": Plan.objects.filter(is_active=True).count(),
            "addons": AddOnCatalog.objects.filter(is_active=True).count(),
            "orgs_with_overrides": OrganizationFeatureOverride.objects.values("organization").distinct().count(),
            "recent_audit": FeatureControlAuditLog.objects.select_related("actor", "organization")[:8],
        }
        return ctx


class GlobalFeatureControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/global.html"
    section = "global"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()
        category = self.request.GET.get("category", "")
        qs = FeatureDefinition.objects.filter(is_active=True, feature_type=FeatureType.FEATURE).select_related("module")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(key__icontains=q))
        if category:
            qs = qs.filter(category=category)
        ctx["features"] = qs.order_by("category", "sort_order", "name")
        ctx["categories"] = (
            FeatureDefinition.objects.filter(is_active=True)
            .exclude(category="")
            .values_list("category", flat=True)
            .distinct()
            .order_by("category")
        )
        ctx["search_q"] = q
        ctx["filter_category"] = category
        return ctx


class ModuleControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/modules.html"
    section = "modules"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modules"] = (
            FeatureModule.objects.annotate(feature_count=Count("features"))
            .order_by("sort_order", "name")
        )
        return ctx


class PageControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/pages.html"
    section = "pages"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["pages"] = PageDefinition.objects.select_related("feature", "module").order_by("sort_order", "name")
        return ctx


class NavigationControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/navigation.html"
    section = "navigation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plan_id = self.request.GET.get("plan", "")
        ctx["plans"] = Plan.objects.filter(is_active=True).order_by("sort_order")
        ctx["selected_plan"] = plan_id
        qs = NavigationItem.objects.select_related("plan").order_by("audience", "sort_order", "label")
        if plan_id:
            qs = qs.filter(plan_id=plan_id)
        else:
            qs = qs.filter(plan__isnull=True)
        ctx["nav_items"] = qs
        ctx["audiences"] = MenuAudience.choices
        return ctx


class RolePermissionView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/roles.html"
    section = "roles"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        features = FeatureDefinition.objects.filter(is_active=True).order_by("sort_order", "name")
        perms = {
            (p.feature_id, p.role): p.is_allowed
            for p in FeatureRolePermission.objects.all()
        }
        rows = []
        for feat in features:
            rows.append(
                {
                    "feature": feat,
                    "admin": perms.get((feat.pk, "ADMIN"), True),
                    "hr": perms.get((feat.pk, "HR"), True),
                    "employee": perms.get((feat.pk, "EMPLOYEE"), False),
                }
            )
        ctx["permission_rows"] = rows
        return ctx


class FieldControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/fields.html"
    section = "fields"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fields"] = FieldDefinition.objects.select_related("feature").order_by("form_context", "sort_order")
        return ctx


class WorkflowControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/workflows.html"
    section = "workflows"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["workflows"] = FeatureDefinition.objects.filter(
            is_active=True, feature_type=FeatureType.WORKFLOW
        ).order_by("sort_order", "name")
        return ctx


class AddonControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/addons.html"
    section = "addons"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["addons"] = AddOnCatalog.objects.order_by("sort_order", "name")
        return ctx


class FeatureAuditView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/audit.html"
    section = "audit"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = FeatureControlAuditLog.objects.select_related(
            "actor", "organization", "plan"
        ).order_by("-created_at")[:200]
        return ctx


class OrganizationFeatureControlView(FeatureControlMixin, TemplateView):
    """Legacy redirect — use superadmin org feature control page."""

    def get(self, request, *args, **kwargs):
        return redirect("dashboard:super_organization_features", pk=kwargs["pk"])


class PlanFeatureControlView(FeatureControlMixin, TemplateView):
    template_name = "dashboard/feature_control/plan_features.html"
    section = "global"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plan = get_object_or_404(Plan, pk=self.kwargs["pk"])
        enabled_ids = set(plan.plan_features.filter(is_enabled=True).values_list("feature_id", flat=True))
        ctx["plan"] = plan
        ctx["features"] = FeatureDefinition.objects.filter(is_active=True).order_by("category", "sort_order")
        ctx["enabled_ids"] = enabled_ids
        return ctx


class FeatureControlAPIView(FeatureControlMixin, View):
    """AJAX endpoint for toggles and bulk actions."""

    def post(self, request):
        if request.content_type and "application/json" in request.content_type:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}
            action = payload.get("action", "")
        else:
            payload = {}
            action = request.POST.get("action", "")

        try:
            if action == "nav_reorder":
                for idx, item_id in enumerate(payload.get("item_ids", [])):
                    NavigationItem.objects.filter(pk=item_id).update(sort_order=idx)
                invalidate_org_entitlements_for_all()
                return JsonResponse({"ok": True})

            if action == "global_toggle":
                feat = get_object_or_404(FeatureDefinition, pk=request.POST.get("feature_id"))
                enabled = request.POST.get("enabled") == "true"
                if not enabled:
                    ok, deps = validate_disable(feat.key)
                    if not ok:
                        return JsonResponse({"ok": False, "error": f"Required by: {', '.join(deps)}"}, status=400)
                set_global_feature(feature=feat, enabled=enabled, actor=request.user, request=request)
                return JsonResponse({"ok": True})

            if action == "plan_toggle":
                plan = get_object_or_404(Plan, pk=request.POST.get("plan_id"))
                feat = get_object_or_404(FeatureDefinition, pk=request.POST.get("feature_id"))
                enabled = request.POST.get("enabled") == "true"
                set_plan_feature(plan=plan, feature=feat, enabled=enabled, actor=request.user, request=request)
                return JsonResponse({"ok": True})

            if action == "org_toggle":
                org = get_object_or_404(Organization, pk=request.POST.get("org_id"))
                feat = get_object_or_404(FeatureDefinition, pk=request.POST.get("feature_id"))
                mode = request.POST.get("mode", "enable")
                reason = request.POST.get("reason", "")
                if mode == "inherit":
                    set_org_feature_override(org=org, feature=feat, enabled=None, actor=request.user, reason=reason, request=request)
                else:
                    set_org_feature_override(
                        org=org, feature=feat, enabled=(mode == "enable"), actor=request.user, reason=reason, request=request
                    )
                return JsonResponse({"ok": True})

            if action == "module_toggle":
                mod = get_object_or_404(FeatureModule, pk=request.POST.get("module_id"))
                enabled = request.POST.get("enabled") == "true"
                old = mod.is_globally_enabled
                mod.is_globally_enabled = enabled
                mod.save(update_fields=["is_globally_enabled"])
                invalidate_org_entitlements_for_all()
                log_feature_action(
                    actor=request.user,
                    action=FeatureControlAuditLog.Action.MODULE_UPDATE,
                    summary=f"{'Enabled' if enabled else 'Disabled'} module {mod.name}",
                    old_value={"is_globally_enabled": old},
                    new_value={"is_globally_enabled": enabled},
                    request=request,
                )
                return JsonResponse({"ok": True})

            if action == "page_toggle":
                page = get_object_or_404(PageDefinition, pk=request.POST.get("page_id"))
                enabled = request.POST.get("enabled") == "true"
                old = page.is_globally_enabled
                page.is_globally_enabled = enabled
                page.save(update_fields=["is_globally_enabled"])
                invalidate_org_entitlements_for_all()
                log_feature_action(
                    actor=request.user,
                    action=FeatureControlAuditLog.Action.PAGE_UPDATE,
                    feature_key=page.key,
                    summary=f"{'Enabled' if enabled else 'Disabled'} page {page.name}",
                    old_value={"is_globally_enabled": old},
                    new_value={"is_globally_enabled": enabled},
                    request=request,
                )
                return JsonResponse({"ok": True})

            if action == "nav_toggle":
                item = get_object_or_404(NavigationItem, pk=request.POST.get("item_id"))
                visible = request.POST.get("visible") == "true"
                item.is_visible = visible
                item.save(update_fields=["is_visible", "updated_at"])
                invalidate_org_entitlements_for_all()
                return JsonResponse({"ok": True})

            if action == "role_toggle":
                feat = get_object_or_404(FeatureDefinition, pk=request.POST.get("feature_id"))
                role = request.POST.get("role")
                allowed = request.POST.get("allowed") == "true"
                FeatureRolePermission.objects.update_or_create(
                    feature=feat, role=role, defaults={"is_allowed": allowed}
                )
                invalidate_org_entitlements_for_all()
                log_feature_action(
                    actor=request.user,
                    action=FeatureControlAuditLog.Action.ROLE_PERMISSION,
                    feature_key=feat.key,
                    summary=f"Role {role} {'allowed' if allowed else 'denied'} for {feat.name}",
                    new_value={"role": role, "is_allowed": allowed},
                    request=request,
                )
                return JsonResponse({"ok": True})

            if action == "field_toggle":
                field = get_object_or_404(FieldDefinition, pk=request.POST.get("field_id"))
                visible = request.POST.get("visible") == "true"
                field.is_globally_visible = visible
                field.save(update_fields=["is_globally_visible"])
                invalidate_org_entitlements_for_all()
                return JsonResponse({"ok": True})

            if action == "addon_toggle":
                addon = get_object_or_404(AddOnCatalog, pk=request.POST.get("addon_id"))
                active = request.POST.get("active") == "true"
                addon.is_active = active
                addon.save(update_fields=["is_active"])
                invalidate_org_entitlements_for_all()
                return JsonResponse({"ok": True})

        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        return JsonResponse({"ok": False, "error": "Unknown action"}, status=400)


class OrgLimitsUpdateView(FeatureControlMixin, View):
    def post(self, request, pk):
        org = get_object_or_404(Organization, pk=pk)
        limits, _ = OrganizationLimit.objects.get_or_create(organization=org)
        for field in ("employee_limit", "storage_limit_mb", "branch_limit", "admin_limit", "hr_limit", "api_limit_daily"):
            val = request.POST.get(field, "").strip()
            setattr(limits, field, int(val) if val else None)
        limits.save()
        invalidate_org_entitlements(org)
        log_feature_action(
            actor=request.user,
            action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
            organization=org,
            summary=f"Updated limits for {org.name}",
            new_value={
                f: getattr(limits, f)
                for f in ("employee_limit", "storage_limit_mb", "branch_limit", "admin_limit", "hr_limit", "api_limit_daily")
            },
            request=request,
        )
        messages.success(request, "Limits updated.")
        return redirect("dashboard:super_organization_features", pk=org.pk)
