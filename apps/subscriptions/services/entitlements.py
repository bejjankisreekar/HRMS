"""Plan-based feature entitlements — delegates to feature_control for resolution."""

from __future__ import annotations

from apps.organizations.models import Organization
from apps.subscriptions.models import Plan, PlanMenuItem, Subscription
from apps.subscriptions.plan_catalog import FEATURE_MIN_PLAN
from apps.subscriptions.services import feature_control as fc

# Re-export cache invalidation
invalidate_org_entitlements = fc.invalidate_org_entitlements


def get_org_plan(org: Organization | None) -> Plan | None:
    if not org:
        return None
    sub = getattr(org, "subscription", None)
    if sub and sub.plan_id:
        return sub.plan
    slug = _org_plan_slug_fallback(org)
    if not slug:
        return Plan.objects.filter(is_active=True).order_by("sort_order").first()
    return Plan.objects.filter(slug=slug, is_active=True).first()


def _org_plan_slug_fallback(org: Organization) -> str:
    mapping = {
        Organization.SubscriptionPlan.BASIC: "basic",
        Organization.SubscriptionPlan.PROFESSIONAL: "professional",
        Organization.SubscriptionPlan.GROWTH: "growth",
    }
    return mapping.get(org.subscription_plan, "basic")


def get_enabled_feature_keys(org: Organization | None, role: str | None = None) -> set[str]:
    return fc.get_enabled_feature_keys(org, role)


def has_feature(org: Organization | None, feature_key: str, role: str | None = None) -> bool:
    return fc.has_feature(org, feature_key, role)


def get_min_plan_for_feature(feature_key: str) -> Plan | None:
    slug = FEATURE_MIN_PLAN.get(feature_key)
    if not slug:
        return None
    return Plan.objects.filter(slug=slug, is_active=True).first()


def get_feature_for_url_name(url_name: str) -> str | None:
    return fc.get_feature_for_url_name(url_name)


def get_upgrade_context(org: Organization, feature_key: str) -> dict:
    plan = get_org_plan(org)
    min_plan = get_min_plan_for_feature(feature_key)
    from apps.subscriptions.models import FeatureDefinition

    feature = FeatureDefinition.objects.filter(key=feature_key).first()
    all_plans = list(Plan.objects.filter(is_active=True).order_by("sort_order"))
    return {
        "feature_key": feature_key,
        "feature_name": feature.name if feature else feature_key.replace("_", " ").title(),
        "current_plan": plan,
        "required_plan": min_plan,
        "required_plan_name": min_plan.name if min_plan else "Professional",
        "available_plans": all_plans,
        "organization": org,
    }


def _audience_for_role(role: str) -> str:
    from apps.accounts.models import User
    from apps.subscriptions.models import MenuAudience

    if role == User.Role.HR:
        return MenuAudience.HR
    if role == User.Role.EMPLOYEE:
        return MenuAudience.EMPLOYEE
    return MenuAudience.ADMIN


def get_plan_menu_items(org: Organization | None, role: str) -> list:
    """Return navigation items — prefers NavigationItem, falls back to PlanMenuItem."""
    if not org:
        return []
    nav = fc.get_navigation_items(org, role)
    if nav:
        return nav

    from apps.subscriptions.models import PlanMenuItem

    audience = _audience_for_role(role)
    plan = get_org_plan(org)
    if not plan:
        return []
    enabled = get_enabled_feature_keys(org, role)
    items = list(
        PlanMenuItem.objects.filter(plan=plan, audience=audience, is_enabled=True).order_by("sort_order", "label")
    )
    return [item for item in items if not item.feature_key or item.feature_key in enabled]


def plan_has_menu_items(plan: Plan) -> bool:
    from apps.subscriptions.models import NavigationItem, PlanMenuItem

    if NavigationItem.objects.filter(plan=plan, is_visible=True).exists():
        return True
    return PlanMenuItem.objects.filter(plan=plan, is_enabled=True).exists()
