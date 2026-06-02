from django.urls import path

from .views import OffboardingManagementView, OnboardingManagementView

app_name = "lifecycle"

urlpatterns = [
    path("onboarding/", OnboardingManagementView.as_view(), name="onboarding"),
    path("offboarding/", OffboardingManagementView.as_view(), name="offboarding"),
]
