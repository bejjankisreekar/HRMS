"""Tests for the leave management module.

Covers: leave type management (Admin/HR), applicability scoping, attachment
enforcement, balance adjustments + rollover, approval workflow configuration
(single/multi-level + auto-approve fallback), manager team visibility, cancel
notifications, audit logging, and the /api/leaves/ REST layer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.dashboard.models import DashboardNotification
from apps.leaves.models import LeaveApproval, LeaveBalance, LeaveRequest, LeaveType
from apps.leaves.services import (
    cancel_leave,
    create_approval_chain,
    get_balance,
    leave_team_for,
    submit_leave_request,
)
from apps.organizations.models import Department, Organization
from apps.team.models import TeamActionAuditLog


def _next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _make_org(name: str, code: str, **flags) -> Organization:
    defaults = dict(
        name=name,
        organization_code=code,
        code=code.lower(),
        schema_name=code.lower(),
        leave_approval_require_manager=True,
        leave_approval_require_hr=False,
        leave_approval_require_admin=False,
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


def _make_type(org, name="Casual", code="casual", **extra) -> LeaveType:
    defaults = dict(annual_quota=Decimal("12"), is_paid=True)
    defaults.update(extra)
    return LeaveType.objects.create(organization=org, name=name, code=code, **defaults)


class LeaveTestBase(TestCase):
    def setUp(self):
        self.org = _make_org("Acme", "LVA")
        self.admin = _make_user(self.org, "admin@lv.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@lv.com", User.Role.HR)
        self.manager = _make_user(self.org, "mgr@lv.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        self.emp = _make_user(
            self.org, "emp@lv.com", User.Role.EMPLOYEE,
            reporting_manager=self.manager, assigned_hr=self.hr,
        )
        self.lt = _make_type(self.org)
        self.start = _next_monday()

    def _submit(self, user=None, leave_type=None, days=1, **kwargs):
        user = user or self.emp
        leave_type = leave_type or self.lt
        req, msg = submit_leave_request(
            user=user,
            leave_type=leave_type,
            start_date=self.start,
            end_date=self.start + timedelta(days=days - 1),
            half_day=LeaveRequest.HalfDay.NONE,
            reason="Test leave",
            **kwargs,
        )
        return req, msg


# ── Leave type management ─────────────────────────────────────────────────────


class LeaveTypeManagementTests(LeaveTestBase):
    def test_hr_can_create_leave_type_via_view(self):
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("leaves:management"),
            {
                "action": "add_leave_type",
                "name": "Comp Off",
                "annual_quota": "5",
                "is_paid": "on",
                "is_active": "on",
                "gender_eligibility": "ALL",
                "applicable_to": "ALL",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            LeaveType.objects.filter(organization=self.org, name="Comp Off").exists()
        )

    def test_employee_cannot_create_leave_type(self):
        self.client.force_login(self.emp)
        self.client.post(
            reverse("leaves:management"),
            {"action": "add_leave_type", "name": "Hacked", "applicable_to": "ALL",
             "gender_eligibility": "ALL"},
        )
        self.assertFalse(LeaveType.objects.filter(name="Hacked").exists())

    def test_hr_can_edit_and_toggle_leave_type(self):
        self.client.force_login(self.hr)
        self.client.post(
            reverse("leaves:management"),
            {
                "action": "edit_leave_type",
                "leave_type_id": str(self.lt.pk),
                "name": "Casual Renamed",
                "code": self.lt.code,
                "annual_quota": "10",
                "is_paid": "on",
                "is_active": "on",
                "gender_eligibility": "ALL",
                "applicable_to": "ALL",
            },
        )
        self.lt.refresh_from_db()
        self.assertEqual(self.lt.name, "Casual Renamed")
        self.assertEqual(self.lt.annual_quota, Decimal("10"))

        self.client.post(
            reverse("leaves:management"),
            {"action": "toggle_leave_type", "leave_type_id": str(self.lt.pk)},
        )
        self.lt.refresh_from_db()
        self.assertFalse(self.lt.is_active)

    def test_department_scoped_type_not_applicable_outside_department(self):
        dept = Department.objects.create(organization=self.org, name="Engineering")
        scoped = _make_type(
            self.org, name="Eng Only", code="eng-only",
            applicable_to=LeaveType.ApplicableTo.DEPARTMENT,
        )
        scoped.applicable_departments.add(dept)

        self.assertFalse(scoped.is_applicable_to(self.emp))
        req, msg = self._submit(leave_type=scoped)
        self.assertIsNone(req)
        self.assertIn("not available", msg)

        self.emp.department = dept
        self.emp.save(update_fields=["department"])
        self.assertTrue(scoped.is_applicable_to(self.emp))

    def test_requires_attachment_enforced(self):
        self.lt.requires_attachment = True
        self.lt.save(update_fields=["requires_attachment"])
        req, msg = self._submit()
        self.assertIsNone(req)
        self.assertIn("supporting document", msg)


# ── Balances ─────────────────────────────────────────────────────────────────


class BalanceTests(LeaveTestBase):
    def test_remaining_includes_adjustment(self):
        bal = get_balance(self.emp, self.lt)
        base_remaining = bal.remaining
        bal.adjusted += Decimal("2")
        bal.save(update_fields=["adjusted"])
        bal.refresh_from_db()
        self.assertEqual(bal.remaining, base_remaining + 2)

    def test_hr_adjusts_balance_via_view_with_audit(self):
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("leaves:management"),
            {
                "action": "adjust_balance",
                "user_id": str(self.emp.pk),
                "leave_type_id": str(self.lt.pk),
                "adjustment": "1.5",
                "reason": "Comp-off credit",
            },
        )
        self.assertEqual(resp.status_code, 302)
        bal = get_balance(self.emp, self.lt)
        self.assertEqual(bal.adjusted, Decimal("1.5"))
        log = TeamActionAuditLog.objects.filter(
            action=TeamActionAuditLog.Action.BALANCE_ADJUST, target_user=self.emp
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.hr)

    def test_manager_cannot_adjust_balance_via_view(self):
        self.client.force_login(self.manager)
        self.client.post(
            reverse("leaves:management"),
            {
                "action": "adjust_balance",
                "user_id": str(self.emp.pk),
                "leave_type_id": str(self.lt.pk),
                "adjustment": "5",
            },
        )
        bal = get_balance(self.emp, self.lt)
        self.assertEqual(bal.adjusted, Decimal("0"))

    def test_rollover_carries_forward_capped(self):
        year = date.today().year
        self.lt.carry_forward_max = Decimal("5")
        self.lt.save(update_fields=["carry_forward_max"])
        LeaveBalance.objects.create(
            user=self.emp, leave_type=self.lt, year=year - 1,
            allocated=Decimal("12"), used=Decimal("2"),
        )
        call_command("rollover_leave_balances", "--year", str(year), "--org", "LVA")
        bal = LeaveBalance.objects.get(user=self.emp, leave_type=self.lt, year=year)
        # remaining was 10 but cap is 5
        self.assertEqual(bal.carried_forward, Decimal("5"))
        self.assertEqual(bal.allocated, Decimal("12"))


# ── Approval workflow ────────────────────────────────────────────────────────


class ApprovalWorkflowTests(LeaveTestBase):
    def test_single_level_manager_chain(self):
        req, _ = self._submit()
        steps = list(req.approvals.order_by("step"))
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].approver, self.manager)
        self.assertIn("Manager", req.current_stage_label)

    def test_two_level_manager_then_hr(self):
        self.org.leave_approval_require_hr = True
        self.org.save(update_fields=["leave_approval_require_hr"])
        req, _ = self._submit()
        approvers = [s.approver for s in req.approvals.order_by("step")]
        self.assertEqual(approvers, [self.manager, self.hr])

    def test_auto_approve_on_when_no_manager(self):
        nomgr = _make_user(self.org, "solo@lv.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        self.org.leave_auto_approve_without_manager = True
        self.org.save(update_fields=["leave_auto_approve_without_manager"])
        req, msg = self._submit(user=nomgr)
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        self.assertIn("auto-approved", msg.lower())

    def test_auto_approve_off_routes_to_hr(self):
        nomgr = _make_user(self.org, "solo2@lv.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        self.org.leave_auto_approve_without_manager = False
        self.org.save(update_fields=["leave_auto_approve_without_manager"])
        req, _ = self._submit(user=nomgr)
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)
        step = req.approvals.get()
        self.assertEqual(step.approver, self.hr)


# ── Manager visibility ───────────────────────────────────────────────────────


class ManagerVisibilityTests(LeaveTestBase):
    def test_leave_team_for_manager_is_reports_plus_self(self):
        other_mgr = _make_user(self.org, "mgr2@lv.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        outsider = _make_user(
            self.org, "out@lv.com", User.Role.EMPLOYEE,
            reporting_manager=other_mgr, assigned_hr=self.hr,
        )
        team_pks = set(leave_team_for(self.manager).values_list("pk", flat=True))
        self.assertEqual(team_pks, {self.manager.pk, self.emp.pk})
        self.assertNotIn(outsider.pk, team_pks)

    def test_manager_can_apply_for_leave(self):
        req, msg = self._submit(user=self.manager)
        self.assertIsNotNone(req, msg)


# ── Cancellation ─────────────────────────────────────────────────────────────


class CancelTests(LeaveTestBase):
    def test_cancel_notifies_pending_approver(self):
        req, _ = self._submit()
        msg = cancel_leave(req, self.emp)
        self.assertIn("cancelled", msg.lower())
        notif = DashboardNotification.objects.filter(
            user=self.manager, source_key__startswith=f"leave-cancelled:{req.pk}:"
        ).first()
        self.assertIsNotNone(notif)


# ── Page rendering smoke tests ───────────────────────────────────────────────


class LeavePageRenderTests(LeaveTestBase):
    def test_management_page_renders_for_each_role(self):
        for user in (self.admin, self.hr, self.manager, self.emp):
            self.client.force_login(user)
            resp = self.client.get(reverse("leaves:management"))
            self.assertEqual(resp.status_code, 200, f"failed for {user.role}")

    def test_management_page_renders_edit_type_form(self):
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("leaves:management") + f"?edit_type={self.lt.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "edit_leave_type")

    def test_apply_page_team_lead_has_same_access_as_employee(self):
        """Team leads pass the role gate of the apply page.

        The bare test org has no subscription plan rows, so the *module* gate
        may redirect — but it must treat a team lead exactly like any other
        employee. (An admin, by contrast, is rejected by the role gate itself.)
        """
        self.client.force_login(self.emp)
        emp_status = self.client.get(reverse("leaves:apply")).status_code
        self.client.force_login(self.manager)
        mgr_status = self.client.get(reverse("leaves:apply")).status_code
        self.assertEqual(mgr_status, emp_status)

    def test_exports_download(self):
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("leaves:management") + "?export=xlsx")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        resp = self.client.get(reverse("leaves:management") + "?export=balances_csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])

    def test_settings_page_shows_workflow_panel_for_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(resp.status_code, 200)


# ── REST API ─────────────────────────────────────────────────────────────────


class LeaveAPITests(LeaveTestBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_employee_balances_and_apply_and_cancel(self):
        self.api.force_authenticate(self.emp)
        resp = self.api.get("/api/leaves/balances/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(b["leave_type_code"] == "casual" for b in resp.json()))

        resp = self.api.post(
            "/api/leaves/apply/",
            {
                "leave_type": str(self.lt.pk),
                "start_date": self.start.isoformat(),
                "end_date": self.start.isoformat(),
                "reason": "API leave",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        req_id = resp.json()["id"]
        self.assertTrue(
            TeamActionAuditLog.objects.filter(
                action=TeamActionAuditLog.Action.LEAVE_APPLY, object_id=req_id
            ).exists()
        )

        resp = self.api.get("/api/leaves/my-requests/")
        self.assertEqual(len(resp.json()), 1)

        resp = self.api.post(f"/api/leaves/{req_id}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], LeaveRequest.Status.CANCELLED)

    def test_manager_team_scope_and_approve(self):
        req, _ = self._submit()
        other_mgr = _make_user(self.org, "mgr3@lv.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        outsider = _make_user(
            self.org, "out2@lv.com", User.Role.EMPLOYEE,
            reporting_manager=other_mgr, assigned_hr=self.hr,
        )
        outsider_req, _ = self._submit(user=outsider)

        self.api.force_authenticate(self.manager)
        resp = self.api.get("/api/leaves/team/")
        ids = {r["id"] for r in resp.json()}
        self.assertIn(str(req.pk), ids)
        self.assertNotIn(str(outsider_req.pk), ids)

        # Cannot act on another team's request.
        resp = self.api.post(f"/api/leaves/{outsider_req.pk}/approve/", {})
        self.assertEqual(resp.status_code, 403)

        # Approves own report's request.
        resp = self.api.post(f"/api/leaves/{req.pk}/approve/", {"comment": "ok"})
        self.assertEqual(resp.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)

    def test_employee_cannot_use_team_or_adjust(self):
        self.api.force_authenticate(self.emp)
        self.assertEqual(self.api.get("/api/leaves/team/").status_code, 403)
        resp = self.api.post(
            "/api/leaves/balances/adjust/",
            {"user_id": str(self.emp.pk), "leave_type": str(self.lt.pk), "adjustment": "9"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_hr_adjusts_balance_via_api(self):
        self.api.force_authenticate(self.hr)
        resp = self.api.post(
            "/api/leaves/balances/adjust/",
            {
                "user_id": str(self.emp.pk),
                "leave_type": str(self.lt.pk),
                "adjustment": "-1",
                "reason": "Correction",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["adjusted"], "-1.0")

    def test_leave_type_api_admin_and_hr_only(self):
        self.api.force_authenticate(self.manager)
        self.assertEqual(self.api.get("/api/leave-types/").status_code, 403)

        self.api.force_authenticate(self.hr)
        resp = self.api.post(
            "/api/leave-types/",
            {"name": "API Type", "code": "api-type", "annual_quota": "3"},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        type_id = resp.json()["id"]

        resp = self.api.put(f"/api/leave-types/{type_id}/", {"annual_quota": "6"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(LeaveType.objects.get(pk=type_id).annual_quota, Decimal("6"))

    def test_workflow_settings_admin_only(self):
        self.api.force_authenticate(self.hr)
        self.assertEqual(self.api.get("/api/settings/leave-workflow/").status_code, 403)

        self.api.force_authenticate(self.admin)
        resp = self.api.get("/api/settings/leave-workflow/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["approval_type"], "SINGLE_LEVEL")

        resp = self.api.put(
            "/api/settings/leave-workflow/",
            {"leave_approval_require_hr": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["approval_type"], "MULTI_LEVEL")
        self.org.refresh_from_db()
        self.assertTrue(self.org.leave_approval_require_hr)

    def test_workflow_settings_rejects_no_approvers(self):
        self.api.force_authenticate(self.admin)
        resp = self.api.put(
            "/api/settings/leave-workflow/",
            {
                "leave_approval_require_manager": False,
                "leave_approval_require_hr": False,
                "leave_approval_require_admin": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_tenant_isolation_on_api(self):
        org_b = _make_org("Beta", "LVB")
        hr_b = _make_user(org_b, "hr@lvb.com", User.Role.HR)
        req, _ = self._submit()

        self.api.force_authenticate(hr_b)
        resp = self.api.get("/api/leaves/team/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(str(req.pk), {r["id"] for r in resp.json()})
        # Cross-tenant approve attempt → 404 (scoped lookup).
        resp = self.api.post(f"/api/leaves/{req.pk}/approve/", {})
        self.assertEqual(resp.status_code, 404)
