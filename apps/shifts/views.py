import calendar as _cal
import json
from datetime import timedelta

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
    export_shift_summary_csv,
    filter_options,
    table_rows,
)
from apps.shifts.forms import RotationForm, ShiftAssignForm, ShiftReassignForm, ShiftSwapForm, WorkShiftManageForm
from apps.shifts.models import ShiftAssignment, ShiftChange, ShiftRotation, ShiftSwapRequest
from apps.shifts.services import (
    ShiftFilters,
    apply_rotation,
    apply_user_filters,
    approve_swap,
    auto_schedule_week,
    build_weekly_grid,
    bulk_assign_shift,
    clone_shift,
    reassign_shift,
    schedulable_users,
)


class ShiftReassignView(PlanFeatureRequiredMixin, TemplateView):
    """Dedicated page for reassigning shifts to one or more employees."""

    template_name = "shifts/shift_reassign.html"
    required_feature = "shifts"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if request.user.role not in (User.Role.ADMIN, User.Role.HR):
            messages.error(request, "Access denied.")
            return redirect("shifts:management")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        user = request.user
        form = ShiftReassignForm(request.POST, organization=org, viewer=user)
        if not form.is_valid():
            context = self.get_context_data(form=form)
            return self.render_to_response(context)

        cd = form.cleaned_data
        scope = cd["scope"]
        today = timezone.localdate()

        if scope == ShiftChange.Scope.WEEK:
            date_from = today - timedelta(days=today.weekday())
            date_to = date_from + timedelta(days=6)
        elif scope == ShiftChange.Scope.MONTH:
            date_from = today.replace(day=1)
            last_day = _cal.monthrange(today.year, today.month)[1]
            date_to = today.replace(day=last_day)
        elif scope == ShiftChange.Scope.PERMANENT:
            date_from = date_to = None
        else:
            date_from = cd.get("date_from")
            date_to = cd.get("date_to")

        users_list = list(cd["users"])
        for employee in users_list:
            reassign_shift(
                organization=org,
                user=employee,
                new_shift=cd["new_shift"],
                scope=scope,
                date_from=date_from,
                date_to=date_to,
                assigned_by=user,
                reason=cd.get("reason") or "",
            )

        names = ", ".join(u.display_name for u in users_list[:3])
        if len(users_list) > 3:
            names += f" +{len(users_list) - 3} more"
        messages.success(
            request,
            f"Shift reassigned for {names}: {cd['new_shift'].name}. Employee(s) notified."
        )
        return redirect("shifts:management")

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        user = self.request.user
        from apps.organizations.models import Department
        context["form"] = form or ShiftReassignForm(organization=org, viewer=user)
        context["recent_changes"] = ShiftChange.objects.filter(
            organization=org
        ).select_related("user", "old_shift", "new_shift", "assigned_by")[:20]
        context["departments"] = Department.objects.filter(
            organization=org, is_active=True
        ).order_by("name")
        from apps.attendance.models import WorkShift as _WS
        context["active_shifts"] = _WS.objects.filter(
            organization=org, is_active=True
        ).order_by("name")
        context["can_manage"] = True
        context["page_back_url"] = reverse("shifts:management")
        context["page_back_label"] = "Shifts"
        return context


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
        if request.GET.get("export") == "summary":
            return self._export_summary(request)
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

    def _export_summary(self, request):
        from datetime import date
        org = request.user.organization
        try:
            date_from = date.fromisoformat(request.GET.get("from", ""))
            date_to = date.fromisoformat(request.GET.get("to", ""))
        except ValueError:
            messages.error(request, "Invalid date range for export.")
            return redirect("shifts:management")
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        users = schedulable_users(request.user)
        content = export_shift_summary_csv(org, users, date_from, date_to)
        fname = f"shift-summary-{date_from}-to-{date_to}.csv"
        resp = HttpResponse(content, content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
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
        if action == "reassign_shift" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._reassign_shift(request, org, user)

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

    def _reassign_shift(self, request, org, user):
        form = ShiftReassignForm(request.POST, organization=org, viewer=user)
        if not form.is_valid():
            messages.error(request, "Could not reassign shift — " + "; ".join(
                e for field_errors in form.errors.values() for e in field_errors
            ))
            return self._redirect(request)

        cd = form.cleaned_data
        scope = cd["scope"]
        today = timezone.localdate()

        # Auto-compute date_from / date_to for WEEK and MONTH scopes
        if scope == ShiftChange.Scope.WEEK:
            date_from = today - timedelta(days=today.weekday())
            date_to = date_from + timedelta(days=6)
        elif scope == ShiftChange.Scope.MONTH:
            date_from = today.replace(day=1)
            last_day = _cal.monthrange(today.year, today.month)[1]
            date_to = today.replace(day=last_day)
        elif scope == ShiftChange.Scope.PERMANENT:
            date_from = date_to = None
        else:
            date_from = cd.get("date_from")
            date_to = cd.get("date_to")

        users_list = list(cd["users"])
        for employee in users_list:
            reassign_shift(
                organization=org,
                user=employee,
                new_shift=cd["new_shift"],
                scope=scope,
                date_from=date_from,
                date_to=date_to,
                assigned_by=user,
                reason=cd.get("reason") or "",
            )
        names = ", ".join(u.display_name for u in users_list[:3])
        if len(users_list) > 3:
            names += f" +{len(users_list) - 3} more"
        messages.success(
            request,
            f"Shift reassigned for {names}: {cd['new_shift'].name}. Employee(s) notified."
        )
        return redirect("shifts:management")

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
                "reassign_form": ShiftReassignForm(organization=org, viewer=user),
                "swap_form": ShiftSwapForm(organization=org, requester=user),
                "rotation_form": RotationForm(organization=org),
                "recent_changes": ShiftChange.objects.filter(
                    organization=org
                ).select_related("user", "old_shift", "new_shift", "assigned_by")[:20],
                "can_manage": user.role in (User.Role.ADMIN, User.Role.HR),
                "is_admin": user.role == User.Role.ADMIN,
                "filter_query": request.GET.urlencode(),
            }
        )
        return context
