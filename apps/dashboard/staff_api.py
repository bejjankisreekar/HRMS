"""Typed JSON APIs for the Employee Directory (card view, saved filters).

The directory list is a DRF endpoint (typed serializer + pagination) reusing the same filter
functions as the server-rendered table, so both stay consistent and tenant-scoped.
"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views import View
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_for

from .mixins import AdminOrHRRequiredMixin  # noqa: F401 (kept for parity / future use)
from .staff_filters import apply_staff_list_filters, staff_list_base_queryset
from .staff_services import can_manage_staff


class IsAdminOrHR(BasePermission):
    message = "Only Organization Admins and HR can view the directory."

    def has_permission(self, request, view) -> bool:
        u = request.user
        return bool(
            u and u.is_authenticated and getattr(u, "organization_id", None)
            and u.role in (User.Role.ADMIN, User.Role.HR)
        )


class StaffDirectorySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    employee_id = serializers.CharField(allow_blank=True)
    name = serializers.CharField(source="display_name")
    username = serializers.CharField(allow_null=True)
    email = serializers.EmailField()
    phone = serializers.CharField(allow_blank=True)
    role = serializers.CharField()
    role_label = serializers.SerializerMethodField()
    department = serializers.CharField(source="department_name", allow_blank=True)
    designation = serializers.CharField(source="designation_label", allow_blank=True)
    branch = serializers.CharField(source="work_location", allow_blank=True)
    grade = serializers.CharField(source="grade_name", allow_blank=True)
    reporting_manager = serializers.SerializerMethodField()
    status = serializers.CharField(source="employment_status")
    status_display = serializers.CharField(source="get_employment_status_display")
    is_active = serializers.BooleanField()
    profile_picture = serializers.SerializerMethodField()
    manageable = serializers.SerializerMethodField()

    def get_role_label(self, obj) -> str:
        return role_display_for(obj.role, getattr(obj, "organization", None))

    def get_reporting_manager(self, obj) -> str:
        return obj.reporting_manager.display_name if obj.reporting_manager_id else ""

    def get_profile_picture(self, obj) -> str:
        return obj.profile_picture.url if obj.profile_picture else ""

    def get_manageable(self, obj) -> bool:
        viewer = self.context.get("viewer")
        return bool(viewer and can_manage_staff(viewer, obj))


class _DirectoryPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100


class StaffDirectoryAPI(APIView):
    """Paginated, filtered directory rows (Admin/HR), tenant-scoped."""

    permission_classes = [IsAdminOrHR]

    def get(self, request):
        user = request.user
        is_hr_view = user.role == User.Role.HR
        qs = staff_list_base_queryset(user).select_related(
            "reporting_manager", "department", "job_grade", "org_designation"
        )
        qs = apply_staff_list_filters(qs, request.GET, is_hr_view=is_hr_view)
        qs = qs.order_by("first_name", "last_name", "username")

        paginator = _DirectoryPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = StaffDirectorySerializer(page, many=True, context={"viewer": user}).data
        return paginator.get_paginated_response(data)


# ── Saved filters (per user + org) ─────────────────────────────────────────────


class SavedFilterAPI(AdminOrHRRequiredMixin, View):
    """List + create saved directory filters for the current user."""

    def _serialize(self, f):
        return {"id": str(f.pk), "name": f.name, "query": f.query}

    def get(self, request):
        from .models import SavedStaffFilter

        rows = SavedStaffFilter.objects.filter(user=request.user, organization=request.user.organization)
        return JsonResponse({"filters": [self._serialize(f) for f in rows]})

    def post(self, request):
        from .models import SavedStaffFilter

        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        name = (body.get("name") or "").strip()[:80]
        if not name:
            return JsonResponse({"error": "Name is required."}, status=400)
        obj, _ = SavedStaffFilter.objects.update_or_create(
            user=request.user,
            name=name,
            defaults={
                "organization": request.user.organization,
                "query": (body.get("query") or "").strip()[:1000],
            },
        )
        return JsonResponse(self._serialize(obj), status=201)


class SavedFilterDeleteAPI(AdminOrHRRequiredMixin, View):
    def post(self, request, pk):
        from .models import SavedStaffFilter

        SavedStaffFilter.objects.filter(
            pk=pk, user=request.user, organization=request.user.organization
        ).delete()
        return JsonResponse({"ok": True})
