"""URL routes for the manager team API (mounted at /api/team/)."""

from django.urls import path

from .api_views import (
    TeamAttendanceView,
    TeamLeaveApproveView,
    TeamLeaveRejectView,
    TeamLeaveRequestsView,
    TeamMembersView,
    TeamRegularizationApproveView,
    TeamRegularizationListView,
    TeamRegularizationRejectView,
)

app_name = "team"

urlpatterns = [
    path("members/", TeamMembersView.as_view(), name="members"),
    path("attendance/", TeamAttendanceView.as_view(), name="attendance"),
    path("leave-requests/", TeamLeaveRequestsView.as_view(), name="leave_requests"),
    path("leave-requests/<uuid:pk>/approve/", TeamLeaveApproveView.as_view(), name="leave_approve"),
    path("leave-requests/<uuid:pk>/reject/", TeamLeaveRejectView.as_view(), name="leave_reject"),
    path(
        "regularization-requests/",
        TeamRegularizationListView.as_view(),
        name="regularization_requests",
    ),
    path(
        "regularization/<uuid:pk>/approve/",
        TeamRegularizationApproveView.as_view(),
        name="regularization_approve",
    ),
    path(
        "regularization/<uuid:pk>/reject/",
        TeamRegularizationRejectView.as_view(),
        name="regularization_reject",
    ),
]
