from django.urls import path

from .views import ShiftManagementView

app_name = "shifts"

urlpatterns = [
    path("", ShiftManagementView.as_view(), name="management"),
]
