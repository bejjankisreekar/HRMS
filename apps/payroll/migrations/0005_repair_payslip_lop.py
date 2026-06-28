"""Repair existing payslips to the conventional model.

Converts prorated-gross payslips (Gross = earned, LOP held only in ``leave_deduction``) to the
conventional model: Gross = full salary, LOP is a deduction line, Net = max(0, Gross − Deductions).
Fixes historically negative ``net_salary`` and ``total_deductions`` that wrongly included LOP.
Idempotent: payslips that already have a Loss-of-Pay line are only re-summed.
"""

from decimal import Decimal

from django.db import migrations


def repair(apps, schema_editor):
    Payslip = apps.get_model("payroll", "Payslip")
    PayslipLine = apps.get_model("payroll", "PayslipLine")
    SalaryComponent = apps.get_model("payroll", "SalaryComponent")
    PayrollRun = apps.get_model("payroll", "PayrollRun")

    lop_cache = {}

    def lop_component(org_id):
        if org_id not in lop_cache:
            comp, _ = SalaryComponent.objects.get_or_create(
                organization_id=org_id,
                code="lop",
                defaults={
                    "name": "Loss of Pay",
                    "component_type": "DEDUCTION",
                    "category": "LOP",
                    "calc_type": "FIXED",
                    "sort_order": 50,
                },
            )
            lop_cache[org_id] = comp
        return lop_cache[org_id]

    for ps in Payslip.objects.select_related("payroll_run").prefetch_related("lines__component"):
        lines = list(ps.lines.all())
        has_lop = any(
            (l.component and l.component.category == "LOP") or l.label == "Loss of Pay"
            for l in lines
        )
        ded = sum((l.amount for l in lines if l.line_type == "DEDUCTION"), Decimal("0"))
        lop = ps.leave_deduction or Decimal("0")

        if not has_lop and lop > 0:
            PayslipLine.objects.create(
                payslip=ps,
                component=lop_component(ps.payroll_run.organization_id),
                label="Loss of Pay",
                line_type="DEDUCTION",
                amount=lop,
                sort_order=50,
            )
            ps.gross_salary = ps.gross_salary + lop
            ded = ded + lop

        ps.total_deductions = ded
        ps.net_salary = max(
            Decimal("0"), ps.gross_salary - ded + (ps.reimbursements or Decimal("0"))
        )
        ps.save(update_fields=["gross_salary", "total_deductions", "net_salary"])

    for run in PayrollRun.objects.prefetch_related("payslips"):
        slips = list(run.payslips.all())
        run.total_gross = sum((p.gross_salary for p in slips), Decimal("0"))
        run.total_net = sum((p.net_salary for p in slips), Decimal("0"))
        run.total_deductions = sum((p.total_deductions for p in slips), Decimal("0"))
        run.save(update_fields=["total_gross", "total_net", "total_deductions"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0004_alter_salarycomponent_category"),
    ]

    operations = [
        migrations.RunPython(repair, noop),
    ]
