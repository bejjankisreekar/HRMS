"""DRF endpoints for manager / team-leader functionality.

All endpoints are scoped to the authenticated manager's direct reports within
their own organization. Object lookups go through the manager-scoped queryset,
so a request for an out-of-team / cross-tenant record returns 404 — a manager
can never read or act on data outside their hierarchy.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.hierarchy import correction_requests_for_reviewer, direct_reports_for
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
from apps.attendance.services import approve_regularization, reject_regularization
from apps.leaves.models import LeaveRequest
from apps.leaves.services import (
    approve_leave,
    manager_pending_leave_requests,
    manager_team_leave_requests,
    reject_leave,
)

from .audit import record_team_action
from .models import TeamActionAuditLog
from .permissions import IsManagerOrTeamLead
from .serializers import (
    DecisionSerializer,
    TeamAttendanceSerializer,
    TeamLeaveRequestSerializer,
    TeamMemberSerializer,
    TeamRegularizationSerializer,
)


def _parse_date(value, default):
    if not value:
        return default
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return default


class TeamAPIView(APIView):
    permission_classes = [IsManagerOrTeamLead]


class TeamMembersView(TeamAPIView):
    def get(self, request):
        members = direct_reports_for(request.user).select_related("department", "organization")
        return Response(TeamMemberSerializer(members, many=True).data)


class TeamAttendanceView(TeamAPIView):
    def get(self, request):
        today = timezone.localdate()
        date_from = _parse_date(request.query_params.get("from"), today.replace(day=1))
        date_to = _parse_date(request.query_params.get("to"), today)
        team_ids = list(direct_reports_for(request.user).values_list("pk", flat=True))
        records = (
            AttendanceRecord.objects.filter(
                user_id__in=team_ids,
                date__gte=date_from,
                date__lte=date_to,
            )
            .select_related("user")
            .order_by("-date")
        )
        return Response(TeamAttendanceSerializer(records, many=True).data)


class TeamLeaveRequestsView(TeamAPIView):
    def get(self, request):
        status_param = request.query_params.get("status")
        if status_param:
            qs = manager_team_leave_requests(request.user, status=status_param.upper())
        else:
            qs = manager_pending_leave_requests(request.user)
        return Response(TeamLeaveRequestSerializer(qs, many=True).data)


class _LeaveDecisionView(TeamAPIView):
    approve = True

    def post(self, request, pk):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data["comment"]

        # Only pending requests awaiting THIS manager are actionable.
        leave_request = get_object_or_404(
            manager_pending_leave_requests(request.user), pk=pk
        )
        employee = leave_request.user

        if self.approve:
            msg = approve_leave(leave_request, request.user, comment)
            action = TeamActionAuditLog.Action.LEAVE_APPROVE
            verb = "Approved"
        else:
            msg = reject_leave(leave_request, request.user, comment)
            action = TeamActionAuditLog.Action.LEAVE_REJECT
            verb = "Rejected"

        record_team_action(
            actor=request.user,
            action=action,
            target=employee,
            object_id=leave_request.pk,
            summary=f"{verb} leave for {employee.display_name}",
            request=request,
            comment=comment,
            leave_type=leave_request.leave_type.code,
        )
        leave_request.refresh_from_db()
        return Response(
            {"detail": msg, "status": leave_request.status},
            status=status.HTTP_200_OK,
        )


class TeamLeaveApproveView(_LeaveDecisionView):
    approve = True


class TeamLeaveRejectView(_LeaveDecisionView):
    approve = False


class TeamRegularizationListView(TeamAPIView):
    def get(self, request):
        status_param = (request.query_params.get("status") or "PENDING").upper()
        qs = correction_requests_for_reviewer(request.user)
        if status_param != "ALL":
            qs = qs.filter(status=status_param)
        qs = qs.order_by("-created_at")
        return Response(TeamRegularizationSerializer(qs, many=True).data)


class _RegularizationDecisionView(TeamAPIView):
    approve = True

    def post(self, request, pk):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data["comment"]

        pending = correction_requests_for_reviewer(request.user).filter(
            status=AttendanceRegularizationRequest.Status.PENDING
        )
        req = get_object_or_404(pending, pk=pk)
        employee = req.user

        if self.approve:
            approve_regularization(request.user, req, comment)
            action = TeamActionAuditLog.Action.REGULARIZATION_APPROVE
            verb = "Approved"
        else:
            reject_regularization(request.user, req, comment)
            action = TeamActionAuditLog.Action.REGULARIZATION_REJECT
            verb = "Rejected"

        record_team_action(
            actor=request.user,
            action=action,
            target=employee,
            object_id=req.pk,
            summary=f"{verb} attendance regularization for {employee.display_name}",
            request=request,
            comment=comment,
            date=str(req.date),
        )
        req.refresh_from_db()
        return Response(
            {"detail": f"{verb} regularization.", "status": req.status},
            status=status.HTTP_200_OK,
        )


class TeamRegularizationApproveView(_RegularizationDecisionView):
    approve = True


class TeamRegularizationRejectView(_RegularizationDecisionView):
    approve = False
