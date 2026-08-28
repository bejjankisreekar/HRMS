"""Tests for the bulk staff CSV import (Admin/HR)."""

from __future__ import annotations

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffAuditLog, User
from apps.dashboard.staff_import import (
    MODE_ABORT,
    MODE_SKIP,
    STAFF_IMPORT_COLUMNS,
    build_template_csv,
    import_rows,
    parse_csv,
)
from django.utils import timezone

import json

from apps.attendance.models import AttendanceReportAudit
from apps.dashboard import hr_analytics as HA
from apps.grades.models import Designation, GradeStatus
from apps.lifecycle.models import OffboardingWorkflow
from apps.organizations.models import Department, Organization


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


def _row(**overrides) -> dict:
    base = {
        "employee_id": "EMP100",
        "first_name": "Test",
        "last_name": "User",
        "email": "test.user@imp.com",
        "phone_number": "9999999999",
        "role": "EMPLOYEE",
        "department": "Engineering",
        "designation": "Software Engineer",
        "reporting_manager_email": "",
        "date_of_joining": "2026-06-01",
        "employment_type": "FULL_TIME",
        "password": "Password@123",
        "is_active": "TRUE",
    }
    base.update(overrides)
    return base


def _csv_bytes(rows: list[dict]) -> bytes:
    import csv as _csv

    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=STAFF_IMPORT_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in STAFF_IMPORT_COLUMNS})
    return buf.getvalue().encode("utf-8")


class StaffImportTestBase(TestCase):
    def setUp(self):
        self.org = _make_org("ImportCo", "IMP")
        self.admin = _make_user(self.org, "admin@imp.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@imp.com", User.Role.HR)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.desig = Designation.objects.create(
            organization=self.org, name="Software Engineer", status=GradeStatus.ACTIVE
        )


class ImportServiceTests(StaffImportTestBase):
    def test_template_has_all_columns(self):
        template = build_template_csv()
        header = template.splitlines()[0]
        self.assertEqual(header.split(","), STAFF_IMPORT_COLUMNS)

    def test_valid_rows_import_all_roles_and_login_works(self):
        rows = [
            _row(employee_id="EMP001", email="h2@imp.com", role="HR",
                 designation="HR Manager"),
            _row(employee_id="EMP002", email="m2@imp.com", role="EMPLOYEE",
                 designation="Team Lead"),
            _row(employee_id="EMP003", email="e2@imp.com", role="EMPLOYEE",
                 reporting_manager_email="m2@imp.com"),
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_ABORT, filename="ok.csv")
        self.assertFalse(summary.aborted)
        self.assertEqual(summary.imported, 3)

        mgr = User.objects.get(email="m2@imp.com")
        emp = User.objects.get(email="e2@imp.com")
        self.assertEqual(mgr.role, User.Role.EMPLOYEE)
        # Same-file manager reference resolved.
        self.assertEqual(emp.reporting_manager, mgr)
        # Catalog designation matched for the employee row.
        self.assertEqual(emp.org_designation, self.desig)
        # Free-text fallback for unmatched designation.
        self.assertEqual(mgr.org_designation, None)
        self.assertEqual(mgr.designation, "Team Lead")
        # Hashed password → login works immediately.
        self.assertTrue(self.client.login(username="e2@imp.com", password="Password@123"))
        # Audit row written.
        log = StaffAuditLog.objects.filter(
            organization=self.org, action=StaffAuditLog.Action.BULK
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details["imported"], 3)

    def test_abort_mode_imports_nothing_on_any_error(self):
        rows = [
            _row(employee_id="EMP010", email="good@imp.com"),
            _row(employee_id="EMP011", email="bad@imp.com", department="Nonexistent"),
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_ABORT)
        self.assertTrue(summary.aborted)
        self.assertEqual(summary.imported, 0)
        self.assertFalse(User.objects.filter(email="good@imp.com").exists())

    def test_skip_mode_imports_valid_rows_only(self):
        rows = [
            _row(employee_id="EMP010", email="good@imp.com"),
            _row(employee_id="EMP011", email="bad@imp.com", department="Nonexistent"),
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_SKIP)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(summary.failed, 1)
        self.assertTrue(User.objects.filter(email="good@imp.com").exists())
        self.assertFalse(User.objects.filter(email="bad@imp.com").exists())

    def test_validation_error_catalogue(self):
        rows = [
            _row(employee_id="", email=""),  # missing required
            _row(employee_id="EMP020", email="x@imp.com", role="CEO"),  # bad role
            _row(employee_id="EMP021", email="hr@imp.com"),  # duplicate email (existing)
            _row(employee_id="EMP022", email="y@imp.com", date_of_joining="01-06-2026"),
            _row(employee_id="EMP023", email="z@imp.com", password="weak"),
            _row(employee_id="EMP024", email="w@imp.com", employment_type="GIG"),
            _row(employee_id="EMP025", email="v@imp.com",
                 reporting_manager_email="ghost@imp.com"),
            _row(employee_id="EMP026", email="u@imp.com", is_active="MAYBE"),
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_SKIP)
        errors = {r.line: " ".join(r.errors) for r in summary.rows}
        self.assertIn("Missing required field", errors[1])
        self.assertIn("Invalid role", errors[2])
        self.assertIn("already registered", errors[3])
        self.assertIn("YYYY-MM-DD", errors[4])
        self.assertIn("Password", errors[5])
        self.assertIn("employment_type", errors[6])
        self.assertIn("not found in your organization", errors[7])
        self.assertIn("is_active", errors[8])

    def test_duplicate_employee_id_within_org_and_file(self):
        _make_user(self.org, "exists@imp.com", User.Role.EMPLOYEE, employee_id="EMP030")
        rows = [
            _row(employee_id="EMP030", email="a1@imp.com"),  # exists in org
            _row(employee_id="EMP031", email="a2@imp.com"),
            _row(employee_id="EMP031", email="a3@imp.com"),  # dup within file
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_SKIP)
        self.assertEqual(summary.imported, 1)
        joined = " ".join(e for r in summary.rows for e in r.errors)
        self.assertIn("already exists in your organization", joined)
        self.assertIn("within the file", joined)

    def test_employee_id_unique_per_org_not_globally(self):
        other = _make_org("OtherCo", "OTH")
        _make_user(other, "emp@oth.com", User.Role.EMPLOYEE, employee_id="EMP040")
        rows = [_row(employee_id="EMP040", email="fresh@imp.com")]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_ABORT)
        self.assertEqual(summary.imported, 1)

    def test_cross_org_manager_rejected(self):
        other = _make_org("OtherCo2", "OT2")
        _make_user(other, "mgr@ot2.com", User.Role.EMPLOYEE)
        rows = [_row(email="emp9@imp.com", reporting_manager_email="mgr@ot2.com")]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_ABORT)
        self.assertTrue(summary.aborted)

    def test_hr_import_defaults_assigned_hr_to_importer(self):
        rows = [_row(email="byhr@imp.com")]
        summary = import_rows(self.org, self.hr, rows, mode=MODE_ABORT)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(User.objects.get(email="byhr@imp.com").assigned_hr, self.hr)

    def test_error_report_csv_contains_row_and_message(self):
        rows = [_row(email="bad2@imp.com", department="Ghost Dept")]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_SKIP)
        report = summary.error_report_csv()
        self.assertIn("bad2@imp.com", report)
        self.assertIn("does not exist", report)

    def test_parse_csv_rejects_missing_columns(self):
        upload = io.BytesIO(b"email,name\nx@y.com,X\n")
        rows, errors = parse_csv(upload)
        self.assertEqual(rows, [])
        self.assertIn("Missing required column", errors[0])


class ImportViewTests(StaffImportTestBase):
    def _upload(self, rows, mode=MODE_ABORT):
        f = SimpleUploadedFile("import.csv", _csv_bytes(rows), content_type="text/csv")
        return self.client.post(
            reverse("dashboard:staff_import"), {"csv_file": f, "mode": mode}
        )

    def test_admin_and_hr_can_open_page_others_cannot(self):
        url = reverse("dashboard:staff_import")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 200)

        emp = _make_user(self.org, "e@imp.com", User.Role.EMPLOYEE)
        for blocked in (emp,):
            self.client.force_login(blocked)
            self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_template_download(self):
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("dashboard:staff_import_template"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("employee_id", resp.content.decode())

    def test_full_import_flow_with_reports(self):
        self.client.force_login(self.admin)
        resp = self._upload(
            [
                _row(employee_id="EMP050", email="ok@imp.com"),
                _row(employee_id="EMP051", email="fail@imp.com", department="Ghost"),
            ],
            mode=MODE_SKIP,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Import summary")
        self.assertTrue(User.objects.filter(email="ok@imp.com").exists())

        # Reports downloadable from session.
        err = self.client.get(reverse("dashboard:staff_import_report") + "?kind=error")
        self.assertIn("fail@imp.com", err.content.decode())
        ok = self.client.get(reverse("dashboard:staff_import_report") + "?kind=success")
        self.assertIn("ok@imp.com", ok.content.decode())

    def test_abort_mode_via_view_blocks_all(self):
        self.client.force_login(self.admin)
        self._upload(
            [
                _row(employee_id="EMP060", email="g1@imp.com"),
                _row(employee_id="EMP061", email="g2@imp.com", role="BAD"),
            ],
            mode=MODE_ABORT,
        )
        self.assertFalse(User.objects.filter(email="g1@imp.com").exists())


class HrRoleLabelTests(StaffImportTestBase):
    """Configurable per-org HR display label across settings, CSV, and forms."""

    def setUp(self):
        super().setUp()
        self.org.hr_role_display_name = "Manager"
        self.org.save(update_fields=["hr_role_display_name"])

    # ── Settings editor ──
    def test_admin_can_save_hr_label(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("dashboard:settings"), {"hr_role_display_name": "Team Leader"}
        )
        self.assertEqual(resp.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.hr_role_display_name, "Team Leader")

    def test_hr_cannot_save_label(self):
        self.client.force_login(self.hr)
        self.client.post(reverse("dashboard:settings"), {"hr_role_display_name": "Boss"})
        self.org.refresh_from_db()
        self.assertEqual(self.org.hr_role_display_name, "Manager")

    # ── CSV import role resolution ──
    def test_csv_accepts_hr_employee_manager_and_org_label(self):
        rows = [
            _row(employee_id="C1", email="c1@imp.com", role="HR", designation="X"),
            _row(employee_id="C2", email="c2@imp.com", role="EMPLOYEE"),
            _row(employee_id="C3", email="c3@imp.com", role="MANAGER", designation="X"),
            _row(employee_id="C4", email="c4@imp.com", role="Manager", designation="X"),
        ]
        summary = import_rows(self.org, self.admin, rows, mode=MODE_ABORT)
        self.assertFalse(summary.aborted)
        self.assertEqual(User.objects.get(email="c1@imp.com").role, User.Role.HR)
        self.assertEqual(User.objects.get(email="c2@imp.com").role, User.Role.EMPLOYEE)
        # Legacy MANAGER and the org label both map to HR.
        self.assertEqual(User.objects.get(email="c3@imp.com").role, User.Role.HR)
        self.assertEqual(User.objects.get(email="c4@imp.com").role, User.Role.HR)

    def test_csv_invalid_role_lists_org_label(self):
        from apps.dashboard.staff_import import validate_rows

        results = validate_rows(self.org, [_row(role="Director")])
        self.assertTrue(results[0].errors)
        self.assertIn("Manager", results[0].errors[0])

    def test_template_shows_org_label_for_hr_row(self):
        from apps.dashboard.staff_import import build_template_csv

        csv_text = build_template_csv(self.org)
        self.assertIn("Manager", csv_text)
        self.assertNotIn(",HR,", csv_text)

    # ── Dropdowns / export ──
    def test_filter_role_choices_use_label(self):
        from apps.dashboard.staff_filters import staff_filter_options

        opts = staff_filter_options(self.org, is_hr_view=False)
        self.assertIn((User.Role.HR, "Manager"), opts["role_choices"])

    def test_staff_create_form_role_label(self):
        from apps.dashboard.forms import StaffCreateForm

        form = StaffCreateForm(organization=self.org, created_by=self.admin)
        self.assertIn((User.Role.HR, "Manager"), list(form.fields["role"].choices))

    def test_export_uses_label_for_hr(self):
        import csv as _csv

        from apps.dashboard.staff_services import export_staff_csv

        export = export_staff_csv(User.objects.filter(pk=self.hr.pk), self.org)
        reader = _csv.DictReader(io.StringIO(export))
        rows = list(reader)
        self.assertEqual(rows[0]["Role"], "Manager")

    # ── Render smoke ──
    def test_staff_detail_renders_label_not_hr_staff(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("dashboard:staff_detail", kwargs={"pk": self.hr.pk}))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Manager", body)
        self.assertNotIn("HR Staff", body)


class AttendanceReportsTests(TestCase):
    """Period KPIs, AJAX trend endpoint, employee-status filter, xlsx export."""

    def setUp(self):
        from datetime import date

        from apps.attendance.models import AttendanceRecord

        self.org = _make_org("RepCo", "REP")
        self.admin = _make_user(self.org, "admin@rep.com", User.Role.ADMIN)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.e1 = _make_user(self.org, "e1@rep.com", User.Role.EMPLOYEE, department=self.dept)
        self.e2 = _make_user(self.org, "e2@rep.com", User.Role.EMPLOYEE, department=self.dept)
        self.inactive = _make_user(
            self.org, "old@rep.com", User.Role.EMPLOYEE, department=self.dept, is_active=False
        )
        S = AttendanceRecord.Status
        AttendanceRecord.objects.create(user=self.e1, date=date(2026, 3, 3), status=S.PRESENT)
        AttendanceRecord.objects.create(user=self.e1, date=date(2026, 3, 4), status=S.ABSENT)
        AttendanceRecord.objects.create(user=self.e2, date=date(2026, 3, 3), status=S.PRESENT)
        AttendanceRecord.objects.create(user=self.e2, date=date(2026, 3, 5), status=S.LEAVE)

    def _filters(self, **params):
        from django.test import RequestFactory

        from apps.dashboard.attendance_analytics import AnalyticsFilters

        params.setdefault("from", "2026-03-01")
        params.setdefault("to", "2026-03-31")
        req = RequestFactory().get("/attendance/reports/", params)
        return AnalyticsFilters.from_request(req)

    def test_period_kpis(self):
        from apps.dashboard.attendance_analytics import build_period_kpis

        k = build_period_kpis(self.admin, self._filters())
        self.assertEqual(k["total_present_days"], 2)
        self.assertEqual(k["total_absences"], 1)
        self.assertEqual(k["total_employees"], 2)  # active only
        self.assertGreaterEqual(k["attendance_rate"], 0)
        self.assertLessEqual(k["attendance_rate"], 100)

    def test_employee_status_filter(self):
        from apps.dashboard.attendance_analytics import build_period_kpis

        self.assertEqual(build_period_kpis(self.admin, self._filters(emp_status="all"))["total_employees"], 3)
        self.assertEqual(build_period_kpis(self.admin, self._filters(emp_status="inactive"))["total_employees"], 1)

    def test_reports_data_endpoint_and_granularity(self):
        self.client.force_login(self.admin)
        url = reverse("attendance:reports_data")
        resp = self.client.get(url, {"from": "2026-03-01", "to": "2026-03-31", "view": "daily"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for key in ("trend", "distribution", "dept_rate", "kpis"):
            self.assertIn(key, data)
        daily_labels = len(data["trend"]["labels"])
        monthly = self.client.get(url, {"from": "2026-03-01", "to": "2026-03-31", "view": "monthly"}).json()
        self.assertLess(len(monthly["trend"]["labels"]), daily_labels)
        # Distribution has the six spec statuses.
        self.assertEqual(len(data["distribution"]["values"]), 6)

    def test_non_admin_blocked(self):
        self.client.force_login(self.e1)
        resp = self.client.get(reverse("attendance:reports_data"), {"from": "2026-03-01", "to": "2026-03-31"})
        self.assertNotEqual(resp.status_code, 200)

    def test_export_xlsx(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("attendance:reports"),
            {"from": "2026-03-01", "to": "2026-03-31", "export": "xlsx"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_reports_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("attendance:reports"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Attendance Trends")


class EmployeeAttendanceOverviewTests(TestCase):
    """Per-employee attendance % report: calc, summary, RBAC, tenant isolation, exports, audit."""

    def setUp(self):
        from datetime import date
        from apps.attendance.models import AttendanceRecord

        self.org = _make_org("OvCo", "OVC")
        self.admin = _make_user(self.org, "admin@ovc.com", User.Role.ADMIN)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.e1 = _make_user(self.org, "e1@ovc.com", User.Role.EMPLOYEE, employee_id="O1", department=self.dept)
        self.e2 = _make_user(self.org, "e2@ovc.com", User.Role.EMPLOYEE, employee_id="O2", department=self.dept)
        S = AttendanceRecord.Status
        # March 2026 weekdays for e1: mostly present; e2: some leave.
        for d in (2, 3, 4, 5, 6, 9, 10):
            AttendanceRecord.objects.create(user=self.e1, date=date(2026, 3, d), status=S.PRESENT)
        AttendanceRecord.objects.create(user=self.e1, date=date(2026, 3, 11), status=S.ABSENT)
        for d in (2, 3, 4):
            AttendanceRecord.objects.create(user=self.e2, date=date(2026, 3, d), status=S.PRESENT)
        for d in (5, 6, 9):
            AttendanceRecord.objects.create(user=self.e2, date=date(2026, 3, d), status=S.LEAVE)

    def _filters(self, **kw):
        from apps.dashboard.attendance_overview import OverviewFilters
        kw.setdefault("year", 2026)
        kw.setdefault("month", 3)
        return OverviewFilters(**kw)

    def test_overview_counts_and_pct(self):
        from apps.dashboard.attendance_overview import employee_attendance_overview

        data = employee_attendance_overview(self.admin, self._filters(), use_cache=False)
        by_id = {r["user_id"]: r for r in data["rows"]}
        r1 = by_id[str(self.e1.pk)]
        self.assertEqual(r1["present"], 7)
        self.assertEqual(r1["absent"], 1)
        self.assertEqual(r1["leave"], 0)
        self.assertGreater(r1["pct"], 0)
        self.assertLessEqual(r1["pct"], 100)

    def test_include_leave_changes_denominator(self):
        from apps.dashboard.attendance_overview import employee_attendance_overview

        inc = employee_attendance_overview(self.admin, self._filters(include_leave=True), use_cache=False)
        exc = employee_attendance_overview(self.admin, self._filters(include_leave=False), use_cache=False)
        e2_inc = next(r for r in inc["rows"] if r["user_id"] == str(self.e2.pk))
        e2_exc = next(r for r in exc["rows"] if r["user_id"] == str(self.e2.pk))
        # Excluding leave from the denominator yields a higher % for an employee with leave days.
        self.assertGreater(e2_inc["pct"], e2_exc["pct"])

    def test_summary_fields(self):
        from apps.dashboard.attendance_overview import employee_attendance_overview

        s = employee_attendance_overview(self.admin, self._filters(), use_cache=False)["summary"]
        self.assertEqual(s["total"], 2)
        self.assertIn("avg", s)
        self.assertIn("below_75", s)
        self.assertIn("perfect", s)

    def test_single_aggregate_query(self):
        from apps.dashboard.attendance_overview import employee_attendance_overview

        # Query count is constant regardless of employee count (no N+1): team fetch +
        # holidays lookup (count_working_days) + ONE grouped status-count query.
        with self.assertNumQueries(3):
            employee_attendance_overview(self.admin, self._filters(), use_cache=False)

    def test_rbac_employee_denied(self):
        self.client.force_login(self.e1)
        resp = self.client.get(reverse("attendance:employee_chart"))
        self.assertEqual(resp.status_code, 302)  # AdminOrHRRequiredMixin redirects employees

    def test_tenant_isolation(self):
        from apps.dashboard.attendance_overview import employee_attendance_overview

        org_b = _make_org("OtherOv", "OOV")
        admin_b = _make_user(org_b, "admin@oov.com", User.Role.ADMIN)
        data = employee_attendance_overview(admin_b, self._filters(), use_cache=False)
        self.assertEqual(data["rows"], [])

    def test_page_renders_and_audits(self):
        from apps.attendance.models import AttendanceReportAudit

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("attendance:employee_chart"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "empAttChart")
        self.assertTrue(
            AttendanceReportAudit.objects.filter(
                organization=self.org, action=AttendanceReportAudit.Action.VIEWED
            ).exists()
        )

    def test_export_xlsx_and_audit(self):
        from apps.attendance.models import AttendanceReportAudit

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("attendance:employee_chart"), {"year": 2026, "month": 3, "export": "xlsx"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertTrue(
            AttendanceReportAudit.objects.filter(
                organization=self.org, action=AttendanceReportAudit.Action.EXPORTED, export_type="xlsx"
            ).exists()
        )

    def test_reports_page_has_card(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("attendance:reports"))
        self.assertContains(resp, "Employee Attendance Chart")


class EmployeeDirectoryTests(TestCase):
    """Directory API, Excel export, saved filters, bulk actions, render smoke."""

    def setUp(self):
        self.org = _make_org("DirCo", "DIR")
        self.admin = _make_user(self.org, "admin@dir.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@dir.com", User.Role.HR)
        self.dept = Department.objects.create(organization=self.org, name="Engineering")
        self.e1 = _make_user(self.org, "alice@dir.com", User.Role.EMPLOYEE, first_name="Alice",
                             employee_id="DR1", department=self.dept)
        self.e2 = _make_user(self.org, "bob@dir.com", User.Role.EMPLOYEE, first_name="Bob",
                             employee_id="DR2", department=self.dept)

    # ── Directory API ──
    def test_directory_api_rbac_and_shape(self):
        url = reverse("dashboard:staff_api_directory")
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertIn("count", data)
        row = data["results"][0]
        for f in ("id", "name", "email", "role", "role_label", "department", "status", "manageable"):
            self.assertIn(f, row)
        # HR allowed, employee blocked.
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.e1)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_directory_api_search_and_tenant_isolation(self):
        self.client.force_login(self.admin)
        url = reverse("dashboard:staff_api_directory")
        names = {r["name"] for r in self.client.get(url, {"q": "Alice"}).json()["results"]}
        self.assertTrue(any("Alice" in n for n in names))
        self.assertFalse(any("Bob" in n for n in names))
        # Org B admin sees none of org A.
        org_b = _make_org("OtherDir", "ODR")
        admin_b = _make_user(org_b, "admin@odr.com", User.Role.ADMIN)
        self.client.force_login(admin_b)
        self.assertEqual(self.client.get(url).json()["count"], 0)

    # ── Excel export ──
    def test_export_xlsx_and_csv(self):
        self.client.force_login(self.admin)
        xlsx = self.client.get(reverse("dashboard:staff_export"), {"format": "xlsx"})
        self.assertIn("spreadsheetml", xlsx["Content-Type"])
        csv = self.client.get(reverse("dashboard:staff_export"))
        self.assertIn("text/csv", csv["Content-Type"])

    # ── Saved filters ──
    def test_saved_filters_crud_scoped(self):
        import json as _json

        self.client.force_login(self.admin)
        url = reverse("dashboard:staff_saved_filters")
        created = self.client.post(url, _json.dumps({"name": "Active eng", "query": "department=x&status=active"}),
                                   content_type="application/json")
        self.assertEqual(created.status_code, 201)
        fid = created.json()["id"]
        self.assertEqual(len(self.client.get(url).json()["filters"]), 1)
        # Another user (HR) doesn't see admin's saved filter.
        self.client.force_login(self.hr)
        self.assertEqual(len(self.client.get(url).json()["filters"]), 0)
        # Owner can delete.
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboard:staff_saved_filter_delete", args=[fid]))
        self.assertEqual(len(self.client.get(url).json()["filters"]), 0)

    # ── Bulk actions (reuse StaffBulkAPIView) ──
    def test_bulk_actions(self):
        import json as _json

        self.client.force_login(self.admin)
        url = reverse("dashboard:staff_api_bulk")
        # Deactivate e1.
        resp = self.client.post(url, _json.dumps({"action": "deactivate", "userIds": [str(self.e1.pk)]}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.e1.refresh_from_db()
        self.assertFalse(self.e1.is_active)
        # Reactivate + reset password (temp password returned).
        self.client.post(url, _json.dumps({"action": "activate", "userIds": [str(self.e1.pk)]}),
                         content_type="application/json")
        self.e1.refresh_from_db()
        self.assertTrue(self.e1.is_active)
        rp = self.client.post(url, _json.dumps({"action": "reset_password", "userIds": [str(self.e1.pk)]}),
                              content_type="application/json")
        self.assertTrue(rp.json().get("tempPassword"))

    # ── Render smoke ──
    def test_directory_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("dashboard:staff_list"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("data-staff-cards", body)   # card view container
        self.assertIn("data-view-toggle", body)    # table/card toggle
        self.assertIn("data-bulk-bar", body)       # bulk action bar


class HRAnalyticsTests(TestCase):
    """HR Analytics engine, views, permissions and exports."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date, timedelta

        cls.today = timezone.localdate()
        cls.org = _make_org("Analytics Co", "ANL1")
        cls.other_org = _make_org("Rival Co", "ANL2")

        cls.eng = Department.objects.create(organization=cls.org, name="Engineering")
        cls.ops = Department.objects.create(organization=cls.org, name="Operations")

        cls.admin = _make_user(cls.org, "admin@analytics.co", User.Role.ADMIN)
        cls.hr = _make_user(cls.org, "hr@analytics.co", User.Role.HR,
                            department=cls.eng, date_of_joining=cls.today - timedelta(days=900))
        cls.employee = _make_user(cls.org, "emp@analytics.co", User.Role.EMPLOYEE)

        # Three engineers, one of whom has left, plus one operations hire.
        cls.staying = _make_user(
            cls.org, "stay@analytics.co", User.Role.EMPLOYEE,
            department=cls.eng, gender=User.Gender.FEMALE,
            employment_type=User.EmploymentType.FULL_TIME,
            date_of_joining=cls.today - timedelta(days=800),
            date_of_birth=date(1990, 5, 1), reporting_manager=cls.hr,
        )
        cls.recent = _make_user(
            cls.org, "recent@analytics.co", User.Role.EMPLOYEE,
            department=cls.eng, gender=User.Gender.MALE,
            employment_type=User.EmploymentType.FULL_TIME,
            date_of_joining=cls.today - timedelta(days=40),
            reporting_manager=cls.hr,
        )
        cls.leaver = _make_user(
            cls.org, "gone@analytics.co", User.Role.EMPLOYEE,
            department=cls.ops, gender=User.Gender.MALE,
            date_of_joining=cls.today - timedelta(days=200), is_active=False,
        )
        OffboardingWorkflow.objects.create(
            organization=cls.org, user=cls.leaver,
            last_working_day=cls.today - timedelta(days=20),
            resignation_reason=OffboardingWorkflow.ResignationReason.BETTER_OPPORTUNITY,
            status=OffboardingWorkflow.Status.COMPLETED,
        )
        # Someone else's employee must never leak into this org's numbers.
        _make_user(cls.other_org, "outsider@rival.co", User.Role.EMPLOYEE)

    def _filters(self, months_back=11, **kwargs):
        from datetime import timedelta

        start = (self.today - timedelta(days=30 * months_back)).replace(day=1)
        return HA.HRFilters(date_from=start, date_to=self.today, period="last_12m", **kwargs)

    # ── engine ────────────────────────────────────────────────────────────

    def test_workforce_excludes_other_orgs_and_admins(self):
        wf = HA.load_workforce(self.org, self._filters())
        emails = {r.name for r in wf.rows}
        self.assertEqual(len(wf.rows), 5)  # hr + 3 employees + the leaver's peer
        self.assertNotIn("outsider@rival.co", emails)

    def test_headcount_excludes_people_who_have_left(self):
        wf = HA.load_workforce(self.org, self._filters())
        active_ids = {r.id for r in wf.active(self.today)}
        self.assertNotIn(str(self.leaver.pk), active_ids)
        self.assertIn(str(self.staying.pk), active_ids)

    def test_headcount_is_measured_as_of_a_date(self):
        from datetime import timedelta

        wf = HA.load_workforce(self.org, self._filters())
        before_exit = self.today - timedelta(days=30)
        self.assertIn(str(self.leaver.pk), {r.id for r in wf.active(before_exit)})
        self.assertNotIn(str(self.leaver.pk), {r.id for r in wf.active(self.today)})
        # And someone hired after that date is not counted retrospectively.
        long_ago = self.today - timedelta(days=500)
        self.assertNotIn(str(self.recent.pk), {r.id for r in wf.active(long_ago)})

    def test_attrition_rate_and_annualisation(self):
        wf = HA.load_workforce(self.org, self._filters())
        rate = wf.attrition_rate(wf.filters.date_from, wf.filters.date_to)
        annual = wf.attrition_rate(wf.filters.date_from, wf.filters.date_to, annualised=True)
        self.assertGreater(rate, 0)
        self.assertGreaterEqual(annual, rate)

    def test_every_section_builds_and_is_json_serialisable(self):
        wf = HA.load_workforce(self.org, self._filters())
        for section in HA.SECTIONS:
            with self.subTest(section=section):
                data = HA.section_data(wf, section)
                self.assertIsInstance(data, dict)
                json.dumps(data)  # must survive JsonResponse

    def test_overview_kpis_cover_the_headline_metrics(self):
        wf = HA.load_workforce(self.org, self._filters())
        keys = {k["key"] for k in HA.section_data(wf, "overview")["kpis"]}
        self.assertTrue(
            {"headcount", "attrition", "retention", "hires", "cost", "diversity"} <= keys
        )

    def test_attrition_section_records_the_separation(self):
        wf = HA.load_workforce(self.org, self._filters())
        data = HA.section_data(wf, "attrition")
        self.assertEqual(data["kpis"]["separations"], 1)
        self.assertEqual(data["recent"][0]["reason"], "Better opportunity")
        self.assertEqual(data["kpis"]["voluntary_share"], 100.0)

    def test_scorecard_has_one_row_per_department(self):
        wf = HA.load_workforce(self.org, self._filters())
        rows = HA.section_data(wf, "scorecard")["rows"]
        names = {r["department"] for r in rows}
        self.assertIn("Engineering", names)
        self.assertIn("Operations", names)

    def test_department_filter_narrows_the_population(self):
        filters = self._filters(department=str(self.eng.pk))
        wf = HA.load_workforce(self.org, filters)
        self.assertTrue(all(r.department == "Engineering" for r in wf.rows))

    def test_zero_denominators_do_not_raise(self):
        empty_org = _make_org("Empty Co", "ANL3")
        wf = HA.load_workforce(empty_org, self._filters())
        self.assertEqual(wf.headcount(), 0)
        for section in HA.SECTIONS:
            with self.subTest(section=section):
                json.dumps(HA.section_data(wf, section))

    def test_period_presets_resolve(self):
        for period, _label in HA.PERIOD_CHOICES:
            if period == "custom":
                continue
            with self.subTest(period=period):
                resolved = HA.resolve_period(period, self.today)
                if period == "fy":
                    self.assertIsNone(resolved)  # needs an FY dict
                    continue
                self.assertIsNotNone(resolved)
                self.assertLessEqual(resolved[0], resolved[1])

    # ── views ─────────────────────────────────────────────────────────────

    def test_page_renders_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:hr_analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HR Analytics")

    def test_page_renders_for_hr(self):
        self.client.force_login(self.hr)
        self.assertEqual(
            self.client.get(reverse("dashboard:hr_analytics")).status_code, 200
        )

    def test_employees_are_redirected_away(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("dashboard:hr_analytics"))
        self.assertEqual(response.status_code, 302)

    def test_data_endpoint_returns_each_section(self):
        self.client.force_login(self.admin)
        for section in HA.SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(
                    reverse("dashboard:hr_analytics_data"), {"section": section}
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["section"], section)
                self.assertIn("filters", payload["data"])

    def test_data_endpoint_rejects_an_unknown_section(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboard:hr_analytics_data"), {"section": "nope"}
        )
        self.assertEqual(response.status_code, 400)

    def test_csv_export(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:hr_analytics"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Engineering", response.content.decode())

    def test_xlsx_export(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:hr_analytics"), {"export": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))

    def test_view_is_audited(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("dashboard:hr_analytics"))
        self.assertTrue(
            AttendanceReportAudit.objects.filter(
                organization=self.org, report="hr_analytics"
            ).exists()
        )
