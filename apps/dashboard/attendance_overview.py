"""Employee Attendance Overview report — per-employee attendance % (bar chart).

Single grouped aggregation query (no N+1) so it scales to large orgs; tenant-scoped via the
viewer's organization. Reuses ``_scoped_team`` and ``count_working_days``.
"""

from __future__ import annotations

import calendar
import csv
import io
from dataclasses import dataclass
from datetime import date

from django.core.cache import cache
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.attendance.work_calendar import count_working_days
from apps.organizations.models import Department

from .attendance_analytics import _scoped_team

_PRESENT = {AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.WFH}
_HALF = AttendanceRecord.Status.HALF_DAY
_ABSENT = AttendanceRecord.Status.ABSENT
_LEAVE = AttendanceRecord.Status.LEAVE


@dataclass
class OverviewFilters:
    year: int
    month: int
    department: str = ""
    designation: str = ""
    employee_id: str = ""
    status: str = ""
    include_leave: bool = True
    sort: str = "pct_desc"
    search: str = ""

    @classmethod
    def from_request(cls, request, fy: dict | None = None) -> "OverviewFilters":
        def _int(v, d):
            try:
                return int(v)
            except (TypeError, ValueError):
                return d

        today = timezone.localdate()
        if fy:
            # Default to the most recent month within the FY (up to today)
            from datetime import date as _date
            fy_end = min(today, fy["date_to"])
            default_year, default_month = fy_end.year, fy_end.month
        else:
            default_year, default_month = today.year, today.month
        return cls(
            year=_int(request.GET.get("year"), default_year),
            month=_int(request.GET.get("month"), default_month),
            department=(request.GET.get("department") or "").strip(),
            designation=(request.GET.get("designation") or "").strip(),
            employee_id=(request.GET.get("employee") or "").strip(),
            status=(request.GET.get("status") or "").strip(),
            include_leave=(request.GET.get("include_leave", "yes").lower() in ("yes", "1", "true")),
            sort=(request.GET.get("sort") or "pct_desc").strip(),
            search=(request.GET.get("q") or "").strip(),
        )

    def cache_key(self, viewer) -> str:
        return ":".join(str(x) for x in [
            "att_overview", viewer.organization_id, viewer.pk, self.year, self.month,
            self.department, self.designation, self.employee_id, self.status,
            self.include_leave, self.sort, self.search,
        ])

    def label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"


def _team(viewer, filters: OverviewFilters):
    qs = _scoped_team(viewer, "active")
    if filters.department:
        qs = qs.filter(department_id=filters.department)
    if filters.designation:
        qs = qs.filter(designation__icontains=filters.designation)
    if filters.employee_id:
        qs = qs.filter(pk=filters.employee_id)
    if filters.search:
        qs = qs.filter(
            Q(first_name__icontains=filters.search)
            | Q(last_name__icontains=filters.search)
            | Q(employee_id__icontains=filters.search)
            | Q(username__icontains=filters.search)
        )
    return qs


def employee_attendance_overview(viewer, filters: OverviewFilters, use_cache: bool = True) -> dict:
    key = filters.cache_key(viewer)
    if use_cache:
        cached = cache.get(key)
        if cached:
            return cached

    org = viewer.organization
    team = list(_team(viewer, filters))
    ids = [u.pk for u in team]
    last_day = calendar.monthrange(filters.year, filters.month)[1]
    start = date(filters.year, filters.month, 1)
    end = date(filters.year, filters.month, last_day)
    working_days = count_working_days(org, start, end) if org else last_day

    # One grouped query for the whole team — no per-employee queries.
    counts: dict = {}
    if ids:
        rows = (
            AttendanceRecord.objects.filter(user_id__in=ids, date__gte=start, date__lte=end)
            .values("user_id", "status")
            .annotate(c=Count("id"))
        )
        for r in rows:
            counts.setdefault(r["user_id"], {})[r["status"]] = r["c"]

    result_rows = []
    for u in team:
        c = counts.get(u.pk, {})
        present = sum(c.get(s, 0) for s in _PRESENT) + c.get(_HALF, 0)
        absent = c.get(_ABSENT, 0)
        leave = c.get(_LEAVE, 0)
        denom = working_days - (leave if filters.include_leave else 0)
        pct = round(present / denom * 100, 1) if denom > 0 else 0.0
        pct = min(100.0, pct)
        result_rows.append({
            "user_id": str(u.pk),
            "employee_id": u.employee_id or "—",
            "name": u.choice_label,
            "department": u.department_name or "—",
            "designation": u.designation or "—",
            "present": present,
            "absent": absent,
            "leave": leave,
            "working_days": working_days,
            "pct": pct,
        })

    if filters.status:
        # Optional attendance-status filter: keep employees who have that status this month.
        import uuid as _uuid

        def _has_status(r):
            uid = _uuid.UUID(r["user_id"])
            return counts.get(uid, {}).get(filters.status, 0) > 0

        result_rows = [r for r in result_rows if _has_status(r)]

    _sort_rows(result_rows, filters.sort)
    summary = _summary(result_rows)
    payload = {"rows": result_rows, "summary": summary, "working_days": working_days,
               "period": filters.label()}
    if use_cache:
        cache.set(key, payload, 60)
    return payload


def _sort_rows(rows: list, sort: str) -> None:
    if sort == "pct_asc":
        rows.sort(key=lambda r: r["pct"])
    elif sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    else:  # pct_desc (default)
        rows.sort(key=lambda r: -r["pct"])


def _summary(rows: list) -> dict:
    total = len(rows)
    if not total:
        return {"total": 0, "avg": 0.0, "above_95": 0, "below_75": 0, "perfect": 0}
    pcts = [r["pct"] for r in rows]
    return {
        "total": total,
        "avg": round(sum(pcts) / total, 1),
        "above_95": sum(1 for p in pcts if p > 95),
        "below_75": sum(1 for p in pcts if p < 75),
        "perfect": sum(1 for p in pcts if p >= 100),
    }


def attendance_overview_widget(viewer) -> dict:
    """Compact org snapshot for the admin dashboard widget (current month)."""
    today = timezone.localdate()
    data = employee_attendance_overview(viewer, OverviewFilters(year=today.year, month=today.month))
    rows = data["rows"]
    top5 = sorted(rows, key=lambda r: -r["pct"])[:5]
    below75 = [r for r in rows if r["pct"] < 75]
    return {
        "avg": data["summary"]["avg"],
        "total": data["summary"]["total"],
        "top5": top5,
        "below75": below75[:5],
        "below75_count": len(below75),
        "period": data["period"],
    }


def filter_options(viewer) -> dict:
    org = viewer.organization
    team = _scoped_team(viewer, "active")
    designations = sorted({
        d for d in team.exclude(designation="").values_list("designation", flat=True).distinct()
    })
    return {
        "years": list(range(timezone.localdate().year, timezone.localdate().year - 5, -1)),
        "months": [(i, calendar.month_name[i]) for i in range(1, 13)],
        "departments": Department.objects.filter(organization=org, is_active=True).order_by("name"),
        "designations": designations,
        "employees": list(team.order_by("first_name", "last_name")),
        "statuses": AttendanceRecord.Status.choices,
    }


# ── Exports (include applied filters + summary + employee table) ─────────────────

_HEADERS = ["Employee ID", "Employee Name", "Department", "Present Days",
            "Absent Days", "Leave Days", "Attendance %"]


def _filter_lines(filters: OverviewFilters, summary: dict) -> list[list]:
    return [
        ["Employee Attendance Overview"],
        ["Period", filters.label()],
        ["Include approved leave", "Yes" if filters.include_leave else "No"],
        ["Department", filters.department or "All"],
        ["Designation", filters.designation or "All"],
        [],
        ["Summary"],
        ["Total Employees", summary["total"]],
        ["Average Attendance %", summary["avg"]],
        ["Above 95%", summary["above_95"]],
        ["Below 75%", summary["below_75"]],
        ["Perfect Attendance", summary["perfect"]],
        [],
    ]


def _row_values(r: dict) -> list:
    return [r["employee_id"], r["name"], r["department"], r["present"],
            r["absent"], r["leave"], r["pct"]]


def export_csv(filters: OverviewFilters, summary: dict, rows: list) -> HttpResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    for line in _filter_lines(filters, summary):
        w.writerow(line)
    w.writerow(_HEADERS)
    for r in rows:
        w.writerow(_row_values(r))
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="employee_attendance.csv"'
    return resp


def export_xlsx(filters: OverviewFilters, summary: dict, rows: list) -> HttpResponse:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    for line in _filter_lines(filters, summary):
        ws.append(line)
    ws.append(_HEADERS)
    for r in rows:
        ws.append(_row_values(r))
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="employee_attendance.xlsx"'
    return resp
