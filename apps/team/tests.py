"""Tests for team-lead capability (users with direct reports).

Covers: direct-report scoping, leave + regularization approval, tenant
isolation, payroll/admin restrictions, notifications, and audit logging —
across both the server-rendered pages and the DRF /api/team/ endpoints.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.hierarchy import direct_reports_for, is_manager
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
from apps.dashboard.models import DashboardNotification
from apps.leaves.models import LeaveRequest, LeaveType
from apps.leaves.services import manager_pending_leave_requests, submit_leave_request
from apps.organizations.models import Organization
from apps.payroll.services import payroll_team_for
from apps.team.models import TeamActionAuditLog


def _make_org(name: str, code: str, **flags) -> Organization:
    defaults = dict(
        name=name,
        organization_code=code,
        code=code.lower(),
        schema_name=code.lower(),
        # Single-level approval (Employee → Manager) unless overridden.
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


class TeamRoleTestBase(TestCase):
    def setUp(self):
        # ── Org A ──
        self.org = _make_org("Acme", "ORGA")
        self.admin = _make_user(self.org, "admin@a.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@a.com", User.Role.HR)
        self.manager = _make_user(self.org, "manager@a.com", User.Role.EMPLOYEE, assigned_hr=self.hr)
        self.emp1 = _make_user(
            self.org, "emp1@a.com", User.Role.EMPLOYEE,
            reporting_manager=self.manager, assigned_hr=self.hr,
            date_of_birth=date(1990, 1, 1),
        )
        self.emp2 = _make_user(
            self.org, "emp2@a.com", User.Role.EMPLOYEE,
            reporting_manager=self.manager, assigned_hr=self.hr,
        )
        # A second team lead + an employee who reports to them (not to self.manager).
        self.manager2 = _make_user(
            self.org, "manager2@a.com", User.Role.EMPLOYEE, assigned_hr=self.hr,
        )
        self.outsider = _make_user(
            self.org, "out@a.com", User.Role.EMPLOYEE,
            reporting_manager=self.manager2, assigned_hr=self.hr,
        )

        self.leave_type = LeaveType.objects.create(
            organization=self.org, name="Loss of Pay", code="lop",
            is_paid=False, annual_quota=None,
        )

        # ── Org B (separate tenant) ──
        self.org_b = _make_org("Beta", "ORGB")
        self.manager_b = _make_user(self.org_b, "manager@b.com", User.Role.EMPLOYEE)
        self.emp_b = _make_user(
            self.org_b, "emp@b.com", User.Role.EMPLOYEE, reporting_manager=self.manager_b,
        )
        self.leave_type_b = LeaveType.objects.create(
            organization=self.org_b, name="Loss of Pay", code="lop", is_paid=False,
        )

    def _next_monday(self):
        d = date.today() + timedelta(days=1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        return d

    def _submit_leave(self, employee, leave_type):
        start = self._next_monday()
        req, msg = submit_leave_request(
            user=employee,
            leave_type=leave_type,
            start_date=start,
            end_date=start,
            half_day=LeaveRequest.HalfDay.NONE,
            reason="Personal",
        )
        assert req is not None, msg
        return req


class HierarchyTests(TeamRoleTestBase):
    def test_user_with_reports_is_manager(self):
        self.assertTrue(is_manager(self.manager))

    def test_user_without_reports_is_not_manager(self):
        self.assertFalse(is_manager(self.emp1))

    def test_direct_reports_only(self):
        reports = set(direct_reports_for(self.manager).values_list("pk", flat=True))
        self.assertEqual(reports, {self.emp1.pk, self.emp2.pk})
        self.assertNotIn(self.outsider.pk, reports)

    def test_payroll_team_is_self_only(self):
        team = set(payroll_team_for(self.manager).values_list("pk", flat=True))
        self.assertEqual(team, {self.manager.pk})


class LeaveApprovalTests(TeamRoleTestBase):
    def test_manager_sees_only_their_reports_pending_leave(self):
        r1 = self._submit_leave(self.emp1, self.leave_type)
        # Outsider's leave should not appear for this manager.
        self._submit_leave(self.outsider, self.leave_type)
        pending = list(manager_pending_leave_requests(self.manager).values_list("pk", flat=True))
        self.assertEqual(pending, [r1.pk])

    def test_manager_approves_report_leave(self):
        req = self._submit_leave(self.emp1, self.leave_type)
        self.client.force_login(self.manager)
        url = reverse("dashboard:team_leave_decision", args=[req.pk, "approve"])
        resp = self.client.post(url, {"comment": "ok"})
        self.assertEqual(resp.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        # Employee notified of the decision.
        self.assertTrue(
            DashboardNotification.objects.filter(
                user=self.emp1, source_key=f"leave-decision:{req.pk}"
            ).exists()
        )
        # Audit row written with actor + target.
        self.assertTrue(
            TeamActionAuditLog.objects.filter(
                actor=self.manager, target_user=self.emp1,
                action=TeamActionAuditLog.Action.LEAVE_APPROVE, object_id=req.pk,
            ).exists()
        )

    def test_manager_cannot_act_on_outside_report_leave(self):
        req = self._submit_leave(self.outsider, self.leave_type)
        self.client.force_login(self.manager)
        url = reverse("dashboard:team_leave_decision", args=[req.pk, "approve"])
        resp = self.client.post(url, {"comment": "x"})
        self.assertEqual(resp.status_code, 404)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)

    def test_two_level_approval_keeps_pending_after_manager(self):
        self.org.leave_approval_require_hr = True
        self.org.save(update_fields=["leave_approval_require_hr"])
        req = self._submit_leave(self.emp1, self.leave_type)
        self.client.force_login(self.manager)
        url = reverse("dashboard:team_leave_decision", args=[req.pk, "approve"])
        self.client.post(url, {"comment": "ok"})
        req.refresh_from_db()
        # Still pending — awaiting HR (two-level: Employee → Manager → HR).
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)


class RegularizationTests(TeamRoleTestBase):
    def _make_reg(self, employee):
        return AttendanceRegularizationRequest.objects.create(
            user=employee, date=date.today() - timedelta(days=2),
            requested_status=AttendanceRecord.Status.PRESENT, reason="Missed punch",
        )

    def test_manager_approves_report_regularization(self):
        reg = self._make_reg(self.emp1)
        self.client.force_login(self.manager)
        url = reverse("dashboard:team_regularization_decision", args=[reg.pk, "approve"])
        resp = self.client.post(url, {"comment": "ok"})
        self.assertEqual(resp.status_code, 302)
        reg.refresh_from_db()
        self.assertEqual(reg.status, AttendanceRegularizationRequest.Status.APPROVED)
        self.assertTrue(
            TeamActionAuditLog.objects.filter(
                actor=self.manager, target_user=self.emp1,
                action=TeamActionAuditLog.Action.REGULARIZATION_APPROVE,
            ).exists()
        )

    def test_manager_cannot_act_on_outside_regularization(self):
        reg = self._make_reg(self.outsider)
        self.client.force_login(self.manager)
        url = reverse("dashboard:team_regularization_decision", args=[reg.pk, "reject"])
        resp = self.client.post(url, {"comment": "x"})
        self.assertEqual(resp.status_code, 404)


class AccessControlTests(TeamRoleTestBase):
    def test_team_lead_can_load_team_pages(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("dashboard:team_attendance"))
        self.assertEqual(resp.status_code, 200)

    def test_manager_blocked_from_staff_management(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("dashboard:staff_list"))
        # AdminOrHRRequiredMixin redirects non-admin/HR away.
        self.assertEqual(resp.status_code, 302)

    def test_employee_without_reports_blocked_from_team_pages(self):
        self.client.force_login(self.emp1)
        resp = self.client.get(reverse("dashboard:team_members"))
        self.assertEqual(resp.status_code, 302)

    def test_team_directory_lists_only_reports(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("dashboard:team_members"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.emp1.display_name)
        self.assertNotContains(resp, self.outsider.display_name)


class TeamAPITests(TeamRoleTestBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_members_endpoint_scoped(self):
        self.api.force_authenticate(self.manager)
        resp = self.api.get("/api/team/members/")
        self.assertEqual(resp.status_code, 200)
        ids = {row["id"] for row in resp.json()}
        self.assertEqual(ids, {str(self.emp1.pk), str(self.emp2.pk)})

    def test_non_manager_denied(self):
        self.api.force_authenticate(self.emp1)
        resp = self.api.get("/api/team/members/")
        self.assertEqual(resp.status_code, 403)

    def test_members_expose_actual_and_display_role(self):
        # Configure the org's HR label and make a direct report an HR user.
        self.org.hr_role_display_name = "Team Leader"
        self.org.save(update_fields=["hr_role_display_name"])
        self.emp1.role = User.Role.HR
        self.emp1.save(update_fields=["role"])

        self.api.force_authenticate(self.manager)
        resp = self.api.get("/api/team/members/")
        self.assertEqual(resp.status_code, 200)
        rows = {row["id"]: row for row in resp.json()}
        hr_row = rows[str(self.emp1.pk)]
        self.assertEqual(hr_row["actual_role"], "HR")
        self.assertEqual(hr_row["display_role"], "Team Leader")
        # A plain employee's display_role is unchanged.
        self.assertEqual(rows[str(self.emp2.pk)]["display_role"], "Employee")

    def test_api_leave_approve_and_audit(self):
        req = self._submit_leave(self.emp1, self.leave_type)
        self.api.force_authenticate(self.manager)
        resp = self.api.post(f"/api/team/leave-requests/{req.pk}/approve/", {"comment": "ok"})
        self.assertEqual(resp.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        self.assertTrue(
            TeamActionAuditLog.objects.filter(
                actor=self.manager, object_id=req.pk,
                action=TeamActionAuditLog.Action.LEAVE_APPROVE,
            ).exists()
        )

    def test_api_cross_tenant_isolation(self):
        # Manager B tries to approve Org A's leave → not in their scoped queryset.
        req = self._submit_leave(self.emp1, self.leave_type)
        self.api.force_authenticate(self.manager_b)
        resp = self.api.post(f"/api/team/leave-requests/{req.pk}/approve/", {"comment": "x"})
        self.assertEqual(resp.status_code, 404)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)
