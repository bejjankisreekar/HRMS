from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, BreakRecord, WorkShift
from apps.organizations.models import Organization


def parse_attendance_date(raw: str | None):
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            pass
    return timezone.localdate()


def combine_date_and_time(on_date, time_str: str | None):
    if time_str:
        try:
            parsed = datetime.strptime(time_str.strip(), "%H:%M").time()
            naive = datetime.combine(on_date, parsed)
            return timezone.make_aware(naive, timezone.get_current_timezone())
        except ValueError:
            pass
    return timezone.now()


def format_time_display(dt) -> str:
    if not dt:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%I:%M %p").lstrip("0")


def ensure_default_shift(organization: Organization) -> WorkShift:
    existing = WorkShift.objects.filter(organization=organization, is_default=True).first()
    if existing:
        return existing
    return WorkShift.objects.create(
        organization=organization,
        name="General Shift",
        is_default=True,
        grace_minutes=15,
    )


def get_effective_shift(user: User) -> WorkShift | None:
    if not user.organization_id:
        return None
    if user.work_shift_id:
        return user.work_shift
    return WorkShift.objects.filter(organization_id=user.organization_id, is_default=True).first()


def compute_working_hours(record: AttendanceRecord | None) -> str:
    """Raw elapsed time (check_out − check_in), no break deduction."""
    if not record or not record.check_in or not record.check_out:
        return "—"
    delta = record.check_out - record.check_in
    if delta.total_seconds() < 0:
        return "—"
    total_mins = int(delta.total_seconds() // 60)
    hours, mins = divmod(total_mins, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def compute_net_hours(record: AttendanceRecord | None, break_minutes: int = 0) -> str:
    """Net working time = raw elapsed − break minutes."""
    if not record or not record.check_in or not record.check_out:
        return "—"
    delta = record.check_out - record.check_in
    if delta.total_seconds() < 0:
        return "—"
    net_mins = max(0, int(delta.total_seconds() // 60) - break_minutes)
    if net_mins == 0:
        return "0m"
    hours, mins = divmod(net_mins, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def analyze_lateness(record: AttendanceRecord | None, shift: WorkShift | None, on_date) -> dict:
    """Return late flags: on_time, in_grace, is_late, late_minutes, label."""
    result = {
        "on_time": None,
        "in_grace": False,
        "is_late": False,
        "late_minutes": 0,
        "label": "—",
        "shift_start_display": "",
    }
    if not record or not record.check_in or not shift:
        return result

    local_in = timezone.localtime(record.check_in)
    shift_start = timezone.make_aware(
        datetime.combine(on_date, shift.start_time),
        timezone.get_current_timezone(),
    )
    result["shift_start_display"] = shift.start_time.strftime("%I:%M %p").lstrip("0")

    if local_in <= shift_start:
        result["on_time"] = True
        result["label"] = "On time"
        return result

    late_delta = local_in - shift_start
    late_mins = int(late_delta.total_seconds() // 60)
    result["late_minutes"] = late_mins
    grace_end = shift_start + timedelta(minutes=shift.grace_minutes)

    if local_in <= grace_end:
        result["in_grace"] = True
        result["label"] = f"Grace +{late_mins}m"
    else:
        result["is_late"] = True
        over = late_mins - shift.grace_minutes
        result["label"] = f"Late +{late_mins}m"

    return result


def shift_timing_info(shift: WorkShift | None) -> dict:
    if not shift:
        return {"has_shift": False}
    start = shift.start_time.strftime("%I:%M %p").lstrip("0")
    end = shift.end_time.strftime("%I:%M %p").lstrip("0")
    grace_end_time = (
        datetime.combine(datetime.min.date(), shift.start_time) + timedelta(minutes=shift.grace_minutes)
    ).time()
    grace_until = grace_end_time.strftime("%I:%M %p").lstrip("0")
    return {
        "has_shift": True,
        "name": shift.name,
        "start": start,
        "end": end,
        "range": f"{start} – {end}",
        "grace_minutes": shift.grace_minutes,
        "grace_label": f"{shift.grace_minutes} min late buffer",
        "grace_until": grace_until,
        "grace_detail": f"Until {grace_until} ({shift.grace_minutes}m after {start})",
    }


def enrich_attendance_row(
    member: User,
    record: AttendanceRecord | None,
    on_date,
    breaks: list | None = None,
) -> dict:
    shift = get_effective_shift(member)
    lateness = analyze_lateness(record, shift, on_date)
    timing = shift_timing_info(shift)
    login_time  = format_time_display(record.check_in)  if record and record.check_in  else "—"
    logout_time = format_time_display(record.check_out) if record and record.check_out else "—"

    # Break summary
    break_list = breaks or []
    total_break_mins = sum(b.duration_minutes or 0 for b in break_list)
    has_ongoing = any(b.is_ongoing for b in break_list)

    actual_hours = compute_working_hours(record)
    net_hours    = compute_net_hours(record, total_break_mins)

    return {
        "member": member,
        "record": record,
        "shift": shift,
        "shift_timing": timing,
        "working_hours": actual_hours,   # kept for backward compat
        "actual_hours": actual_hours,
        "net_hours": net_hours,
        "login_time": login_time,
        "logout_time": logout_time,
        "lateness": lateness,
        "is_marked": bool(record and (record.check_in or record.check_out or record.status)),
        "breaks": break_list,
        "total_break_mins": total_break_mins,
        "total_break_display": format_total_minutes(total_break_mins) if total_break_mins else "—",
        "has_ongoing_break": has_ongoing,
        # pre-formatted time values for quick time pickers
        "check_in_hhmm":  (timezone.localtime(record.check_in).strftime("%H:%M")
                           if record and record.check_in else ""),
        "check_out_hhmm": (timezone.localtime(record.check_out).strftime("%H:%M")
                           if record and record.check_out else ""),
    }


def sum_team_working_minutes(team_rows: list) -> int:
    total = 0
    for row in team_rows:
        record = row.get("record")
        if record and record.check_in and record.check_out:
            delta = record.check_out - record.check_in
            if delta.total_seconds() > 0:
                total += int(delta.total_seconds() // 60)
    return total


def attendance_mark_team_for(user: User):
    """Users listed on mark-attendance (HR self excluded unless org setting allows it)."""
    qs = attendance_team_for(user)
    org = user.organization
    if (
        user.role == User.Role.HR
        and user.organization_id
        and org
        and not org.hr_self_in_mark_attendance
    ):
        qs = qs.exclude(pk=user.pk)
    return qs


def _load_breaks_for_records(records: dict) -> dict:
    """Batch-load BreakRecord objects for a dict of {user_id: AttendanceRecord}.
    Returns {attendance_record_id: [BreakRecord, ...]}."""
    record_ids = [r.pk for r in records.values()]
    if not record_ids:
        return {}
    breaks_map: dict = {}
    for brk in BreakRecord.objects.filter(
        attendance_record_id__in=record_ids
    ).select_related("marked_by"):
        breaks_map.setdefault(brk.attendance_record_id, []).append(brk)
    return breaks_map


def get_visible_attendance_rows(viewer: User, on_date):
    """Read-only team rows for managers (direct reportees)."""
    from apps.accounts.hierarchy import attendance_visible_team_for

    team = list(
        attendance_visible_team_for(viewer).select_related("work_shift", "organization")
    )
    if not team:
        return []
    ensure_default_shift(viewer.organization)
    records = {
        r.user_id: r
        for r in AttendanceRecord.objects.filter(user__in=team, date=on_date)
    }
    breaks_map = _load_breaks_for_records(records)
    return [
        enrich_attendance_row(
            m,
            records.get(m.pk),
            on_date,
            breaks=breaks_map.get(records[m.pk].pk, []) if m.pk in records else [],
        )
        for m in team
    ]


def get_team_attendance_rows(manager: User, on_date):
    team = list(
        attendance_mark_team_for(manager).select_related("work_shift", "organization")
    )
    if not team:
        return []
    ensure_default_shift(manager.organization)
    records = {
        r.user_id: r
        for r in AttendanceRecord.objects.filter(user__in=team, date=on_date)
    }
    breaks_map = _load_breaks_for_records(records)
    return [
        enrich_attendance_row(
            m,
            records.get(m.pk),
            on_date,
            breaks=breaks_map.get(records[m.pk].pk, []) if m.pk in records else [],
        )
        for m in team
    ]


def build_shift_attendance_filters(team_rows: list) -> list[dict]:
    """Build shift tabs for mark-attendance header (one entry per effective shift)."""
    groups: dict[str, dict] = {}
    for row in team_rows:
        shift = row.get("shift")
        timing = row.get("shift_timing") or {}
        key = str(shift.pk) if shift else "none"
        if key not in groups:
            groups[key] = {
                "id": str(shift.pk) if shift else "none",
                "name": timing.get("name") or (shift.name if shift else "No shift"),
                "range": timing.get("range", ""),
                "grace_minutes": timing.get("grace_minutes", 0),
                "grace_until": timing.get("grace_until", ""),
                "grace_label": timing.get("grace_label", ""),
                "has_shift": bool(timing.get("has_shift")),
                "count": 0,
            }
        groups[key]["count"] += 1
    result = list(groups.values())
    result.sort(key=lambda item: item["name"].lower())
    return result


def filter_team_rows_by_shift(team_rows: list, shift_id: str | None) -> list:
    if not shift_id or shift_id == "all":
        return team_rows
    if shift_id == "none":
        return [row for row in team_rows if not row.get("shift")]
    return [
        row
        for row in team_rows
        if row.get("shift") and str(row["shift"].pk) == shift_id
    ]


def get_active_shift_meta(shift_filters: list[dict], selected_shift: str) -> dict | None:
    if not selected_shift or selected_shift == "all":
        return None
    for item in shift_filters:
        if item["id"] == selected_shift:
            return item
    return None


def summarize_team_rows(team_rows: list) -> dict:
    summary = {
        "total": len(team_rows),
        "present": 0,
        "absent": 0,
        "leave": 0,
        "other": 0,
        "unmarked": 0,
        "late": 0,
        "grace": 0,
    }
    for row in team_rows:
        record = row.get("record")
        lateness = row.get("lateness", {})
        if lateness.get("is_late"):
            summary["late"] += 1
        elif lateness.get("in_grace"):
            summary["grace"] += 1
        if not record:
            summary["unmarked"] += 1
            continue
        if record.status == AttendanceRecord.Status.PRESENT:
            summary["present"] += 1
        elif record.status == AttendanceRecord.Status.ABSENT:
            summary["absent"] += 1
        elif record.status == AttendanceRecord.Status.LEAVE:
            summary["leave"] += 1
        else:
            summary["other"] += 1
    return summary


def resolve_attendance_target(manager: User, user_id: str) -> User | None:
    if not user_id:
        return None
    try:
        return attendance_mark_team_for(manager).get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        return None


def get_attendance_report_queryset(manager: User, date_from, date_to, user_id: str | None = None):
    team_qs = attendance_team_for(manager)
    if user_id:
        team_qs = team_qs.filter(pk=user_id)
    team_ids = list(team_qs.values_list("pk", flat=True))
    records = (
        AttendanceRecord.objects.filter(
            user_id__in=team_ids,
            date__gte=date_from,
            date__lte=date_to,
        )
        .select_related("user", "user__work_shift")
        .order_by("-date", "user__first_name")
    )
    rows = []
    for rec in records:
        shift = get_effective_shift(rec.user)
        lateness = analyze_lateness(rec, shift, rec.date)
        rows.append(
            {
                "record": rec,
                "member": rec.user,
                "shift": shift,
                "working_hours": compute_working_hours(rec),
                "lateness": lateness,
            }
        )
    return rows


def format_total_minutes(total_minutes: int) -> str:
    if total_minutes <= 0:
        return "0h"
    hours, mins = divmod(total_minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def summarize_report_rows(report_rows: list) -> dict:
    """Aggregate counts for attendance report filters."""
    summary = {
        "total_records": len(report_rows),
        "present": 0,
        "absent": 0,
        "leave": 0,
        "half_day": 0,
        "wfh": 0,
        "other": 0,
        "on_time": 0,
        "grace": 0,
        "late": 0,
        "punctuality_na": 0,
        "total_minutes": 0,
    }
    for row in report_rows:
        record = row.get("record")
        lateness = row.get("lateness") or {}

        if lateness.get("is_late"):
            summary["late"] += 1
        elif lateness.get("in_grace"):
            summary["grace"] += 1
        elif lateness.get("on_time"):
            summary["on_time"] += 1
        else:
            summary["punctuality_na"] += 1

        if not record:
            continue

        if record.status == AttendanceRecord.Status.PRESENT:
            summary["present"] += 1
        elif record.status == AttendanceRecord.Status.ABSENT:
            summary["absent"] += 1
        elif record.status == AttendanceRecord.Status.LEAVE:
            summary["leave"] += 1
        elif record.status == AttendanceRecord.Status.HALF_DAY:
            summary["half_day"] += 1
        elif record.status == AttendanceRecord.Status.WFH:
            summary["wfh"] += 1
        else:
            summary["other"] += 1

        if record.check_in and record.check_out:
            delta = record.check_out - record.check_in
            if delta.total_seconds() > 0:
                summary["total_minutes"] += int(delta.total_seconds() // 60)

    summary["total_hours_display"] = format_total_minutes(summary["total_minutes"])
    summary["punctuality_total"] = summary["on_time"] + summary["grace"] + summary["late"]
    return summary


def apply_team_attendance_action(
    manager: User,
    target: User,
    on_date,
    action: str,
    status: str = "",
    check_in_time: str | None = None,
    check_out_time: str | None = None,
) -> str:
    record, _ = AttendanceRecord.objects.get_or_create(
        user=target,
        date=on_date,
        defaults={"status": AttendanceRecord.Status.PRESENT},
    )

    if action in ("check_in", "set_check_in"):
        at = combine_date_and_time(on_date, check_in_time)
        if action == "check_in" and record.check_in:
            return f"{target.choice_label} already checked in."
        record.check_in = at
        record.status = AttendanceRecord.Status.PRESENT
        record.save(update_fields=["check_in", "status", "updated_at"])
        return f"In time for {target.choice_label}: {format_time_display(at)}."

    if action in ("check_out", "set_check_out"):
        if not record.check_in:
            return f"Set check-in time for {target.choice_label} first."
        at = combine_date_and_time(on_date, check_out_time)
        if record.check_in and at < record.check_in:
            return "Check-out time must be after check-in time."
        if action == "check_out" and record.check_out:
            return f"{target.choice_label} already checked out."
        record.check_out = at
        record.save(update_fields=["check_out", "updated_at"])
        return f"Out time for {target.choice_label}: {format_time_display(at)}."

    if action == "set_times":
        update_fields = ["updated_at"]
        if check_in_time:
            record.check_in = combine_date_and_time(on_date, check_in_time)
            record.status = AttendanceRecord.Status.PRESENT
            update_fields.extend(["check_in", "status"])
        if check_out_time:
            if not record.check_in:
                return f"Set check-in time for {target.choice_label} first."
            out_at = combine_date_and_time(on_date, check_out_time)
            if record.check_in and out_at < record.check_in:
                return "Check-out time must be after check-in time."
            record.check_out = out_at
            update_fields.append("check_out")
        if len(update_fields) == 1:
            return "Enter at least one time (in or out)."
        record.save(update_fields=update_fields)
        parts = []
        if record.check_in:
            parts.append(f"In {format_time_display(record.check_in)}")
        if record.check_out:
            parts.append(f"Out {format_time_display(record.check_out)}")
        return f"Saved {target.choice_label}: {', '.join(parts)}."

    if action == "set_status":
        if status not in AttendanceRecord.Status.values:
            return "Invalid status."
        record.status = status
        update_fields = ["status", "updated_at"]
        if status in (
            AttendanceRecord.Status.ABSENT,
            AttendanceRecord.Status.LEAVE,
            AttendanceRecord.Status.HOLIDAY,
            AttendanceRecord.Status.WEEKEND_OFF,
        ):
            record.check_in = None
            record.check_out = None
            update_fields.extend(["check_in", "check_out"])
        record.save(update_fields=update_fields)
        return f"Marked {target.choice_label} as {record.get_status_display()}."

    return "Invalid action."


def _sync_break_minutes(record: AttendanceRecord) -> None:
    """Recalculate and save break_minutes on the AttendanceRecord from BreakRecord rows."""
    total = sum(
        b.duration_minutes or 0
        for b in BreakRecord.objects.filter(attendance_record=record)
        if b.duration_minutes is not None
    )
    if record.break_minutes != total:
        record.break_minutes = total
        record.save(update_fields=["break_minutes", "updated_at"])


def apply_break_action(
    manager: User,
    target: User,
    on_date,
    action: str,
    break_type: str = "OTHER",
    break_start: str | None = None,
    break_end: str | None = None,
    break_note: str = "",
    break_id: str | None = None,
    end_time_str: str | None = None,
) -> str:
    """Add, end or delete a BreakRecord for a team member."""

    if action == "add_break":
        record = AttendanceRecord.objects.filter(user=target, date=on_date).first()
        if not record:
            return f"Mark attendance for {target.choice_label} first before logging a break."
        if break_type not in BreakRecord.BreakType.values:
            break_type = BreakRecord.BreakType.OTHER
        start_dt = combine_date_and_time(on_date, break_start) if break_start else timezone.now()
        end_dt = combine_date_and_time(on_date, break_end) if break_end else None
        if end_dt and end_dt <= start_dt:
            return "Break end time must be after start time."
        BreakRecord.objects.create(
            attendance_record=record,
            break_type=break_type,
            start_time=start_dt,
            end_time=end_dt,
            note=break_note,
            marked_by=manager,
        )
        _sync_break_minutes(record)
        label = BreakRecord.BreakType(break_type).label
        return f"{label} added for {target.choice_label}."

    if action in ("end_break", "edit_break", "delete_break"):
        if not break_id:
            return "Break ID missing."
        try:
            brk = BreakRecord.objects.select_related("attendance_record").get(
                pk=break_id,
                attendance_record__user=target,
                attendance_record__date=on_date,
            )
        except BreakRecord.DoesNotExist:
            return "Break not found."

        if action == "delete_break":
            record = brk.attendance_record
            brk.delete()
            _sync_break_minutes(record)
            return f"Break removed for {target.choice_label}."

        if action == "end_break":
            if brk.end_time:
                return "Break already ended."
            end_dt = combine_date_and_time(on_date, end_time_str) if end_time_str else timezone.now()
            if end_dt <= brk.start_time:
                return "End time must be after start time."
            brk.end_time = end_dt
            brk.save(update_fields=["end_time"])
            _sync_break_minutes(brk.attendance_record)
            return f"Break ended for {target.choice_label}."

        if action == "edit_break":
            update_fields: list[str] = []
            if break_type and break_type in BreakRecord.BreakType.values:
                brk.break_type = break_type
                update_fields.append("break_type")
            if break_start:
                start_dt = combine_date_and_time(on_date, break_start)
                brk.start_time = start_dt
                update_fields.append("start_time")
            if break_end:
                end_dt = combine_date_and_time(on_date, break_end)
                if end_dt <= brk.start_time:
                    return "End time must be after start time."
                brk.end_time = end_dt
                update_fields.append("end_time")
            brk.note = break_note
            update_fields.append("note")
            if update_fields:
                brk.save(update_fields=update_fields)
                _sync_break_minutes(brk.attendance_record)
            return f"Break updated for {target.choice_label}."

    return "Invalid break action."


def get_shift_assignment_roster(organization: Organization) -> list[dict]:
    """Staff list with explicit or default shift for the shifts admin page."""
    default_shift = WorkShift.objects.filter(organization=organization, is_default=True).first()
    staff = (
        User.objects.filter(
            organization=organization,
            is_active=True,
            role__in=[User.Role.HR, User.Role.EMPLOYEE],
        )
        .select_related("work_shift")
        .order_by("first_name", "last_name", "username")
    )
    roster = []
    for user in staff:
        if user.work_shift_id:
            roster.append(
                {
                    "user": user,
                    "shift": user.work_shift,
                    "shift_name": user.work_shift.name,
                    "shift_range": user.work_shift.time_range_display,
                    "uses_default": False,
                }
            )
        else:
            roster.append(
                {
                    "user": user,
                    "shift": default_shift,
                    "shift_name": default_shift.name if default_shift else "—",
                    "shift_range": default_shift.time_range_display if default_shift else "",
                    "uses_default": True,
                }
            )
    return roster


def set_default_shift(organization: Organization, shift: WorkShift) -> None:
    """Make this shift the org default (clears any other default first)."""
    WorkShift.objects.filter(organization=organization, is_default=True).exclude(pk=shift.pk).update(
        is_default=False
    )
    if not shift.is_default:
        shift.is_default = True
        shift.save(update_fields=["is_default"])
