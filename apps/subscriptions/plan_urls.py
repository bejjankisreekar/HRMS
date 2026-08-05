from django.urls import path

from .plan_matrix_views import (
    LegacyFeatureControlRedirectView,
    PlanFeatureMatrixAPIView,
    PlanFeatureMatrixView,
)
from .plan_views import (
    BillingSettingsUpdateView,
    PlanCloneView,
    PlanCreateView,
    PlanDetailView,
    PlanFeatureToggleView,
    PlanMenuItemCreateView,
    PlanMenuItemUpdateView,
    PlanMenuReorderView,
    PlanUpdateView,
)

app_name = "plans"

urlpatterns = [
    path("", PlanFeatureMatrixView.as_view(), name="matrix"),
    path("list/", LegacyFeatureControlRedirectView.as_view(), name="list"),
    path("api/", PlanFeatureMatrixAPIView.as_view(), name="matrix_api"),
    path("create/", PlanCreateView.as_view(), name="create"),
    path("billing-settings/", BillingSettingsUpdateView.as_view(), name="billing_settings_update"),
    path("<uuid:pk>/", PlanDetailView.as_view(), name="detail"),
    path("<uuid:pk>/update/", PlanUpdateView.as_view(), name="update"),
    path("<uuid:pk>/clone/", PlanCloneView.as_view(), name="clone"),
    path("<uuid:pk>/features/toggle/", PlanFeatureToggleView.as_view(), name="feature_toggle"),
    path("<uuid:pk>/menu/reorder/", PlanMenuReorderView.as_view(), name="menu_reorder"),
    path("<uuid:pk>/menu/add/", PlanMenuItemCreateView.as_view(), name="menu_add"),
    path("<uuid:pk>/menu/<uuid:item_pk>/", PlanMenuItemUpdateView.as_view(), name="menu_edit"),
]
