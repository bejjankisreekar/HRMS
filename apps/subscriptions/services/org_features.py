"""Organization-specific feature control — bulk ops, hierarchy, and UI data."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization
from apps.subscriptions.models import (
    FeatureCategory,
    FeatureControlAuditLog,
    FeatureDefinition,
    OrganizationFeatureOverride,
    PlanFeature,
)
from apps.subscriptions.services.entitlements import get_org_plan
from apps.subscriptions.services.feature_control import (
    get_enabled_feature_keys,
    get_org_addon_feature_keys,
    get_plan_feature_keys,
    invalidate_org_entitlements,
    log_feature_action,
    set_org_feature_override,
)


def get_org_feature_summary(org: Organization) -> dict:
    enabled = get_enabled_feature_keys(org)
    plan = get_org_plan(org)
    plan_keys = get_plan_feature_keys(plan)
    all_features = list(FeatureDefinition.objects.filter(is_active=True, feature_type="FEATURE"))
    enabled_count = sum(1 for f in all_features if f.key in enabled)
    disabled_count = len(all_features) - enabled_count
    plan_count = sum(1 for f in all_features if f.key in enabled and f.key in plan_keys)
    complementary_count = sum(
        1 for f in all_features if f.key in enabled and f.key not in plan_keys
    )
    addon_count = org.billing_addons.filter(is_active=True).count()
    last_override = org.feature_overrides.order_by("-updated_at").first()
    last_audit = org.feature_control_logs.order_by("-created_at").first()
    last_modified = None
    for dt in filter(None, [
        last_override.updated_at if last_override else None,
        last_audit.created_at if last_audit else None,
    ]):
        if last_modified is None or dt > last_modified:
            last_modified = dt
    return {
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "plan_count": plan_count,
        "complementary_count": complementary_count,
        "addon_count": addon_count,
        "override_count": org.feature_overrides.count(),
        "last_modified": last_modified,
    }


def build_org_feature_matrix(org: Organization) -> dict:
    """Side-by-side plan vs organization feature comparison for Super Admin."""
    plan = get_org_plan(org)
    categories = build_org_feature_categories(org)
    groups = []
    for cat in categories:
        rows = []
        for item in cat["items"]:
            feat = item["feature"]
            is_complementary = item["effective"] and not item["in_plan"]
            rows.append(
                {
                    "feature_id": feat.pk,
                    "feature_key": feat.key,
                    "name": feat.name,
                    "in_plan": item["in_plan"],
                    "effective": item["effective"],
                    "override": item["override"],
                    "is_complementary": is_complementary,
                    "parent_key": item["parent_key"],
                    "parent_disabled": item["parent_disabled"],
                    "is_child": bool(feat.parent_id),
                }
            )
        groups.append(
            {
                "category": cat["category"],
                "category_id": cat["category"].pk if cat["category"] else "other",
                "category_name": cat["category"].name if cat["category"] else "Other",
                "category_icon": getattr(cat["category"], "icon", "layers") if cat["category"] else "layers",
                "rows": rows,
            }
        )
    total = sum(len(g["rows"]) for g in groups)
    return {
        "plan": plan,
        "groups": groups,
        "summary": get_org_feature_summary(org),
        "total_features": total,
    }


def build_org_feature_categories(org: Organization) -> list[dict]:
    """Build categorized feature rows for the org control UI."""
    plan = get_org_plan(org)
    plan_keys = get_plan_feature_keys(plan)
    enabled = get_enabled_feature_keys(org)
    overrides = {o.feature_id: o for o in org.feature_overrides.select_related("feature")}

    categories = list(FeatureCategory.objects.filter(is_active=True).order_by("sort_order", "name"))
    features = list(
        FeatureDefinition.objects.filter(is_active=True, feature_type="FEATURE")
        .select_related("display_category", "parent")
        .order_by("sort_order", "name")
    )

    by_category: dict[str | None, list] = {c.pk: [] for c in categories}
    by_category[None] = []

    for feat in features:
        cat_id = feat.display_category_id
        ov = overrides.get(feat.pk)
        parent_enabled = True
        if feat.parent_id:
            parent_enabled = feat.parent.key in enabled
        effective = feat.key in enabled and parent_enabled
        by_category.get(cat_id, by_category[None]).append(
            {
                "feature": feat,
                "effective": effective,
                "override": ov.is_enabled if ov else None,
                "in_plan": feat.key in plan_keys,
                "global_on": feat.is_globally_enabled,
                "parent_key": feat.parent.key if feat.parent_id else "",
                "parent_disabled": feat.parent_id and not parent_enabled,
                "is_parent": FeatureDefinition.objects.filter(parent=feat, is_active=True).exists(),
            }
        )

    result = []
    for cat in categories:
        items = by_category.get(cat.pk, [])
        if items:
            result.append({"category": cat, "items": items})
    if by_category[None]:
        result.append({"category": None, "items": by_category[None]})
    return result


def _child_features(feature: FeatureDefinition) -> list[FeatureDefinition]:
    return list(FeatureDefinition.objects.filter(parent=feature, is_active=True))


@transaction.atomic
def set_org_feature_enabled(
    *,
    org: Organization,
    feature: FeatureDefinition,
    enabled: bool,
    actor,
    reason: str = "",
    request=None,
    cascade: bool = True,
) -> None:
    """Enable/disable a feature for an org; cascade to children when disabling."""
    set_org_feature_override(
        org=org,
        feature=feature,
        enabled=enabled,
        actor=actor,
        reason=reason,
        request=request,
    )
    if cascade and not enabled:
        for child in _child_features(feature):
            set_org_feature_override(
                org=org,
                feature=child,
                enabled=False,
                actor=actor,
                reason=f"Auto-disabled: parent {feature.key} disabled",
                request=request,
            )


@transaction.atomic
def reset_org_to_plan_defaults(*, org: Organization, actor, request=None) -> int:
    count = org.feature_overrides.count()
    for ov in org.feature_overrides.select_related("feature"):
        log_feature_action(
            actor=actor,
            action=FeatureControlAuditLog.Action.ORG_OVERRIDE_CLEAR,
            feature_key=ov.feature.key,
            organization=org,
            summary=f"Reset {ov.feature.name} to plan default for {org.name}",
            old_value={"is_enabled": ov.is_enabled},
            new_value={},
            request=request,
        )
    org.feature_overrides.all().delete()
    invalidate_org_entitlements(org)
    return count


@transaction.atomic
def bulk_set_category(
    *,
    org: Organization,
    category: FeatureCategory,
    enabled: bool,
    actor,
    request=None,
) -> int:
    features = FeatureDefinition.objects.filter(display_category=category, is_active=True).order_by("parent_id", "sort_order")
    count = 0
    for feat in features:
        set_org_feature_enabled(
            org=org, feature=feat, enabled=enabled, actor=actor, request=request, cascade=enabled is False
        )
        count += 1
    return count


@transaction.atomic
def bulk_set_all(*, org: Organization, enabled: bool, actor, request=None) -> int:
    roots = FeatureDefinition.objects.filter(is_active=True, feature_type="FEATURE", parent__isnull=True)
    count = 0
    for feat in roots:
        set_org_feature_enabled(
            org=org, feature=feat, enabled=enabled, actor=actor, request=request, cascade=not enabled
        )
        count += 1
    return count


def get_path_prefix_map() -> list[tuple[str, str, bool]]:
    """Return (prefix, feature_key, is_api) sorted longest-first."""
    rows = []
    for feat in FeatureDefinition.objects.filter(is_active=True):
        if feat.path_prefix:
            rows.append((feat.path_prefix, feat.key, False))
        if feat.api_path_prefix:
            rows.append((feat.api_path_prefix, feat.key, True))
    rows.sort(key=lambda r: len(r[0]), reverse=True)
    return rows


def feature_for_path(path: str) -> tuple[str | None, bool]:
    for prefix, key, is_api in get_path_prefix_map():
        if path.startswith(prefix):
            return key, is_api
    return None, False
