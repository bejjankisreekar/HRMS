from django.urls import path

from .views import (
    ApplyLeaveSuccessView,
    ApplyLeaveView,
    LeaveApplyPreviewAPIView,
    LeaveManagementView,
)

app_name = "leaves"

urlpatterns = [
    path("", LeaveManagementView.as_view(), name="management"),
    path("apply/", ApplyLeaveView.as_view(), name="apply"),
    path("apply/success/<uuid:pk>/", ApplyLeaveSuccessView.as_view(), name="apply_success"),
    path("api/apply-preview/", LeaveApplyPreviewAPIView.as_view(), name="apply_preview"),
]
