from django.urls import path

from .views import (
    ContactPageView,
    FeaturesPageView,
    LandingPageView,
    LoginView,
    LogoutView,
    ProfileView,
    PricingPageView,
    RegisterOrganizationView,
    RegisterSuccessView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterOrganizationView.as_view(), name="register"),
    path("register/success/", RegisterSuccessView.as_view(), name="register_success"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    # optional marketing landing mirror (main landing is in root urls)
    path("landing/", LandingPageView.as_view(), name="landing"),
    path("features/", FeaturesPageView.as_view(), name="features"),
    path("pricing/", PricingPageView.as_view(), name="pricing"),
    path("contact/", ContactPageView.as_view(), name="contact"),
]

