"""Payroll Reports hub: Summary, Salary Register, Payslip Distribution.

Reuses the deductions reporting layer so the register/summary stay consistent with the deductions
dashboard and compliance reports. Read-only; tenant-scoped via the viewer's organization.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.http import HttpResponse

from . import deductions as D

# Hub metadata. Internal reports point at the new detail view; the rest link to existing pages.
REPORTS = [
    {"key": "summary", "label": "Payroll Summary Report", "icon": "file-text",
     "description": "Employee · Gross · Deductions · Net.", "kind": "internal"},
    {"key": "register", "label": "Salary Register", "icon": "book-open",
     "description": "Classic employee-wise register for audits.", "kind": "internal"},
    {"key": "deduction", "label": "Deduction Report", "icon": "receipt",
     "description": "TDS, PF, ESI, PT, loans and more.", "kind": "deductions"},
    {"key": "tds", "label": "TDS Report", "icon": "percent",
     "description": "Employee-wise TDS deductions.", "kind": "compliance"},
    {"key": "pf", "label": "PF Contribution Report", "icon": "landmark",
     "description": "Employee PF + Employer PF.", "kind": "compliance"},
    {"key": "esi", "label": "ESI Report", "icon": "heart-pulse",
     "description": "ESI deductions.", "kind": "compliance"},
    {"key": "pt", "label": "Professional Tax Report", "icon": "map-pin",
     "description": "State-wise professional tax deductions.", "kind": "compliance"},
    {"key": "distribution", "label": "Payslip Distribution Report", "icon": "send",
     "description": "Generated · Downloaded · Pending.", "kind": "internal"},
]

INTERNAL_KINDS = {"summary", "register", "distribution"}


# ── Summary ──────────────────────────────────────────────────────────────────

def summary_rows(viewer, filters) -> list[dict]:
    rows = []
    for p in D.payslips_for(viewer, filters):
        b = D.deduction_breakdown(p)
        rows.append({
            "employee_id": p.user.employee_id or "—",
            "name": p.user.choice_label,
            "department": p.user.department_name or "—",
            "period": p.payroll_run.period_label,
            "gross": float(b["gross"]),
            "deductions": float(b["total_deductions"]),
            "net": float(b["net"]),
        })
    return rows


# ── Salary Register (full breakdown — reuse deductions) ──────────────────────

def salary_register_rows(viewer, filters) -> list[dict]:
    return D.org_report_rows(viewer, filters)


# ── Payslip Distribution ─────────────────────────────────────────────────────

def payslip_distribution(viewer, filters) -> dict:
    total = generated = downloaded = 0
    rows = []
    for p in D.payslips_for(viewer, filters):
        total += 1
        is_gen = p.generated_at is not None
        is_dl = (p.download_count or 0) > 0
        generated += 1 if is_gen else 0
        downloaded += 1 if is_dl else 0
        if not is_gen:
            status = "Not generated"
        elif is_dl:
            status = "Downloaded"
        else:
            status = "Pending download"
        rows.append({
            "employee_id": p.user.employee_id or "—",
            "name": p.user.choice_label,
            "period": p.payroll_run.period_label,
            "generated": is_gen,
            "downloaded": is_dl,
            "download_count": p.download_count or 0,
            "status": status,
        })
    return {
        "totals": {
            "total": total,
            "generated": generated,
            "downloaded": downloaded,
            "pending": generated - downloaded,   # generated but not yet downloaded
            "not_generated": total - generated,
        },
        "rows": rows,
    }


# ── Dispatch + exports ───────────────────────────────────────────────────────

_HEADERS = {
    "summary": ["Employee ID", "Employee", "Department", "Period", "Gross", "Deductions", "Net"],
    "distribution": ["Employee ID", "Employee", "Period", "Generated", "Downloads", "Status"],
}


def _register_totals(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    keys = ["gross", "tds", "employee_pf", "esi", "pt", "lop", "loan", "custom", "total_deductions", "net"]
    t = {k: Decimal("0") for k in keys}
    for r in rows:
        for k in keys:
            t[k] += Decimal(str(r.get(k) or 0))
    return t


def _summary_totals(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    t = {"gross": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0")}
    for r in rows:
        t["gross"] += Decimal(str(r.get("gross") or 0))
        t["deductions"] += Decimal(str(r.get("deductions") or 0))
        t["net"] += Decimal(str(r.get("net") or 0))
    return t


def report_rows(viewer, kind: str, filters) -> dict:
    """Return {columns?, rows, totals?} for a given internal report kind."""
    if kind == "summary":
        rows = summary_rows(viewer, filters)
        return {"rows": rows, "totals": _summary_totals(rows)}
    if kind == "register":
        rows = salary_register_rows(viewer, filters)
        return {"rows": rows, "totals": _register_totals(rows)}
    if kind == "distribution":
        return payslip_distribution(viewer, filters)
    return {"rows": []}


def _summary_values(r: dict) -> list:
    return [r["employee_id"], r["name"], r["department"], r["period"], r["gross"], r["deductions"], r["net"]]


def _distribution_values(r: dict) -> list:
    return [r["employee_id"], r["name"], r["period"], "Yes" if r["generated"] else "No",
            r["download_count"], r["status"]]


def export(viewer, kind: str, filters, fmt: str) -> HttpResponse:
    if kind == "register":
        rows = salary_register_rows(viewer, filters)
        return D.export_xlsx(rows) if fmt in ("xlsx", "excel") else D.export_csv(rows)

    if kind == "summary":
        rows, headers, to_vals = summary_rows(viewer, filters), _HEADERS["summary"], _summary_values
    else:  # distribution
        rows, headers, to_vals = payslip_distribution(viewer, filters)["rows"], _HEADERS["distribution"], _distribution_values

    if fmt in ("xlsx", "excel"):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = kind.title()
        ws.append(headers)
        for r in rows:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in to_vals(r)])
        buf = io.BytesIO()
        wb.save(buf)
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="payroll_{kind}.xlsx"'
        return resp

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(to_vals(r))
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="payroll_{kind}.csv"'
    return resp
