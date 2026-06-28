"""Financial year utility service.

All modules must use these functions instead of hard-coding date ranges.
The financial year is configured per-organization via Organization.fy_start_month.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.organizations.models import Organization


def get_fy_start_month(org: "Organization") -> int:
    """Return the FY start month (1–12) for the organization. Defaults to April (4)."""
    return int(getattr(org, "fy_start_month", 4) or 4)


def _fy_label(start_year: int, end_year: int, start_month: int) -> str:
    if start_month == 1:
        return f"FY {start_year}"
    return f"FY {start_year}-{str(end_year)[2:]}"


def _fy_end_month(start_month: int) -> int:
    return 12 if start_month == 1 else start_month - 1


def get_fy(org: "Organization", ref_date: date | None = None) -> dict:
    """Return FY details containing the ref_date (defaults to today).

    Returns:
        {start_year, end_year, label, date_from, date_to}
    """
    if ref_date is None:
        ref_date = date.today()
    m = get_fy_start_month(org)

    if m == 1:
        y = ref_date.year
        return {
            "start_year": y, "end_year": y,
            "label": _fy_label(y, y, 1),
            "date_from": date(y, 1, 1),
            "date_to": date(y, 12, 31),
        }

    if ref_date.month >= m:
        start_year = ref_date.year
    else:
        start_year = ref_date.year - 1
    end_year = start_year + 1
    end_month = _fy_end_month(m)
    last_day = calendar.monthrange(end_year, end_month)[1]
    return {
        "start_year": start_year, "end_year": end_year,
        "label": _fy_label(start_year, end_year, m),
        "date_from": date(start_year, m, 1),
        "date_to": date(end_year, end_month, last_day),
    }


# Aliases matching the names the user requested
def get_current_financial_year(org: "Organization") -> dict:
    return get_fy(org)


def get_previous_financial_year(org: "Organization") -> dict:
    current = get_current_financial_year(org)
    ref = date(current["start_year"] - 1, get_fy_start_month(org), 1)
    return get_fy(org, ref)


def get_financial_year(org: "Organization", ref_date: date) -> dict:
    return get_fy(org, ref_date)


def get_fy_range(org: "Organization", start_year: int) -> dict:
    """Return date range for the FY beginning in start_year."""
    m = get_fy_start_month(org)
    return get_fy(org, date(start_year, m, 1))


def get_financial_quarter(org: "Organization", ref_date: date | None = None) -> dict:
    """Return the financial quarter (Q1–Q4) containing ref_date.

    Returns:
        {quarter, label, date_from, date_to}
    """
    if ref_date is None:
        ref_date = date.today()
    m = get_fy_start_month(org)
    fy = get_fy(org, ref_date)

    months_into_fy = (ref_date.month - m) % 12
    quarter = months_into_fy // 3 + 1

    q_start_offset = (quarter - 1) * 3
    q_start_m = ((m - 1 + q_start_offset) % 12) + 1
    q_end_m = ((m - 1 + q_start_offset + 2) % 12) + 1

    q_start_y = fy["start_year"] if q_start_m >= m else fy["end_year"]
    q_end_y = fy["start_year"] if q_end_m >= m else fy["end_year"]
    last_day = calendar.monthrange(q_end_y, q_end_m)[1]

    return {
        "quarter": quarter,
        "label": f"Q{quarter} {fy['label']}",
        "date_from": date(q_start_y, q_start_m, 1),
        "date_to": date(q_end_y, q_end_m, last_day),
    }


def get_months_in_financial_year(org: "Organization", ref_date: date | None = None) -> list[dict]:
    """Return the 12 months in the FY that contains ref_date, in FY order.

    Each entry: {month, year, label, short}
    """
    if ref_date is None:
        ref_date = date.today()
    m = get_fy_start_month(org)
    fy = get_fy(org, ref_date)

    months = []
    for i in range(12):
        month_num = ((m - 1 + i) % 12) + 1
        year = fy["start_year"] if month_num >= m else fy["end_year"]
        months.append({
            "month": month_num,
            "year": year,
            "label": f"{calendar.month_name[month_num]} {year}",
            "short": f"{calendar.month_abbr[month_num]} {year}",
        })
    return months


# Alias
def getMonthsInFinancialYear(org: "Organization", ref_date: date | None = None) -> list[dict]:
    return get_months_in_financial_year(org, ref_date)


def get_financial_year_range(org: "Organization", ref_date: date | None = None) -> dict:
    fy = get_fy(org, ref_date)
    return {"date_from": fy["date_from"], "date_to": fy["date_to"]}


def get_current_payroll_month(org: "Organization") -> dict:
    """Return current payroll month/year label."""
    today = date.today()
    return {
        "month": today.month,
        "year": today.year,
        "label": f"{calendar.month_name[today.month]} {today.year}",
    }


def fy_year_choices(org: "Organization", n: int = 5) -> list[dict]:
    """Return n financial years as dropdown choices (most recent last).

    Each entry: {start_year, end_year, label, date_from, date_to}
    """
    current = get_current_financial_year(org)
    choices = []
    for offset in range(n - 1, -1, -1):
        start_year = current["start_year"] - offset
        fy = get_fy_range(org, start_year)
        choices.append({
            "start_year": start_year,
            "end_year": fy["end_year"],
            "label": fy["label"],
            "date_from": fy["date_from"],
            "date_to": fy["date_to"],
        })
    return choices


def payroll_month_choices(org: "Organization", n_years: int = 2) -> list[dict]:
    """Return month/year pairs for payroll period dropdown, covering n_years of history.

    Most recent first. Each entry: {month, year, label, short}
    """
    today = date.today()
    m = get_fy_start_month(org)
    current_fy = get_current_financial_year(org)
    start_year = current_fy["start_year"] - (n_years - 1)
    start_fy = get_fy_range(org, start_year)
    from_date = start_fy["date_from"]

    choices = []
    yr, mo = from_date.year, from_date.month
    while (yr, mo) <= (today.year, today.month):
        choices.append({
            "month": mo,
            "year": yr,
            "label": f"{calendar.month_name[mo]} {yr}",
            "short": f"{calendar.month_abbr[mo]} {yr}",
        })
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1

    choices.reverse()
    return choices


def quarter_choices(org: "Organization", n_fy: int = 2) -> list[dict]:
    """Return quarter choices for the last n_fy financial years.

    Each entry: {label, quarter, date_from, date_to}
    """
    today = date.today()
    m = get_fy_start_month(org)
    current_fy = get_current_financial_year(org)
    choices = []
    for fy_offset in range(n_fy - 1, -1, -1):
        start_year = current_fy["start_year"] - fy_offset
        for q in range(1, 5):
            q_start_m = ((m - 1 + (q - 1) * 3) % 12) + 1
            q_start_y = start_year if q_start_m >= m else start_year + 1
            ref = date(q_start_y, q_start_m, 1)
            if ref > today:
                break
            qd = get_financial_quarter(org, ref)
            choices.append(qd)
    choices.reverse()
    return choices
