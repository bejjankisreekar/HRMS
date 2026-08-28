"""Shared plan × feature matrix for Super Admin and public pricing page."""

from __future__ import annotations

from apps.subscriptions import plan_features
from apps.subscriptions.models import (
    AddOnCatalog,
    BillingSettings,
    FeatureCategory,
    FeatureDefinition,
    FeatureType,
    Plan,
    PlanFeature,
)

# Plan slug shown as "Most popular" on marketing site
FEATURED_PLAN_SLUG = plan_features.FEATURED_TIER.slug


def _plan_enabled_map() -> dict:
    """plan_id → set of enabled feature ids."""
    result: dict = {}
    for row in PlanFeature.objects.filter(is_enabled=True).select_related("plan", "feature"):
        result.setdefault(row.plan_id, set()).add(row.feature_id)
    return result


def get_active_plans() -> list[Plan]:
    return list(Plan.objects.filter(is_active=True).order_by("sort_order", "name"))


def get_catalog_plans() -> list[Plan]:
    """All plans for Super Admin matrix (includes inactive tiers like Basic)."""
    return list(Plan.objects.all().order_by("sort_order", "name"))


def build_feature_matrix(*, include_meta: bool = True, plans: list[Plan] | None = None) -> dict:
    if plans is None:
        plans = get_active_plans()
    enabled_map = _plan_enabled_map()
    categories = list(FeatureCategory.objects.filter(is_active=True).order_by("sort_order", "name"))
    features = list(
        FeatureDefinition.objects.filter(is_active=True, feature_type=FeatureType.FEATURE)
        .select_related("display_category", "parent")
        .order_by("display_category__sort_order", "parent_id", "sort_order", "name")
    )

    groups: list[dict] = []
    for cat in categories:
        items = [f for f in features if f.display_category_id == cat.pk]
        if not items:
            continue
        rows = []
        for feat in items:
            rows.append(
                {
                    "feature": feat,
                    "feature_id": str(feat.pk),
                    "feature_key": feat.key,
                    "name": feat.name,
                    "is_child": bool(feat.parent_id),
                    "parent_key": feat.parent.key if feat.parent_id else "",
                    "cells": {str(p.pk): feat.pk in enabled_map.get(p.pk, set()) for p in plans},
                }
            )
        groups.append({"category": cat, "rows": rows})

    uncategorized = [f for f in features if not f.display_category_id]
    if uncategorized:
        rows = [
            {
                "feature": f,
                "feature_id": str(f.pk),
                "feature_key": f.key,
                "name": f.name,
                "is_child": bool(f.parent_id),
                "parent_key": f.parent.key if f.parent_id else "",
                "cells": {str(p.pk): f.pk in enabled_map.get(p.pk, set()) for p in plans},
            }
            for f in uncategorized
        ]
        groups.append({"category": None, "rows": rows})

    meta_rows = []
    if include_meta and plans:
        meta_rows = [
            {
                "label": "Monthly price",
                "cells": {str(p.pk): f"₹{p.monthly_price_inr:,.0f}" for p in plans},
                "is_meta": True,
            },
            {
                "label": "Annual price",
                "cells": {str(p.pk): f"₹{p.yearly_price_inr:,.0f}" for p in plans},
                "is_meta": True,
            },
            {
                "label": "Employee limit",
                "cells": {
                    str(p.pk): str(p.employee_limit) if p.employee_limit else "Unlimited"
                    for p in plans
                },
                "is_meta": True,
            },
        ]

    return {
        "plans": plans,
        "groups": groups,
        "meta_rows": meta_rows,
        "enabled_map": enabled_map,
    }


def _employee_limit_label(plan: Plan) -> str:
    if not plan.employee_limit:
        return "Unlimited employees"
    return f"Up to {plan.employee_limit} employees"


def _plan_tagline(plan: Plan) -> str:
    """e.g. "Growth — scaling organizations", built from plan_features."""
    tier = plan_features.get_tier(plan.slug)
    if not tier:
        return plan.name
    return f"{tier.name} — {tier.tagline}"


def plan_to_marketing_card(plan: Plan, enabled_map: dict) -> dict:
    enabled_ids = enabled_map.get(plan.pk, set())
    feature_names = list(
        FeatureDefinition.objects.filter(pk__in=enabled_ids, parent__isnull=True)
        .order_by("sort_order", "name")
        .values_list("name", flat=True)[:8]
    )
    if not feature_names:
        feature_names = list(
            FeatureDefinition.objects.filter(pk__in=enabled_ids)
            .order_by("sort_order", "name")
            .values_list("name", flat=True)[:8]
        )
    feature_names.insert(0, _employee_limit_label(plan))

    return {
        "id": plan.slug,
        "name": plan.name,
        "tagline": _plan_tagline(plan),
        "description": plan.description or f"{plan.name} plan for your organization.",
        "monthly_price": int(plan.monthly_price_inr),
        "yearly_price": int(plan.yearly_price_inr),
        "employee_limit": _employee_limit_label(plan),
        "popular": plan.slug == FEATURED_PLAN_SLUG,
        "cta_label": "Start free trial",
        "cta_style": "primary" if plan.slug == FEATURED_PLAN_SLUG else "outline",
        "features": feature_names,
    }


def build_comparison_rows(plans: list[Plan], groups: list[dict], meta_rows: list[dict]) -> list[dict]:
    """Flat rows for marketing comparison table."""
    rows: list[dict] = []
    for meta in meta_rows:
        if meta["label"] in ("Annual price",):
            continue
        rows.append(
            {
                "label": meta["label"],
                "is_meta": True,
                "is_category": False,
                "values": [
                    {"val": meta["cells"].get(str(p.pk), "—"), "popular": p.slug == FEATURED_PLAN_SLUG}
                    for p in plans
                ],
            }
        )
    for group in groups:
        cat = group["category"]
        if cat:
            rows.append({"label": cat.name, "is_category": True, "is_meta": False, "values": []})
        for row in group["rows"]:
            if row["is_child"]:
                continue
            rows.append(
                {
                    "label": row["name"],
                    "is_meta": False,
                    "is_category": False,
                    "values": [
                        {
                            "val": True if row["cells"].get(str(p.pk)) else False,
                            "popular": p.slug == FEATURED_PLAN_SLUG,
                        }
                        for p in plans
                    ],
                }
            )
    return rows


def get_marketing_addons() -> list[dict]:
    return [
        {
            "name": a.name,
            "description": a.description,
            "monthly_price": int(a.monthly_price_inr),
            "icon": a.icon or "puzzle",
        }
        for a in AddOnCatalog.objects.filter(is_active=True).order_by("sort_order", "name")
    ]


def get_pricing_page_context() -> dict:
    matrix = build_feature_matrix()
    plans = matrix["plans"]
    enabled_map = matrix["enabled_map"]
    pricing_plans = [plan_to_marketing_card(p, enabled_map) for p in plans]
    comparison_features = build_comparison_rows(plans, matrix["groups"], matrix["meta_rows"])

    return {
        "pricing_plans": pricing_plans,
        "comparison_features": comparison_features,
        "pricing_matrix": matrix,
        "pricing_addons": get_marketing_addons(),
        "yearly_savings_percent": BillingSettings.get_solo().yearly_discount_percent,
        # Static content retained
        "pricing_faq": _PRICING_FAQ,
        "trust_items": _TRUST_ITEMS,
        "pricing_testimonials": _PRICING_TESTIMONIALS,
    }


_PRICING_FAQ = [
    (
        "Is pricing per organization or per employee?",
        "All plans are flat monthly or annual fees for your organization — not per employee. Employee limits are included in each tier.",
    ),
    (
        "Can I switch plans later?",
        "Yes. Upgrade or downgrade anytime. Changes take effect on your next billing cycle.",
    ),
    (
        "Is there a free trial?",
        "Every plan includes a 14-day free trial with full access. No credit card required to start.",
    ),
    (
        "Are add-ons billed separately?",
        "Yes. Add-ons are optional flat monthly charges added to your base plan.",
    ),
]

_TRUST_ITEMS = [
    ("Secure payments", "PCI-compliant payment processing via Razorpay / Stripe.", "shield-check"),
    ("Cloud hosting", "Hosted on secure cloud infrastructure with daily backups.", "cloud"),
    ("Data privacy", "Tenant-isolated data with encryption at rest and in transit.", "lock"),
    ("Uptime guarantee", f"99.9% uptime SLA on {plan_features.GROWTH.name} plan.", "activity"),
]

_PRICING_TESTIMONIALS = [
    {
        "quote": "Flat monthly pricing gives us everything we need without per-seat surprises.",
        "name": "Priya Sharma",
        "role": "HR Director, NovaTech",
    },
    {
        "quote": f"We started on {plan_features.BASIC.name} and upgraded to {plan_features.GROWTH.name} as we scaled — predictable costs throughout.",
        "name": "Michael Chen",
        "role": "Finance Lead, GreenLeaf",
    },
]
