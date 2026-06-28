"""Master feature control — resolution, dependencies, audit, and bulk operations."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.core.cache import cache
from django.db import transaction

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    AddOnCatalog,
    FeatureControlAuditLog,
    FeatureDefinition,
    FeatureModule,
    FeatureRolePermission,
    FieldDefinition,
    NavigationItem,
    OrganizationFeatureOverride,
    OrganizationFieldOverride,
    OrganizationLimit,
    OrganizationNavigationOverride,
    PageDefinition,
    Plan,
    PlanFeature,
)

CACHE_TTL = 300


def _org_cache_key(org_id: str, suffix: str) -> str:
    return f"fcc:{org_id}:{suffix}"


def invalidate_org_entitlements(org: Organization) -> None:
    oid = str(org.pk)
    for suffix in (
        "features",
        "features_admin",
        "features_hr",
        "features_manager",
        "features_employee",
        "menu_admin",
        "menu_hr",
        "menu_manager",
        "menu_employee",
        "fields",
        "limits",
    ):
        cache.delete(_org_cache_key(oid, suffix))
    cache.delete("fcc:global:disabled_features")
    cache.delete("fcc:global:disabled_pages")


def _sanitize_audit_payload(value):
    """Ensure audit JSON fields are serializable (Decimal, UUID, etc.)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_audit_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_audit_payload(v) for v in value]
    return value


def log_feature_action(
    *,
    actor,
    action: str,
    summary: str,
    feature_key: str = "",
    organization=None,
    plan=None,
    old_value=None,
    new_value=None,
    reason: str = "",
    request=None,
) -> FeatureControlAuditLog:
    ip = None
    if request:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    return FeatureControlAuditLog.objects.create(
        actor=actor,
        action=action,
        feature_key=feature_key or "",
        organization=organization,
        plan=plan,
        summary=summary,
        old_value=_sanitize_audit_payload(old_value) or {},
        new_value=_sanitize_audit_payload(new_value) or {},
        reason=reason,
        ip_address=ip,
    )


def get_globally_disabled_features() -> set[str]:
    cached = cache.get("fcc:global:disabled_features")
    if cached is not None:
        return set(cached)
    keys = set(
        FeatureDefinition.objects.filter(is_active=True, is_globally_enabled=False).values_list("key", flat=True)
    )
    disabled_modules = set(
        FeatureModule.objects.filter(is_active=True, is_globally_enabled=False).values_list("key", flat=True)
    )
    if disabled_modules:
        keys.update(
            FeatureDefinition.objects.filter(module__key__in=disabled_modules, is_active=True).values_list(
                "key", flat=True
            )
        )
    cache.set("fcc:global:disabled_features", list(keys), CACHE_TTL)
    return keys


def get_plan_feature_keys(plan: Plan | None) -> set[str]:
    if not plan:
        return set()
    keys = set(
        PlanFeature.objects.filter(plan=plan, is_enabled=True, feature__is_active=True).values_list(
            "feature__key", flat=True
        )
    )
    flags = plan.feature_flags or {}
    if isinstance(flags, dict):
        keys.update(k for k, v in flags.items() if v)
    elif isinstance(flags, list):
        keys.update(flags)
    return keys


def get_org_addon_feature_keys(org: Organization) -> set[str]:
    keys: set[str] = set()
    for row in org.billing_addons.filter(is_active=True).select_related("addon"):
        keys.update(row.addon.feature_keys or [])
    return keys


def get_org_override_map(org: Organization) -> dict[str, bool]:
    return {
        row.feature.key: row.is_enabled
        for row in org.feature_overrides.select_related("feature").filter(feature__is_active=True)
    }


def resolve_feature_enabled(org: Organization | None, feature_key: str) -> bool:
    """Priority: global off → org override → plan + addons → parent hierarchy."""
    if not org or not feature_key:
        return False
    if feature_key in get_globally_disabled_features():
        return False
    feat = FeatureDefinition.objects.filter(key=feature_key, is_active=True).select_related("parent").first()
    if not feat:
        return False
    if not feat.is_globally_enabled:
        return False
    if feat.module_id and feat.module and not feat.module.is_globally_enabled:
        return False
    if feat.parent_id and not resolve_feature_enabled(org, feat.parent.key):
        return False

    overrides = get_org_override_map(org)
    if feature_key in overrides:
        return overrides[feature_key]

    from apps.subscriptions.services.entitlements import get_org_plan

    plan = get_org_plan(org)
    plan_keys = get_plan_feature_keys(plan)
    addon_keys = get_org_addon_feature_keys(org)
    return feature_key in plan_keys or feature_key in addon_keys


def _apply_parent_hierarchy(enabled: set[str]) -> set[str]:
    if not enabled:
        return enabled
    parent_map = {
        f.key: f.parent.key
        for f in FeatureDefinition.objects.filter(is_active=True, parent__isnull=False).select_related("parent")
    }
    result = set(enabled)
    changed = True
    while changed:
        changed = False
        for key in list(result):
            parent_key = parent_map.get(key)
            if parent_key and parent_key not in result:
                result.discard(key)
                changed = True
    return result


def get_enabled_feature_keys(org: Organization | None, role: str | None = None) -> set[str]:
    if not org:
        return set()
    suffix = f"features_{role.lower()}" if role else "features"
    cache_key = _org_cache_key(str(org.pk), suffix)
    cached = cache.get(cache_key)
    if cached is not None:
        return set(cached)

    from apps.subscriptions.services.entitlements import get_org_plan

    plan = get_org_plan(org)
    candidates = set(
        FeatureDefinition.objects.filter(is_active=True, is_globally_enabled=True).values_list("key", flat=True)
    )
    globally_off = get_globally_disabled_features()
    candidates -= globally_off

    plan_keys = get_plan_feature_keys(plan)
    addon_keys = get_org_addon_feature_keys(org)
    overrides = get_org_override_map(org)

    enabled: set[str] = set()
    for key in candidates:
        if key in overrides:
            if overrides[key]:
                enabled.add(key)
            continue
        if key in plan_keys or key in addon_keys:
            enabled.add(key)

    enabled = _apply_parent_hierarchy(enabled)

    if role:
        enabled = _filter_by_role(enabled, role)

    cache.set(cache_key, list(enabled), CACHE_TTL)
    if not role:
        cache.set(_org_cache_key(str(org.pk), "features"), list(enabled), CACHE_TTL)
    return enabled


def _filter_by_role(keys: set[str], role: str) -> set[str]:
    role_map = {
        User.Role.ADMIN: FeatureRolePermission.Role.ADMIN,
        User.Role.HR: FeatureRolePermission.Role.HR,
        User.Role.EMPLOYEE: FeatureRolePermission.Role.EMPLOYEE,
    }
    perm_role = role_map.get(role)
    if not perm_role:
        return keys
    denied = set(
        FeatureRolePermission.objects.filter(role=perm_role, is_allowed=False).values_list("feature__key", flat=True)
    )
    allowed_explicit = set(
        FeatureRolePermission.objects.filter(role=perm_role, is_allowed=True).values_list("feature__key", flat=True)
    )
    result = keys - denied
    for key in allowed_explicit:
        if key in keys:
            result.add(key)
    return result


def has_feature(org: Organization | None, feature_key: str, role: str | None = None) -> bool:
    if role:
        return feature_key in get_enabled_feature_keys(org, role)
    return resolve_feature_enabled(org, feature_key)


def check_dependencies(feature_key: str, enabled_keys: set[str]) -> list[str]:
    """Return list of dependency keys that would block disabling `feature_key`."""
    dependents = FeatureDefinition.objects.filter(is_active=True, depends_on__contains=[feature_key])
    warnings: list[str] = []
    for dep in FeatureDefinition.objects.filter(is_active=True):
        if feature_key in (dep.depends_on or []) and dep.key in enabled_keys:
            warnings.append(dep.key)
    for d in dependents:
        if d.key in enabled_keys:
            warnings.append(d.key)
    return list(dict.fromkeys(warnings))


def validate_disable(feature_key: str, org: Organization | None = None) -> tuple[bool, list[str]]:
    """Check if disabling feature_key would break dependents."""
    if org:
        enabled = get_enabled_feature_keys(org)
    else:
        enabled = set(FeatureDefinition.objects.filter(is_active=True, is_globally_enabled=True).values_list("key", flat=True))
    dependents = []
    for feat in FeatureDefinition.objects.filter(is_active=True):
        if feature_key in (feat.depends_on or []) and feat.key in enabled:
            dependents.append(feat.name)
    return len(dependents) == 0, dependents


@transaction.atomic
def set_global_feature(*, feature: FeatureDefinition, enabled: bool, actor, reason: str = "", request=None) -> None:
    ok, deps = validate_disable(feature.key) if not enabled else (True, [])
    if not ok:
        raise ValueError(f"Cannot disable — required by: {', '.join(deps)}")
    old = feature.is_globally_enabled
    feature.is_globally_enabled = enabled
    feature.save(update_fields=["is_globally_enabled"])
    invalidate_org_entitlements_for_all()
    log_feature_action(
        actor=actor,
        action=FeatureControlAuditLog.Action.GLOBAL_ENABLE if enabled else FeatureControlAuditLog.Action.GLOBAL_DISABLE,
        feature_key=feature.key,
        summary=f"{'Enabled' if enabled else 'Disabled'} {feature.name} globally",
        old_value={"is_globally_enabled": old},
        new_value={"is_globally_enabled": enabled},
        reason=reason,
        request=request,
    )


@transaction.atomic
def set_org_feature_override(
    *,
    org: Organization,
    feature: FeatureDefinition,
    enabled: bool | None,
    actor,
    reason: str = "",
    request=None,
) -> None:
    existing = OrganizationFeatureOverride.objects.filter(organization=org, feature=feature).first()
    old = {"is_enabled": existing.is_enabled if existing else None}
    if enabled is None:
        if existing:
            existing.delete()
        log_feature_action(
            actor=actor,
            action=FeatureControlAuditLog.Action.ORG_OVERRIDE_CLEAR,
            feature_key=feature.key,
            organization=org,
            summary=f"Cleared override for {feature.name} on {org.name}",
            old_value=old,
            new_value={},
            reason=reason,
            request=request,
        )
    else:
        OrganizationFeatureOverride.objects.update_or_create(
            organization=org,
            feature=feature,
            defaults={"is_enabled": enabled, "reason": reason, "set_by": actor},
        )
        log_feature_action(
            actor=actor,
            action=FeatureControlAuditLog.Action.ORG_OVERRIDE,
            feature_key=feature.key,
            organization=org,
            summary=f"{'Enabled' if enabled else 'Disabled'} {feature.name} for {org.name}",
            old_value=old,
            new_value={"is_enabled": enabled},
            reason=reason,
            request=request,
        )
    invalidate_org_entitlements(org)


@transaction.atomic
def set_plan_feature(*, plan: Plan, feature: FeatureDefinition, enabled: bool, actor, reason: str = "", request=None) -> None:
    pf, _ = PlanFeature.objects.get_or_create(plan=plan, feature=feature, defaults={"is_enabled": enabled})
    old = pf.is_enabled
    pf.is_enabled = enabled
    pf.save(update_fields=["is_enabled"])
    flags = dict(plan.feature_flags or {})
    flags[feature.key] = enabled
    plan.feature_flags = flags
    plan.save(update_fields=["feature_flags", "updated_at"])
    log_feature_action(
        actor=actor,
        action=FeatureControlAuditLog.Action.PLAN_ENABLE if enabled else FeatureControlAuditLog.Action.PLAN_DISABLE,
        feature_key=feature.key,
        plan=plan,
        summary=f"{'Enabled' if enabled else 'Disabled'} {feature.name} on {plan.name}",
        old_value={"is_enabled": old},
        new_value={"is_enabled": enabled},
        reason=reason,
        request=request,
    )
    for org in Organization.objects.filter(subscription__plan=plan):
        invalidate_org_entitlements(org)


def get_org_limits(org: Organization) -> dict:
    cached = cache.get(_org_cache_key(str(org.pk), "limits"))
    if cached:
        return cached
    from apps.subscriptions.services.entitlements import get_org_plan

    plan = get_org_plan(org)
    limits = {
        "employee_limit": plan.employee_limit if plan else None,
        "storage_limit_mb": plan.storage_limit_mb if plan else None,
        "branch_limit": plan.branch_limit if plan else None,
        "admin_limit": None,
        "hr_limit": None,
        "api_limit_daily": None,
    }
    try:
        override = org.feature_limits
        for field in limits:
            val = getattr(override, field, None)
            if val is not None:
                limits[field] = val
    except OrganizationLimit.DoesNotExist:
        pass
    cache.set(_org_cache_key(str(org.pk), "limits"), limits, CACHE_TTL)
    return limits


def get_visible_fields(org: Organization, form_context: str) -> set[str]:
    cache_key = _org_cache_key(str(org.pk), "fields")
    cached = cache.get(cache_key)
    if cached is None:
        all_fields = {f.key: f.is_globally_visible for f in FieldDefinition.objects.all()}
        for ov in org.field_overrides.select_related("field"):
            all_fields[ov.field.key] = ov.is_visible
        cached = all_fields
        cache.set(cache_key, cached, CACHE_TTL)
    return {k for k, v in cached.items() if v and FieldDefinition.objects.filter(key=k, form_context=form_context).exists()}


def get_navigation_items(org: Organization | None, role: str) -> list[NavigationItem]:
    if not org:
        return []
    from apps.subscriptions.services.entitlements import _audience_for_role, get_org_plan

    audience = _audience_for_role(role)
    cache_key = _org_cache_key(str(org.pk), f"menu_{audience.lower()}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    plan = get_org_plan(org)
    enabled = get_enabled_feature_keys(org, role)
    qs = NavigationItem.objects.filter(is_visible=True, audience=audience)
    if plan:
        items = list(qs.filter(plan=plan).order_by("sort_order", "label"))
        if not items:
            items = list(qs.filter(plan__isnull=True).order_by("sort_order", "label"))
    else:
        items = list(qs.filter(plan__isnull=True).order_by("sort_order", "label"))

    nav_overrides = {
        row.navigation_item_id: row
        for row in OrganizationNavigationOverride.objects.filter(organization=org).select_related("navigation_item")
    }
    filtered: list[NavigationItem] = []
    for item in items:
        ov = nav_overrides.get(item.pk)
        if ov and not ov.is_visible:
            continue
        if item.feature_key and item.feature_key not in enabled:
            continue
        filtered.append(item)

    if nav_overrides:
        filtered.sort(key=lambda i: (nav_overrides[i.pk].sort_order if i.pk in nav_overrides and nav_overrides[i.pk].sort_order is not None else i.sort_order))

    cache.set(cache_key, filtered, CACHE_TTL)
    return filtered


def invalidate_org_entitlements_for_all() -> None:
    cache.delete("fcc:global:disabled_features")
    for org in Organization.objects.all().only("pk"):
        invalidate_org_entitlements(org)


def get_feature_for_url_name(url_name: str) -> str | None:
    page = PageDefinition.objects.filter(url_name=url_name, is_globally_enabled=True).select_related("feature").first()
    if page and page.feature_id:
        return page.feature.key
    for feat in FeatureDefinition.objects.filter(is_active=True):
        if url_name in (feat.url_names or []):
            return feat.key
    return None


def is_page_enabled(org: Organization | None, url_name: str, role: str | None = None) -> bool:
    page = PageDefinition.objects.filter(url_name=url_name).select_related("feature").first()
    if page and not page.is_globally_enabled:
        return False
    key = get_feature_for_url_name(url_name)
    if not key:
        return True
    return has_feature(org, key, role)
