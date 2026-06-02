from django.urls import path

from .views import (
    OrgTreeDataAPIView,
    OrgTreeEmployeeAPIView,
    OrgTreeExportView,
    OrgTreeMoveAPIView,
    OrgTreeSearchAPIView,
    OrgTreeTeamCreateView,
    OrgTreeView,
)

app_name = "orgchart"

urlpatterns = [
    path("", OrgTreeView.as_view(), name="tree"),
    path("api/data/", OrgTreeDataAPIView.as_view(), name="api_data"),
    path("api/employee/<uuid:pk>/", OrgTreeEmployeeAPIView.as_view(), name="api_employee"),
    path("api/move/", OrgTreeMoveAPIView.as_view(), name="api_move"),
    path("api/search/", OrgTreeSearchAPIView.as_view(), name="api_search"),
    path("api/team/", OrgTreeTeamCreateView.as_view(), name="api_team"),
    path("export/", OrgTreeExportView.as_view(), name="export"),
]
