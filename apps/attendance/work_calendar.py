"""Organization working-day calendar: weekends, holidays, and shift-based off days."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q

from apps.accounts.models import User
from apps.leaves.models import Holiday
from apps.organizations.models import Organization

WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DEFAULT_ROTATING_PATTERNS = [
    {"off_days": [5, 6]},
    {"off_days": [6]},
]


def parse_weekday_csv(raw: str) -> set[int]:
    result: set[int] = set()
    if not raw:
        return result
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 0 <= n <= 6:
                result.add(n)
    return result


def format_weekday_csv(days: set[int] | list[int]) -> str:
    return ",".join(str(d) for d in sorted(days))


def weekday_labels(days: set[int] | list[int]) -> str:
    return ", ".join(WEEKDAY_LABELS[d] for d in sorted(days) if 0 <= d <= 6)


def _patterns(org: Organization) -> list[dict]:
    patterns = org.rotating_off_patterns or []
    return patterns if patterns else list(DEFAULT_ROTATING_PATTERNS)


def _rotating_weekly_off(org: Organization, on_date: date) -> set[int]:
    patterns = _patterns(org)
    anchor = org.rotating_off_anchor or date(2024, 1, 1)
    weeks = max((on_date - anchor).days // 7, 0)
    step = patterns[weeks % len(patterns)]
    return set(step.get("off_days") or [6])


def _rotating_monthly_off(org: Organization, on_date: date) -> set[int]:
    patterns = _patterns(org)
    week_idx = min((on_date.day - 1) // 7, len(patterns) - 1)
    step = patterns[week_idx]
    return set(step.get("off_days") or [6])


def get_org_off_weekdays(org: Organization, on_date: date) -> set[int]:
    """Weekday indices (0=Mon) that are off for the org on a given date."""
    policy = org.weekend_policy or Organization.WeekendPolicy.SAT_SUN
    if policy == Organization.WeekendPolicy.SAT_SUN:
        return {5, 6}
    if policy == Organization.WeekendPolicy.SUN_ONLY:
        return {6}
    if policy == Organization.WeekendPolicy.CUSTOM:
        days = parse_weekday_csv(org.weekend_custom_days)
        return days if days else {6}
    if policy == Organization.WeekendPolicy.ROTATING_WEEKLY:
        return _rotating_weekly_off(org, on_date)
    if policy == Organization.WeekendPolicy.ROTATING_MONTHLY:
        return _rotating_monthly_off(org, on_date)
    return set()


def get_shift_off_weekdays(user: User, on_date: date) -> set[int]:
    from apps.shifts.services import effective_shift_for_date

    shift = effective_shift_for_date(user, on_date)
    if shift and shift.weekly_off_days:
        return parse_weekday_csv(shift.weekly_off_days)
    return set()


def is_weekend(org: Organization, on_date: date, user: User | None = None) -> bool:
    policy = org.weekend_policy or Organization.WeekendPolicy.SAT_SUN
    if policy == Organization.WeekendPolicy.SHIFT_BASED and user:
        off = get_shift_off_weekdays(user, on_date)
        if off:
            return on_date.weekday() in off
        return on_date.weekday() >= 5
    off_days = get_org_off_weekdays(org, on_date)
    return on_date.weekday() in off_days


def get_holidays_between(
    organization: Organization,
    start: date,
    end: date,
    branch: str = "",
    *,
    include_optional: bool | None = None,
) -> set[date]:
    qs = Holiday.objects.filter(organization=organization, date__gte=start, date__lte=end)
    if branch:
        qs = qs.filter(Q(branch="") | Q(branch__iexact=branch))
    if include_optional is None:
        include_optional = not organization.holidays_exclude_optional
    if not include_optional:
        qs = qs.filter(is_optional=False)
    return set(qs.values_list("date", flat=True))


def is_holiday(
    org: Organization,
    on_date: date,
    branch: str = "",
    *,
    include_optional: bool | None = None,
) -> bool:
    return on_date in get_holidays_between(
        org,
        on_date,
        on_date,
        branch,
        include_optional=include_optional,
    )


def is_working_day(
    org: Organization,
    on_date: date,
    *,
    user: User | None = None,
    branch: str = "",
) -> bool:
    if is_holiday(org, on_date, branch):
        return False
    return not is_weekend(org, on_date, user)


def count_working_days(
    org: Organization,
    start: date,
    end: date,
    *,
    user: User | None = None,
    branch: str = "",
) -> int:
    if end < start:
        return 0
    holidays = get_holidays_between(org, start, end, branch)
    count = 0
    current = start
    while current <= end:
        if current not in holidays and not is_weekend(org, current, user):
            count += 1
        current += timedelta(days=1)
    return count


def weekend_policy_summary(org: Organization) -> str:
    policy = org.weekend_policy or Organization.WeekendPolicy.SAT_SUN
    labels = dict(Organization.WeekendPolicy.choices)
    if policy == Organization.WeekendPolicy.CUSTOM:
        days = parse_weekday_csv(org.weekend_custom_days)
        return f"Custom: {weekday_labels(days) or '—'}"
    if policy == Organization.WeekendPolicy.ROTATING_WEEKLY:
        n = len(_patterns(org))
        return f"Rotating weekly ({n} week cycle)"
    if policy == Organization.WeekendPolicy.ROTATING_MONTHLY:
        n = len(_patterns(org))
        return f"Rotating monthly ({n} week patterns)"
    if policy == Organization.WeekendPolicy.SHIFT_BASED:
        return "Per shift / employee schedule"
    return labels.get(policy, policy)


def calendar_preview(
    org: Organization,
    year: int,
    month: int,
    *,
    user: User | None = None,
) -> list[list[dict]]:
    """Month grid with day metadata for admin calendar preview."""
    import calendar as cal_mod

    holidays = {
        h.date: h
        for h in Holiday.objects.filter(
            organization=org,
            date__year=year,
            date__month=month,
        )
    }
    weeks: list[list[dict]] = []
    for week in cal_mod.monthcalendar(year, month):
        row: list[dict] = []
        for day in week:
            if day == 0:
                row.append({"day": 0})
                continue
            on_date = date(year, month, day)
            hol = holidays.get(on_date)
            off = not is_working_day(org, on_date, user=user)
            row.append(
                {
                    "day": day,
                    "date": on_date,
                    "is_off": off,
                    "is_weekend": is_weekend(org, on_date, user),
                    "is_holiday": hol is not None,
                    "holiday_name": hol.name if hol else "",
                }
            )
        weeks.append(row)
    return weeks
