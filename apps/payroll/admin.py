from django.contrib import admin

from .models import (
    EmployeeLoan,
    EmployeeSalary,
    PayrollApproval,
    PayrollCycleConfig,
    PayrollRun,
    PayrollSettings,
    Payslip,
    PayslipLine,
    Reimbursement,
    SalaryComponent,
    SalaryRevision,
    SalaryStructure,
    TaxConfiguration,
    TaxSlab,
)


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "component_type", "category", "is_active")
    list_filter = ("organization", "component_type")


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("organization", "year", "month", "status", "total_net", "employee_count")
    list_filter = ("status", "organization")


class PayslipLineInline(admin.TabularInline):
    model = PayslipLine
    extra = 0


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("user", "payroll_run", "net_salary", "payment_status")
    inlines = [PayslipLineInline]


admin.site.register(SalaryStructure)
admin.site.register(EmployeeSalary)
admin.site.register(Reimbursement)
admin.site.register(EmployeeLoan)
admin.site.register(PayrollApproval)
admin.site.register(SalaryRevision)
admin.site.register(TaxConfiguration)
admin.site.register(TaxSlab)
admin.site.register(PayrollCycleConfig)
admin.site.register(PayrollSettings)
