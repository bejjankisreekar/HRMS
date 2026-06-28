from django.urls import path

from apps.dashboard.analytics_views import (
    AttendanceAnalyticsEmployeeView,
    AttendanceAnalyticsView,
    AttendanceReportsDataView,
    EmployeeAttendanceChartView,
)

app_name = "attendance"

urlpatterns = [
    path("reports/", AttendanceAnalyticsView.as_view(), name="reports"),
    path("reports/data/", AttendanceReportsDataView.as_view(), name="reports_data"),
    path(
        "reports/employee-attendance-chart/",
        EmployeeAttendanceChartView.as_view(),
        name="employee_chart",
    ),
    path(
        "reports/employee/<uuid:pk>/",
        AttendanceAnalyticsEmployeeView.as_view(),
        name="reports_employee",
    ),
]
