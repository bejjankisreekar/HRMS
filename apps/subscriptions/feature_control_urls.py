from django.urls import path

from .feature_control_views import (
    AddonControlView,
    FeatureAuditView,
    FeatureControlAPIView,
    FeatureControlHubView,
    FieldControlView,
    GlobalFeatureControlView,
    ModuleControlView,
    NavigationControlView,
    OrganizationFeatureControlView,
    OrgLimitsUpdateView,
    PageControlView,
    PlanFeatureControlView,
    RolePermissionView,
    WorkflowControlView,
)

app_name = "feature_control"

urlpatterns = [
    path("", GlobalFeatureControlView.as_view(), name="global"),
    path("hub/", FeatureControlHubView.as_view(), name="hub"),
    path("modules/", ModuleControlView.as_view(), name="modules"),
    path("pages/", PageControlView.as_view(), name="pages"),
    path("navigation/", NavigationControlView.as_view(), name="navigation"),
    path("roles/", RolePermissionView.as_view(), name="roles"),
    path("fields/", FieldControlView.as_view(), name="fields"),
    path("workflows/", WorkflowControlView.as_view(), name="workflows"),
    path("addons/", AddonControlView.as_view(), name="addons"),
    path("audit/", FeatureAuditView.as_view(), name="audit"),
    path("api/", FeatureControlAPIView.as_view(), name="api"),
    path("organizations/<uuid:pk>/features/", OrganizationFeatureControlView.as_view(), name="org_features"),
    path("organizations/<uuid:pk>/limits/", OrgLimitsUpdateView.as_view(), name="org_limits"),
    path("plans/<uuid:pk>/features/", PlanFeatureControlView.as_view(), name="plan_features"),
]
