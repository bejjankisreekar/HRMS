"""Serializers for the manager team API."""

from __future__ import annotations

from rest_framework import serializers

from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
from apps.leaves.models import LeaveRequest


class TeamMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    employee_id = serializers.CharField()
    name = serializers.CharField(source="display_name")
    email = serializers.EmailField()
    role = serializers.CharField()
    actual_role = serializers.CharField(source="role")
    display_role = serializers.SerializerMethodField()
    department = serializers.CharField(source="department_name")
    designation = serializers.CharField(source="designation_label")
    phone = serializers.CharField()

    def get_display_role(self, obj) -> str:
        from apps.accounts.role_labels import role_display_for

        return role_display_for(obj.role, getattr(obj, "organization", None))


class TeamAttendanceSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField()
    employee = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "user_id",
            "employee",
            "date",
            "status",
            "check_in",
            "check_out",
            "break_minutes",
        ]


class TeamLeaveRequestSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField()
    employee = serializers.CharField(source="user.display_name", read_only=True)
    leave_type = serializers.CharField(source="leave_type.name", read_only=True)

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
            "applied_at",
        ]


class TeamRegularizationSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField()
    employee = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = AttendanceRegularizationRequest
        fields = [
            "id",
            "user_id",
            "employee",
            "date",
            "requested_check_in",
            "requested_check_out",
            "requested_status",
            "reason",
            "status",
            "created_at",
        ]


class DecisionSerializer(serializers.Serializer):
    """Optional comment for an approve / reject action."""

    comment = serializers.CharField(required=False, allow_blank=True, default="")
