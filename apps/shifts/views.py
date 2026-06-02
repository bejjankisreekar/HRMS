import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.attendance.models import WorkShift
from apps.dashboard.attendance_utils import ensure_default_shift
from apps.subscriptions.mixins import PlanFeatureRequiredMixin
from apps.shifts.analytics import (
    build_charts,
    build_insights,
    build_summary,
    export_schedule_csv,
    filter_options,
    table_rows,
)
from apps.shifts.forms import RotationForm, ShiftAssignForm, ShiftSwapForm, WorkShiftManageForm
from apps.shifts.models import ShiftAssignment, ShiftRotation, ShiftSwapRequest
from apps.shifts.services import (
    ShiftFilters,
    apply_rotation,
    apply_user_filters,
    approve_swap,
    auto_schedule_week,
    build_weekly_grid,
    bulk_assign_shift,
    clone_shift,
    schedulable_users,
)


class ShiftManagementView(PlanFeatureRequiredMixin, TemplateView):
    template_name = "shifts/shift_management.html"
    required_feature = "shifts"
    paginate_by = 25

    def _redirect(self, request):
        q = request.GET.urlencode()
        url = reverse("shifts:management")
        return redirect(f"{url}?{q}" if q else url)

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            return self._export_csv(request)
        return super().get(request, *args, **kwargs)

    def _export_csv(self, request):
        org = request.user.organization
        filters = ShiftFilters.from_request(request)
        users = apply_user_filters(schedulable_users(request.user), filters)
        rows = table_rows(org, users, filters)
        content = export_schedule_csv(rows)
        resp = HttpResponse(content, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="shift-schedule.csv"'
        return resp

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        user = request.user
        action = request.POST.get("action")

        if action == "create_shift" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._create_shift(request, org)
        if action == "clone_shift" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._clone_shift(request, org)
        if action == "assign_shift" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._assign_shift(request, org, user)
        if action == "auto_schedule" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._auto_schedule(request, org, user)
        if action == "request_swap":
            return self._request_swap(request, org, user)
        if action == "approve_swap" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._approve_swap(request, org, user)
        if action == "reject_swap" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._reject_swap(request, org, user)
        if action == "create_rotation" and user.role == User.Role.ADMIN:
            return self._create_rotation(request, org)

        messages.error(request, "Invalid action.")
        return self._redirect(request)

    def _create_shift(self, request, org):
        form = WorkShiftManageForm(request.POST, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Shift “{form.instance.name}” created.")
        else:
            messages.error(request, "Could not save shift. Check the form.")
        return self._redirect(request)

    def _clone_shift(self, request, org):
        shift = get_object_or_404(WorkShift, pk=request.POST.get("shift_id"), organization=org)
        clone_shift(shift)
        messages.success(request, f"Cloned shift “{shift.name}”.")
        return self._redirect(request)

    def _assign_shift(self, request, org, user):
        form = ShiftAssignForm(request.POST, organization=org, viewer=user)
        if form.is_valid():
            users = list(form.cleaned_data["users"])
            count = bulk_assign_shift(
                organization=org,
                users=users,
                shift=form.cleaned_data["shift"],
                on_date=form.cleaned_data["date"],
                assigned_by=user,
                notes=form.cleaned_data.get("notes") or "",
            )
            messages.success(request, f"Assigned shift to {count} employee(s).")
        else:
            messages.error(request, "Select shift, date, and at least one employee.")
        return self._redirect(request)

    def _auto_schedule(self, request, org, user):
        filters = ShiftFilters.from_request(request)
        users = apply_user_filters(schedulable_users(user), filters)
        count = auto_schedule_week(
            organization=org,
            users=users,
            week_start=filters.date_from,
            assigned_by=user,
        )
        messages.success(request, f"Auto-scheduled {count} shift slot(s).")
        return self._redirect(request)

    def _request_swap(self, request, org, user):
        form = ShiftSwapForm(request.POST, organization=org, requester=user)
        if form.is_valid():
            swap = form.save(commit=False)
            swap.organization = org
            swap.requester = user
            swap.save()
            messages.success(request, "Shift swap request submitted.")
        else:
            messages.error(request, "Could not submit swap request.")
        return self._redirect(request)

    def _approve_swap(self, request, org, user):
        swap = get_object_or_404(
            ShiftSwapRequest,
            pk=request.POST.get("swap_id"),
            organization=org,
            status=ShiftSwapRequest.Status.PENDING,
        )
        approve_swap(swap, user)
        messages.success(request, "Swap approved and schedule updated.")
        return self._redirect(request)

    def _reject_swap(self, request, org, user):
        swap = get_object_or_404(
            ShiftSwapRequest,
            pk=request.POST.get("swap_id"),
            organization=org,
        )
        swap.status = ShiftSwapRequest.Status.REJECTED
        swap.reviewed_by = user
        swap.reviewed_at = timezone.now()
        swap.save()
        messages.success(request, "Swap request rejected.")
        return self._redirect(request)

    def _create_rotation(self, request, org):
        form = RotationForm(request.POST, organization=org)
        if form.is_valid():
            rotation = form.save()
            shift_ids = request.POST.getlist("rotation_shifts")
            for i, sid in enumerate(shift_ids):
                try:
                    shift = WorkShift.objects.get(pk=sid, organization=org)
                    rotation.steps.create(shift=shift, step_order=i)
                except WorkShift.DoesNotExist:
                    pass
            users = apply_user_filters(schedulable_users(request.user), ShiftFilters.from_request(request))
            apply_rotation(rotation, users, ShiftFilters.from_request(request).date_from, 14)
            messages.success(request, f"Rotation “{rotation.name}” created and applied.")
        else:
            messages.error(request, "Could not create rotation.")
        return self._redirect(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        user = request.user
        org = user.organization
        ensure_default_shift(org)
        filters = ShiftFilters.from_request(request)
        users = apply_user_filters(schedulable_users(user), filters)
        summary = build_summary(org, users, filters)
        charts = build_charts(org, users, filters)
        all_rows = table_rows(org, users, filters)
        paginator = Paginator(all_rows, self.paginate_by)
        page = paginator.get_page(request.GET.get("page"))

        pending_swaps = ShiftSwapRequest.objects.filter(
            organization=org, status=ShiftSwapRequest.Status.PENDING
        ).select_related("requester", "current_shift", "requested_shift")[:12]

        context.update(
            {
                "organization": org,
                "filters": filters,
                "filters_get": request.GET,
                "filter_options": filter_options(org, user),
                "summary": summary,
                "insights": build_insights(org, users, summary),
                "charts_json": json.dumps(charts),
                "weekly_grid_json": json.dumps(build_weekly_grid(users, filters.date_from)),
                "shifts": WorkShift.objects.filter(organization=org).order_by("-is_default", "name"),
                "rotations": ShiftRotation.objects.filter(organization=org, is_active=True),
                "pending_swaps": pending_swaps,
                "report_page": page,
                "shift_form": WorkShiftManageForm(organization=org),
                "assign_form": ShiftAssignForm(organization=org, viewer=user),
                "swap_form": ShiftSwapForm(organization=org, requester=user),
                "rotation_form": RotationForm(organization=org),
                "can_manage": user.role in (User.Role.ADMIN, User.Role.HR),
                "is_admin": user.role == User.Role.ADMIN,
                "filter_query": request.GET.urlencode(),
            }
        )
        return context
