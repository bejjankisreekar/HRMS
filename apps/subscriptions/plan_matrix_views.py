"""Super Admin — side-by-side plan feature matrix."""

from __future__ import annotations

import json

from decimal import Decimal, InvalidOperation

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.subscriptions.models import FeatureControlAuditLog, FeatureDefinition, Plan, Subscription, SubscriptionStatus
from apps.subscriptions.services.feature_control import (
    invalidate_org_entitlements_for_all,
    log_feature_action,
    set_plan_feature,
)
from apps.subscriptions.services.pricing_matrix import FEATURED_PLAN_SLUG, build_feature_matrix, get_catalog_plans


PLAN_SHORT_NAMES = {
    "basic": "Basic",
    "professional": "Pro",
    "growth": "Growth",
}

PLAN_ACCENTS = {
    "basic": {"color": "#475569", "bg": "#f8fafc", "ring": "#e2e8f0"},
    "professional": {"color": "#2563eb", "bg": "#eff6ff", "ring": "#bfdbfe"},
    "growth": {"color": "#7c3aed", "bg": "#f5f3ff", "ring": "#ddd6fe"},
}


def _storage_label(mb: int | None) -> str:
    if not mb:
        return "Unlimited"
    if mb >= 1024:
        gb = mb / 1024
        return f"{int(gb)} GB" if gb == int(gb) else f"{gb:.1f} GB"
    return f"{mb} MB"


def _employee_label(limit: int | None) -> str:
    if not limit:
        return "Unlimited"
    return f"{limit:,} employees"


def _org_counts_for_plans(plans: list[Plan]) -> dict[str, int]:
    active_statuses = (
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIAL,
        SubscriptionStatus.PAST_DUE,
    )
    rows = (
        Subscription.objects.filter(plan__in=plans, status__in=active_statuses)
        .values("plan_id")
        .annotate(total=Count("id"))
    )
    return {str(r["plan_id"]): r["total"] for r in rows}


def _matrix_context() -> dict:
    plans = get_catalog_plans()
    matrix = build_feature_matrix(plans=plans)
    org_counts = _org_counts_for_plans(plans)
    meta_display = []
    for meta in matrix["meta_rows"]:
        if meta["label"] in ("Annual price", "Employee limit", "Monthly price"):
            continue
        meta_display.append(
            {
                "label": meta["label"],
                "values": [meta["cells"].get(str(p.pk), "—") for p in plans],
            }
        )
    plan_cards = []
    for p in plans:
        accent = PLAN_ACCENTS.get(p.slug, PLAN_ACCENTS["basic"])
        plan_cards.append(
            {
                "plan_id": p.pk,
                "plan_slug": p.slug,
                "plan_name": p.name,
                "monthly_price_inr": p.monthly_price_inr,
                "employee_limit": p.employee_limit,
                "storage_limit_mb": p.storage_limit_mb,
                "employee_label": _employee_label(p.employee_limit),
                "storage_label": _storage_label(p.storage_limit_mb),
                "org_count": org_counts.get(str(p.pk), 0),
                "is_featured": p.slug == FEATURED_PLAN_SLUG,
                "is_active": p.is_active,
                "accent_color": accent["color"],
                "accent_bg": accent["bg"],
                "accent_ring": accent["ring"],
            }
        )
    groups = []
    for group in matrix["groups"]:
        rows = []
        for row in group["rows"]:
            rows.append(
                {
                    **row,
                    "checks": [
                        {
                            "plan_id": p.pk,
                            "plan_slug": p.slug,
                            "enabled": row["cells"].get(str(p.pk), False),
                        }
                        for p in plans
                    ],
                }
            )
        groups.append({
            "category": group["category"],
            "rows": rows,
            "category_id": group["category"].pk if group["category"] else "other",
            "category_name": group["category"].name if group["category"] else "Other",
            "category_icon": getattr(group["category"], "icon", "layers") if group["category"] else "layers",
        })
    total_features = sum(len(g["rows"]) for g in groups)
    enabled_map = matrix["enabled_map"]
    plan_summaries = [
        {
            "plan_id": p.pk,
            "plan_slug": p.slug,
            "plan_name": p.name,
            "plan_short": PLAN_SHORT_NAMES.get(p.slug, p.name[:3]),
            "enabled_count": len(enabled_map.get(p.pk, set())),
            "accent_color": PLAN_ACCENTS.get(p.slug, PLAN_ACCENTS["basic"])["color"],
            "is_featured": p.slug == FEATURED_PLAN_SLUG,
        }
        for p in plans
    ]
    total_orgs = sum(org_counts.values())
    return {
        "plans": plans,
        "plan_cards": plan_cards,
        "plan_summaries": plan_summaries,
        "groups": groups,
        "meta_rows": meta_display,
        "total_features": total_features,
        "page_stats": {
            "plan_count": len(plans),
            "feature_count": total_features,
            "org_count": total_orgs,
            "category_count": len(groups),
        },
    }


class PlanFeatureMatrixView(SuperAdminRequiredMixin, TemplateView):
    template_name = "dashboard/plans/feature_matrix.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_matrix_context())
        return ctx


class PlanFeatureMatrixAPIView(SuperAdminRequiredMixin, View):
    def post(self, request):
        if request.content_type and "application/json" in request.content_type:
            try:
                data = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        else:
            data = request.POST.dict()

        action = data.get("action", "toggle")
        if action == "toggle":
            plan = Plan.objects.filter(pk=data.get("plan_id")).first()
            feature = FeatureDefinition.objects.filter(pk=data.get("feature_id")).first()
            if not plan or not feature:
                return JsonResponse({"ok": False, "error": "Invalid plan or feature"}, status=400)
            enabled = data.get("enabled") in (True, "true", "1", 1)
            set_plan_feature(plan=plan, feature=feature, enabled=enabled, actor=request.user, request=request)
            return JsonResponse({"ok": True, "enabled": enabled, "feature_key": feature.key})

        if action == "bulk_column":
            plan = Plan.objects.filter(pk=data.get("plan_id")).first()
            if not plan:
                return JsonResponse({"ok": False, "error": "Invalid plan"}, status=400)
            enabled = data.get("enabled") in (True, "true", "1", 1)
            for feat in FeatureDefinition.objects.filter(is_active=True):
                set_plan_feature(plan=plan, feature=feat, enabled=enabled, actor=request.user, request=request)
            return JsonResponse({"ok": True})

        if action == "update_plan_settings":
            plan = Plan.objects.filter(pk=data.get("plan_id")).first()
            if not plan:
                return JsonResponse({"ok": False, "error": "Invalid plan"}, status=400)

            int_fields = ("employee_limit", "storage_limit_mb")
            old_values = {}
            new_values = {}

            for field in int_fields:
                if field not in data:
                    continue
                raw = str(data.get(field, "")).strip()
                if raw.lower() in ("", "unlimited", "null", "none"):
                    new_val = None
                else:
                    try:
                        new_val = int(raw)
                        if new_val < 0:
                            raise ValueError
                    except ValueError:
                        return JsonResponse(
                            {"ok": False, "error": f"Invalid {field.replace('_', ' ')}"},
                            status=400,
                        )
                old_values[field] = getattr(plan, field)
                new_values[field] = new_val
                setattr(plan, field, new_val)

            if "monthly_price_inr" in data:
                raw = str(data.get("monthly_price_inr", "")).strip()
                if not raw:
                    return JsonResponse({"ok": False, "error": "Monthly price is required"}, status=400)
                try:
                    new_price = Decimal(raw)
                    if new_price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    return JsonResponse({"ok": False, "error": "Enter a valid monthly price"}, status=400)
                old_values["monthly_price_inr"] = plan.monthly_price_inr
                new_values["monthly_price_inr"] = new_price
                plan.monthly_price_inr = new_price

            if not new_values:
                return JsonResponse({"ok": False, "error": "Nothing to save"}, status=400)

            plan.save()
            invalidate_org_entitlements_for_all()
            log_feature_action(
                actor=request.user,
                action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
                plan=plan,
                summary=f"Updated plan settings for {plan.name}",
                old_value=old_values,
                new_value=new_values,
                request=request,
            )
            return JsonResponse(
                {
                    "ok": True,
                    "plan_id": str(plan.pk),
                    "monthly_price_inr": float(plan.monthly_price_inr),
                    "employee_limit": plan.employee_limit,
                    "storage_limit_mb": plan.storage_limit_mb,
                    "employee_label": _employee_label(plan.employee_limit),
                    "storage_label": _storage_label(plan.storage_limit_mb),
                }
            )

        if action == "update_plan_limit":
            plan = Plan.objects.filter(pk=data.get("plan_id")).first()
            if not plan:
                return JsonResponse({"ok": False, "error": "Invalid plan"}, status=400)
            field = data.get("field", "employee_limit")
            if field not in ("employee_limit", "storage_limit_mb"):
                return JsonResponse({"ok": False, "error": "Invalid field"}, status=400)
            raw = str(data.get("value", "")).strip()
            if raw.lower() in ("", "unlimited", "null", "none"):
                new_val = None
            else:
                try:
                    new_val = int(raw)
                    if new_val < 0:
                        raise ValueError
                except ValueError:
                    return JsonResponse({"ok": False, "error": "Enter a positive number or leave empty for unlimited"}, status=400)
            old_val = getattr(plan, field)
            setattr(plan, field, new_val)
            plan.save(update_fields=[field, "updated_at"])
            invalidate_org_entitlements_for_all()
            log_feature_action(
                actor=request.user,
                action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
                plan=plan,
                summary=f"Updated {field.replace('_', ' ')} for {plan.name}",
                old_value={field: old_val},
                new_value={field: new_val},
                request=request,
            )
            display = str(new_val) if new_val is not None else "Unlimited"
            return JsonResponse({"ok": True, "display": display})

        return JsonResponse({"ok": False, "error": "Unknown action"}, status=400)


class LegacyFeatureControlRedirectView(SuperAdminRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect("dashboard:plans:matrix")
