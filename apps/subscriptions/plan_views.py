"""Super Admin plan & feature management."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.subscriptions.models import (
    AddOnCatalog,
    BillingSettings,
    FeatureDefinition,
    MenuAudience,
    Plan,
    PlanFeature,
    PlanMenuItem,
)
from apps.subscriptions.services.feature_control import invalidate_org_entitlements
from apps.organizations.models import Organization


PLAN_NAV = [
    ("list", "All plans", "layers", "dashboard:plans:list"),
    ("features", "Feature catalog", "toggle-right", "dashboard:plans:features"),
]


class PlanManagementMixin(SuperAdminRequiredMixin):
    section = "list"

    def get_plan_nav(self):
        current = self.section
        return [
            {
                "id": sid,
                "label": label,
                "icon": icon,
                "url": reverse(url_name),
                "active": sid == current,
            }
            for sid, label, icon, url_name in PLAN_NAV
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plan_nav"] = self.get_plan_nav()
        ctx["plan_section"] = self.section
        return ctx


class PlanListView(PlanManagementMixin, TemplateView):
    template_name = "dashboard/plans/list.html"
    section = "list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plans"] = (
            Plan.objects.annotate(
                sub_count=Count("subscriptions"),
                feature_count=Count("plan_features", distinct=True),
                menu_count=Count("menu_items", distinct=True),
            )
            .order_by("sort_order", "name")
        )
        return ctx


class PlanCreateView(PlanManagementMixin, View):
    section = "list"

    def post(self, request):
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Plan name is required.")
            return redirect("dashboard:plans:list")
        slug = (request.POST.get("slug") or name.lower().replace(" ", "-"))[:40]
        if Plan.objects.filter(slug=slug).exists():
            slug = f"{slug}-{uuid4().hex[:6]}"
        plan = Plan.objects.create(
            slug=slug,
            name=name,
            description=request.POST.get("description", ""),
            sort_order=Plan.objects.count() + 1,
        )
        messages.success(request, f"Plan “{plan.name}” created.")
        return redirect("dashboard:plans:detail", pk=plan.pk)


class PlanCloneView(PlanManagementMixin, View):
    section = "list"

    @transaction.atomic
    def post(self, request, pk):
        source = get_object_or_404(Plan, pk=pk)
        slug = f"{source.slug}-copy-{uuid4().hex[:6]}"
        clone = Plan.objects.create(
            slug=slug,
            name=f"{source.name} (Copy)",
            description=source.description,
            monthly_price_inr=source.monthly_price_inr,
            yearly_price_inr=source.yearly_price_inr,
            per_employee_price_inr=source.per_employee_price_inr,
            setup_fee_inr=source.setup_fee_inr,
            employee_limit=source.employee_limit,
            branch_limit=source.branch_limit,
            storage_limit_mb=source.storage_limit_mb,
            trial_days=source.trial_days,
            feature_flags=dict(source.feature_flags or {}),
            features_json=list(source.features_json or []),
            sort_order=Plan.objects.count() + 1,
            is_active=False,
        )
        for pf in source.plan_features.select_related("feature"):
            PlanFeature.objects.create(plan=clone, feature=pf.feature, is_enabled=pf.is_enabled)
        for item in source.menu_items.all():
            PlanMenuItem.objects.create(
                plan=clone,
                label=item.label,
                icon=item.icon,
                url_name=item.url_name,
                query_string=item.query_string,
                feature_key=item.feature_key,
                sort_order=item.sort_order,
                is_enabled=item.is_enabled,
                audience=item.audience,
                active_views=list(item.active_views or []),
                keywords=list(item.keywords or []),
            )
        messages.success(request, f"Cloned “{source.name}” → “{clone.name}”.")
        return redirect("dashboard:plans:detail", pk=clone.pk)


class PlanDetailView(PlanManagementMixin, TemplateView):
    template_name = "dashboard/plans/detail.html"
    section = "list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plan = get_object_or_404(Plan, pk=self.kwargs["pk"])
        ctx["plan"] = plan
        ctx["plan_features"] = list(
            FeatureDefinition.objects.filter(is_active=True)
            .prefetch_related("plan_assignments")
            .order_by("sort_order", "name")
        )
        enabled_ids = set(
            plan.plan_features.filter(is_enabled=True).values_list("feature_id", flat=True)
        )
        ctx["enabled_feature_ids"] = enabled_ids
        ctx["menu_items"] = list(plan.menu_items.order_by("audience", "sort_order", "label"))
        ctx["audiences"] = MenuAudience.choices
        ctx["addons"] = AddOnCatalog.objects.filter(is_active=True).order_by("sort_order", "name")
        ctx["sub_count"] = plan.subscriptions.count()
        ctx["yearly_discount_percent"] = BillingSettings.get_solo().yearly_discount_percent
        return ctx


class PlanUpdateView(PlanManagementMixin, View):
    section = "list"

    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        plan.name = (request.POST.get("name") or plan.name).strip()
        plan.description = request.POST.get("description", plan.description)
        plan.is_active = request.POST.get("is_active") == "on"
        plan.trial_days = int(request.POST.get("trial_days") or plan.trial_days or 14)
        try:
            plan.monthly_price_inr = Decimal(request.POST.get("monthly_price_inr") or plan.monthly_price_inr)
            plan.setup_fee_inr = Decimal(request.POST.get("setup_fee_inr") or plan.setup_fee_inr)
        except InvalidOperation:
            messages.error(request, "Invalid pricing value.")
            return redirect("dashboard:plans:detail", pk=pk)
        plan.yearly_price_inr = BillingSettings.get_solo().compute_yearly_price(plan.monthly_price_inr)

        emp = request.POST.get("employee_limit", "").strip()
        plan.employee_limit = int(emp) if emp else None
        storage = request.POST.get("storage_limit_mb", "").strip()
        plan.storage_limit_mb = int(storage) if storage else None
        plan.save()
        _invalidate_plan_subscribers(plan)
        messages.success(request, f"Plan “{plan.name}” updated.")
        return redirect("dashboard:plans:detail", pk=pk)


class BillingSettingsUpdateView(PlanManagementMixin, View):
    """Updates the platform-wide yearly discount %; recomputes every plan's yearly price from it."""

    section = "list"

    def post(self, request):
        try:
            percent = Decimal(request.POST.get("yearly_discount_percent", ""))
            if percent < 0 or percent > 100:
                raise InvalidOperation
        except InvalidOperation:
            messages.error(request, "Enter a discount percent between 0 and 100.")
            return redirect("dashboard:plans:matrix")

        settings_obj = BillingSettings.get_solo()
        settings_obj.yearly_discount_percent = percent
        settings_obj.save(update_fields=["yearly_discount_percent", "updated_at"])

        for plan in Plan.objects.all():
            plan.yearly_price_inr = settings_obj.compute_yearly_price(plan.monthly_price_inr)
            plan.save(update_fields=["yearly_price_inr", "updated_at"])

        messages.success(request, f"Yearly discount set to {percent}% — all plans’ yearly prices recalculated.")
        return redirect("dashboard:plans:matrix")


class PlanFeatureToggleView(PlanManagementMixin, View):
    section = "list"

    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        feature = get_object_or_404(FeatureDefinition, pk=request.POST.get("feature_id"))
        enabled = request.POST.get("enabled") == "true"
        pf, _ = PlanFeature.objects.get_or_create(plan=plan, feature=feature, defaults={"is_enabled": enabled})
        pf.is_enabled = enabled
        pf.save(update_fields=["is_enabled"])
        flags = dict(plan.feature_flags or {})
        flags[feature.key] = enabled
        plan.feature_flags = flags
        plan.save(update_fields=["feature_flags", "updated_at"])
        _invalidate_plan_subscribers(plan)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "feature_key": feature.key, "enabled": enabled})
        return redirect("dashboard:plans:detail", pk=pk)


class PlanMenuReorderView(PlanManagementMixin, View):
    section = "list"

    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        try:
            order = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        item_ids = order.get("item_ids") or []
        for idx, item_id in enumerate(item_ids):
            PlanMenuItem.objects.filter(plan=plan, pk=item_id).update(sort_order=idx)
        _invalidate_plan_subscribers(plan)
        return JsonResponse({"ok": True})


class PlanMenuItemUpdateView(PlanManagementMixin, View):
    section = "list"

    def post(self, request, pk, item_pk):
        plan = get_object_or_404(Plan, pk=pk)
        item = get_object_or_404(PlanMenuItem, pk=item_pk, plan=plan)
        item.label = (request.POST.get("label") or item.label).strip()
        item.icon = (request.POST.get("icon") or item.icon).strip()
        item.url_name = (request.POST.get("url_name") or item.url_name).strip()
        item.feature_key = request.POST.get("feature_key", item.feature_key).strip()
        item.query_string = request.POST.get("query_string", item.query_string).strip()
        item.audience = request.POST.get("audience", item.audience)
        item.is_enabled = request.POST.get("is_enabled") == "on"
        item.save()
        _invalidate_plan_subscribers(plan)
        messages.success(request, f"Menu item “{item.label}” updated.")
        return redirect("dashboard:plans:detail", pk=pk)


class PlanMenuItemCreateView(PlanManagementMixin, View):
    section = "list"

    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        label = (request.POST.get("label") or "").strip()
        if not label:
            messages.error(request, "Menu label is required.")
            return redirect("dashboard:plans:detail", pk=pk)
        max_order = plan.menu_items.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
        PlanMenuItem.objects.create(
            plan=plan,
            label=label,
            icon=request.POST.get("icon", "circle"),
            url_name=request.POST.get("url_name", "dashboard:home"),
            feature_key=request.POST.get("feature_key", ""),
            query_string=request.POST.get("query_string", ""),
            audience=request.POST.get("audience", MenuAudience.ADMIN),
            sort_order=max_order + 1,
            active_views=[request.POST.get("url_name", "dashboard:home")],
            keywords=[label.lower()],
        )
        _invalidate_plan_subscribers(plan)
        messages.success(request, f"Added menu item “{label}”.")
        return redirect("dashboard:plans:detail", pk=pk)


class FeatureCatalogView(PlanManagementMixin, TemplateView):
    template_name = "dashboard/plans/features.html"
    section = "features"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["features"] = FeatureDefinition.objects.order_by("category", "sort_order", "name")
        return ctx


def _invalidate_plan_subscribers(plan: Plan) -> None:
    for org in Organization.objects.filter(subscription__plan=plan).select_related("subscription"):
        invalidate_org_entitlements(org)
