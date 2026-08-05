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
from apps.accounts.role_labels import STAFF_SELF_SERVICE_ROLES
from apps.dashboard.mixins import OrganizationRequiredMixin
from apps.organizations.models import Organization
from apps.organizations.module_utils import ensure_module, plan_includes_module
from apps.organizations.fy_utils import get_selected_fy

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


def _audit_leave_event(request, action, leave_request, summary):
    """Record a leave lifecycle event in the team action audit log."""
    from apps.team.audit import record_team_action

    record_team_action(
        actor=request.user,
        action=action,
        target=leave_request.user,
        object_id=leave_request.pk,
        summary=summary,
        request=request,
        leave_type=leave_request.leave_type.code,
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
        export = request.GET.get("export")
        if export in ("csv", "xlsx"):
            fy = get_selected_fy(request)
            filters = LeaveFilters.from_request(request, fy=fy)
            rows = table_rows(filtered_requests(request.user, filters))
            if export == "xlsx":
                from .analytics import export_xlsx

                return export_xlsx(rows)
            return export_csv(rows)
        if export in ("balances_csv", "balances_xlsx") and request.user.role in (
            User.Role.ADMIN,
            User.Role.HR,
        ):
            from .analytics import balance_report_rows, export_balance_csv, export_balance_xlsx

            rows = balance_report_rows(request.user, fy=get_selected_fy(request))
            if export == "balances_xlsx":
                return export_balance_xlsx(rows)
            return export_balance_csv(rows)
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
        if action == "add_leave_type" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._add_leave_type(request, org)
        if action == "edit_leave_type" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._edit_leave_type(request, org)
        if action == "toggle_leave_type" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._toggle_leave_type(request, org)
        if action == "delete_leave_type" and request.user.role == User.Role.ADMIN:
            return self._delete_leave_type(request, org)
        if action == "adjust_balance" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._adjust_balance(request, org)
        if action == "delete_holiday" and request.user.role in (User.Role.ADMIN, User.Role.HR):
            return self._delete_holiday(request, org)
        if action == "save_approval_workflow" and request.user.role == User.Role.ADMIN:
            return self._save_approval_workflow(request, org)

        messages.error(request, "Invalid action.")
        return redirect("leaves:management")

    def _apply_leave(self, request, org: Organization):
        if request.user.role not in STAFF_SELF_SERVICE_ROLES:
            messages.error(request, "Only HR, managers, and employees can apply for leave.")
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
            if req.status != LeaveRequest.Status.DRAFT:
                from apps.team.models import TeamActionAuditLog

                _audit_leave_event(
                    request,
                    TeamActionAuditLog.Action.LEAVE_APPLY,
                    req,
                    f"{request.user.display_name} applied for {req.leave_type.name}",
                )
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect("leaves:management")

    def _approve(self, request):
        from apps.team.models import TeamActionAuditLog

        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"), user__organization=request.user.organization)
        if not user_can_act_on_leave(request.user, req):
            messages.error(request, "You are not authorized to approve this request.")
            return redirect("leaves:management")
        msg = approve_leave(req, request.user, request.POST.get("comment", ""))
        _audit_leave_event(
            request,
            TeamActionAuditLog.Action.LEAVE_APPROVE,
            req,
            f"Approved leave for {req.user.display_name}",
        )
        messages.success(request, msg)
        return redirect("leaves:management")

    def _reject(self, request):
        from apps.team.models import TeamActionAuditLog

        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"), user__organization=request.user.organization)
        if not user_can_act_on_leave(request.user, req):
            messages.error(request, "You are not authorized to reject this request.")
            return redirect("leaves:management")
        msg = reject_leave(req, request.user, request.POST.get("comment", ""))
        _audit_leave_event(
            request,
            TeamActionAuditLog.Action.LEAVE_REJECT,
            req,
            f"Rejected leave for {req.user.display_name}",
        )
        messages.warning(request, msg)
        return redirect("leaves:management")

    def _cancel(self, request):
        from apps.team.models import TeamActionAuditLog

        req = get_object_or_404(LeaveRequest, pk=request.POST.get("request_id"))
        was_actionable = req.status in (LeaveRequest.Status.PENDING, LeaveRequest.Status.DRAFT)
        msg = cancel_leave(req, request.user)
        if was_actionable and req.status == LeaveRequest.Status.CANCELLED:
            _audit_leave_event(
                request,
                TeamActionAuditLog.Action.LEAVE_CANCEL,
                req,
                f"Cancelled leave for {req.user.display_name}",
            )
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

    def _edit_leave_type(self, request, org: Organization):
        lt = get_object_or_404(LeaveType, pk=request.POST.get("leave_type_id"), organization=org)
        form = LeaveTypeForm(request.POST, organization=org, instance=lt)
        if form.is_valid():
            lt = form.save()
            sync_org_staff_balances(org, lt)
            messages.success(request, f"Updated leave type: {lt.name}.")
        else:
            messages.error(request, "Could not update leave type. Check the form.")
        return redirect("leaves:management")

    def _toggle_leave_type(self, request, org: Organization):
        lt = get_object_or_404(LeaveType, pk=request.POST.get("leave_type_id"), organization=org)
        lt.is_active = not lt.is_active
        lt.save(update_fields=["is_active"])
        state = "activated" if lt.is_active else "deactivated"
        messages.success(request, f"Leave type {lt.name} {state}.")
        return redirect("leaves:management")

    def _adjust_balance(self, request, org: Organization):
        from decimal import Decimal, InvalidOperation

        from apps.team.audit import record_team_action
        from apps.team.models import TeamActionAuditLog

        from .models import LeaveBalance
        from .services import get_balance

        target = get_object_or_404(
            User, pk=request.POST.get("user_id"), organization=org, is_active=True
        )
        lt = get_object_or_404(LeaveType, pk=request.POST.get("leave_type_id"), organization=org)
        try:
            delta = Decimal(request.POST.get("adjustment") or "0")
        except InvalidOperation:
            messages.error(request, "Invalid adjustment value.")
            return redirect("leaves:management")
        reason = (request.POST.get("reason") or "").strip()
        if not delta:
            messages.error(request, "Adjustment cannot be zero.")
            return redirect("leaves:management")

        bal = get_balance(target, lt)
        bal.adjusted += delta
        bal.save(update_fields=["adjusted"])
        record_team_action(
            actor=request.user,
            action=TeamActionAuditLog.Action.BALANCE_ADJUST,
            target=target,
            object_id=bal.pk,
            summary=f"Adjusted {lt.name} balance for {target.display_name} by {delta:+}",
            request=request,
            reason=reason,
            leave_type=lt.code,
            adjustment=str(delta),
        )
        messages.success(
            request,
            f"Adjusted {lt.name} for {target.display_name} by {delta:+} day(s). "
            f"Remaining: {bal.remaining}.",
        )
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
        org.leave_auto_approve_without_manager = (
            request.POST.get("leave_auto_approve_without_manager") == "on"
        )
        org.save(
            update_fields=[
                "leave_approval_require_manager",
                "leave_approval_require_hr",
                "leave_approval_require_admin",
                "leave_auto_approve_without_manager",
                "updated_at",
            ]
        )
        messages.success(request, "Leave approval workflow updated.")
        from django.utils.http import url_has_allowed_host_and_scheme

        next_url = request.POST.get("next") or ""
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return redirect(next_url)
        return redirect("leaves:management")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        if user.role != User.Role.ADMIN:
            ensure_balances_for_user(user)

        fy = get_selected_fy(self.request)
        filters = LeaveFilters.from_request(self.request, fy=fy)
        qs = filtered_requests(user, filters)
        paginator = Paginator(table_rows(qs), self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page") or 1)

        charts = build_charts(user, filters)
        cal_year = int(self.request.GET.get("cal_year") or (fy["start_year"] if fy else timezone.localdate().year))
        cal_month = int(self.request.GET.get("cal_month") or timezone.localdate().month)

        from .models import AttendanceLeaveDeduction
        year = fy["start_year"] if fy else timezone.localdate().year
        balances = user.leave_balances.filter(year=year).select_related("leave_type")
        attendance_deductions = (
            AttendanceLeaveDeduction.objects.filter(user=user, leave_balance__year=year)
            .select_related("leave_balance__leave_type")
            .order_by("-attendance_date")[:50]
        )
        # Admin/HR manage the policy panel, so they also see deactivated types.
        types_qs = LeaveType.objects.filter(organization=org)
        if user.role not in (User.Role.ADMIN, User.Role.HR):
            types_qs = types_qs.filter(is_active=True)
        org_leave_types = list(types_qs.order_by("sort_order", "name"))

        edit_type_obj = None
        edit_type_form = None
        if user.role in (User.Role.ADMIN, User.Role.HR) and self.request.GET.get("edit_type"):
            edit_type_obj = LeaveType.objects.filter(
                organization=org, pk=self.request.GET["edit_type"]
            ).first()
            if edit_type_obj:
                edit_type_form = LeaveTypeForm(organization=org, instance=edit_type_obj)
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
                "can_apply_leave": user.role in STAFF_SELF_SERVICE_ROLES,
                "is_admin": user.role == User.Role.ADMIN,
                "is_hr": user.role == User.Role.HR,
                "can_manage_types": user.role in (User.Role.ADMIN, User.Role.HR),
                "edit_type_obj": edit_type_obj,
                "edit_type_form": edit_type_form,
                "can_manage_calendar": user.role in (User.Role.ADMIN, User.Role.HR),
                "org_leave_types": org_leave_types,
                "today": timezone.localdate(),
                "attendance_deductions": attendance_deductions,
                "view_mode": self.request.GET.get("view", "dashboard"),
                "calendar_weeks": calendar.monthcalendar(cal_year, cal_month),
                "month_name": calendar.month_name[cal_month],
            }
        )
        context["leave_types"] = context["filter_options"]["leave_types"]
        return context


class ApplyLeaveAccessMixin(OrganizationRequiredMixin):
    """HR, managers, and employees only — not org admins applying on behalf."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in STAFF_SELF_SERVICE_ROLES:
            messages.error(request, "Only HR, managers, and employees can apply for leave.")
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

        from apps.team.models import TeamActionAuditLog

        _audit_leave_event(
            request,
            TeamActionAuditLog.Action.LEAVE_APPLY,
            req,
            f"{request.user.display_name} applied for {req.leave_type.name}",
        )
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
