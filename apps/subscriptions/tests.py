"""Tests for the role-based feature-permission system.

Covers: FeatureRolePermission role mapping (permissive default, explicit
deny), cache invalidation of role entitlements, menu audiences for
plan-driven sidebars, and the Super Admin role-permissions UI/API.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    FeatureDefinition,
    FeatureRolePermission,
    MenuAudience,
    NavigationItem,
    Plan,
    PlanFeature,
)
from apps.subscriptions.services.entitlements import (
    _audience_for_role,
    get_plan_menu_items,
)
from apps.subscriptions.services.feature_control import (
    get_enabled_feature_keys,
    has_feature,
    invalidate_org_entitlements,
)


def _make_org(name: str, code: str, **flags) -> Organization:
    defaults = dict(
        name=name,
        organization_code=code,
        code=code.lower(),
        schema_name=code.lower(),
    )
    defaults.update(flags)
    return Organization.objects.create(**defaults)


def _make_user(org, email, role, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="Passw0rd!",
        username=email.replace("@", "-").replace(".", "-"),
        first_name=email.split("@")[0].title(),
        role=role,
        organization=org,
        **extra,
    )


class FeatureControlTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.org = _make_org("Acme Subs", "SUBA")
        # org.subscription_plan defaults to BASIC → resolves to this plan.
        self.plan = Plan.objects.create(slug="basic", name="Basic", is_active=True)
        self.attendance = FeatureDefinition.objects.create(key="attendance", name="Attendance")
        self.payroll = FeatureDefinition.objects.create(key="payroll_basic", name="Payroll")
        PlanFeature.objects.create(plan=self.plan, feature=self.attendance, is_enabled=True)
        PlanFeature.objects.create(plan=self.plan, feature=self.payroll, is_enabled=True)


class RoleFilterTests(FeatureControlTestBase):
    def test_role_choices(self):
        self.assertEqual(
            set(FeatureRolePermission.Role.values), {"ADMIN", "HR", "EMPLOYEE"}
        )
        perm = FeatureRolePermission(
            feature=self.payroll, role=FeatureRolePermission.Role.EMPLOYEE, is_allowed=False
        )
        perm.full_clean()  # choice is valid

    def test_permissive_default_without_rows(self):
        keys = get_enabled_feature_keys(self.org, User.Role.EMPLOYEE)
        self.assertEqual(keys, {"attendance", "payroll_basic"})

    def test_deny_row_filters_feature(self):
        FeatureRolePermission.objects.create(
            feature=self.payroll, role=FeatureRolePermission.Role.EMPLOYEE, is_allowed=False
        )
        keys = get_enabled_feature_keys(self.org, User.Role.EMPLOYEE)
        self.assertEqual(keys, {"attendance"})
        self.assertFalse(has_feature(self.org, "payroll_basic", User.Role.EMPLOYEE))
        self.assertTrue(has_feature(self.org, "attendance", User.Role.EMPLOYEE))

    def test_deny_does_not_affect_other_roles(self):
        FeatureRolePermission.objects.create(
            feature=self.payroll, role=FeatureRolePermission.Role.EMPLOYEE, is_allowed=False
        )
        self.assertIn("payroll_basic", get_enabled_feature_keys(self.org, User.Role.ADMIN))
        self.assertIn("payroll_basic", get_enabled_feature_keys(self.org, User.Role.HR))

    def test_invalidate_clears_entitlement_cache(self):
        # Prime the employee entitlement cache, then deny and invalidate.
        self.assertIn("payroll_basic", get_enabled_feature_keys(self.org, User.Role.EMPLOYEE))
        FeatureRolePermission.objects.create(
            feature=self.payroll, role=FeatureRolePermission.Role.EMPLOYEE, is_allowed=False
        )
        invalidate_org_entitlements(self.org)
        self.assertNotIn("payroll_basic", get_enabled_feature_keys(self.org, User.Role.EMPLOYEE))


class MenuAudienceTests(FeatureControlTestBase):
    def test_audience_for_role(self):
        self.assertEqual(_audience_for_role(User.Role.HR), MenuAudience.HR)
        self.assertEqual(_audience_for_role(User.Role.EMPLOYEE), MenuAudience.EMPLOYEE)
        self.assertEqual(_audience_for_role(User.Role.ADMIN), MenuAudience.ADMIN)

    def test_employee_menu_does_not_leak_admin_items(self):
        NavigationItem.objects.create(
            plan=self.plan, label="Admin Home", url_name="dashboard:home", audience=MenuAudience.ADMIN
        )
        items = get_plan_menu_items(self.org, User.Role.EMPLOYEE)
        self.assertEqual(items, [])
        admin_items = get_plan_menu_items(self.org, User.Role.ADMIN)
        self.assertEqual([i.label for i in admin_items], ["Admin Home"])

    def test_employee_audience_menu_items_returned(self):
        NavigationItem.objects.create(
            plan=self.plan, label="My Dashboard", url_name="dashboard:employee", audience=MenuAudience.EMPLOYEE
        )
        NavigationItem.objects.create(
            plan=self.plan,
            label="My Payslips",
            url_name="payroll:management",
            feature_key="payroll_basic",
            audience=MenuAudience.EMPLOYEE,
        )
        FeatureRolePermission.objects.create(
            feature=self.payroll, role=FeatureRolePermission.Role.EMPLOYEE, is_allowed=False
        )
        items = get_plan_menu_items(self.org, User.Role.EMPLOYEE)
        self.assertEqual([i.label for i in items], ["My Dashboard"])


class RolePermissionAdminUITests(FeatureControlTestBase):
    def setUp(self):
        super().setUp()
        self.super_admin = _make_user(None, "root@platform.com", User.Role.SUPER_ADMIN)
        self.client.force_login(self.super_admin)

    def test_roles_page_renders_role_columns(self):
        resp = self.client.get(reverse("dashboard:feature_control:roles"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-role="EMPLOYEE"')
        self.assertNotContains(resp, 'data-role="MANAGER"')

    def test_role_toggle_api_persists_permission(self):
        resp = self.client.post(
            reverse("dashboard:feature_control:api"),
            {
                "action": "role_toggle",
                "feature_id": str(self.payroll.pk),
                "role": "EMPLOYEE",
                "allowed": "false",
            },
        )
        self.assertEqual(resp.status_code, 200)
        perm = FeatureRolePermission.objects.get(feature=self.payroll, role="EMPLOYEE")
        self.assertFalse(perm.is_allowed)
        self.assertNotIn("payroll_basic", get_enabled_feature_keys(self.org, User.Role.EMPLOYEE))

    def test_navigation_page_lists_audiences(self):
        resp = self.client.get(reverse("dashboard:feature_control:navigation"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-audience="EMPLOYEE"')
        self.assertNotContains(resp, 'data-audience="MANAGER"')
