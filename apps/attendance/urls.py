from django.urls import path

from apps.dashboard.analytics_views import (
    AttendanceAnalyticsEmployeeView,
    AttendanceAnalyticsView,
)

app_name = "attendance"

urlpatterns = [
    path("reports/", AttendanceAnalyticsView.as_view(), name="reports"),
    path(
        "reports/employee/<uuid:pk>/",
        AttendanceAnalyticsEmployeeView.as_view(),
        name="reports_employee",
    ),
]
