"""Digital Attendance Register — register-book style monthly grid builder.

Produces a per-employee × per-day status grid for ADMIN/HR, reusing the
existing attendance, weekend-policy and holiday infrastructure.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.attendance.work_calendar import (
    get_holidays_between,
    get_org_off_weekdays,
    get_shift_off_weekdays,
)
from apps.organizations.models import Department, Organization

from .attendance_utils import analyze_lateness, get_effective_shift

# Register status codes
CODE_PRESENT = "P"
CODE_ABSENT = "A"
CODE_LEAVE = "L"
CODE_HALF = "HD"
CODE_WFH = "WFH"
CODE_HOLIDAY = "H"
CODE_WEEKEND = "WO"
CODE_LATE = "LT"
CODE_BLANK = ""  # not marked, working day

STATUS_META = {
    CODE_PRESENT: {"label": "Present", "cls": "dr-present"},
    CODE_ABSENT: {"label": "Absent", "cls": "dr-absent"},
    CODE_LEAVE: {"label": "Leave", "cls": "dr-leave"},
    CODE_HALF: {"label": "Half day", "cls": "dr-half"},
    CODE_WFH: {"label": "Work from home", "cls": "dr-wfh"},
    CODE_HOLIDAY: {"label": "Holiday", "cls": "dr-holiday"},
    CODE_WEEKEND: {"label": "Weekly off", "cls": "dr-weekend"},
    CODE_LATE: {"label": "Late", "cls": "dr-late"},
    CODE_BLANK: {"label": "Not marked", "cls": "dr-blank"},
}

LEGEND = [
    (CODE_PRESENT, "Present"),
    (CODE_LATE, "Late"),
    (CODE_HALF, "Half day"),
    (CODE_WFH, "WFH"),
    (CODE_LEAVE, "Leave"),
    (CODE_ABSENT, "Absent"),
    (CODE_HOLIDAY, "Holiday"),
    (CODE_WEEKEND, "Weekly off"),
]


@dataclass
class RegisterFilters:
    start: date
    end: date
    department_id: str = ""
    employee_id: str = ""
    search: str = ""

    @classmethod
    def from_request(cls, request) -> "RegisterFilters":
        today = timezone.localdate()
        g = request.GET

        # Custom range takes priority if both provided
        start_raw = g.get("start_date") or ""
        end_raw = g.get("end_date") or ""
        if start_raw and end_raw:
            start = _parse_date(start_raw) or today.replace(day=1)
            end = _parse_date(end_raw) or _month_end(start)
        else:
            try:
                month = int(g.get("month") or today.month)
                year = int(g.get("year") or today.year)
            except (TypeError, ValueError):
                month, year = today.month, today.year
            month = min(max(month, 1), 12)
            start = date(year, month, 1)
            end = _month_end(start)

        # Cap range to a sane maximum (62 days) to protect rendering
        if (end - start).days > 62:
            end = start + timedelta(days=62)

        return cls(
            start=start,
            end=end,
            department_id=g.get("department") or g.get("department_id") or "",
            employee_id=g.get("employee") or g.get("employee_id") or "",
            search=(g.get("search") or "").strip(),
        )


def _parse_date(raw: str) -> date | None:
    try:
        y, m, d = (int(x) for x in raw.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def _month_end(d: date) -> date:
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)


def _daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _resolve_team(manager: User, filters: RegisterFilters):
    qs = attendance_team_for(manager).select_related("work_shift", "department")
    if filters.department_id:
        qs = qs.filter(department_id=filters.department_id)
    if filters.employee_id:
        qs = qs.filter(pk=filters.employee_id)
    if filters.search:
        from django.db.models import Q

        term = filters.search
        qs = qs.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(username__icontains=term)
            | Q(employee_id__icontains=term)
        )
    return qs.order_by("first_name", "last_name", "username")


def build_register(manager: User, filters: RegisterFilters, *, page: int = 1, page_size: int = 100) -> dict:
    org: Organization = manager.organization
    start, end = filters.start, filters.end
    today = timezone.localdate()

    days = list(_daterange(start, end))
    day_headers = [
        {
            "date": d,
            "day": d.day,
            "weekday": d.strftime("%a"),
            "is_today": d == today,
            "iso": d.isoformat(),
        }
        for d in days
    ]

    team_qs = _resolve_team(manager, filters)
    total_employees = team_qs.count()

    # Server-side pagination
    page = max(1, page)
    offset = (page - 1) * page_size
    team = list(team_qs[offset : offset + page_size])
    team_ids = [u.pk for u in team]

    # Holidays in range (set of dates)
    holidays = get_holidays_between(org, start, end) if org else set()

    # Weekend weekdays per date (org-level). Shift-based handled per-user below.
    org_off_by_date: dict[date, set[int]] = {}
    if org:
        for d in days:
            org_off_by_date[d] = get_org_off_weekdays(org, d)
    shift_based = bool(
        org and org.weekend_policy == Organization.WeekendPolicy.SHIFT_BASED
    )

    # Bulk-load attendance records for the team in range
    records = AttendanceRecord.objects.filter(
        user_id__in=team_ids, date__gte=start, date__lte=end
    )
    rec_map: dict[tuple, AttendanceRecord] = {}
    for rec in records:
        rec_map[(rec.user_id, rec.date)] = rec

    rows = []
    for member in team:
        shift = get_effective_shift(member)
        # per-user weekend resolution (cached by shift for shift-based policy)
        user_off_cache: dict[date, set[int]] = {}
        if shift_based:
            for d in days:
                off = get_shift_off_weekdays(member, d)
                user_off_cache[d] = off or {5, 6}

        cells = []
        present = absent = leave = half = wfh = late = holiday_ct = weekend_ct = 0

        for d in days:
            rec = rec_map.get((member.pk, d))
            is_weekend = (
                d.weekday() in user_off_cache.get(d, set())
                if shift_based
                else d.weekday() in org_off_by_date.get(d, set())
            )
            is_holiday = d in holidays

            code = CODE_BLANK
            tip = None

            if rec and rec.status == AttendanceRecord.Status.PRESENT:
                lateness = analyze_lateness(rec, shift, d)
                code = CODE_LATE if lateness.get("is_late") else CODE_PRESENT
                present += 1
                if code == CODE_LATE:
                    late += 1
            elif rec and rec.status == AttendanceRecord.Status.HALF_DAY:
                code = CODE_HALF
                half += 1
            elif rec and rec.status == AttendanceRecord.Status.WFH:
                code = CODE_WFH
                wfh += 1
            elif rec and rec.status == AttendanceRecord.Status.LEAVE:
                code = CODE_LEAVE
                leave += 1
            elif rec and rec.status == AttendanceRecord.Status.ABSENT:
                code = CODE_ABSENT
                absent += 1
            elif is_holiday:
                code = CODE_HOLIDAY
                holiday_ct += 1
            elif is_weekend:
                code = CODE_WEEKEND
                weekend_ct += 1
            else:
                # no record on a working day
                code = CODE_BLANK

            if rec:
                tip = {
                    "in": _fmt_time(rec.check_in),
                    "out": _fmt_time(rec.check_out),
                    "hours": _fmt_hours(rec),
                }

            cells.append(
                {
                    "code": code,
                    "cls": STATUS_META[code]["cls"],
                    "label": STATUS_META[code]["label"],
                    "iso": d.isoformat(),
                    "is_today": d == today,
                    "tip": tip,
                }
            )

        rows.append(
            {
                "member": member,
                "employee_id": member.employee_id or "—",
                "name": member.display_name,
                "department": member.department.name if member.department_id else "—",
                "cells": cells,
                "present_days": present,
                "absent_days": absent,
                "leave_days": leave,
                "half_days": half,
                "wfh_days": wfh,
                "late_days": late,
            }
        )

    total_pages = max(1, (total_employees + page_size - 1) // page_size)

    return {
        "day_headers": day_headers,
        "rows": rows,
        "legend": LEGEND,
        "total_employees": total_employees,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "showing_from": offset + 1 if team else 0,
        "showing_to": offset + len(team),
        "start": start,
        "end": end,
        "num_days": len(days),
    }


def build_summary_cards(manager: User, filters: RegisterFilters) -> dict:
    org = manager.organization
    today = timezone.localdate()
    team_qs = _resolve_team(manager, filters)
    total = team_qs.count()
    team_ids = list(team_qs.values_list("pk", flat=True))

    todays = AttendanceRecord.objects.filter(user_id__in=team_ids, date=today)
    present = todays.filter(
        status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.WFH]
    ).count()
    absent = todays.filter(status=AttendanceRecord.Status.ABSENT).count()
    on_leave = todays.filter(status=AttendanceRecord.Status.LEAVE).count()

    # Attendance % over the selected range (present+wfh+half / marked working slots)
    range_recs = AttendanceRecord.objects.filter(
        user_id__in=team_ids, date__gte=filters.start, date__lte=filters.end
    )
    marked = range_recs.count()
    good = range_recs.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.WFH,
            AttendanceRecord.Status.HALF_DAY,
        ]
    ).count()
    pct = round(good / marked * 100, 1) if marked else 0.0

    return {
        "total_employees": total,
        "present_today": present,
        "absent_today": absent,
        "on_leave_today": on_leave,
        "attendance_pct": pct,
    }


def register_filter_options(manager: User) -> dict:
    org = manager.organization
    team = attendance_team_for(manager)
    departments = (
        Department.objects.filter(organization=org, is_active=True).order_by(
            "sort_order", "name"
        )
        if org
        else Department.objects.none()
    )
    return {
        "departments": list(departments),
        "employees": list(team.order_by("first_name", "last_name")),
        "dept_label": org.department_label if org else "Department",
        "dept_label_plural": org.department_label_plural if org else "Departments",
    }


def _fmt_time(dt) -> str:
    if not dt:
        return "—"
    return timezone.localtime(dt).strftime("%I:%M %p").lstrip("0")


def _fmt_hours(rec: AttendanceRecord) -> str:
    if not rec.check_in or not rec.check_out:
        return "—"
    mins = int((rec.check_out - rec.check_in).total_seconds() // 60) - (rec.break_minutes or 0)
    if mins <= 0:
        return "—"
    h, m = divmod(mins, 60)
    return f"{h:02d}h {m:02d}m"


def build_register_json(manager: User, filters: RegisterFilters, page: int = 1) -> dict:
    """API-shaped payload matching the spec."""
    data = build_register(manager, filters, page=page)
    employees = []
    for row in data["rows"]:
        attendance = {}
        for cell, hdr in zip(row["cells"], data["day_headers"]):
            attendance[str(hdr["day"])] = cell["code"] or "-"
        employees.append(
            {
                "employee_id": row["employee_id"],
                "employee_name": row["name"],
                "department": row["department"],
                "attendance": attendance,
                "present_days": row["present_days"],
                "absent_days": row["absent_days"],
                "leave_days": row["leave_days"],
                "half_days": row["half_days"],
                "wfh_days": row["wfh_days"],
                "late_days": row["late_days"],
            }
        )
    return {
        "start_date": filters.start.isoformat(),
        "end_date": filters.end.isoformat(),
        "days": [h["day"] for h in data["day_headers"]],
        "employees": employees,
        "pagination": {
            "page": data["page"],
            "page_size": data["page_size"],
            "total_pages": data["total_pages"],
            "total_employees": data["total_employees"],
        },
    }


def export_register_csv(manager: User, filters: RegisterFilters):
    import csv
    from django.http import HttpResponse

    data = build_register(manager, filters, page=1, page_size=100000)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="attendance_register_{filters.start}_{filters.end}.csv"'
    )
    writer = csv.writer(response)
    header = ["Employee ID", "Employee Name", "Department"]
    header += [f"{h['day']} ({h['weekday']})" for h in data["day_headers"]]
    header += ["Present", "Absent", "Leave", "Half", "WFH", "Late"]
    writer.writerow(header)
    for row in data["rows"]:
        line = [row["employee_id"], row["name"], row["department"]]
        line += [c["code"] or "-" for c in row["cells"]]
        line += [
            row["present_days"],
            row["absent_days"],
            row["leave_days"],
            row["half_days"],
            row["wfh_days"],
            row["late_days"],
        ]
        writer.writerow(line)
    return response
