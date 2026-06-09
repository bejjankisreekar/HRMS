from django.urls import path

from .views import EmployeeFinancialsView, PayrollManagementView, SalaryStructuresView

app_name = "payroll"

urlpatterns = [
    path("", PayrollManagementView.as_view(), name="management"),
    path("salary-structures/", SalaryStructuresView.as_view(), name="salary_structures"),
    path("salary-structures/<uuid:pk>/", EmployeeFinancialsView.as_view(), name="employee_financials"),
]
