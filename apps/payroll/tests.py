"""Payroll tests: non-negative pay under both LOP policies, run history, policy save."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.organizations.models import Organization

from .analytics import recent_runs
from .models import EmployeeLoan, EmployeeSalary, PayrollRun, Payslip, PayslipLine
from .services import get_or_create_payroll_run, process_payroll_run

YEAR, MONTH = 2026, 3  # March 2026 — has working days under the default Sat/Sun policy


def _grant_payroll_features(org):
    """Test DB has no seeded Plan/FeatureDefinition catalog by default — create the
    minimal rows so PlanFeatureRequiredMixin-gated payroll pages don't 403 in tests."""
    from apps.subscriptions.models import FeatureDefinition, Plan, PlanFeature, Subscription
    from apps.subscriptions.services.feature_control import invalidate_org_entitlements

    plan, _ = Plan.objects.get_or_create(slug="growth", defaults={"name": "Growth"})
    for key in ("payroll_basic", "payroll_advanced", "payroll_growth"):
        feat, _ = FeatureDefinition.objects.get_or_create(
            key=key, defaults={"name": key, "is_active": True, "is_globally_enabled": True}
        )
        PlanFeature.objects.get_or_create(plan=plan, feature=feat, defaults={"is_enabled": True})
    Subscription.objects.get_or_create(organization=org, defaults={"plan": plan})
    invalidate_org_entitlements(org)


def _make_org(name, code, **flags) -> Organization:
    return Organization.objects.create(
        name=name, organization_code=code, code=code.lower(), schema_name=code.lower(), **flags
    )


def _make_user(org, email, role=User.Role.EMPLOYEE, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="Passw0rd!",
        username=email.replace("@", "-").replace(".", "-"),
        role=role,
        organization=org,
        **extra,
    )


def _salary(user, ctc="50000") -> EmployeeSalary:
    return EmployeeSalary.objects.create(
        user=user, monthly_ctc=Decimal(ctc), effective_from=date(2026, 1, 1), is_active=True
    )


class PayrollCalcTests(TestCase):
    def setUp(self):
        self.org = _make_org("PayCo", "PAY")
        self.admin = _make_user(self.org, "admin@pay.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "emp@pay.com", employee_id="E1")
        _salary(self.emp)

    def _run(self):
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)
        run.refresh_from_db()
        return run

    def _set_policy(self, policy):
        self.org.payroll_lop_policy = policy
        self.org.save(update_fields=["payroll_lop_policy"])

    def test_assume_present_pays_full_when_no_attendance(self):
        self._set_policy(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        run = self._run()
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        self.assertGreater(slip.net_salary, Decimal("0"))
        self.assertGreaterEqual(run.total_net, Decimal("0"))
        # Full attendance factor → gross equals the full monthly earnings.
        self.assertEqual(slip.leave_deduction, Decimal("0.00"))

    def test_strict_zero_when_no_attendance_but_never_negative(self):
        self._set_policy(Organization.PayrollLopPolicy.STRICT)
        run = self._run()
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        self.assertEqual(slip.net_salary, Decimal("0.00"))
        self.assertGreaterEqual(run.total_net, Decimal("0"))

    def test_assume_present_prorates_only_marked_absences(self):
        # Two explicit absent days → net reduced but still positive.
        for d in (3, 4):  # early-March weekdays
            AttendanceRecord.objects.create(
                user=self.emp, date=date(YEAR, MONTH, d), status=AttendanceRecord.Status.ABSENT
            )
        self._set_policy(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        run = self._run()
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        self.assertGreater(slip.net_salary, Decimal("0"))
        self.assertGreater(slip.leave_deduction, Decimal("0"))  # LOP recorded (informational)

    def test_strict_pays_for_present_days(self):
        for d in (3, 4, 5, 6, 7):
            AttendanceRecord.objects.create(
                user=self.emp, date=date(YEAR, MONTH, d), status=AttendanceRecord.Status.PRESENT
            )
        self._set_policy(Organization.PayrollLopPolicy.STRICT)
        run = self._run()
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        self.assertGreater(slip.net_salary, Decimal("0"))

    def test_loan_emi_counted_once_no_crash(self):
        EmployeeLoan.objects.create(
            user=self.emp, principal=Decimal("24000"), emi_amount=Decimal("2000"),
            balance=Decimal("24000"), status=EmployeeLoan.Status.ACTIVE,
        )
        self._set_policy(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        run = self._run()
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        emi_lines = slip.lines.filter(label="Loan EMI")
        self.assertEqual(emi_lines.count(), 1)
        self.assertEqual(emi_lines.first().amount, Decimal("2000.00"))
        self.assertGreaterEqual(slip.net_salary, Decimal("0"))

    def test_recent_runs_history(self):
        self._set_policy(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        r1 = get_or_create_payroll_run(self.org, 2026, 3)
        process_payroll_run(r1, self.admin)
        r2 = get_or_create_payroll_run(self.org, 2026, 4)
        process_payroll_run(r2, self.admin)
        history = recent_runs(self.org)
        self.assertEqual([(r.year, r.month) for r in history[:2]], [(2026, 4), (2026, 3)])
        r1.refresh_from_db()
        self.assertEqual(history[1].total_net, r1.total_net)


class PayrollPolicyViewTests(TestCase):
    def setUp(self):
        self.org = _make_org("PolCo", "POL")
        self.admin = _make_user(self.org, "admin@pol.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "emp@pol.com")

    def test_dashboard_renders(self):
        # Catches template load/render errors (e.g. tag libraries), which only surface on GET.
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:management"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_saves_policy(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("payroll:management"),
            {"action": "save_payroll_policy", "payroll_lop_policy": "STRICT",
             "year": YEAR, "month": MONTH},
        )
        self.org.refresh_from_db()
        self.assertEqual(self.org.payroll_lop_policy, "STRICT")

    def test_non_admin_cannot_save_policy(self):
        self.client.force_login(self.emp)
        self.client.post(
            reverse("payroll:management"),
            {"action": "save_payroll_policy", "payroll_lop_policy": "STRICT",
             "year": YEAR, "month": MONTH},
        )
        self.org.refresh_from_db()
        self.assertEqual(self.org.payroll_lop_policy, "ASSUME_PRESENT")


class DeductionsDashboardTests(TestCase):
    """Engine extension + deductions reporting layer + RBAC + tenant isolation."""

    def setUp(self):
        from apps.organizations.models import Department
        from .models import EmployeeDeduction

        self.org = _make_org("DedCo", "DED")
        self.admin = _make_user(self.org, "admin@ded.com", User.Role.ADMIN)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.e1 = _make_user(self.org, "e1@ded.com", employee_id="D1", department=self.dept)
        self.e2 = _make_user(self.org, "e2@ded.com", employee_id="D2", department=self.dept)
        _salary(self.e1)
        _salary(self.e2)
        # An advance recovery for e1 — should appear as a real deduction line.
        EmployeeDeduction.objects.create(
            user=self.e1, deduction_type=EmployeeDeduction.Type.ADVANCE,
            amount=Decimal("2000"), balance=Decimal("0"),
        )
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)
        self.run = run

    def _ps(self, user):
        return Payslip.objects.get(payroll_run=self.run, user=user)

    def test_engine_employer_pf_and_advance(self):
        from .deductions import deduction_breakdown

        slip = self._ps(self.e1)
        b = deduction_breakdown(slip)
        self.assertGreater(b["employee_pf"], Decimal("0"))
        self.assertEqual(slip.employer_pf, b["employee_pf"])  # employer match
        self.assertEqual(b["advance"], Decimal("2000"))       # advance recovered
        self.assertGreaterEqual(slip.net_salary, Decimal("0"))

    def test_breakdown_reconciles(self):
        from .deductions import deduction_breakdown

        b = deduction_breakdown(self._ps(self.e1))
        # net = gross - total_deductions (no reimbursements in test)
        self.assertEqual(b["net"], b["gross"] - b["total_deductions"])

    def test_summary_and_rows(self):
        from .deductions import DeductionFilters, org_report_rows, summary_cards

        f = DeductionFilters(year=YEAR, month=MONTH)
        rows = org_report_rows(self.admin, f)
        self.assertEqual(len(rows), 2)
        s = summary_cards(self.admin, f)
        self.assertEqual(s["employees"], 2)
        self.assertGreater(s["tds"] + s["employee_pf"] + s["pt"], Decimal("0"))

    def test_analytics_periods(self):
        from .deductions import analytics

        self.assertEqual(len(analytics(self.admin, "monthly", YEAR)["labels"]), 12)
        self.assertEqual(len(analytics(self.admin, "quarterly", YEAR)["labels"]), 4)
        self.assertEqual(len(analytics(self.admin, "annual", YEAR)["labels"]), 1)

    def test_rbac_employee_sees_only_own(self):
        from .deductions import DeductionFilters, org_report_rows

        rows = org_report_rows(self.e1, DeductionFilters(year=YEAR, month=MONTH))
        self.assertEqual({r["user_id"] for r in rows}, {str(self.e1.pk)})
        self.client.force_login(self.e1)
        # Own employee detail → 200; another employee → 403.
        own = self.client.get(f"/api/payroll/deductions/employee/{self.e1.pk}/", {"year": YEAR, "month": MONTH})
        self.assertEqual(own.status_code, 200)
        other = self.client.get(f"/api/payroll/deductions/employee/{self.e2.pk}/", {"year": YEAR, "month": MONTH})
        self.assertEqual(other.status_code, 403)

    def test_tenant_isolation(self):
        from .deductions import DeductionFilters, org_report_rows

        org_b = _make_org("OtherCo", "OTH")
        admin_b = _make_user(org_b, "admin@oth.com", User.Role.ADMIN)
        self.assertEqual(org_report_rows(admin_b, DeductionFilters(year=YEAR, month=MONTH)), [])

    def test_export_xlsx(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:deductions_export"), {"year": YEAR, "month": MONTH, "format": "xlsx"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_page_renders_and_audits(self):
        from .models import PayrollAuditLog

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:deductions"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Payroll Deductions")
        self.assertTrue(
            PayrollAuditLog.objects.filter(organization=self.org, action=PayrollAuditLog.Action.VIEWED).exists()
        )
        # Employee self-service also renders.
        self.client.force_login(self.e1)
        self.assertEqual(self.client.get(reverse("payroll:deductions")).status_code, 200)

    def test_button_on_payroll_page(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:management"))
        self.assertContains(resp, "Payroll Deductions")


class ComplianceReportsTests(TestCase):
    """Admin-only statutory compliance reports (PF/ESI/TDS/PT/Form16)."""

    def setUp(self):
        from apps.organizations.models import Department

        self.org = _make_org("CompCo", "CMP")
        self.admin = _make_user(self.org, "admin@cmp.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@cmp.com", User.Role.HR)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.e1 = _make_user(self.org, "e1@cmp.com", User.Role.EMPLOYEE, employee_id="C1",
                             department=self.dept, uan_number="UAN1", pan_number="PAN1")
        _salary(self.e1)
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)

    def _filters(self):
        from .deductions import DeductionFilters
        return DeductionFilters(year=YEAR, month=MONTH)

    # ── RBAC ──
    def test_access_matrix(self):
        from .compliance import can_view_compliance

        url = reverse("payroll:compliance")
        # Admin: always.
        self.client.force_login(self.admin)
        self.assertTrue(can_view_compliance(self.admin))
        self.assertEqual(self.client.get(url).status_code, 200)
        # HR without the grant: blocked.
        self.client.force_login(self.hr)
        self.assertFalse(can_view_compliance(self.hr))
        self.assertEqual(self.client.get(url).status_code, 302)
        # HR with the grant: allowed.
        self.hr.can_access_compliance = True
        self.hr.save(update_fields=["can_access_compliance"])
        self.assertTrue(can_view_compliance(self.hr))
        self.assertEqual(self.client.get(url).status_code, 200)
        # Employee: never (even if the flag were set).
        self.e1.can_access_compliance = True
        self.e1.save(update_fields=["can_access_compliance"])
        self.client.force_login(self.e1)
        self.assertFalse(can_view_compliance(self.e1))
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_grant_toggle_visibility_and_save(self):
        from apps.dashboard.staff_forms import StaffEditForm

        # Field exposed only when an Admin edits an HR account.
        admin_hr = StaffEditForm(instance=self.hr, organization=self.org, editor=self.admin)
        self.assertIn("can_access_compliance", admin_hr.fields)
        admin_emp = StaffEditForm(instance=self.e1, organization=self.org, editor=self.admin)
        self.assertNotIn("can_access_compliance", admin_emp.fields)  # not for employees
        hr_editor = StaffEditForm(instance=self.hr, organization=self.org, editor=self.hr)
        self.assertNotIn("can_access_compliance", hr_editor.fields)  # HR can't grant

    def test_payroll_button_visibility(self):
        url = reverse("payroll:management")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), "Compliance Reports")
        self.client.force_login(self.hr)
        self.assertNotContains(self.client.get(url), "Compliance Reports")  # no grant
        self.hr.can_access_compliance = True
        self.hr.save(update_fields=["can_access_compliance"])
        self.assertContains(self.client.get(url), "Compliance Reports")

    def test_nav_admin_only(self):
        from apps.dashboard.sidebar_menu import build_sidebar_menu

        admin_nav = build_sidebar_menu(self.admin, "", "/payroll/compliance/")
        labels_admin = [i["label"] for i in admin_nav["search_items"]]
        self.assertIn("Compliance Reports", labels_admin)
        hr_nav = build_sidebar_menu(self.hr, "", "/")
        self.assertNotIn("Compliance Reports", [i["label"] for i in hr_nav["search_items"]])

    # ── Report content ──
    def test_pf_report_rows(self):
        from .compliance import compliance_rows

        rows = compliance_rows(self.admin, "pf", self._filters())
        self.assertTrue(rows)
        r = rows[0]
        self.assertEqual(r["uan"], "UAN1")
        self.assertGreater(r["employee_pf"], 0)
        self.assertEqual(r["employer_pf"], r["employee_pf"])  # 12% employer match
        self.assertEqual(r["total_pf"], r["employee_pf"] + r["employer_pf"])

    def test_tds_and_pt_reports(self):
        from .compliance import compliance_rows

        tds = compliance_rows(self.admin, "tds", self._filters())
        self.assertTrue(tds)
        self.assertEqual(tds[0]["pan"], "PAN1")
        self.assertGreater(tds[0]["tds"], 0)
        # PT is a flat 200 deduction in the default structure.
        pt = compliance_rows(self.admin, "pt", self._filters())
        self.assertTrue(pt)
        self.assertGreater(pt[0]["pt"], 0)

    def test_form16_placeholder(self):
        from .compliance import compliance_rows, report_meta

        self.assertEqual(compliance_rows(self.admin, "form16", self._filters()), [])
        self.assertFalse(report_meta("form16")["ready"])

    def test_each_report_renders(self):
        self.client.force_login(self.admin)
        for rep in ("pf", "esi", "tds", "pt", "form16"):
            resp = self.client.get(reverse("payroll:compliance"), {"report": rep, "year": YEAR, "month": MONTH})
            self.assertEqual(resp.status_code, 200)

    def test_export_xlsx_and_audit(self):
        from .models import PayrollAuditLog

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:compliance"),
                               {"report": "pf", "year": YEAR, "month": MONTH, "export": "xlsx"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertTrue(
            PayrollAuditLog.objects.filter(organization=self.org, action=PayrollAuditLog.Action.EXPORTED).exists()
        )

    def test_tenant_isolation(self):
        from .compliance import compliance_rows

        org_b = _make_org("OtherCmp", "OCM")
        admin_b = _make_user(org_b, "admin@ocm.com", User.Role.ADMIN)
        self.assertEqual(compliance_rows(admin_b, "pf", self._filters()), [])


class PayslipLopModelTests(TestCase):
    """Conventional model: Gross = full salary, LOP is a deduction, Net never negative."""

    def setUp(self):
        self.org = _make_org("LopCo", "LOP")
        self.admin = _make_user(self.org, "admin@lop.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "emp@lop.com", employee_id="L1")
        _salary(self.emp)  # CTC 50000 → full earnings sum to 50000

    def _run(self, policy):
        self.org.payroll_lop_policy = policy
        self.org.save(update_fields=["payroll_lop_policy"])
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)
        return run

    def _slip(self, run):
        return Payslip.objects.get(payroll_run=run, user=self.emp)

    def test_heavy_absence_full_gross_lop_net_zero(self):
        # STRICT + no attendance → everything is LOP; net floors at 0, never negative.
        run = self._run(Organization.PayrollLopPolicy.STRICT)
        slip = self._slip(run)
        self.assertEqual(slip.gross_salary, Decimal("50000.00"))      # full salary
        self.assertEqual(slip.net_salary, Decimal("0.00"))            # not negative
        self.assertLessEqual(slip.leave_deduction, slip.gross_salary)  # LOP ≤ gross
        lop_lines = slip.lines.filter(label="Loss of Pay")
        self.assertEqual(lop_lines.count(), 1)
        self.assertEqual(lop_lines.first().amount, slip.leave_deduction)

    def test_partial_absence_lop_less_than_gross(self):
        for d in (3, 4):  # two absent days
            AttendanceRecord.objects.create(
                user=self.emp, date=date(YEAR, MONTH, d), status=AttendanceRecord.Status.ABSENT
            )
        run = self._run(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        slip = self._slip(run)
        self.assertEqual(slip.gross_salary, Decimal("50000.00"))     # full
        self.assertGreater(slip.leave_deduction, Decimal("0"))       # some LOP
        self.assertLess(slip.leave_deduction, slip.gross_salary)     # but < gross
        self.assertGreater(slip.net_salary, Decimal("0"))

    def test_payslip_invariants(self):
        run = self._run(Organization.PayrollLopPolicy.ASSUME_PRESENT)
        slip = self._slip(run)
        # Net ≥ 0, LOP ≤ Gross, and Gross − Total Deductions = Net (no reimbursements here).
        self.assertGreaterEqual(slip.net_salary, Decimal("0"))
        self.assertLessEqual(slip.leave_deduction, slip.gross_salary)
        self.assertEqual(slip.gross_salary - slip.total_deductions, slip.net_salary)

    def test_breakdown_lop_from_line_not_double_counted(self):
        from .deductions import deduction_breakdown

        run = self._run(Organization.PayrollLopPolicy.STRICT)  # full LOP
        slip = self._slip(run)
        b = deduction_breakdown(slip)
        self.assertEqual(b["lop"], slip.leave_deduction)
        self.assertEqual(b["net"], b["gross"] - b["total_deductions"])
        self.assertGreaterEqual(b["net"], Decimal("0"))

    def test_legacy_prorated_payslip_renders_coherently(self):
        # Simulate a pre-migration payslip: prorated gross, LOP only in the field, negative
        # stored net, no Loss-of-Pay line. deduction_breakdown must still show net ≥ 0, LOP ≤ gross.
        from .deductions import deduction_breakdown

        run = get_or_create_payroll_run(self.org, 2026, 7)
        slip = Payslip.objects.create(
            payroll_run=run, user=self.emp,
            gross_salary=Decimal("3818"), total_deductions=Decimal("48677"),
            net_salary=Decimal("-44859"), leave_deduction=Decimal("48387"),
        )
        PayslipLine.objects.create(payslip=slip, label="Provident Fund",
                                   line_type="DEDUCTION", amount=Decimal("77"))
        PayslipLine.objects.create(payslip=slip, label="Professional Tax",
                                   line_type="DEDUCTION", amount=Decimal("200"))
        b = deduction_breakdown(slip)
        self.assertEqual(b["gross"], Decimal("3818") + Decimal("48387"))  # full
        self.assertGreaterEqual(b["net"], Decimal("0"))                   # not negative
        self.assertLessEqual(b["lop"], b["gross"])                        # LOP ≤ gross


class BulkSalaryGridTests(TestCase):
    """Bulk salary-structure grid: shape, save semantics, RBAC, tenant isolation."""

    def setUp(self):
        from apps.organizations.models import Department

        self.org = _make_org("GridCo", "GRD")
        self.admin = _make_user(self.org, "admin@grd.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@grd.com", User.Role.HR)
        self.dept = Department.objects.create(organization=self.org, name="Eng")
        self.e1 = _make_user(self.org, "e1@grd.com", employee_id="G1", department=self.dept)
        self.e2 = _make_user(self.org, "e2@grd.com", employee_id="G2", department=self.dept)
        _salary(self.e1)
        _salary(self.e2)
        from .services import ensure_payroll_setup
        ensure_payroll_setup(self.org)  # canonical component codes for direct seed_employee_components

    def test_grid_shape(self):
        from .salary_grid import bulk_salary_grid

        grid = bulk_salary_grid(self.admin)
        # Admin's payroll team also includes HR users, so both employees are a subset of the grid.
        uids = {r["uid"] for r in grid["rows"]}
        self.assertIn(str(self.e1.pk), uids)
        self.assertIn(str(self.e2.pk), uids)
        codes = {c["code"] for c in grid["columns"]}
        self.assertIn("basic", codes)   # an earning
        self.assertIn("pf", codes)      # a deduction
        self.assertEqual({c["kind"] for c in grid["columns"]}, {"EARNING", "DEDUCTION"})
        r0 = grid["rows"][0]
        for k in ("ctc", "cells", "gross", "total_deductions", "net"):
            self.assertIn(k, r0)
        self.assertEqual(len(r0["cells"]), len(grid["columns"]))  # rectangular

    def test_save_changes_cell_and_ctc_preserves_untouched(self):
        from decimal import Decimal as D

        from .models import EmployeeSalaryComponent as ESC
        from .salary_grid import save_bulk_salary
        from .services import get_active_salary, seed_employee_components

        sal = get_active_salary(self.e1)
        seed_employee_components(sal)
        uid = str(self.e1.pk)
        basic_mode_before = sal.components.get(code="basic").mode  # PCT_CTC (seeded)

        count = save_bulk_salary(self.admin, {f"ctc_{uid}": "60000", f"c_{uid}_pf": "999"})
        self.assertEqual(count, 1)

        sal.refresh_from_db()
        self.assertEqual(sal.monthly_ctc, D("60000"))
        pf = sal.components.get(code="pf")
        self.assertEqual(pf.mode, ESC.Mode.FIXED)     # edited cell → fixed override
        self.assertEqual(pf.value, D("999.00"))
        basic = sal.components.get(code="basic")
        self.assertEqual(basic.mode, basic_mode_before)  # untouched cell unchanged

    def test_rbac(self):
        url = reverse("payroll:salary_structures_bulk")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.e1)
        self.assertEqual(self.client.get(url).status_code, 302)  # employees blocked

    def test_tenant_isolation(self):
        from .salary_grid import bulk_salary_grid

        org_b = _make_org("OtherGrid", "OGD")
        admin_b = _make_user(org_b, "admin@ogd.com", User.Role.ADMIN)
        self.assertEqual(bulk_salary_grid(admin_b)["rows"], [])


class PayrollReportsTests(TestCase):
    """Payroll Reports hub: summary, salary register, payslip distribution, RBAC, exports."""

    def setUp(self):
        from apps.organizations.models import Department

        self.org = _make_org("RepHub", "RPH")
        self.admin = _make_user(self.org, "admin@rph.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@rph.com", User.Role.HR)
        self.dept = Department.objects.create(organization=self.org, name="Eng")
        self.e1 = _make_user(self.org, "e1@rph.com", employee_id="R1", department=self.dept)
        _salary(self.e1)
        self.run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(self.run, self.admin)

    def _filters(self):
        from .deductions import DeductionFilters
        return DeductionFilters(year=YEAR, month=MONTH)

    def test_summary_rows(self):
        from .reports import summary_rows

        rows = summary_rows(self.admin, self._filters())
        self.assertTrue(rows)
        r = next(x for x in rows if x["employee_id"] == "R1")
        self.assertGreaterEqual(r["net"], 0)
        self.assertEqual(round(r["gross"] - r["deductions"], 2), round(r["net"], 2))

    def test_register_equals_deductions_rows(self):
        from .deductions import org_report_rows
        from .reports import salary_register_rows

        self.assertEqual(
            [r["payslip_id"] for r in salary_register_rows(self.admin, self._filters())],
            [r["payslip_id"] for r in org_report_rows(self.admin, self._filters())],
        )

    def test_distribution_and_download_tracking(self):
        from .reports import payslip_distribution
        from .services import generate_payslip_numbers

        generate_payslip_numbers(self.run)  # marks generated_at
        d0 = payslip_distribution(self.admin, self._filters())["totals"]
        self.assertGreater(d0["generated"], 0)
        self.assertEqual(d0["downloaded"], 0)
        self.assertEqual(d0["pending"], d0["generated"])

        # Opening the payslip preview counts as a download.
        slip = Payslip.objects.get(payroll_run=self.run, user=self.e1)
        self.client.force_login(self.admin)
        self.client.get(reverse("payroll:management"), {"payslip": str(slip.pk)})
        slip.refresh_from_db()
        self.assertEqual(slip.download_count, 1)
        d1 = payslip_distribution(self.admin, self._filters())["totals"]
        self.assertEqual(d1["downloaded"], 1)

    def test_rbac_hub_and_detail(self):
        for url in (reverse("payroll:reports"), reverse("payroll:report", args=["summary"]),
                    reverse("payroll:report", args=["distribution"])):
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.client.force_login(self.hr)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.client.force_login(self.e1)
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_compliance_cards_hidden_without_permission(self):
        from .reports import REPORTS

        self.client.force_login(self.hr)  # HR without can_access_compliance
        resp = self.client.get(reverse("payroll:reports"))
        self.assertContains(resp, "Payroll Summary Report")
        self.assertNotContains(resp, "TDS Report")
        # Admin sees compliance cards.
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("payroll:reports")), "TDS Report")

    def test_export_xlsx(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:report", args=["summary"]),
                               {"year": YEAR, "month": MONTH, "export": "xlsx"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_tenant_isolation(self):
        from .reports import summary_rows

        org_b = _make_org("OtherHub", "OHB")
        admin_b = _make_user(org_b, "admin@ohb.com", User.Role.ADMIN)
        self.assertEqual(summary_rows(admin_b, self._filters()), [])

    def test_button_on_payroll_page(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("payroll:management")), "Payroll Reports")


class PayrollNewPagesTests(TestCase):
    """Phase 1 sidebar restructure: smoke-test every new dedicated page renders,
    RBAC blocks the right roles, and the core workflow actions still work."""

    def setUp(self):
        self.org = _make_org("NewPageCo", "NPC")
        _grant_payroll_features(self.org)
        self.admin = _make_user(self.org, "admin@npc.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@npc.com", User.Role.HR)
        self.emp = _make_user(self.org, "emp@npc.com", User.Role.EMPLOYEE, employee_id="E1")
        _salary(self.emp)

    def test_admin_hr_pages_render(self):
        self.client.force_login(self.admin)
        for name in (
            "payroll:dashboard", "payroll:cycles", "payroll:runs", "payroll:payslips",
            "payroll:components", "payroll:tax_management", "payroll:loans",
            "payroll:reimbursements", "payroll:revisions", "payroll:settings",
            "payroll:form16", "payroll:bonuses", "payroll:overtime",
            "payroll:arrears", "payroll:final_settlement",
        ):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, f"{name} did not render for admin")

    def test_employee_my_salary_redirects_to_dashboard(self):
        # My Salary was merged into the Payroll Dashboard; the old URL redirects.
        self.client.force_login(self.emp)
        resp = self.client.get(reverse("payroll:my_salary"))
        self.assertRedirects(resp, reverse("payroll:dashboard"))

    def test_employee_dashboard_embeds_salary_breakdown(self):
        self.client.force_login(self.emp)
        resp = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Salary revision history")

    def test_employee_blocked_from_admin_only_pages(self):
        self.client.force_login(self.emp)
        for name in ("payroll:cycles", "payroll:components", "payroll:tax_management", "payroll:revisions"):
            resp = self.client.get(reverse(name))
            self.assertNotEqual(resp.status_code, 200, f"{name} should not be reachable by an employee")

    def test_admin_dashboard_has_no_salary_breakdown(self):
        # The embedded salary structure is employee-only; finance roles keep charts.
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("payroll:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Salary revision history")

    def test_run_workflow_via_runs_page(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:runs"), {"action": "run_payroll", "year": YEAR, "month": MONTH})
        run = PayrollRun.objects.get(organization=self.org, year=YEAR, month=MONTH)
        self.assertEqual(run.status, PayrollRun.Status.REVIEW)
        self.client.post(reverse("payroll:runs"), {"action": "approve_payroll", "year": YEAR, "month": MONTH})
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.client.post(reverse("payroll:runs"), {"action": "mark_paid", "year": YEAR, "month": MONTH})
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.client.post(reverse("payroll:runs"), {"action": "lock_payroll", "year": YEAR, "month": MONTH})
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.LOCKED)

    def test_bank_file_export(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:runs"), {"action": "run_payroll", "year": YEAR, "month": MONTH})
        resp = self.client.get(reverse("payroll:runs"), {"export": "bank", "year": YEAR, "month": MONTH})
        self.assertEqual(resp.status_code, 200)
        # The bank file is a formatted .xlsx workbook (see _export_bank_file), not CSV.
        self.assertIn("spreadsheetml.sheet", resp["Content-Type"])

    def test_payslip_pdf_download(self):
        self.client.force_login(self.admin)
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        resp = self.client.get(reverse("payroll:payslips"), {"payslip": str(slip.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_employee_cannot_download_others_payslip(self):
        run = get_or_create_payroll_run(self.org, YEAR, MONTH)
        process_payroll_run(run, self.admin)
        slip = Payslip.objects.get(payroll_run=run, user=self.emp)
        other = _make_user(self.org, "other@npc.com", User.Role.EMPLOYEE, employee_id="E2")
        _salary(other)
        self.client.force_login(other)
        resp = self.client.get(reverse("payroll:payslips"), {"payslip": str(slip.pk)})
        self.assertNotEqual(resp.status_code, 200)

    def test_salary_component_create(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:components"), {
            "name": "Night Allowance", "code": "night-allow", "component_type": "EARNING",
            "category": "OTHER", "calc_type": "FIXED", "default_amount": "500", "default_percent": "0",
            "is_taxable": "on", "is_active": "on",
        })
        from .models import SalaryComponent

        self.assertTrue(SalaryComponent.objects.filter(organization=self.org, code="night-allow").exists())

    def test_loan_apply_and_approve(self):
        self.client.force_login(self.emp)
        self.client.post(reverse("payroll:loans"), {
            "action": "apply", "principal": "10000", "interest_rate": "0",
            "tenure_months": "6", "emi_amount": "1700", "start_date": "2026-01-01",
        })
        loan = EmployeeLoan.objects.get(user=self.emp)
        self.assertEqual(loan.status, EmployeeLoan.Status.PENDING)

        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:loans"), {"action": "approve", "loan_id": str(loan.pk)})
        loan.refresh_from_db()
        self.assertEqual(loan.status, EmployeeLoan.Status.ACTIVE)
        self.assertEqual(loan.approved_by, self.admin)

    def test_reimbursement_claim_and_approve(self):
        self.client.force_login(self.emp)
        self.client.post(reverse("payroll:reimbursements"), {
            "action": "add", "category": "TRAVEL", "amount": "500", "description": "Taxi fare",
        })
        from .models import Reimbursement

        claim = Reimbursement.objects.get(user=self.emp)
        self.assertEqual(claim.status, Reimbursement.Status.PENDING)

        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:reimbursements"), {"action": "approve", "reimbursement_id": str(claim.pk)})
        claim.refresh_from_db()
        self.assertEqual(claim.status, Reimbursement.Status.APPROVED)

    def test_cycle_config_save(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:cycles"), {
            "frequency": "MONTHLY", "payroll_day": "20", "salary_day": "1",
            "attendance_cutoff_day": "18", "leave_cutoff_day": "18", "approval_deadline_day": "19",
        })
        from .models import PayrollCycleConfig

        cfg = PayrollCycleConfig.objects.get(organization=self.org)
        self.assertEqual(cfg.payroll_day, 20)

    def test_settings_save(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("payroll:settings"), {
            "currency": "INR", "decimal_precision": "2", "rounding_rule": "NEAREST",
            "payroll_lop_policy": "STRICT",
        })
        from .models import PayrollSettings

        self.assertTrue(PayrollSettings.objects.filter(organization=self.org).exists())
        self.org.refresh_from_db()
        self.assertEqual(self.org.payroll_lop_policy, "STRICT")

    def test_grade_fk_on_salary_structure(self):
        """SalaryStructure.grade is now a FK to grades.Grade (was a free-text CharField)."""
        from apps.grades.models import Grade

        from .models import SalaryStructure

        grade = Grade.objects.create(organization=self.org, name="L3")
        structure = SalaryStructure.objects.create(
            organization=self.org, name="L3 Structure", code="l3", grade=grade,
        )
        structure.refresh_from_db()
        self.assertEqual(structure.grade, grade)


# Tax engine, declarations and Form 16 live in their own module for size;
# re-exported here so `manage.py test apps.payroll` picks them up.
from .tax_tests import *  # noqa: F401,F403
