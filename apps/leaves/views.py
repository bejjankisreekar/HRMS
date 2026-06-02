import calendar
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import OrganizationRequiredMixin
from apps.organizations.models import Organization
from apps.organizations.module_utils import ensure_module, plan_includes_module

from .apply_utils import build_apply_preview, get_apply_leave_context, leave_request_reference

from .analytics import (
    LeaveFilters,
    build_calendar_events,
    build_charts,
    build_insights,
    build_summary,
    export_csv,
    filter_options,
    filtered_requests,
    table_rows,
)
from .forms import HolidayForm, LeaveApplyForm, LeaveTypeForm
from .approval_policy import user_can_act_on_leave, user_is_configured_approver
from .models import Holiday, LeaveApproval, LeaveRequest, LeaveType
from .services import (
    approve_leave,
    cancel_leave,
    ensure_balances_for_user,
    reject_leave,
    submit_leave_request,
    sync_org_staff_balances,
)


class LeaveManagementView(OrganizationRequiredMixin, TemplateView):
    template_name = "leaves/leave_management.html"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        org = request.user.organization
        if org and not org.leave_management_enabled:
            messages.warning(request, "Leave management is disabled for your organization.")
        return resp

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            filters = LeaveFilters.from_request(request)
            rows = table_rows(filtered_requests(request.user, filters))
            return export_csv(rows)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action")

        if action == "apply_leave":
            if request.user.role == User.Role.ADMIN:
                messages.error(request, "Admins approve leave requests; they do not apply for leave here.")
                return redirect("leaves:management")
            return self._apply_leave(request, org)
        if action == "approve":
            return self._approve(request)
        if action == "reject":
            return self._reject(request)
        if action == "cancel":
            return self._cancel(request)
        if action == "add_holiday" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._add_holiday(request, org)
        if action == "add_leave_type" and request.user.role == User.Role.ADMIN:
            return self._add_leave_type(request, org)
        if action == "delete_leave_type" and request.user.role == User.Role.ADMIN:
            return self._delete_leave_type(request, org)
        if action == "delete_holiday" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._delete_holiday(request, org)
        if action == "save_approval_workflow" and request.user.role == User.Role.ADMIN:
            return self._save_approval_workflow(request, org)

        messages.error(request, "Invalid action.")
        return redirect("leaves:management")

    def _apply_leave(self, request, org: Organization):
        if request.user.role not in (User.Role.HR, User.Role.EMPLOYEE):
            messages.error(request, "Only HR and employees can apply for leave.")
            return redirect("leaves:management")
        target_user = request.user
        form = LeaveApplyForm(request.POST, request.FILES, organization=org, user=target_user)
        if not form.is_valid():
            messages.error(request, "Please correct the leave form.")
            return redirect("leaves:management")
        req, msg = submit_leave_request(
            user=target_user,
            leave_type=form.cleaned_data["leave_type"],
            start_date=form.cleaned_data["start_date"],
            end_date=form.cleaned_data["end_date"],
            half_day=form.cleaned_data["half_day"],
            reason=form.cleaned_data["reason"],
            emergency_contact=form.cleaned_data.get("emergency_contact", ""),
            attachment=form.cleaned_data.get("attachment"),
            as_draft=bool(request.POST.get("save_draft")),
        )
        if req:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect("leaves:management")

    def _approve(self, request):
        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"), user__organization=request.user.organization)
        if not user_can_act_on_leave(request.user, req):
            messages.error(request, "You are not authorized to approve this request.")
            return redirect("leaves:management")
        msg = approve_leave(req, request.user, request.POST.get("comment", ""))
        messages.success(request, msg)
        return redirect("leaves:management")

    def _reject(self, request):
        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"), user__organization=request.user.organization)
        if not user_can_act_on_leave(request.user, req):
            messages.error(request, "You are not authorized to reject this request.")
            return redirect("leaves:management")
        msg = reject_leave(req, request.user, request.POST.get("comment", ""))
        messages.warning(request, msg)
        return redirect("leaves:management")

    def _cancel(self, request):
        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"))
        msg = cancel_leave(req, request.user)
        messages.info(request, msg)
        return redirect("leaves:management")

    def _add_holiday(self, request, org: Organization):
        form = HolidayForm(request.POST, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, f"Holiday published: {form.cleaned_data['name']}.")
        else:
            messages.error(request, "Invalid holiday data.")
        return redirect("leaves:management")

    def _add_leave_type(self, request, org: Organization):
        form = LeaveTypeForm(request.POST, organization=org)
        if form.is_valid():
            lt = form.save()
            sync_org_staff_balances(org, lt)
            messages.success(request, f"Added leave type: {lt.name}.")
        else:
            messages.error(request, "Could not add leave type. Check the form.")
        return redirect("leaves:management")

    def _delete_leave_type(self, request, org: Organization):
        lt = get_object_or_404(LeaveType, pk=request.POST.get("leave_type_id"), organization=org)
        name = lt.name
        lt.delete()
        messages.success(request, f"Removed leave type: {name}.")
        return redirect("leaves:management")

    def _delete_holiday(self, request, org: Organization):
        hol = get_object_or_404(Holiday, pk=request.POST.get("holiday_id"), organization=org)
        name = hol.name
        hol.delete()
        messages.success(request, f"Removed holiday: {name}.")
        return redirect("leaves:management")

    def _save_approval_workflow(self, request, org: Organization):
        require_manager = request.POST.get("leave_approval_require_manager") == "on"
        require_hr = request.POST.get("leave_approval_require_hr") == "on"
        require_admin = request.POST.get("leave_approval_require_admin") == "on"
        if not (require_manager or require_hr or require_admin):
            messages.error(request, "Select at least one approver, or leave will be auto-approved.")
            return redirect("leaves:management")
        org.leave_approval_require_manager = require_manager
        org.leave_approval_require_hr = require_hr
        org.leave_approval_require_admin = require_admin
        org.save(
            update_fields=[
                "leave_approval_require_manager",
                "leave_approval_require_hr",
                "leave_approval_require_admin",
                "updated_at",
            ]
        )
        messages.success(request, "Leave approval workflow updated.")
        return redirect("leaves:management")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        if user.role != User.Role.ADMIN:
            ensure_balances_for_user(user)

        filters = LeaveFilters.from_request(self.request)
        qs = filtered_requests(user, filters)
        paginator = Paginator(table_rows(qs), self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page") or 1)

        charts = build_charts(user, filters)
        cal_year = int(self.request.GET.get("cal_year") or timezone.localdate().year)
        cal_month = int(self.request.GET.get("cal_month") or timezone.localdate().month)

        year = timezone.localdate().year
        balances = user.leave_balances.filter(year=year).select_related("leave_type")
        org_leave_types = list(
            LeaveType.objects.filter(organization=org, is_active=True).order_by("sort_order", "name")
        )
        org_holidays = list(
            Holiday.objects.filter(organization=org).order_by("date")
        )
        pending_for_me = list(
            LeaveRequest.objects.filter(
                user__organization=org,
                status=LeaveRequest.Status.PENDING,
                approvals__approver=user,
                approvals__status=LeaveApproval.StepStatus.PENDING,
            )
            .distinct()
            .select_related("user", "leave_type")[:15]
        )

        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("export", None)

        context.update(
            {
                "organization": org,
                "filters": filters,
                "filters_get": self.request.GET,
                "filter_query": query.urlencode(),
                "summary": build_summary(user, filters),
                "charts_json": json.dumps(charts),
                "insights": build_insights(user, filters),
                "filter_options": filter_options(user, org),
                "table_rows": page.object_list,
                "page_obj": page,
                "leave_types": LeaveRequest.objects.none(),
                "apply_form": LeaveApplyForm(organization=org, user=user),
                "holiday_form": HolidayForm(organization=org),
                "leave_type_form": LeaveTypeForm(organization=org),
                "org_holidays": org_holidays,
                "show_add_leave_type": self.request.GET.get("add_type") == "1",
                "balances": balances,
                "calendar_events": json.dumps(
                    build_calendar_events(user, cal_year, cal_month, org)
                ),
                "cal_year": cal_year,
                "cal_month": cal_month,
                "pending_approvals": pending_for_me,
                "is_approver": user_is_configured_approver(user),
                "can_apply_leave": user.role in (User.Role.HR, User.Role.EMPLOYEE),
                "is_admin": user.role == User.Role.ADMIN,
                "can_manage_calendar": user.role in (User.Role.ADMIN, User.Role.HR),
                "org_leave_types": org_leave_types,
                "today": timezone.localdate(),
                "view_mode": self.request.GET.get("view", "dashboard"),
                "calendar_weeks": calendar.monthcalendar(cal_year, cal_month),
                "month_name": calendar.month_name[cal_month],
            }
        )
        context["leave_types"] = context["filter_options"]["leave_types"]
        return context


class ApplyLeaveAccessMixin(OrganizationRequiredMixin):
    """HR and employees only — not org admins applying on behalf."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.HR, User.Role.EMPLOYEE):
            messages.error(request, "Only HR and employees can apply for leave.")
            return redirect("leaves:management")
        org = request.user.organization
        if org:
            active, synced = ensure_module(org, "leave", getattr(request.user, "role", None))
            if synced:
                messages.info(request, "Leave management has been enabled for your organization.")
            if not active:
                if plan_includes_module(org, "leave"):
                    messages.warning(
                        request,
                        "Leave management is disabled for your organization. "
                        "An admin can re-enable it under Settings → HR modules.",
                    )
                else:
                    messages.warning(request, "Leave management is not included in your subscription plan.")
                return redirect("leaves:management")
        return super().dispatch(request, *args, **kwargs)


class ApplyLeaveView(ApplyLeaveAccessMixin, TemplateView):
    template_name = "leaves/apply_leave.html"

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        form = LeaveApplyForm(
            request.POST,
            request.FILES,
            organization=org,
            user=request.user,
            apply_page=True,
        )
        if not form.is_valid():
            detail = "; ".join(
                f"{form.fields[field].label or field}: {errs[0]}"
                for field, errs in form.errors.items()
            )
            messages.error(request, detail or "Please correct the errors below.")
            return self.render_to_response(self.get_context_data(form=form))

        as_draft = request.POST.get("action") == "save_draft"
        req, msg = submit_leave_request(
            user=request.user,
            leave_type=form.cleaned_data["leave_type"],
            start_date=form.cleaned_data["start_date"],
            end_date=form.cleaned_data["end_date"],
            half_day=form.cleaned_data["half_day"],
            reason=form.cleaned_data["reason"],
            emergency_contact=form.cleaned_data.get("emergency_contact", ""),
            attachment=form.cleaned_data.get("attachment"),
            as_draft=as_draft,
        )
        if not req:
            messages.error(request, msg)
            return self.render_to_response(self.get_context_data(form=form))

        if as_draft:
            messages.success(request, msg)
            return redirect("leaves:management")

        return redirect("leaves:apply_success", pk=req.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        ensure_balances_for_user(user)

        form = kwargs.get("form") or LeaveApplyForm(
            organization=org,
            user=user,
            apply_page=True,
        )

        apply_ctx = get_apply_leave_context(user)
        context.update(
            {
                "organization": org,
                "form": form,
                "can_apply_leave": True,
                **apply_ctx,
                "leave_types_json": json.dumps(apply_ctx["leave_types_json"]),
                "holiday_dates_json": json.dumps(apply_ctx["holiday_dates"]),
                "preview_api_url": reverse("leaves:apply_preview"),
            }
        )
        return context


class ApplyLeaveSuccessView(ApplyLeaveAccessMixin, TemplateView):
    template_name = "leaves/apply_leave_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        req = get_object_or_404(
            LeaveRequest.objects.select_related("leave_type", "user"),
            pk=self.kwargs["pk"],
            user=self.request.user,
        )
        context.update(
            {
                "leave_request": req,
                "request_ref": leave_request_reference(req),
                "organization": self.request.user.organization,
            }
        )
        return context


class LeaveApplyPreviewAPIView(ApplyLeaveAccessMixin, View):
    def get(self, request, *args, **kwargs):
        from datetime import datetime

        user = request.user
        leave_type_id = request.GET.get("leave_type") or None
        half_day = request.GET.get("half_day") or LeaveRequest.HalfDay.NONE
        start = end = None

        try:
            if request.GET.get("start_date"):
                start = datetime.strptime(request.GET["start_date"], "%Y-%m-%d").date()
            if request.GET.get("end_date"):
                end = datetime.strptime(request.GET["end_date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid date format."}, status=400)

        data = build_apply_preview(
            user,
            leave_type_id=leave_type_id,
            start=start,
            end=end,
            half_day=half_day,
        )
        return JsonResponse(data)
