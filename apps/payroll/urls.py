from django.urls import path

from .deductions_views import (
    ComplianceReportsView,
    DeductionExportView,
    PayrollDeductionsView,
    PayrollReportView,
    PayrollReportsHubView,
)
from .views import (
    BulkSalaryStructureView,
    EmployeeFinancialsView,
    PayrollManagementView,
    SalaryStructuresView,
)

app_name = "payroll"

urlpatterns = [
    path("", PayrollManagementView.as_view(), name="management"),
    path("deductions/", PayrollDeductionsView.as_view(), name="deductions"),
    path("deductions/export/", DeductionExportView.as_view(), name="deductions_export"),
    path("compliance/", ComplianceReportsView.as_view(), name="compliance"),
    path("reports/", PayrollReportsHubView.as_view(), name="reports"),
    path("reports/<slug:kind>/", PayrollReportView.as_view(), name="report"),
    path("salary-structures/", SalaryStructuresView.as_view(), name="salary_structures"),
    path("salary-structures/bulk/", BulkSalaryStructureView.as_view(), name="salary_structures_bulk"),
    path("salary-structures/<uuid:pk>/", EmployeeFinancialsView.as_view(), name="employee_financials"),
]
