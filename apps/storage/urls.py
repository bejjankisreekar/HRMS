from django.urls import path

from .views import (
    FileAuditHubView,
    ResourcesHubView,
    StorageActionAPIView,
    StorageHubView,
    UsageComparisonHubView,
)

app_name = "storage"

urlpatterns = [
    path("", StorageHubView.as_view(), name="hub"),
    path("resources/", ResourcesHubView.as_view(), name="resources"),
    path("file-audits/", FileAuditHubView.as_view(), name="file_audits"),
    path("usage/", UsageComparisonHubView.as_view(), name="usage"),
    path("api/action/", StorageActionAPIView.as_view(), name="api_action"),
]
