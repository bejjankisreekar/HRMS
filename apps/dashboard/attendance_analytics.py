"""Enterprise attendance analytics: aggregates, charts, table rows, insights."""

from __future__ import annotations

import calendar
import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Count, Q, QuerySet, Sum
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, WorkShift
from apps.attendance.work_calendar import count_working_days
from apps.organizations.models import Department, Organization

from .attendance_utils import (
    analyze_lateness,
    compute_working_hours,
    ensure_default_shift,
    format_time_display,
    format_total_minutes,
    get_effective_shift,
    parse_attendance_date,
)


def _preset_range(preset: str, today):
    """Resolve a date-range preset to (date_from, date_to). None = use from/to."""
    if preset == "today":
        return today, today
    if preset == "this_week":
        return today - timedelta(days=today.weekday()), today
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if preset == "this_quarter":
        q_start_month = 3 * ((today.month - 1) // 3) + 1
        return today.replace(month=q_start_month, day=1), today
    return None


@dataclass
class AnalyticsFilters:
    date_from: Any
    date_to: Any
    department: str = ""
    branch: str = ""
    employee_id: str = ""
    shift_id: str = ""
    status: str = ""
    employment_type: str = ""
    employee_status: str = "active"
    granularity: str = "monthly"
    date_range: str = "custom"
    late_only: bool = False
    wfh_only: bool = False
    leave_only: bool = False
    search: str = ""
    sort: str = "-date"

    @classmethod
    def from_request(cls, request, fy: dict | None = None) -> AnalyticsFilters:
        today = timezone.localdate()
        preset = (request.GET.get("range") or "custom").strip()
        preset_dates = _preset_range(preset, today)
        if preset_dates:
            date_from, date_to = preset_dates
        else:
            preset = "custom"
            if fy:
                default_from = str(fy["date_from"])
                default_to = str(min(today, fy["date_to"]))
            else:
                default_from = str(today.replace(day=1))
                default_to = str(today)
            date_from = parse_attendance_date(request.GET.get("from") or default_from)
            date_to = parse_attendance_date(request.GET.get("to") or default_to)
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        granularity = (request.GET.get("view") or "monthly").strip().lower()
        if granularity not in ("daily", "weekly", "monthly"):
            granularity = "monthly"
        employee_status = (request.GET.get("emp_status") or "active").strip().lower()
        if employee_status not in ("active", "inactive", "all"):
            employee_status = "active"
        return cls(
            date_from=date_from,
            date_to=date_to,
            department=(request.GET.get("department") or "").strip(),
            branch=(request.GET.get("branch") or "").strip(),
            employee_id=(request.GET.get("employee") or "").strip(),
            shift_id=(request.GET.get("shift") or "").strip(),
            status=(request.GET.get("status") or "").strip(),
            employment_type=(request.GET.get("employment_type") or "").strip(),
            employee_status=employee_status,
            granularity=granularity,
            date_range=preset,
            late_only=request.GET.get("late") == "1",
            wfh_only=request.GET.get("wfh") == "1",
            leave_only=request.GET.get("leave") == "1",
            search=(request.GET.get("q") or "").strip(),
            sort=request.GET.get("sort") or "-date",
        )

    def cache_key_suffix(self) -> str:
        parts = [
            str(self.date_from),
            str(self.date_to),
            self.department,
            self.branch,
            self.employee_id,
            self.shift_id,
            self.status,
            self.employment_type,
            self.employee_status,
            self.granularity,
            str(self.late_only),
            str(self.wfh_only),
            str(self.leave_only),
            self.search,
        ]
        return ":".join(parts)


def record_working_minutes(record: AttendanceRecord | None) -> int:
    if not record or not record.check_in or not record.check_out:
        return 0
    delta = record.check_out - record.check_in
    mins = int(delta.total_seconds() // 60) - (record.break_minutes or 0)
    return max(0, mins)


def compute_overtime_minutes(record: AttendanceRecord | None, shift: WorkShift | None) -> int:
    if not record or not record.check_out or not shift:
        return 0
    local_out = timezone.localtime(record.check_out)
    shift_end = timezone.make_aware(
        datetime.combine(record.date, shift.end_time),
        timezone.get_current_timezone(),
    )
    if local_out <= shift_end:
        return 0
    return int((local_out - shift_end).total_seconds() // 60)


def compute_early_exit_minutes(record: AttendanceRecord | None, shift: WorkShift | None) -> int:
    if not record or not record.check_out or not shift:
        return 0
    local_out = timezone.localtime(record.check_out)
    shift_end = timezone.make_aware(
        datetime.combine(record.date, shift.end_time),
        timezone.get_current_timezone(),
    )
    if local_out >= shift_end:
        return 0
    return int((shift_end - local_out).total_seconds() // 60)


def _scoped_team(manager: User, employee_status: str = "active") -> QuerySet[User]:
    """Attendance team scoped by role, with the is_active filter per employee_status.

    Mirrors ``attendance_team_for`` (Admin → org HR+EMPLOYEE; HR → assigned
    employees + self) but lets callers include inactive users.
    """
    org = manager.organization
    if not org:
        return User.objects.none()
    base = User.objects.filter(organization=org)
    if manager.role == User.Role.ADMIN:
        base = base.filter(role__in=[User.Role.HR, User.Role.EMPLOYEE])
    elif manager.role == User.Role.HR:
        base = base.filter(
            Q(assigned_hr=manager, role=User.Role.EMPLOYEE) | Q(pk=manager.pk)
        )
    else:
        base = base.filter(pk=manager.pk)
    if employee_status == "active":
        base = base.filter(is_active=True)
    elif employee_status == "inactive":
        base = base.filter(is_active=False)
    return base.select_related("department", "work_shift")


def filter_team(manager: User, filters: AnalyticsFilters) -> QuerySet[User]:
    qs = _scoped_team(manager, filters.employee_status)
    if filters.employee_id:
        qs = qs.filter(pk=filters.employee_id)
    if filters.department:
        qs = qs.filter(department_id=filters.department)
    if filters.branch:
        qs = qs.filter(work_location__iexact=filters.branch)
    if filters.employment_type:
        qs = qs.filter(employment_type=filters.employment_type)
    if filters.shift_id == "default":
        qs = qs.filter(work_shift__isnull=True)
    elif filters.shift_id:
        qs = qs.filter(work_shift_id=filters.shift_id)
    if filters.search:
        qs = qs.filter(
            Q(first_name__icontains=filters.search)
            | Q(last_name__icontains=filters.search)
            | Q(username__icontains=filters.search)
            | Q(employee_id__icontains=filters.search)
            | Q(email__icontains=filters.search)
        )
    return qs


def filter_records(
    records_qs: QuerySet[AttendanceRecord],
    filters: AnalyticsFilters,
    team_ids: list,
) -> QuerySet[AttendanceRecord]:
    qs = records_qs.filter(
        user_id__in=team_ids,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
    ).select_related("user", "user__work_shift")
    if filters.status:
        qs = qs.filter(status=filters.status)
    if filters.wfh_only:
        qs = qs.filter(status=AttendanceRecord.Status.WFH)
    if filters.leave_only:
        qs = qs.filter(status=AttendanceRecord.Status.LEAVE)
    return qs.order_by("-date", "user__first_name")


def enrich_record_row(record: AttendanceRecord) -> dict:
    member = record.user
    shift = get_effective_shift(member)
    lateness = analyze_lateness(record, shift, record.date)
    work_mins = record_working_minutes(record)
    ot_mins = compute_overtime_minutes(record, shift)
    early_mins = compute_early_exit_minutes(record, shift)
    leave_type = ""
    if record.status == AttendanceRecord.Status.LEAVE:
        leave_type = record.note or "Leave"
    return {
        "record": record,
        "member": member,
        "shift": shift,
        "employee_id": member.employee_id or "—",
        "employee_name": member.choice_label,
        "department": member.department_name or "—",
        "designation": member.designation or "—",
        "date": record.date,
        "check_in": format_time_display(record.check_in) if record.check_in else "—",
        "check_out": format_time_display(record.check_out) if record.check_out else "—",
        "working_hours": format_total_minutes(work_mins) if work_mins else compute_working_hours(record),
        "working_minutes": work_mins,
        "break_time": format_total_minutes(record.break_minutes) if record.break_minutes else "—",
        "overtime": format_total_minutes(ot_mins) if ot_mins else "—",
        "overtime_minutes": ot_mins,
        "status": record.status,
        "status_display": record.get_status_display(),
        "late_by": lateness.get("label", "—") if lateness.get("is_late") else ("—" if not lateness.get("in_grace") else lateness.get("label")),
        "is_late": lateness.get("is_late"),
        "early_exit": format_total_minutes(early_mins) if early_mins else "—",
        "leave_type": leave_type or "—",
        "attendance_source": record.get_attendance_source_display() if record.attendance_source else "—",
        "remarks": record.note or "—",
        "lateness": lateness,
    }


def build_table_rows(
    manager: User,
    filters: AnalyticsFilters,
) -> list[dict]:
    team = filter_team(manager, filters)
    team_ids = list(team.values_list("pk", flat=True))
    if not team_ids:
        return []
    records_qs = AttendanceRecord.objects.filter(user_id__in=team_ids)
    records = filter_records(records_qs, filters, team_ids)
    rows = []
    for rec in records:
        row = enrich_record_row(rec)
        if filters.late_only and not row["is_late"]:
            continue
        rows.append(row)
    sort_key = filters.sort.lstrip("-")
    reverse = filters.sort.startswith("-")
    key_map = {
        "date": lambda r: r["date"],
        "name": lambda r: r["employee_name"].lower(),
        "department": lambda r: r["department"].lower(),
        "hours": lambda r: r["working_minutes"],
    }
    fn = key_map.get(sort_key, key_map["date"])
    rows.sort(key=fn, reverse=reverse)
    return rows


def _today_records(team_ids: list, today) -> QuerySet[AttendanceRecord]:
    return AttendanceRecord.objects.filter(user_id__in=team_ids, date=today).select_related("user")


def build_summary_cards(manager: User, filters: AnalyticsFilters) -> dict:
    today = timezone.localdate()
    team = filter_team(manager, filters)
    team_count = team.count()
    team_ids = list(team.values_list("pk", flat=True))

    today_recs = {r.user_id: r for r in _today_records(team_ids, today)}
    present = absent = on_leave = late = wfh = half_day = 0
    total_work_mins = 0
    work_days = 0

    for member in team:
        rec = today_recs.get(member.pk)
        if not rec:
            absent += 1
            continue
        shift = get_effective_shift(member)
        lateness = analyze_lateness(rec, shift, today)
        if lateness.get("is_late"):
            late += 1
        if rec.status == AttendanceRecord.Status.PRESENT:
            present += 1
        elif rec.status == AttendanceRecord.Status.ABSENT:
            absent += 1
        elif rec.status == AttendanceRecord.Status.LEAVE:
            on_leave += 1
        elif rec.status == AttendanceRecord.Status.WFH:
            wfh += 1
        elif rec.status == AttendanceRecord.Status.HALF_DAY:
            half_day += 1
        wm = record_working_minutes(rec)
        if wm:
            total_work_mins += wm
            work_days += 1

    marked_present = present
    attendance_rate = round((marked_present / team_count) * 100) if team_count else 0
    avg_hours = format_total_minutes(total_work_mins // work_days) if work_days else "0h"

    period_recs = AttendanceRecord.objects.filter(
        user_id__in=team_ids,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
    )
    prev_from = filters.date_from - (filters.date_to - filters.date_from) - timedelta(days=1)
    prev_to = filters.date_from - timedelta(days=1)
    prev_present = period_recs.filter(
        date__gte=prev_from, date__lte=prev_to, status=AttendanceRecord.Status.PRESENT
    ).count()
    cur_present = period_recs.filter(status=AttendanceRecord.Status.PRESENT).count()
    trend_present = _pct_change(prev_present, cur_present)

    return {
        "total_employees": team_count,
        "present_today": present,
        "absent_today": absent,
        "on_leave": on_leave,
        "late_checkins": late,
        "wfh": wfh,
        "half_day": half_day,
        "avg_working_hours": avg_hours,
        "attendance_rate": attendance_rate,
        "trend_present": trend_present,
        "today": today,
    }


def _pct_change(old: int, new: int) -> float:
    if old == 0:
        return 100.0 if new else 0.0
    return round(((new - old) / old) * 100, 1)


def build_chart_data(manager: User, filters: AnalyticsFilters) -> dict:
    team = filter_team(manager, filters)
    team_ids = list(team.values_list("pk", flat=True))
    if not team_ids:
        return _empty_charts()

    records = AttendanceRecord.objects.filter(
        user_id__in=team_ids,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
    )

    monthly: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "leave": 0})
    weekly: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0})
    dept: dict[str, int] = defaultdict(int)
    late_by_day: dict[str, int] = defaultdict(int)
    login_times: list[int] = []
    logout_times: list[int] = []
    overtime_total = 0

    for rec in records.select_related("user"):
        key = rec.date.strftime("%Y-%m")
        wkey = rec.date.strftime("%Y-W%W")
        if rec.status == AttendanceRecord.Status.PRESENT:
            monthly[key]["present"] += 1
            weekly[wkey]["present"] += 1
            dept[rec.user.department_name or "Unassigned"] += 1
        elif rec.status == AttendanceRecord.Status.ABSENT:
            monthly[key]["absent"] += 1
            weekly[wkey]["absent"] += 1
        elif rec.status == AttendanceRecord.Status.LEAVE:
            monthly[key]["leave"] += 1

        shift = get_effective_shift(rec.user)
        lateness = analyze_lateness(rec, shift, rec.date)
        if lateness.get("is_late"):
            late_by_day[rec.date.isoformat()] += 1
        if rec.check_in:
            local = timezone.localtime(rec.check_in)
            login_times.append(local.hour * 60 + local.minute)
        if rec.check_out:
            local = timezone.localtime(rec.check_out)
            logout_times.append(local.hour * 60 + local.minute)
        overtime_total += compute_overtime_minutes(rec, shift)

    months_sorted = sorted(monthly.keys())[-12:]
    monthly_labels = months_sorted
    monthly_present = [monthly[m]["present"] for m in months_sorted]
    monthly_absent = [monthly[m]["absent"] for m in months_sorted]
    monthly_leave = [monthly[m]["leave"] for m in months_sorted]

    weeks_sorted = sorted(weekly.keys())[-8:]
    weekly_labels = [w.split("-W")[1] if "-W" in w else w for w in weeks_sorted]
    weekly_present = [weekly[w]["present"] for w in weeks_sorted]
    weekly_absent = [weekly[w]["absent"] for w in weeks_sorted]

    dept_labels = list(dept.keys())[:10]
    dept_values = [dept[d] for d in dept_labels]

    late_labels = sorted(late_by_day.keys())[-14:]
    late_values = [late_by_day[d] for d in late_labels]

    emp_pct = _employee_attendance_percentages(team_ids, filters)

    avg_login = _format_avg_minutes(login_times)
    avg_logout = _format_avg_minutes(logout_times)

    return {
        "monthly": {
            "labels": monthly_labels,
            "present": monthly_present,
            "absent": monthly_absent,
            "leave": monthly_leave,
        },
        "weekly": {
            "labels": weekly_labels,
            "present": weekly_present,
            "absent": weekly_absent,
        },
        "department": {"labels": dept_labels, "values": dept_values},
        "late": {"labels": late_labels, "values": late_values},
        "employee_pct": emp_pct,
        "avg_login": avg_login,
        "avg_logout": avg_logout,
        "overtime_hours": format_total_minutes(overtime_total),
    }


def _empty_charts() -> dict:
    return {
        "monthly": {"labels": [], "present": [], "absent": [], "leave": []},
        "weekly": {"labels": [], "present": [], "absent": []},
        "department": {"labels": [], "values": []},
        "late": {"labels": [], "values": []},
        "employee_pct": [],
        "avg_login": "—",
        "avg_logout": "—",
        "overtime_hours": "0h",
    }


def _format_avg_minutes(mins_list: list[int]) -> str:
    if not mins_list:
        return "—"
    avg = sum(mins_list) // len(mins_list)
    h, m = divmod(avg, 60)
    t = datetime.min.replace(hour=h % 24, minute=m)
    return t.strftime("%I:%M %p").lstrip("0")


def _employee_attendance_percentages(team_ids: list, filters: AnalyticsFilters) -> list[dict]:
    total_days = (filters.date_to - filters.date_from).days + 1
    if total_days <= 0:
        return []
    users = User.objects.filter(pk__in=team_ids).only(
        "pk", "first_name", "last_name", "username", "employee_id"
    )
    present_counts = (
        AttendanceRecord.objects.filter(
            user_id__in=team_ids,
            date__gte=filters.date_from,
            date__lte=filters.date_to,
            status=AttendanceRecord.Status.PRESENT,
        )
        .values("user_id")
        .annotate(c=Count("id"))
    )
    by_user = {row["user_id"]: row["c"] for row in present_counts}
    result = []
    for u in users:
        present = by_user.get(u.pk, 0)
        pct = round((present / total_days) * 100) if total_days else 0
        result.append({"name": u.choice_label, "pct": min(100, pct)})
    result.sort(key=lambda x: -x["pct"])
    return result[:12]


def build_period_kpis(manager: User, filters: AnalyticsFilters) -> dict:
    """Period-based KPI cards: rate, present days, absences, late, leave days."""
    from apps.leaves.models import LeaveRequest

    org = manager.organization
    team_ids = list(filter_team(manager, filters).values_list("pk", flat=True))
    empty = {
        "attendance_rate": 0.0,
        "total_present_days": 0,
        "total_absences": 0,
        "late_arrivals": 0,
        "leave_days": 0.0,
        "wfh": 0,
        "half_day": 0,
        "total_employees": 0,
    }
    if not team_ids:
        return empty
    team_count = len(team_ids)
    records = AttendanceRecord.objects.filter(
        user_id__in=team_ids,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
    ).select_related("user", "user__work_shift")

    present = absent = half = wfh = late = 0
    for rec in records:
        st = rec.status
        if st == AttendanceRecord.Status.PRESENT:
            present += 1
        elif st == AttendanceRecord.Status.ABSENT:
            absent += 1
        elif st == AttendanceRecord.Status.HALF_DAY:
            half += 1
        elif st == AttendanceRecord.Status.WFH:
            wfh += 1
        shift = get_effective_shift(rec.user)
        if analyze_lateness(rec, shift, rec.date).get("is_late"):
            late += 1

    working_days = (
        count_working_days(org, filters.date_from, filters.date_to)
        if org
        else (filters.date_to - filters.date_from).days + 1
    )
    denom = working_days * team_count
    rate = round(present / denom * 100, 1) if denom else 0.0
    rate = min(100.0, rate)

    leave_days = (
        LeaveRequest.objects.filter(
            user_id__in=team_ids,
            status=LeaveRequest.Status.APPROVED,
            start_date__lte=filters.date_to,
            end_date__gte=filters.date_from,
        ).aggregate(s=Sum("total_days"))["s"]
        or 0
    )

    return {
        "attendance_rate": rate,
        "total_present_days": present,
        "total_absences": absent,
        "late_arrivals": late,
        "leave_days": float(leave_days),
        "wfh": wfh,
        "half_day": half,
        "total_employees": team_count,
    }


def build_trend(manager: User, filters: AnalyticsFilters, use_cache: bool = True) -> dict:
    """AJAX payload: attendance-% line by granularity, status distribution, dept rates, KPIs."""
    cache_key = (
        f"att_trend:{manager.organization_id}:{manager.pk}:{filters.cache_key_suffix()}"
    )
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    org = manager.organization
    members = list(filter_team(manager, filters))
    team_ids = [m.pk for m in members]
    dist_labels = ["Present", "Absent", "Late", "Half Day", "Leave", "WFH"]
    if not team_ids:
        payload = {
            "granularity": filters.granularity,
            "trend": {"labels": [], "values": []},
            "distribution": {"labels": dist_labels, "values": [0, 0, 0, 0, 0, 0]},
            "dept_rate": [],
            "kpis": build_period_kpis(manager, filters),
        }
        if use_cache:
            cache.set(cache_key, payload, 60)
        return payload

    team_count = len(team_ids)
    records = AttendanceRecord.objects.filter(
        user_id__in=team_ids,
        date__gte=filters.date_from,
        date__lte=filters.date_to,
    ).select_related("user", "user__work_shift")

    present_by_date: dict = defaultdict(int)
    dist = {"PRESENT": 0, "ABSENT": 0, "LATE": 0, "HALF_DAY": 0, "LEAVE": 0, "WFH": 0}
    dept_present: dict = defaultdict(int)
    for rec in records:
        st = rec.status
        if st in dist:
            dist[st] += 1
        if st == AttendanceRecord.Status.PRESENT:
            present_by_date[rec.date] += 1
            dept_present[rec.user.department_name or "Unassigned"] += 1
        shift = get_effective_shift(rec.user)
        if analyze_lateness(rec, shift, rec.date).get("is_late"):
            dist["LATE"] += 1

    def day_pct(d) -> float:
        return round(present_by_date.get(d, 0) / team_count * 100, 1) if team_count else 0.0

    span = (filters.date_to - filters.date_from).days + 1
    days = [filters.date_from + timedelta(days=i) for i in range(max(0, span))]

    labels: list[str] = []
    values: list[float] = []
    if filters.granularity == "daily":
        for d in days:
            labels.append(d.strftime("%d %b"))
            values.append(day_pct(d))
    elif filters.granularity == "weekly":
        buckets: dict = defaultdict(list)
        for d in days:
            buckets[(d - filters.date_from).days // 7].append(day_pct(d))
        for wk in sorted(buckets):
            vals = buckets[wk]
            labels.append(f"Week {wk + 1}")
            values.append(round(sum(vals) / len(vals), 1) if vals else 0.0)
    else:  # monthly
        buckets = defaultdict(list)
        for d in days:
            buckets[(d.year, d.month)].append(day_pct(d))
        for (y, m) in sorted(buckets):
            vals = buckets[(y, m)]
            labels.append(f"{calendar.month_abbr[m]} {y}")
            values.append(round(sum(vals) / len(vals), 1) if vals else 0.0)

    working_days = count_working_days(org, filters.date_from, filters.date_to) if org else span
    working_days = working_days or 1
    dept_members: dict = defaultdict(int)
    for m in members:
        dept_members[m.department_name or "Unassigned"] += 1
    dept_rate = []
    for name, cnt in dept_members.items():
        denom = cnt * working_days
        pct = round(dept_present.get(name, 0) / denom * 100, 1) if denom else 0.0
        dept_rate.append({"name": name, "pct": min(100.0, pct)})
    dept_rate.sort(key=lambda x: -x["pct"])

    payload = {
        "granularity": filters.granularity,
        "trend": {"labels": labels, "values": values},
        "distribution": {
            "labels": dist_labels,
            "values": [
                dist["PRESENT"], dist["ABSENT"], dist["LATE"],
                dist["HALF_DAY"], dist["LEAVE"], dist["WFH"],
            ],
        },
        "dept_rate": dept_rate,
        "kpis": build_period_kpis(manager, filters),
    }
    if use_cache:
        cache.set(cache_key, payload, 60)
    return payload


def build_insights(manager: User, filters: AnalyticsFilters) -> list[dict]:
    team = filter_team(manager, filters)
    team_ids = list(team.values_list("pk", flat=True))
    if not team_ids:
        return []

    records = list(
        AttendanceRecord.objects.filter(
            user_id__in=team_ids,
            date__gte=filters.date_from,
            date__lte=filters.date_to,
        ).select_related("user")
    )
    late_counts: dict = defaultdict(int)
    dept_present: dict = defaultdict(int)
    dept_total: dict = defaultdict(int)

    for rec in records:
        dept = rec.user.department_name or "Unassigned"
        dept_total[dept] += 1
        if rec.status == AttendanceRecord.Status.PRESENT:
            dept_present[dept] += 1
        shift = get_effective_shift(rec.user)
        if analyze_lateness(rec, shift, rec.date).get("is_late"):
            late_counts[rec.user_id] += 1

    insights = []
    if late_counts:
        worst_uid = max(late_counts, key=late_counts.get)
        worst = User.objects.filter(pk=worst_uid).first()
        if worst:
            insights.append(
                {
                    "icon": "alert-triangle",
                    "title": "Frequent late check-ins",
                    "body": f"{worst.choice_label} was late {late_counts[worst_uid]} times in this period.",
                    "tone": "warning",
                }
            )

    if dept_present:
        best_dept = max(dept_present.keys(), key=lambda d: dept_present[d] / max(dept_total[d], 1))
        rate = round((dept_present[best_dept] / dept_total[best_dept]) * 100)
        insights.append(
            {
                "icon": "building-2",
                "title": "Highest attendance department",
                "body": f"{best_dept} leads with ~{rate}% present marks in range.",
                "tone": "success",
            }
        )

    punctual = None
    for rec in records:
        if rec.status != AttendanceRecord.Status.PRESENT or not rec.check_in:
            continue
        shift = get_effective_shift(rec.user)
        lat = analyze_lateness(rec, shift, rec.date)
        if lat.get("on_time"):
            punctual = rec.user
            break
    if punctual:
        insights.append(
            {
                "icon": "award",
                "title": "Punctual employee",
                "body": f"{punctual.choice_label} shows consistent on-time check-ins.",
                "tone": "info",
            }
        )

    ot_total = sum(compute_overtime_minutes(r, get_effective_shift(r.user)) for r in records)
    if ot_total > 60:
        insights.append(
            {
                "icon": "clock",
                "title": "Overtime trend",
                "body": f"Team logged {format_total_minutes(ot_total)} overtime in selected range.",
                "tone": "neutral",
            }
        )

    leave_count = sum(1 for r in records if r.status == AttendanceRecord.Status.LEAVE)
    if leave_count:
        insights.append(
            {
                "icon": "palmtree",
                "title": "Leave usage",
                "body": f"{leave_count} leave day records across the team in this period.",
                "tone": "neutral",
            }
        )

    insights.append(
        {
            "icon": "scan",
            "title": "Biometric ready",
            "body": "Connect biometric devices to auto-sync attendance source and reduce manual entry.",
            "tone": "info",
        }
    )
    return insights[:6]


def build_calendar(month: int, year: int, user: User) -> dict:
    """Month grid with status per day for one employee."""
    _, last_day = calendar.monthrange(year, month)
    records = {
        r.date.day: r
        for r in AttendanceRecord.objects.filter(
            user=user,
            date__gte=datetime(year, month, 1).date(),
            date__lte=datetime(year, month, last_day).date(),
        )
    }
    days = []
    for day in range(1, last_day + 1):
        rec = records.get(day)
        status = rec.status if rec else "NONE"
        days.append({"day": day, "status": status})
    return {"year": year, "month": month, "days": days}


def filter_options(manager: User) -> dict:
    org = manager.organization
    team = attendance_team_for(manager)
    departments = Department.objects.filter(
        organization=org, is_active=True
    ).order_by("sort_order", "name")
    branches = (
        team.exclude(work_location="")
        .values_list("work_location", flat=True)
        .distinct()
        .order_by("work_location")
    )
    shifts = []
    if org:
        ensure_default_shift(org)
        shifts = list(WorkShift.objects.filter(organization=org).order_by("-is_default", "name"))
    return {
        "departments": departments,
        "dept_label": org.department_label if org else "Department",
        "dept_label_plural": org.department_label_plural if org else "Departments",
        "branches": list(branches),
        "employees": list(team.order_by("first_name", "last_name")),
        "shifts": shifts,
        "employment_types": User.EmploymentType.choices,
        "status_choices": AttendanceRecord.Status.choices,
        "organization": org,
    }


def employee_detail_payload(manager: User, employee_id: str, month: int | None, year: int | None) -> dict:
    try:
        employee = attendance_team_for(manager).get(pk=employee_id)
    except User.DoesNotExist:
        return {}

    today = timezone.localdate()
    month = month or today.month
    year = year or today.year
    cal = build_calendar(month, year, employee)
    shift = get_effective_shift(employee)
    recent = [
        enrich_record_row(r)
        for r in AttendanceRecord.objects.filter(user=employee)
        .order_by("-date")[:31]
    ]
    total_present = AttendanceRecord.objects.filter(
        user=employee,
        status=AttendanceRecord.Status.PRESENT,
        date__year=year,
        date__month=month,
    ).count()
    return {
        "employee": {
            "id": str(employee.pk),
            "name": employee.choice_label,
            "employee_id": employee.employee_id or "—",
            "department": employee.department_name or "—",
            "designation": employee.designation or "—",
            "email": employee.email,
        },
        "shift": {
            "name": shift.name if shift else "—",
            "range": shift.time_range_display if shift else "—",
        },
        "calendar": cal,
        "recent_records": [
            {
                "date": r["date"].isoformat(),
                "check_in": r["check_in"],
                "check_out": r["check_out"],
                "status": r["status_display"],
                "hours": r["working_hours"],
            }
            for r in recent
        ],
        "month_stats": {"present_days": total_present},
        "integrations": {
            "biometric": "Ready",
            "gps": "Not configured",
            "facial": "Not configured",
        },
    }


def export_rows_csv(rows: list[dict]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Employee ID",
            "Employee Name",
            "Department",
            "Designation",
            "Date",
            "Check-in",
            "Check-out",
            "Working Hours",
            "Break",
            "Overtime",
            "Status",
            "Late By",
            "Early Exit",
            "Leave Type",
            "Source",
            "Remarks",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["employee_id"],
                r["employee_name"],
                r["department"],
                r["designation"],
                r["date"].isoformat(),
                r["check_in"],
                r["check_out"],
                r["working_hours"],
                r["break_time"],
                r["overtime"],
                r["status_display"],
                r["late_by"],
                r["early_exit"],
                r["leave_type"],
                r["attendance_source"],
                r["remarks"],
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="attendance_report.csv"'
    return response


_EXPORT_HEADERS = [
    "Employee ID", "Employee Name", "Department", "Designation", "Date",
    "Check-in", "Check-out", "Working Hours", "Break", "Overtime", "Status",
    "Late By", "Early Exit", "Leave Type", "Source", "Remarks",
]


def _export_row_values(r: dict) -> list:
    return [
        r["employee_id"], r["employee_name"], r["department"], r["designation"],
        r["date"].isoformat(), r["check_in"], r["check_out"], r["working_hours"],
        r["break_time"], r["overtime"], r["status_display"], r["late_by"],
        r["early_exit"], r["leave_type"], r["attendance_source"], r["remarks"],
    ]


def export_rows_xlsx(rows: list[dict]) -> HttpResponse:
    """Real .xlsx export via openpyxl (same columns as the CSV export)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(_EXPORT_HEADERS)
    for r in rows:
        ws.append(_export_row_values(r))
    buffer = io.BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="attendance_report.xlsx"'
    return response


def get_analytics_context(manager: User, request, use_cache: bool = True) -> dict:
    from apps.organizations.fy_utils import get_selected_fy
    filters = AnalyticsFilters.from_request(request, fy=get_selected_fy(request))
    cache_key = f"att_analytics:{manager.organization_id}:{manager.pk}:{filters.cache_key_suffix()}"
    cached = None
    if use_cache and request.method == "GET" and not request.GET.get("export"):
        cached = cache.get(cache_key)

    if cached:
        ctx = dict(cached)
    else:
        summary = build_summary_cards(manager, filters)
        charts = build_chart_data(manager, filters)
        insights = build_insights(manager, filters)
        options = filter_options(manager)
        period_kpis = build_period_kpis(manager, filters)
        trend = build_trend(manager, filters)
        ctx = {
            "filters": filters,
            "summary": summary,
            "period_kpis": period_kpis,
            "charts_json": json.dumps(charts),
            "trend_json": json.dumps(trend),
            "insights": insights,
            "filter_options": options,
            "organization": manager.organization,
            "is_admin": manager.role == User.Role.ADMIN,
        }
        if use_cache:
            cache.set(cache_key, ctx, 60)

    ctx["table_rows"] = build_table_rows(manager, filters)
    ctx.setdefault("filters", filters)
    return ctx
