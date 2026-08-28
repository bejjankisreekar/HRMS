from django.urls import path
from django.views.generic import RedirectView

from .deductions_views import (
    ComplianceReportsView,
    DeductionExportView,
    PayrollDeductionsView,
    PayrollReportView,
    PayrollReportsHubView,
)
from .form16_views import Form16DetailView, Form16ListView, Form16PDFView
from .tax_views import TaxDeclarationReviewView, TaxDeclarationView, TaxProjectionView
from .views import (
    BulkSalaryStructureView,
    EmployeeFinancialsView,
    LoansAdvancesView,
    PayrollCyclesView,
    PayrollDashboardView,
    PayrollManagementView,
    PayrollPlaceholderView,
    PayrollRunsView,
    PayrollSettingsView,
    PayslipsView,
    ReimbursementsView,
    SalaryComponentsView,
    SalaryRevisionsView,
    SalaryStructuresView,
    TaxManagementView,
)

app_name = "payroll"

urlpatterns = [
    path("", PayrollManagementView.as_view(), name="management"),
    path("dashboard/", PayrollDashboardView.as_view(), name="dashboard"),
    path("deductions/", PayrollDeductionsView.as_view(), name="deductions"),
    path("deductions/export/", DeductionExportView.as_view(), name="deductions_export"),
    path("compliance/", ComplianceReportsView.as_view(), name="compliance"),
    path("reports/", PayrollReportsHubView.as_view(), name="reports"),
    path("reports/<slug:kind>/", PayrollReportView.as_view(), name="report"),
    path("salary-structures/", SalaryStructuresView.as_view(), name="salary_structures"),
    path("salary-structures/bulk/", BulkSalaryStructureView.as_view(), name="salary_structures_bulk"),
    path("salary-structures/<uuid:pk>/", EmployeeFinancialsView.as_view(), name="employee_financials"),
    path("components/", SalaryComponentsView.as_view(), name="components"),
    path("cycles/", PayrollCyclesView.as_view(), name="cycles"),
    path("runs/", PayrollRunsView.as_view(), name="runs"),
    path("payslips/", PayslipsView.as_view(), name="payslips"),
    path("tax-management/", TaxManagementView.as_view(), name="tax_management"),
    path("tax-declaration/", TaxDeclarationView.as_view(), name="tax_declaration"),
    path("tax-declarations/", TaxDeclarationReviewView.as_view(), name="tax_declaration_review"),
    path("tax-projection/", TaxProjectionView.as_view(), name="tax_projection"),
    path("loans/", LoansAdvancesView.as_view(), name="loans"),
    path("reimbursements/", ReimbursementsView.as_view(), name="reimbursements"),
    path("revisions/", SalaryRevisionsView.as_view(), name="revisions"),
    path("settings/", PayrollSettingsView.as_view(), name="settings"),
    # My Salary was merged into the Payroll Dashboard; keep the URL as a redirect
    # so old bookmarks and notification links don't 404.
    path("my-salary/", RedirectView.as_view(pattern_name="payroll:dashboard", query_string=True), name="my_salary"),
    path("form16/", Form16ListView.as_view(), name="form16"),
    path("form16/me/", Form16DetailView.as_view(), name="form16_mine"),
    path("form16/me/pdf/", Form16PDFView.as_view(), name="form16_mine_pdf"),
    path("form16/<uuid:pk>/", Form16DetailView.as_view(), name="form16_detail"),
    path("form16/<uuid:pk>/pdf/", Form16PDFView.as_view(), name="form16_pdf"),
    path(
        "bonuses/",
        PayrollPlaceholderView.as_view(
            feature_name="Bonuses & Incentives",
            feature_description="Performance, festival, referral, and one-time bonus runs with an approval workflow — coming in a future release.",
        ),
        name="bonuses",
    ),
    path(
        "overtime/",
        PayrollPlaceholderView.as_view(
            feature_name="Overtime",
            feature_description="Attendance-driven overtime entry with hourly/holiday/weekend/night rates — coming in a future release.",
        ),
        name="overtime",
    ),
    path(
        "arrears/",
        PayrollPlaceholderView.as_view(
            feature_name="Arrears",
            feature_description="Retroactive salary adjustments automatically folded into the next payroll run — coming in a future release.",
        ),
        name="arrears",
    ),
    path(
        "final-settlement/",
        PayrollPlaceholderView.as_view(
            feature_name="Final Settlement",
            feature_description="Full & final settlement covering leave encashment, notice pay, gratuity, and asset recovery — coming in a future release.",
        ),
        name="final_settlement",
    ),
]
