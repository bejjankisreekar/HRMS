from django.urls import path

from .views import (
    CareerPathView,
    DesignationListView,
    GradesActionAPIView,
    GradesAnalyticsView,
    GradeListView,
    GradesHubView,
    HierarchyView,
)

app_name = "grades"

urlpatterns = [
    path("", GradesHubView.as_view(), name="hub"),
    path("list/", GradeListView.as_view(), name="list"),
    path("designations/", DesignationListView.as_view(), name="designations"),
    path("hierarchy/", HierarchyView.as_view(), name="hierarchy"),
    path("career/", CareerPathView.as_view(), name="career"),
    path("analytics/", GradesAnalyticsView.as_view(), name="analytics"),
    path("api/action/", GradesActionAPIView.as_view(), name="api_action"),
]
