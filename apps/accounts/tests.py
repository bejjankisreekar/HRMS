"""Tests for org-aware role display labels (configurable HR label)."""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.role_labels import (
    hr_label_for_org,
    role_display_for,
    role_display_label,
)
from apps.organizations.models import Organization


def _make_org(name, code, **flags) -> Organization:
    return Organization.objects.create(
        name=name, organization_code=code, code=code.lower(), schema_name=code.lower(), **flags
    )


def _make_user(org, email, role, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="Passw0rd!",
        username=email.replace("@", "-").replace(".", "-"),
        role=role,
        organization=org,
        **extra,
    )


class RoleLabelTests(TestCase):
    def setUp(self):
        self.default_org = _make_org("DefaultCo", "DEF")
        self.labeled_org = _make_org("LabeledCo", "LBL", hr_role_display_name="Manager")

    def test_role_display_for_hr_without_org_is_hr(self):
        self.assertEqual(role_display_for("HR"), "HR")

    def test_role_display_for_hr_uses_org_label(self):
        self.assertEqual(role_display_for("HR", self.labeled_org), "Manager")

    def test_role_display_for_hr_default_org_falls_back_to_hr(self):
        self.assertEqual(role_display_for("HR", self.default_org), "HR")

    def test_non_hr_role_ignores_org_label(self):
        self.assertEqual(role_display_for("EMPLOYEE", self.labeled_org), "Employee")
        self.assertEqual(role_display_for(User.Role.ADMIN, self.labeled_org), "Organization Admin")

    def test_blank_label_falls_back_to_hr(self):
        org = _make_org("BlankCo", "BLK", hr_role_display_name="")
        self.assertEqual(role_display_for("HR", org), "HR")
        self.assertEqual(org.hr_label, "HR")

    def test_hr_label_for_org_none(self):
        self.assertEqual(hr_label_for_org(None), "HR")

    def test_role_display_label_reflects_org(self):
        hr_default = _make_user(self.default_org, "hr@def.com", User.Role.HR)
        hr_labeled = _make_user(self.labeled_org, "hr@lbl.com", User.Role.HR)
        emp = _make_user(self.labeled_org, "emp@lbl.com", User.Role.EMPLOYEE)
        self.assertEqual(role_display_label(hr_default), "HR")
        self.assertEqual(role_display_label(hr_labeled), "Manager")
        # Employees are unaffected by the HR label.
        self.assertEqual(role_display_label(emp), "Employee")

    def test_label_is_tenant_isolated(self):
        # Changing one org's label must not affect another.
        self.labeled_org.hr_role_display_name = "Team Leader"
        self.labeled_org.save(update_fields=["hr_role_display_name"])
        self.assertEqual(role_display_for("HR", self.labeled_org), "Team Leader")
        self.assertEqual(role_display_for("HR", self.default_org), "HR")
