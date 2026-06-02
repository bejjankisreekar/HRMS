from django.urls import path

from .views import PayrollManagementView

app_name = "payroll"

urlpatterns = [
    path("", PayrollManagementView.as_view(), name="management"),
]
