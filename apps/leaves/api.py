"""REST API for leave management (mounted at /api/leaves/, /api/leave-types/,
and /api/settings/leave-workflow/).

All endpoints are session/JWT-authenticated and tenant-scoped: every queryset
filters by the caller's organization, and visibility follows the same rules as
the server-rendered UI (employee = own data; manager = direct reports; HR/Admin
= organization).
"""

from __future__ import annotations

from datetime import datetime

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.hierarchy import is_manager
from apps.accounts.models import User
from apps.team.audit import record_team_action
from apps.team.models import TeamActionAuditLog

from .approval_policy import user_can_act_on_leave
from .models import LeaveBalance, LeaveRequest, LeaveType
from .services import (
    cancel_leave,
    ensure_balances_for_user,
    get_balance,
    approve_leave,
    leave_team_for,
    manager_team_leave_requests,
    reject_leave,
    submit_leave_request,
    sync_org_staff_balances,
)


# ── Permissions ───────────────────────────────────────────────────────────────


class IsOrgMember(BasePermission):
    def has_permission(self, request, view) -> bool:
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "organization_id", None))


class IsOrgAdminOrHR(IsOrgMember):
    message = "Only Organization Admins and HR can perform this action."

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.user.role in (
            User.Role.ADMIN,
            User.Role.HR,
        )


class IsOrgAdmin(IsOrgMember):
    message = "Only Organization Admins can perform this action."

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.user.role == User.Role.ADMIN


# ── Serializers ───────────────────────────────────────────────────────────────


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type = serializers.CharField(source="leave_type.name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    remaining = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)

    class Meta:
        model = LeaveBalance
        fields = [
            "id",
            "leave_type",
            "leave_type_code",
            "year",
            "allocated",
            "used",
            "adjusted",
            "carried_forward",
            "remaining",
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee = serializers.CharField(source="user.display_name", read_only=True)
    user_id = serializers.UUIDField(read_only=True)
    leave_type = serializers.CharField(source="leave_type.name", read_only=True)
    stage = serializers.CharField(source="current_stage_label", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "user_id",
            "employee",
            "leave_type",
            "start_date",
            "end_date",
            "total_days",
            "half_day",
            "reason",
            "status",
            "stage",
            "applied_at",
            "reviewed_at",
            "review_comment",
        ]


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            "id",
            "name",
            "code",
            "description",
            "color",
            "annual_quota",
            "carry_forward_max",
            "accrual_monthly",
            "gender_eligibility",
            "applicable_to",
            "requires_attachment",
            "is_paid",
            "is_active",
            "sort_order",
        ]
        read_only_fields = ["id"]


class ApplySerializer(serializers.Serializer):
    leave_type = serializers.UUIDField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    half_day = serializers.ChoiceField(
        choices=LeaveRequest.HalfDay.choices, default=LeaveRequest.HalfDay.NONE
    )
    reason = serializers.CharField(max_length=500)
    emergency_contact = serializers.CharField(required=False, allow_blank=True, default="")


class DecisionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class BalanceAdjustSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    leave_type = serializers.UUIDField()
    adjustment = serializers.DecimalField(max_digits=6, decimal_places=1)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ── Employee endpoints ────────────────────────────────────────────────────────


class MyBalancesView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        year = int(request.query_params.get("year") or timezone.localdate().year)
        ensure_balances_for_user(request.user, year)
        qs = LeaveBalance.objects.filter(user=request.user, year=year).select_related("leave_type")
        return Response(LeaveBalanceSerializer(qs, many=True).data)


class MyRequestsView(APIView):
    permission_classes = [IsOrgMember]

    def get(self, request):
        qs = (
            LeaveRequest.objects.filter(user=request.user)
            .select_related("user", "leave_type")
            .prefetch_related("approvals")
        )
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return Response(LeaveRequestSerializer(qs, many=True).data)


class ApplyView(APIView):
    permission_classes = [IsOrgMember]

    def post(self, request):
        if request.user.role == User.Role.ADMIN:
            return Response(
                {"detail": "Admins approve leave; they do not apply here."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave_type = get_object_or_404(
            LeaveType, pk=data["leave_type"], organization=request.user.organization, is_active=True
        )
        req, msg = submit_leave_request(
            user=request.user,
            leave_type=leave_type,
            start_date=data["start_date"],
            end_date=data["end_date"],
            half_day=data["half_day"],
            reason=data["reason"],
            emergency_contact=data["emergency_contact"],
        )
        if not req:
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        record_team_action(
            actor=request.user,
            action=TeamActionAuditLog.Action.LEAVE_APPLY,
            target=request.user,
            object_id=req.pk,
            summary=f"{request.user.display_name} applied for {leave_type.name}",
            request=request,
            leave_type=leave_type.code,
        )
        return Response(
            {"detail": msg, **LeaveRequestSerializer(req).data}, status=status.HTTP_201_CREATED
        )


class CancelView(APIView):
    permission_classes = [IsOrgMember]

    def post(self, request, pk):
        req = get_object_or_404(
            LeaveRequest, pk=pk, user__organization=request.user.organization
        )
        if req.user_id != request.user.pk and request.user.role not in (
            User.Role.ADMIN,
            User.Role.HR,
        ):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        msg = cancel_leave(req, request.user)
        req.refresh_from_db()
        if req.status == LeaveRequest.Status.CANCELLED:
            record_team_action(
                actor=request.user,
                action=TeamActionAuditLog.Action.LEAVE_CANCEL,
                target=req.user,
                object_id=req.pk,
                summary=f"Cancelled leave for {req.user.display_name}",
                request=request,
                leave_type=req.leave_type.code,
            )
        return Response({"detail": msg, "status": req.status})


# ── Manager / HR / Admin endpoints ────────────────────────────────────────────


class TeamRequestsView(APIView):
    """Manager: direct reports. HR/Admin: their org-wide leave team."""

    permission_classes = [IsOrgMember]

    def get(self, request):
        user = request.user
        if user.role in (User.Role.ADMIN, User.Role.HR):
            team_ids = list(leave_team_for(user).values_list("pk", flat=True))
            qs = LeaveRequest.objects.filter(user_id__in=team_ids).select_related(
                "user", "leave_type"
            )
        elif is_manager(user):
            qs = manager_team_leave_requests(user)
        else:
            return Response(
                {"detail": "You do not manage a team."}, status=status.HTTP_403_FORBIDDEN
            )
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.upper())
        qs = qs.prefetch_related("approvals").order_by("-applied_at")
        return Response(LeaveRequestSerializer(qs, many=True).data)


class _DecisionView(APIView):
    permission_classes = [IsOrgMember]
    approve = True

    def post(self, request, pk):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data["comment"]

        req = get_object_or_404(
            LeaveRequest, pk=pk, user__organization=request.user.organization
        )
        if not user_can_act_on_leave(request.user, req):
            return Response(
                {"detail": "You are not authorized to act on this request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if self.approve:
            msg = approve_leave(req, request.user, comment)
            action = TeamActionAuditLog.Action.LEAVE_APPROVE
            verb = "Approved"
        else:
            msg = reject_leave(req, request.user, comment)
            action = TeamActionAuditLog.Action.LEAVE_REJECT
            verb = "Rejected"
        record_team_action(
            actor=request.user,
            action=action,
            target=req.user,
            object_id=req.pk,
            summary=f"{verb} leave for {req.user.display_name}",
            request=request,
            comment=comment,
            leave_type=req.leave_type.code,
        )
        req.refresh_from_db()
        return Response({"detail": msg, "status": req.status})


class ApproveView(_DecisionView):
    approve = True


class RejectView(_DecisionView):
    approve = False


class BalanceAdjustView(APIView):
    permission_classes = [IsOrgAdminOrHR]

    def post(self, request):
        serializer = BalanceAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data["adjustment"]:
            return Response(
                {"detail": "Adjustment cannot be zero."}, status=status.HTTP_400_BAD_REQUEST
            )
        target = get_object_or_404(
            User, pk=data["user_id"], organization=request.user.organization, is_active=True
        )
        lt = get_object_or_404(
            LeaveType, pk=data["leave_type"], organization=request.user.organization
        )
        bal = get_balance(target, lt)
        bal.adjusted += data["adjustment"]
        bal.save(update_fields=["adjusted"])
        record_team_action(
            actor=request.user,
            action=TeamActionAuditLog.Action.BALANCE_ADJUST,
            target=target,
            object_id=bal.pk,
            summary=(
                f"Adjusted {lt.name} balance for {target.display_name} by {data['adjustment']:+}"
            ),
            request=request,
            reason=data["reason"],
            leave_type=lt.code,
            adjustment=str(data["adjustment"]),
        )
        return Response(LeaveBalanceSerializer(bal).data)


# ── Leave types (Admin/HR) ────────────────────────────────────────────────────


class LeaveTypeListCreateView(APIView):
    permission_classes = [IsOrgAdminOrHR]

    def get(self, request):
        qs = LeaveType.objects.filter(organization=request.user.organization).order_by(
            "sort_order", "name"
        )
        return Response(LeaveTypeSerializer(qs, many=True).data)

    def post(self, request):
        serializer = LeaveTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lt = serializer.save(organization=request.user.organization)
        sync_org_staff_balances(request.user.organization, lt)
        return Response(LeaveTypeSerializer(lt).data, status=status.HTTP_201_CREATED)


class LeaveTypeDetailView(APIView):
    permission_classes = [IsOrgAdminOrHR]

    def put(self, request, pk):
        lt = get_object_or_404(LeaveType, pk=pk, organization=request.user.organization)
        serializer = LeaveTypeSerializer(lt, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lt = serializer.save()
        sync_org_staff_balances(request.user.organization, lt)
        return Response(LeaveTypeSerializer(lt).data)


# ── Workflow settings (Admin) ────────────────────────────────────────────────


class LeaveWorkflowSettingsView(APIView):
    permission_classes = [IsOrgAdmin]

    _FIELDS = (
        "leave_approval_require_manager",
        "leave_approval_require_hr",
        "leave_approval_require_admin",
        "leave_auto_approve_without_manager",
    )

    def _payload(self, org) -> dict:
        data = {f: getattr(org, f) for f in self._FIELDS}
        levels = sum(
            1
            for f in (
                "leave_approval_require_manager",
                "leave_approval_require_hr",
                "leave_approval_require_admin",
            )
            if data[f]
        )
        data["approval_type"] = "MULTI_LEVEL" if levels > 1 else "SINGLE_LEVEL"
        return data

    def get(self, request):
        return Response(self._payload(request.user.organization))

    def put(self, request):
        org = request.user.organization
        updates = []
        for f in self._FIELDS:
            if f in request.data:
                setattr(org, f, bool(request.data[f]))
                updates.append(f)
        if not (
            org.leave_approval_require_manager
            or org.leave_approval_require_hr
            or org.leave_approval_require_admin
        ):
            return Response(
                {"detail": "Select at least one approver, or leave will be auto-approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if updates:
            updates.append("updated_at")
            org.save(update_fields=updates)
        return Response(self._payload(org))
