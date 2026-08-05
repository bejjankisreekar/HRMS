from django.urls import path

from .views import ShiftManagementView, ShiftReassignView

app_name = "shifts"

urlpatterns = [
    path("", ShiftManagementView.as_view(), name="management"),
    path("reassign/", ShiftReassignView.as_view(), name="reassign"),
]
