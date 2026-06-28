"""URL routes for the leave REST API (mounted at /api/leaves/)."""

from django.urls import path

from .api import (
    ApplyView,
    ApproveView,
    BalanceAdjustView,
    CancelView,
    MyBalancesView,
    MyRequestsView,
    RejectView,
    TeamRequestsView,
)

app_name = "leaves_api"

urlpatterns = [
    path("balances/", MyBalancesView.as_view(), name="balances"),
    path("balances/adjust/", BalanceAdjustView.as_view(), name="balances_adjust"),
    path("my-requests/", MyRequestsView.as_view(), name="my_requests"),
    path("apply/", ApplyView.as_view(), name="apply"),
    path("team/", TeamRequestsView.as_view(), name="team"),
    path("<uuid:pk>/cancel/", CancelView.as_view(), name="cancel"),
    path("<uuid:pk>/approve/", ApproveView.as_view(), name="approve"),
    path("<uuid:pk>/reject/", RejectView.as_view(), name="reject"),
]
