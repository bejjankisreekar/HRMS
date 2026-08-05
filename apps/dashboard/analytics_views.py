import json
from datetime import timedelta
from collections import defaultdict

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User

from .attendance_analytics import (
    AnalyticsFilters,
    build_table_rows,
    build_trend,
    employee_detail_payload,
    export_rows_csv,
    export_rows_xlsx,
    get_analytics_context,
)
from .mixins import AdminOrHRRequiredMixin
from apps.organizations.fy_utils import get_selected_fy


class AttendanceAnalyticsView(AdminOrHRRequiredMixin, TemplateView):
    """Enterprise attendance analytics dashboard."""

    template_name = "dashboard/attendance_analytics.html"
    paginate_by = 25

    def get(self, request, *args, **kwargs):
        export = request.GET.get("export")
        if export in ("csv", "excel", "xlsx"):
            filters = AnalyticsFilters.from_request(request, fy=get_selected_fy(request))
            rows = build_table_rows(request.user, filters)
            if export in ("xlsx", "excel"):
                return export_rows_xlsx(rows)
            return export_rows_csv(rows)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = get_analytics_context(self.request.user, self.request)
        rows = ctx.pop("table_rows")
        paginator = Paginator(rows, self.paginate_by)
        page_num = self.request.GET.get("page") or 1
        page = paginator.get_page(page_num)
        ctx["page_obj"] = page
        ctx["table_rows"] = page.object_list

        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("export", None)
        ctx["filter_query"] = query.urlencode()
        ctx["filters_get"] = self.request.GET
        ctx["today"] = timezone.localdate()
        ctx["status_choices"] = [
            ("PRESENT", "Present"),
            ("ABSENT", "Absent"),
            ("LEAVE", "Leave"),
            ("HALF_DAY", "Half day"),
            ("WFH", "Work from home"),
        ]
        ctx["range_choices"] = [
            ("today", "Today"),
            ("this_week", "This Week"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
            ("this_quarter", "This Quarter"),
            ("custom", "Custom Range"),
        ]
        ctx["granularity_choices"] = [
            ("daily", "Daily View"),
            ("weekly", "Weekly View"),
            ("monthly", "Monthly View"),
        ]
        ctx["emp_status_choices"] = [
            ("active", "Active Employees"),
            ("inactive", "Inactive Employees"),
            ("all", "All Employees"),
        ]
        return ctx


class AttendanceReportsDataView(AdminOrHRRequiredMixin, View):
    """JSON payload for the AJAX trend/distribution/department + KPI refresh."""

    def get(self, request, *args, **kwargs):
        filters = AnalyticsFilters.from_request(request, fy=get_selected_fy(request))
        return JsonResponse(build_trend(request.user, filters))


class EmployeeAttendanceChartView(AdminOrHRRequiredMixin, TemplateView):
    """Employee Attendance Overview — per-employee attendance % bar chart (Admin/HR only)."""

    template_name = "dashboard/employee_attendance_chart.html"

    def get(self, request, *args, **kwargs):
        from . import attendance_overview as AO

        if request.GET.get("export") in ("csv", "xlsx", "excel"):
            from apps.attendance.models import AttendanceReportAudit, record_report_audit

            filters = AO.OverviewFilters.from_request(request, fy=get_selected_fy(request))
            data = AO.employee_attendance_overview(request.user, filters)
            fmt = request.GET["export"]
            record_report_audit(
                request.user.organization, request.user,
                AttendanceReportAudit.Action.EXPORTED,
                export_type=("xlsx" if fmt in ("xlsx", "excel") else "csv"),
                filters={"period": filters.label(), "department": filters.department},
            )
            if fmt in ("xlsx", "excel"):
                return AO.export_xlsx(filters, data["summary"], data["rows"])
            return AO.export_csv(filters, data["summary"], data["rows"])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from . import attendance_overview as AO
        from apps.attendance.models import AttendanceReportAudit, record_report_audit

        import json

        ctx = super().get_context_data(**kwargs)
        filters = AO.OverviewFilters.from_request(self.request, fy=get_selected_fy(self.request))
        data = AO.employee_attendance_overview(self.request.user, filters)

        query = self.request.GET.copy()
        query.pop("export", None)

        ctx.update({
            "organization": self.request.user.organization,
            "filters": filters,
            "filters_get": self.request.GET,
            "filter_query": query.urlencode(),
            "filter_options": AO.filter_options(self.request.user),
            "summary": data["summary"],
            "rows": data["rows"],
            "rows_json": json.dumps(data["rows"]),
            "working_days": data["working_days"],
            "today": timezone.localdate(),
        })
        record_report_audit(
            self.request.user.organization, self.request.user,
            AttendanceReportAudit.Action.VIEWED,
            filters={"period": filters.label(), "department": filters.department},
        )
        return ctx


class AttendanceAnalyticsEmployeeView(AdminOrHRRequiredMixin, View):
    """JSON payload for employee detail modal."""

    def get(self, request, pk):
        month = request.GET.get("month")
        year = request.GET.get("year")
        try:
            month_i = int(month) if month else None
            year_i = int(year) if year else None
        except ValueError:
            month_i = year_i = None
        data = employee_detail_payload(request.user, str(pk), month_i, year_i)
        if not data:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse(data)


class AttendanceReportLegacyRedirectView(AdminOrHRRequiredMixin, View):
    """Redirect old dashboard report URL to new analytics page."""

    def get(self, request):
        q = request.GET.urlencode()
        url = "/attendance/reports/"
        if q:
            url = f"{url}?{q}"
        return redirect(url)


# ── Unified Analytics Dashboard ────────────────────────────────────────────────

class AnalyticsDashboardView(AdminOrHRRequiredMixin, TemplateView):
    """Unified analytics page: attendance, payroll, workforce."""

    template_name = "dashboard/analytics_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["is_admin"] = user.role == User.Role.ADMIN
        ctx["org"] = user.organization
        ctx["today"] = timezone.localdate()
        return ctx


class AnalyticsDataView(AdminOrHRRequiredMixin, View):
    """JSON API returning chart data for the analytics dashboard.

    Query params:
      section : attendance | payroll | workforce
      days    : int (attendance trend window, default 30)
      months  : int (payroll window, default 12)
    """

    def get(self, request, *args, **kwargs):
        section = request.GET.get("section", "attendance")
        user = request.user

        if section == "attendance":
            return JsonResponse(self._attendance(user, request))
        if section == "payroll":
            return JsonResponse(self._payroll(user, request))
        if section == "workforce":
            return JsonResponse(self._workforce(user))
        return JsonResponse({"error": "Unknown section"}, status=400)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _org_employees(self, user):
        if user.role == User.Role.ADMIN:
            return User.objects.filter(
                organization=user.organization,
                role__in=[User.Role.HR, User.Role.EMPLOYEE],
                is_active=True,
            )
        return User.objects.filter(
            organization=user.organization,
            assigned_hr=user,
            is_active=True,
        )

    def _all_org_employees(self, user):
        """All employees regardless of status (for headcount)."""
        return User.objects.filter(
            organization=user.organization,
            role__in=[User.Role.HR, User.Role.EMPLOYEE],
        )

    # ── attendance section ────────────────────────────────────────────────────

    def _attendance(self, user, request):
        from apps.attendance.models import AttendanceRecord
        from apps.organizations.models import Department

        days = min(int(request.GET.get("days", 30) or 30), 90)
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        employees = self._org_employees(user)

        records = list(AttendanceRecord.objects.filter(
            user__in=employees, date__gte=start, date__lte=today
        ).values("date", "status", "check_in", "check_out", "break_minutes", "user_id"))

        # ── Trend (stacked bar) ──
        by_date = defaultdict(lambda: defaultdict(int))
        for r in records:
            by_date[r["date"]][r["status"]] += 1

        trend_labels, t_present, t_absent, t_half, t_leave, t_wfh = [], [], [], [], [], []
        for i in range(days):
            d = start + timedelta(days=i)
            c = by_date.get(d, {})
            trend_labels.append(d.strftime("%d %b"))
            t_present.append(c.get("PRESENT", 0))
            t_absent.append(c.get("ABSENT", 0))
            t_half.append(c.get("HALF_DAY", 0))
            t_leave.append(c.get("LEAVE", 0))
            t_wfh.append(c.get("WFH", 0))

        # ── Today's donut ──
        today_counts = by_date.get(today, {})
        total_emp = employees.count()
        marked = sum(today_counts.values())
        donut_values = [
            today_counts.get("PRESENT", 0),
            today_counts.get("ABSENT", 0),
            today_counts.get("HALF_DAY", 0),
            today_counts.get("LEAVE", 0),
            today_counts.get("WFH", 0),
            max(0, total_emp - marked),
        ]

        # ── Avg working hours per day ──
        from django.utils import timezone as tz
        hours_by_date = defaultdict(list)
        for r in records:
            if r["check_in"] and r["check_out"]:
                ci = tz.localtime(r["check_in"]) if timezone.is_aware(r["check_in"]) else r["check_in"]
                co = tz.localtime(r["check_out"]) if timezone.is_aware(r["check_out"]) else r["check_out"]
                mins = max(0, int((co - ci).total_seconds() // 60) - (r["break_minutes"] or 0))
                hours_by_date[r["date"]].append(mins / 60)

        avg_hours_labels, avg_hours_vals = [], []
        for i in range(days):
            d = start + timedelta(days=i)
            vals = hours_by_date.get(d, [])
            avg_hours_labels.append(d.strftime("%d %b"))
            avg_hours_vals.append(round(sum(vals) / len(vals), 2) if vals else None)

        # ── Department attendance rate ──
        dept_qs = Department.objects.filter(
            organization=user.organization, is_active=True
        ).values("id", "name")
        dept_map = {str(d["id"]): d["name"] for d in dept_qs}

        emp_dept = {
            str(u["id"]): str(u["department_id"] or "")
            for u in employees.values("id", "department_id")
        }
        dept_present = defaultdict(int)
        dept_total = defaultdict(int)
        for uid, dept_id in emp_dept.items():
            if dept_id and dept_id in dept_map:
                dept_total[dept_id] += days
        for r in records:
            uid = str(r["user_id"])
            dept_id = emp_dept.get(uid, "")
            if dept_id and dept_id in dept_map and r["status"] == "PRESENT":
                dept_present[dept_id] += 1

        dept_labels, dept_rates = [], []
        for dept_id, name in dept_map.items():
            total = dept_total.get(dept_id, 0)
            if total > 0:
                dept_labels.append(name)
                dept_rates.append(round(dept_present.get(dept_id, 0) / total * 100, 1))

        return {
            "trend": {"labels": trend_labels, "present": t_present, "absent": t_absent,
                      "half_day": t_half, "leave": t_leave, "wfh": t_wfh},
            "donut": {"labels": ["Present","Absent","Half Day","Leave","WFH","Unmarked"],
                      "values": donut_values, "total": total_emp},
            "avg_hours": {"labels": avg_hours_labels, "values": avg_hours_vals},
            "dept_rate": {"labels": dept_labels, "values": dept_rates},
        }

    # ── payroll section ───────────────────────────────────────────────────────

    def _payroll(self, user, request):
        try:
            from apps.payroll.models import PayrollRun, Payslip
        except ImportError:
            return {"error": "Payroll module not available"}

        months = min(int(request.GET.get("months", 12) or 12), 24)
        today = timezone.localdate()

        runs = list(PayrollRun.objects.filter(
            organization=user.organization
        ).order_by("year", "month")[:months * 2])

        import calendar
        # Last N months
        month_list = []
        y, m = today.year, today.month
        for _ in range(months):
            month_list.insert(0, (y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        run_map = {(r.year, r.month): r for r in runs}
        labels, gross_vals, net_vals, deduction_vals, emp_count_vals = [], [], [], [], []
        for y, m in month_list:
            labels.append(f"{calendar.month_abbr[m]} {y}")
            run = run_map.get((y, m))
            gross_vals.append(float(run.total_gross) if run else None)
            net_vals.append(float(run.total_net) if run else None)
            deduction_vals.append(float(run.total_deductions) if run else None)
            emp_count_vals.append(run.employee_count if run else None)

        # Status donut
        status_counts = defaultdict(int)
        for r in runs:
            status_counts[r.status] += 1
        status_labels = [PayrollRun.Status(k).label for k in status_counts]
        status_values = list(status_counts.values())

        # Latest payslip payment status
        latest_run = runs[-1] if runs else None
        payment_labels, payment_values = [], []
        if latest_run:
            payslip_statuses = defaultdict(int)
            for ps in Payslip.objects.filter(payroll_run=latest_run).values("payment_status"):
                payslip_statuses[ps["payment_status"]] += 1
            payment_labels = [Payslip.PaymentStatus(k).label for k in payslip_statuses]
            payment_values = list(payslip_statuses.values())

        return {
            "trend": {"labels": labels, "gross": gross_vals, "net": net_vals,
                      "deductions": deduction_vals, "employee_count": emp_count_vals},
            "run_status": {"labels": status_labels, "values": status_values},
            "payment_status": {"labels": payment_labels, "values": payment_values,
                               "period": latest_run.period_label if latest_run else ""},
        }

    # ── workforce section ─────────────────────────────────────────────────────

    def _workforce(self, user):
        import calendar
        from apps.organizations.models import Department

        all_emp = self._all_org_employees(user)

        # Department headcount (horizontal bar)
        dept_qs = Department.objects.filter(
            organization=user.organization, is_active=True
        ).values("id", "name")
        dept_map = {d["id"]: d["name"] for d in dept_qs}
        dept_counts = defaultdict(int)
        for u in all_emp.values("department_id"):
            if u["department_id"] and u["department_id"] in dept_map:
                dept_counts[u["department_id"]] += 1
        dept_labels = [dept_map[k] for k in dept_counts]
        dept_values = list(dept_counts.values())

        # Employment type donut
        emp_type_counts = defaultdict(int)
        for u in all_emp.values("employment_type"):
            emp_type_counts[u["employment_type"] or "Unknown"] += 1
        type_labels = [User.EmploymentType(k).label if k in User.EmploymentType.values else k
                       for k in emp_type_counts]
        type_values = list(emp_type_counts.values())

        # Gender donut
        gender_counts = defaultdict(int)
        for u in all_emp.values("gender"):
            gender_counts[u["gender"] or "Unknown"] += 1
        gender_labels = [User.Gender(k).label if k in User.Gender.values else "Not specified"
                         for k in gender_counts]
        gender_values = list(gender_counts.values())

        # Work mode donut
        wm_counts = defaultdict(int)
        for u in all_emp.values("work_mode"):
            wm_counts[u["work_mode"] or "Unknown"] += 1
        wm_labels = [User.WorkMode(k).label if k in User.WorkMode.values else "Unknown"
                     for k in wm_counts]
        wm_values = list(wm_counts.values())

        # Monthly joiners (last 12 months)
        today = timezone.localdate()
        join_map = defaultdict(int)
        twelve_ago = today.replace(day=1) - timedelta(days=335)
        for u in all_emp.filter(date_of_joining__gte=twelve_ago).values("date_of_joining"):
            if u["date_of_joining"]:
                key = (u["date_of_joining"].year, u["date_of_joining"].month)
                join_map[key] += 1
        join_labels, join_values = [], []
        y, m = twelve_ago.year, twelve_ago.month
        for _ in range(12):
            join_labels.append(f"{calendar.month_abbr[m]} {y}")
            join_values.append(join_map.get((y, m), 0))
            m += 1
            if m > 12:
                m = 1
                y += 1

        # Employment status (active vs other)
        emp_status_counts = defaultdict(int)
        for u in self._all_org_employees(user).values("employment_status"):
            emp_status_counts[u["employment_status"] or "Unknown"] += 1
        es_labels = [User.EmploymentStatus(k).label if k in User.EmploymentStatus.values else k
                     for k in emp_status_counts]
        es_values = list(emp_status_counts.values())

        # Leave usage by type (last 3 months)
        leave_data = {"labels": [], "approved": [], "pending": []}
        try:
            from apps.leaves.models import LeaveType, LeaveRequest
            three_ago = today - timedelta(days=90)
            lt_qs = LeaveType.objects.filter(organization=user.organization).values("id", "name")
            for lt in lt_qs:
                approved = LeaveRequest.objects.filter(
                    user__organization=user.organization,
                    leave_type_id=lt["id"],
                    status="APPROVED",
                    start_date__gte=three_ago,
                ).count()
                pending = LeaveRequest.objects.filter(
                    user__organization=user.organization,
                    leave_type_id=lt["id"],
                    status="PENDING",
                    start_date__gte=three_ago,
                ).count()
                if approved + pending > 0:
                    leave_data["labels"].append(lt["name"])
                    leave_data["approved"].append(approved)
                    leave_data["pending"].append(pending)
        except Exception:
            pass

        return {
            "dept_headcount": {"labels": dept_labels, "values": dept_values},
            "emp_type": {"labels": type_labels, "values": type_values},
            "gender": {"labels": gender_labels, "values": gender_values},
            "work_mode": {"labels": wm_labels, "values": wm_values},
            "joiners": {"labels": join_labels, "values": join_values},
            "emp_status": {"labels": es_labels, "values": es_values},
            "leave_usage": leave_data,
            "totals": {
                "active": all_emp.filter(is_active=True).count(),
                "inactive": all_emp.filter(is_active=False).count(),
                "total": all_emp.count(),
            },
        }
