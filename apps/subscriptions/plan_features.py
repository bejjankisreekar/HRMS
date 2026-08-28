"""
THE PLANS - the one file to edit.

This file defines the three plans in two parts:

    1. WHAT THEY ARE CALLED - the PLAN_TIERS registry (name, slug, tagline,
       short name, brand colour). This is the single source of truth for plan
       naming across the whole project, before and after login: the public
       pricing page, the signup dropdown, dashboard badges, Super Admin, the
       plan comparison matrix. Change `name` here and it changes everywhere.

    2. WHAT THEY INCLUDE - three plain lists, BASIC_FEATURES,
       PROFESSIONAL_FEATURES and GROWTH_FEATURES. A feature key in a list means
       that plan includes it. To move a feature between plans, add or remove the
       key. Nothing else in the codebase needs to change.

The feature lists are written out IN FULL on purpose. Growth is not
"professional + extras" and professional is not "basic + extras": each list says
exactly what that plan has, so you can read one list and know the whole plan. The
trade-off is that a feature every plan should have must be added to all three.


    == RENAMING A PLAN ====================================================
    Edit `name` on the tier, then push it onto existing database rows (the
    pricing page and Super Admin read Plan.name out of the database):

        python manage.py sync_plan_identity --dry-run
        python manage.py sync_plan_identity

    Changing a `slug` also needs the database told about the old value:

        python manage.py sync_plan_identity --rename basic=starter

    Changing `enum_value` is the one field that needs a real data migration -
    it is the value stored in Organization.subscription_plan. Leave it alone
    unless you know why you are changing it.

    Renaming may make Django want a no-op AlterField migration, because the
    Organization.SubscriptionPlan labels follow these names. It is cosmetic:
    the column data does not change, and nothing breaks if you skip it.


    == MOVING A FEATURE BETWEEN PLANS =====================================
    Edit the three lists, then re-seed - organizations read entitlements from
    the database, not from this file:

        python manage.py seed_plan_features

    ...then invalidate the per-org cache (5-minute TTL) for affected orgs:

        from apps.subscriptions.services.entitlements import invalidate_org_entitlements

    Careful: `seed_feature_control` also rebuilds FeatureRolePermission defaults
    platform-wide, which discards any role permissions an admin has customised.
    Prefer a targeted row update over a full re-seed on a live database.


    == ADDING A BRAND-NEW FEATURE =========================================
    1. Add the key + display name to FEATURE_CATALOG in `plan_catalog.py`.
    2. Add the key to whichever of the three lists should include it.
    3. Re-seed as above.


    == CHECKING YOUR EDITS ================================================
        python manage.py shell -c "from apps.subscriptions.plan_features import check; print(check())"

    `check()` catches the failure mode that bites hardest here: a mistyped
    feature key is not an error anywhere - the nav row silently vanishes.
    `sync_plan_identity` runs it for you and reports database drift too.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── The three plans: names, slugs and branding ─────────────────────────────
#
# This block is the single source of truth for what the plans are CALLED —
# everywhere in the project, before and after login: the public pricing page,
# the signup form, dashboard badges, Super Admin, the plan comparison matrix.
#
# Change `name` here and it changes everywhere (run `sync_plan_identity`, below,
# to push the new name onto existing database rows).


@dataclass(frozen=True)
class PlanTier:
    """One plan's identity. See PLAN_TIERS below."""

    slug: str
    """Internal key. Used as a dict key, a Plan.slug database value and in URLs.
    Changing this needs a database rename — see `sync_plan_identity --rename`."""

    name: str
    """Display name shown to users. Safe to change freely."""

    short_name: str
    """Compact label for narrow columns (the comparison matrix header)."""

    tagline: str
    """Who the plan is for, shown under the name on the pricing page."""

    description: str
    """One-line summary, seeded into Plan.description."""

    enum_value: str
    """Value stored in Organization.subscription_plan. Changing this needs a
    data migration — leave it alone unless you know why you are changing it."""

    accent: str
    """Brand colour, used by the plan matrix and pricing cards."""

    accent_bg: str
    accent_ring: str

    aliases: tuple[str, ...] = ()
    """Historic slugs that should still resolve to this tier."""


BASIC = PlanTier(
    slug="basic",
    name="Basic",
    short_name="Basic",
    tagline="small teams",
    description="Core HR for small teams.",
    enum_value="BASIC",
    accent="#475569",
    accent_bg="#f8fafc",
    accent_ring="#e2e8f0",
    aliases=("essential", "starter", "free"),
)

PROFESSIONAL = PlanTier(
    slug="professional",
    name="Professional",
    short_name="Pro",
    tagline="growing companies",
    description="Payroll, performance, and analytics.",
    enum_value="PROFESSIONAL",
    accent="#2563eb",
    accent_bg="#eff6ff",
    accent_ring="#bfdbfe",
    aliases=("premium",),
)

GROWTH = PlanTier(
    slug="growth",
    name="Growth",      # <- change this
    short_name="Growth",
    tagline="scaling organizations",
    description=(
        "Full platform — multi-branch, advanced analytics, compliance, "
        "and unlimited scale."
    ),
    enum_value="GROWTH",
    accent="#7c3aed",
    accent_bg="#f5f3ff",
    accent_ring="#ddd6fe",
    aliases=("business", "enterprise"),
)

PLAN_TIERS: tuple[PlanTier, ...] = (BASIC, PROFESSIONAL, GROWTH)

#: Plan shown as "Most popular" on the marketing pricing page.
FEATURED_TIER = GROWTH

#: Fallback when a plan cannot be resolved.
DEFAULT_TIER = BASIC

BASIC_SLUG = BASIC.slug
PROFESSIONAL_SLUG = PROFESSIONAL.slug
GROWTH_SLUG = GROWTH.slug

PLAN_SLUGS: tuple[str, ...] = tuple(t.slug for t in PLAN_TIERS)


# ── Resolving a tier ───────────────────────────────────────────────────────


def get_tier(slug: str | None) -> PlanTier | None:
    """Tier for a slug, honouring historic aliases. None if unknown."""
    key = (slug or "").strip().lower()
    for tier in PLAN_TIERS:
        if key == tier.slug or key in tier.aliases:
            return tier
    return None


def tier_for_enum(enum_value: str | None) -> PlanTier:
    """Tier for an Organization.subscription_plan value, falling back to Basic."""
    key = (enum_value or "").strip().upper()
    for tier in PLAN_TIERS:
        if key == tier.enum_value:
            return tier
    return DEFAULT_TIER


def plan_name(slug: str | None) -> str:
    """Display name for a slug — what users should see. Falls back to the slug."""
    tier = get_tier(slug)
    return tier.name if tier else (slug or "")


def slug_to_enum(slug: str | None) -> str:
    """Slug → the value stored in Organization.subscription_plan."""
    tier = get_tier(slug)
    return (tier or DEFAULT_TIER).enum_value


def enum_to_slug(enum_value: str | None) -> str:
    """Organization.subscription_plan value → plan slug."""
    return tier_for_enum(enum_value).slug


def enum_choices() -> list[tuple[str, str]]:
    """(value, label) pairs for Organization.SubscriptionPlan and any form
    that renders a plan dropdown. Labels follow `name` above."""
    return [(t.enum_value, t.name) for t in PLAN_TIERS]


def template_context() -> dict:
    """Plan identity for templates. Exposed as `plan_tiers` / `plan_names`
    by `apps.dashboard.context_processors.plan_identity`."""
    return {
        "plan_tiers": list(PLAN_TIERS),
        "plan_names": {t.slug: t.name for t in PLAN_TIERS},
        "plan_by_slug": {t.slug: t for t in PLAN_TIERS},
        "featured_plan": FEATURED_TIER,
    }


# ── BASIC ──────────────────────────────────────────────────────────────────
# Core HR for small teams. Attendance, leave, simple payroll, basic reports.

BASIC_FEATURES: list[str] = [
    # Core
    "dashboard",
    "employees",
    "departments",
    "attendance",
    "leave",
    "holidays",
    "announcements",
    "employee_self_service",
    # Payroll
    "payroll_basic",
    # Reports
    "reports_basic",
    # Admin
    "org_settings",
]


# ── PROFESSIONAL ───────────────────────────────────────────────────────────
# Everything in Basic, plus advanced payroll, org structure, performance,
# documents, shifts, expenses and basic analytics.

PROFESSIONAL_FEATURES: list[str] = [
    # Core
    "dashboard",
    "employees",
    "departments",
    "attendance",
    "leave",
    "holidays",
    "announcements",
    "employee_self_service",
    # Payroll
    "payroll_basic",
    "payroll_advanced",
    # Attendance
    "shifts",
    # Structure
    "org_hierarchy",
    "grades",
    "designations",
    # Talent
    "performance",
    # Finance
    "expenses",
    # Reports & analytics
    "reports_basic",
    "reports_advanced",
    "analytics_basic",
    # Admin
    "org_settings",
]


# ── GROWTH ─────────────────────────────────────────────────────────────────
# The full platform. Everything in Professional, plus the complete payroll
# suite, operations, automation, integrations, compliance and advanced modules.

GROWTH_FEATURES: list[str] = [
    # Core
    "dashboard",
    "employees",
    "departments",
    "attendance",
    "leave",
    "holidays",
    "announcements",
    "employee_self_service",
    # Payroll
    "payroll_basic",
    "payroll_advanced",
    "payroll_growth",
    # Attendance
    "shifts",
    # Structure
    "org_hierarchy",
    "grades",
    "designations",
    # Talent
    "performance",
    # Finance
    "expenses",
    # Reports & analytics
    "reports_basic",
    "reports_advanced",
    "custom_reports",
    "analytics_basic",
    "analytics_advanced",
    "ai_analytics",
    "executive_dashboard",
    # Operations
    "assets",
    "projects",
    "tasks",
    "timesheets",
    # Automation
    "workflows",
    # Integrations
    "api_access",
    "mobile_app",
    "biometric",
    "integrations",
    # Support
    "helpdesk",
    # Security
    "audit_logs",
    "security_center",
    "sso",
    "custom_roles",
    # Advanced
    "multi_branch",
    "multi_company",
    "lms",
    "compliance",
    "workforce_planning",
    "succession",
    "white_label",
    # Admin
    "org_settings",
]


# ── Lookup used by the rest of the app ─────────────────────────────────────

PLAN_FEATURES: dict[str, list[str]] = {
    BASIC_SLUG: BASIC_FEATURES,
    PROFESSIONAL_SLUG: PROFESSIONAL_FEATURES,
    GROWTH_SLUG: GROWTH_FEATURES,
}


def features_for(plan_slug: str) -> list[str]:
    """Feature keys included in `plan_slug`. Unknown plans get nothing."""
    return list(PLAN_FEATURES.get((plan_slug or "").lower(), []))


def plan_has_feature(plan_slug: str, feature_key: str) -> bool:
    """Whether `plan_slug` includes `feature_key`."""
    return feature_key in PLAN_FEATURES.get((plan_slug or "").lower(), [])


def plans_with_feature(feature_key: str) -> list[str]:
    """Every plan slug that includes `feature_key`, cheapest plan first."""
    return [slug for slug in PLAN_SLUGS if feature_key in PLAN_FEATURES[slug]]


def feature_min_plan() -> dict[str, str]:
    """Feature key → the cheapest plan slug that includes it."""
    min_plan: dict[str, str] = {}
    for slug in PLAN_SLUGS:
        for key in PLAN_FEATURES[slug]:
            min_plan.setdefault(key, slug)
    return min_plan


def check() -> dict[str, list[str]]:
    """Validate the three lists. Empty lists everywhere means all good.

    Reports unknown keys (typos — these fail silently at runtime), duplicates
    within one plan, and catalog features that no plan offers.
    """
    from .plan_catalog import FEATURE_CATALOG

    problems: dict[str, list[str]] = {
        "unknown_keys": [],
        "duplicates": [],
        "orphaned_features": [],
    }
    for slug in PLAN_SLUGS:
        keys = PLAN_FEATURES[slug]
        problems["unknown_keys"] += [
            f"{slug}: {k}" for k in keys if k not in FEATURE_CATALOG
        ]
        seen: set[str] = set()
        problems["duplicates"] += [
            f"{slug}: {k}" for k in keys if k in seen or seen.add(k)  # type: ignore[func-returns-value]
        ]
    problems["orphaned_features"] = [
        k for k in FEATURE_CATALOG if not plans_with_feature(k)
    ]
    return problems
