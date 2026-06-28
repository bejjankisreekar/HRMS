"""Bulk salary-structure grid: every employee's components in one editable list.

Read + write layer over EmployeeSalary / EmployeeSalaryComponent, reusing the salary engine in
services.py. Tenant-scoped via the viewer's organization. No model changes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import EmployeeSalaryComponent as ESC
from .models import SalaryComponent
from .services import (
    _money,
    _resolve_component_amount,
    compute_employee_breakdown,
    ensure_payroll_setup,
    get_active_salary,
    payroll_team_for,
    seed_employee_components,
)

EARNING = SalaryComponent.ComponentType.EARNING
DEDUCTION = SalaryComponent.ComponentType.DEDUCTION


def bulk_salary_grid(viewer) -> dict:
    """Columns (earnings then deductions) + one row per employee with editable cell amounts."""
    org = viewer.organization
    if not org:
        return {"columns": [], "rows": []}
    ensure_payroll_setup(org)  # canonical component codes (basic/pf/…) must exist before seeding

    team = payroll_team_for(viewer).order_by("first_name", "last_name")
    col_order: dict[str, dict] = {}
    rows: list[dict] = []

    for emp in team:
        salary = get_active_salary(emp)
        seed_employee_components(salary)
        bd = compute_employee_breakdown(salary)
        cells: dict[str, float] = {}
        for ln in bd["earnings"] + bd["deductions"]:
            code = ln["code"]
            if not code:
                continue
            cells[code] = float(ln["amount"])
            if code not in col_order:
                col_order[code] = {"code": code, "label": ln["label"], "kind": ln["kind"]}
        rows.append({
            "uid": str(emp.pk),
            "name": emp.display_name,
            "emp_id": emp.employee_id or "—",
            "department": emp.department_name or "—",
            "ctc": float(_money(salary.monthly_ctc)),
            "cells": cells,
            "gross": float(bd["gross"]),
            "total_deductions": float(bd["total_deductions"]),
            "net": float(bd["net"]),
        })

    cols = list(col_order.values())
    columns = [c for c in cols if c["kind"] == EARNING] + [c for c in cols if c["kind"] == DEDUCTION]
    # Flatten each row's cell map into an ordered list aligned to `columns` (templates can't
    # index a dict by a variable key), so header and body iterate in lockstep.
    for r in rows:
        cell_map = r["cells"]
        r["cells"] = [
            {"code": c["code"], "kind": c["kind"], "value": cell_map.get(c["code"], 0.0)}
            for c in columns
        ]
    return {"columns": columns, "rows": rows}


@transaction.atomic
def save_bulk_salary(viewer, post) -> int:
    """Apply edits. A changed cell becomes a FIXED override; untouched cells are left intact."""
    org = viewer.organization
    if not org:
        return 0
    ensure_payroll_setup(org)

    updated = 0
    for emp in payroll_team_for(viewer):
        uid = str(emp.pk)
        salary = get_active_salary(emp)
        changed = False

        ctc_raw = post.get(f"ctc_{uid}")
        if ctc_raw not in (None, ""):
            try:
                new_ctc = Decimal(str(ctc_raw))
            except (InvalidOperation, TypeError, ValueError):
                new_ctc = None
            if new_ctc is not None and new_ctc >= 0 and new_ctc != salary.monthly_ctc:
                salary.monthly_ctc = new_ctc
                salary.save(update_fields=["monthly_ctc"])
                changed = True

        ctc = _money(salary.monthly_ctc)
        comps = list(salary.components.all())
        basic = Decimal("0")
        for c in comps:
            if c.code == "basic":
                basic = _resolve_component_amount(c, ctc, Decimal("0"), Decimal("1"))
                break

        for comp in comps:
            raw = post.get(f"c_{uid}_{comp.code}")
            if raw in (None, ""):
                continue
            try:
                val = _money(Decimal(str(raw)))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if val < 0:
                continue
            current = _resolve_component_amount(comp, ctc, basic, Decimal("1"))
            if val != current:
                comp.mode = ESC.Mode.FIXED
                comp.value = val
                comp.save(update_fields=["mode", "value"])
                changed = True

        if changed:
            updated += 1
    return updated
