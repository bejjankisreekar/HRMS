"""Payroll deduction JSON APIs, mounted at /api/payroll/."""

from django.urls import path

from .deductions_views import (
    DeductionsEmployeeAPI,
    DeductionsExportAPI,
    DeductionsListAPI,
    DeductionsSummaryAPI,
    DeductionTypeAPI,
)

app_name = "payroll_api"

urlpatterns = [
    path("deductions/", DeductionsListAPI.as_view(), name="deductions"),
    path("deductions/summary/", DeductionsSummaryAPI.as_view(), name="deductions_summary"),
    path("deductions/employee/<uuid:pk>/", DeductionsEmployeeAPI.as_view(), name="deductions_employee"),
    path("deductions/export/", DeductionsExportAPI.as_view(), name="deductions_export"),
    path("deductions/tax/", DeductionTypeAPI.as_view(deduction_type="tds"), name="deductions_tax"),
    path("deductions/pf/", DeductionTypeAPI.as_view(deduction_type="employee_pf"), name="deductions_pf"),
    path("deductions/esi/", DeductionTypeAPI.as_view(deduction_type="esi"), name="deductions_esi"),
    path("deductions/pt/", DeductionTypeAPI.as_view(deduction_type="pt"), name="deductions_pt"),
]
