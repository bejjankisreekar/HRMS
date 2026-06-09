from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, ListView, TemplateView, View

from apps.accounts.hierarchy import (
    attendance_team_for,
    can_manage_team_attendance,
    can_review_attendance_corrections,
    can_view_team_attendance,
    has_direct_reports,
    staff_list_for,
)
from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.attendance.forms import RegularizationRequestForm
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest, WorkShift
from apps.attendance.services import (
    approve_regularization,
    build_employee_attendance_stats,
    period_bounds,
    reject_regularization,
    submit_regularization,
)
from apps.attendance.services import pending_corrections_for

from .attendance_forms import AssignShiftForm, WorkShiftForm, _staff_for_shift_assign
from .attendance_utils import (
    analyze_lateness,
    apply_break_action,
    apply_team_attendance_action,
    combine_date_and_time,
    compute_working_hours,
    ensure_default_shift,
    format_time_display,
    get_attendance_report_queryset,
    get_effective_shift,
    get_shift_assignment_roster,
    get_team_attendance_rows,
    get_visible_attendance_rows,
    filter_team_rows_by_shift,
    get_active_shift_meta,
    build_shift_attendance_filters,
    enrich_attendance_row,
    format_total_minutes,
    parse_attendance_date,
    shift_timing_info,
    sum_team_working_minutes,
    resolve_attendance_target,
    set_default_shift,
    summarize_report_rows,
    summarize_team_rows,
)
from apps.accounts.models import StaffAuditLog, User
from .forms import StaffCreateForm
from .staff_services import log_staff_action
from .staff_filters import (
    apply_staff_list_filters,
    staff_filter_options,
    staff_list_base_queryset,
)
from .mixins import AdminOrHRRequiredMixin, AdminRequiredMixin, OrganizationRequiredMixin
from .org_dashboard_utils import get_org_admin_dashboard_data
from .professional_dashboard_utils import get_professional_dashboard_context
from .starter_dashboard_utils import get_starter_dashboard_context


class DashboardRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        user: User = request.user
        if user.role == User.Role.SUPER_ADMIN:
            return redirect("dashboard:superadmin")
        if user.role == User.Role.ADMIN:
            org = user.organization
            if org and org.subscription_plan in (
                Organization.SubscriptionPlan.PROFESSIONAL,
                Organization.SubscriptionPlan.GROWTH,
            ):
                return redirect("dashboard:professional_admin")
            return redirect("dashboard:starter_admin")
        if user.role == User.Role.HR:
            return redirect("dashboard:attendance_team")
        return redirect("dashboard:employee")


class OrgAdminDashboardView(OrganizationRequiredMixin, TemplateView):
    template_name = "dashboard/org_admin.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_org_admin_dashboard_data(self.request.user))
        context["today"] = timezone.localdate()
        return context


class StarterAdminDashboardView(AdminRequiredMixin, TemplateView):
    """Starter Plan dashboard for small teams (<50 employees)."""

    template_name = "dashboard/starter_admin.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_starter_dashboard_context(self.request.user))
        return context


class ProfessionalAdminDashboardView(AdminRequiredMixin, TemplateView):
    """Professional Plan enterprise dashboard for mid-size organizations."""

    template_name = "dashboard/professional_admin.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_professional_dashboard_context(self.request.user))
        return context


class EmployeeDashboardView(OrganizationRequiredMixin, TemplateView):
    template_name = "dashboard/employee.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.role != User.Role.EMPLOYEE:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from .employee_dashboard_utils import get_employee_dashboard_context

        context = super().get_context_data(**kwargs)
        context.update(get_employee_dashboard_context(self.request.user))
        return context


class SettingsView(OrganizationRequiredMixin, TemplateView):
    template_name = "dashboard/settings.html"

    def get_context_data(self, **kwargs):
        from apps.organizations.models import Department
        from apps.organizations.module_utils import plan_includes_module

        context = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        context["organization"] = org
        context["is_admin"] = user.role == User.Role.ADMIN
        context["is_hr"] = user.role == User.Role.HR
        if org:
            context["dept_label"] = org.department_label
            context["dept_label_plural"] = org.department_label_plural
            context["department_count"] = Department.objects.filter(organization=org).count()
            context["plan_has_leave"] = plan_includes_module(org, "leave")
            context["plan_has_payroll"] = plan_includes_module(org, "payroll")
        return context


class ModuleSettingsView(AdminRequiredMixin, TemplateView):
    """Admin: enable or disable leave and payroll modules for the org."""

    template_name = "dashboard/module_settings.html"

    def get_context_data(self, **kwargs):
        from apps.organizations.module_utils import plan_includes_module

        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        context["organization"] = org
        context["plan_has_leave"] = plan_includes_module(org, "leave")
        context["plan_has_payroll"] = plan_includes_module(org, "payroll")
        return context

    def post(self, request, *args, **kwargs):
        from apps.organizations.module_utils import plan_includes_module

        org = request.user.organization
        updates: list[str] = []
        if plan_includes_module(org, "leave"):
            org.leave_management_enabled = request.POST.get("leave_management_enabled") == "on"
            updates.append("leave_management_enabled")
        if plan_includes_module(org, "payroll"):
            org.payroll_enabled = request.POST.get("payroll_enabled") == "on"
            updates.append("payroll_enabled")
        if updates:
            updates.append("updated_at")
            org.save(update_fields=updates)
            messages.success(request, "HR module settings saved.")
        return redirect("dashboard:module_settings")


class StaffCreateView(AdminOrHRRequiredMixin, FormView):
    template_name = "dashboard/staff_create.html"
    form_class = StaffCreateForm

    def get_context_data(self, **kwargs):
        from apps.dashboard.staff_services import get_staff_create_context

        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        context.update(get_staff_create_context(org, self.request.user))
        context["organization"] = org
        context["is_hr_creator"] = self.request.user.role == User.Role.HR
        context["dept_label"] = org.department_label
        context["dept_label_plural"] = org.department_label_plural
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.request.user.organization
        kwargs["created_by"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        self.created_user = user
        log_staff_action(
            organization=self.request.user.organization,
            actor=self.request.user,
            target=user,
            action=StaffAuditLog.Action.CREATE,
            summary=f"Created {user.display_name} ({user.get_role_display()})",
        )
        messages.success(self.request, f"Created {user.get_role_display()} user: {user.display_name}")
        return super().form_valid(form)

    def get_success_url(self):
        user = getattr(self, "created_user", None)
        if user:
            return reverse("dashboard:staff_detail", kwargs={"pk": user.pk})
        return reverse("dashboard:staff_list")


class AttendanceBaseMixin:
    """Shared attendance helpers for my vs team pages."""

    template_name = "dashboard/attendance.html"
    redirect_url_name = "dashboard:attendance"

    def _redirect_with_date(self, on_date, shift: str | None = None):
        url = reverse(self.redirect_url_name)
        params: list[str] = []
        if on_date != timezone.localdate():
            params.append(f"date={on_date.isoformat()}")
        period = self.request.GET.get("period") or self.request.POST.get("period")
        if period and self.redirect_url_name == "dashboard:attendance":
            params.append(f"period={period}")
        shift = shift or self.request.GET.get("shift") or self.request.POST.get("shift")
        if shift and shift != "all":
            params.append(f"shift={shift}")
        if params:
            return redirect(f"{url}?{'&'.join(params)}")
        return redirect(url)

    def _base_context(self, user, on_date):
        from apps.organizations.models import Organization

        org = user.organization
        attendance_mode = getattr(org, "attendance_mode", "") or Organization.AttendanceMode.TIME_BASED
        return {
            "selected_date": on_date,
            "prev_date": on_date - timedelta(days=1),
            "next_date": on_date + timedelta(days=1),
            "today": timezone.localdate(),
            "attendance_url_name": self.redirect_url_name,
            "can_review_corrections": can_review_attendance_corrections(user),
            "status_choices": AttendanceRecord.Status.choices,
            "pending_corrections_count": (
                pending_corrections_for(user).count()
                if can_review_attendance_corrections(user)
                else 0
            ),
            "month_label": on_date.strftime("%B %Y"),
            "attendance_mode": attendance_mode,
            "is_status_based": attendance_mode == Organization.AttendanceMode.STATUS_BASED,
        }

    def _self_attendance_context(self, user, on_date):
        ensure_default_shift(user.organization)
        period = self.request.GET.get("period", "month")
        if period not in ("day", "week", "month"):
            period = "month"
        stats_from, stats_to = period_bounds(on_date, period)
        today_record = AttendanceRecord.objects.filter(user=user, date=on_date).first()
        shift = get_effective_shift(user)
        my_row = enrich_attendance_row(user, today_record, on_date)
        history = list(
            AttendanceRecord.objects.filter(
                user=user, date__gte=stats_from, date__lte=stats_to
            ).order_by("-date")
        )
        ctx = {
            "is_team_view": False,
            "today_record": today_record,
            "my_shift": shift,
            "my_shift_timing": shift_timing_info(shift),
            "my_lateness": my_row["lateness"],
            "my_hours": my_row["working_hours"],
            "my_login_time": my_row["login_time"],
            "my_logout_time": my_row["logout_time"],
            "my_row": my_row,
            "history_period": period,
            "stats_from": stats_from,
            "stats_to": stats_to,
            "employee_stats": build_employee_attendance_stats(user, stats_from, stats_to),
            "history_rows": [enrich_attendance_row(user, rec, rec.date) for rec in history],
            "records": history,
            "my_regularizations": list(
                AttendanceRegularizationRequest.objects.filter(user=user).order_by("-created_at")[:10]
            ),
            "regularization_form": RegularizationRequestForm(initial={"date": on_date}),
            "page_title": "My attendance",
            "page_subtitle": user.display_name,
            "show_staff_attendance_link": user.role in (User.Role.ADMIN, User.Role.HR),
            "has_team_link": has_direct_reports(user) and not can_manage_team_attendance(user),
        }
        return ctx

    def _team_attendance_context(self, user, on_date):
        from apps.organizations.models import Department

        can_mark = can_manage_team_attendance(user)
        if can_mark:
            all_team_rows = get_team_attendance_rows(user, on_date)
        else:
            all_team_rows = get_visible_attendance_rows(user, on_date)

        # ── Shift filter ──
        selected_shift = self.request.GET.get("shift", "all")
        shift_filters = build_shift_attendance_filters(all_team_rows)
        team_rows = filter_team_rows_by_shift(all_team_rows, selected_shift)

        # ── Department filter (admin only — HR sees only their assigned employees) ──
        dept_filter = self.request.GET.get("dept", "all")
        departments = []
        if user.role == User.Role.ADMIN:
            departments = list(
                Department.objects.filter(organization=user.organization, is_active=True)
                .order_by("sort_order", "name")
                .values("id", "name")
            )
            if dept_filter != "all":
                team_rows = [
                    r for r in team_rows
                    if str(getattr(r["member"].department_id, "hex", r["member"].department_id) or "")
                    == dept_filter
                    or str(r["member"].department_id or "") == dept_filter
                ]

        # ── Status filter ──
        status_filter = self.request.GET.get("status", "all")
        if status_filter != "all":
            if status_filter == "UNMARKED":
                team_rows = [r for r in team_rows if not r.get("is_marked")]
            else:
                team_rows = [
                    r for r in team_rows
                    if r.get("record") and r["record"].status == status_filter
                ]

        # ── Role filter (admin: show HR-only, Employee-only, or all) ──
        role_filter = self.request.GET.get("role", "all")
        if role_filter != "all" and user.role == User.Role.ADMIN:
            team_rows = [r for r in team_rows if r["member"].role == role_filter]

        if user.role == User.Role.ADMIN:
            page_title = "Staff attendance"
            page_subtitle = "Mark and manage attendance for all HR and employees"
        elif user.role == User.Role.HR:
            page_title = "Staff attendance"
            page_subtitle = "Mark attendance for employees assigned to you"
        else:
            page_title = "Team attendance"
            page_subtitle = "View attendance for your direct reportees"

        return {
            "is_team_view": True,
            "can_mark_team": can_mark,
            "all_team_rows": all_team_rows,
            "team_rows": team_rows,
            "shift_filters": shift_filters,
            "selected_shift": selected_shift,
            "active_shift_meta": get_active_shift_meta(shift_filters, selected_shift),
            "team_summary": summarize_team_rows(team_rows),
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "is_admin": user.role == User.Role.ADMIN,
            "team_total_hours": format_total_minutes(sum_team_working_minutes(team_rows)),
            "show_my_attendance_link": False,
            # Filter context
            "departments": departments,
            "dept_filter": dept_filter,
            "status_filter": status_filter,
            "role_filter": role_filter,
        }


class MyAttendanceView(AttendanceBaseMixin, OrganizationRequiredMixin, TemplateView):
    """Personal attendance: check-in/out, analytics, correction requests.

    Org Admins do not have personal attendance records — they are redirected to
    the full team attendance view instead.
    """

    redirect_url_name = "dashboard:attendance"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
            # Preserve date param so the team view opens on the same date
            qs = request.GET.urlencode()
            url = reverse("dashboard:attendance_team")
            if qs:
                url = f"{url}?{qs}"
            return redirect(url)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        on_date = parse_attendance_date(request.POST.get("date"))
        action = request.POST.get("action", "")

        if action == "request_regularization":
            form = RegularizationRequestForm(request.POST)
            if form.is_valid():
                try:
                    submit_regularization(
                        user,
                        on_date=form.cleaned_data["date"],
                        reason=form.cleaned_data["reason"],
                        requested_check_in=form.cleaned_data.get("requested_check_in"),
                        requested_check_out=form.cleaned_data.get("requested_check_out"),
                        requested_status=form.cleaned_data.get("requested_status") or "",
                    )
                    messages.success(request, "Correction request submitted for approval.")
                except ValueError as exc:
                    messages.error(request, str(exc))
            else:
                messages.error(request, "Could not submit correction request. Check the form.")
            return self._redirect_with_date(on_date)

        if action in ("check_in", "set_check_in", "check_out", "set_check_out", "set_times"):
            messages.info(
                request,
                "Attendance is marked by HR. Submit a correction request below if something is wrong.",
            )
            return self._redirect_with_date(on_date)

        messages.error(request, "Invalid action.")
        return self._redirect_with_date(on_date)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        on_date = parse_attendance_date(self.request.GET.get("date"))
        context.update(self._base_context(user, on_date))
        context.update(self._self_attendance_context(user, on_date))
        return context


class TeamAttendanceView(AttendanceBaseMixin, OrganizationRequiredMixin, TemplateView):
    """HR/Admin: mark staff attendance. Managers: read-only reportee view."""

    redirect_url_name = "dashboard:attendance_team"

    def dispatch(self, request, *args, **kwargs):
        # Let OrganizationRequiredMixin handle anonymous users (redirect to login)
        # before touching role-dependent helpers, which AnonymousUser lacks.
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        user = request.user
        if not can_manage_team_attendance(user) and not has_direct_reports(user):
            return redirect("dashboard:attendance")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        on_date = parse_attendance_date(request.POST.get("date"))
        action = request.POST.get("action", "")

        if not can_manage_team_attendance(user):
            messages.error(request, "You can view team attendance only.")
            return self._redirect_with_date(on_date)

        # ── Bulk save (edit-mode "Save all") ───────────────────────
        if action == "bulk_save":
            return self._handle_bulk_save(request, user, on_date)

        if request.POST.get("user_id"):
            target = resolve_attendance_target(user, request.POST.get("user_id"))
            if not target:
                messages.error(request, "Invalid team member.")
                return self._redirect_with_date(on_date)

            # ── Break actions ──────────────────────────────────────
            if action in ("add_break", "end_break", "edit_break", "delete_break"):
                msg = apply_break_action(
                    manager=user,
                    target=target,
                    on_date=on_date,
                    action=action,
                    break_type=request.POST.get("break_type", "OTHER"),
                    break_start=request.POST.get("break_start"),
                    break_end=request.POST.get("break_end"),
                    break_note=request.POST.get("break_note", ""),
                    break_id=request.POST.get("break_id"),
                    end_time_str=request.POST.get("end_time"),
                )
                if any(x in msg.lower() for x in ("invalid", "first", "after", "missing", "not found")):
                    messages.error(request, msg)
                else:
                    messages.success(request, msg)
                return self._redirect_with_date(on_date)

            # ── Attendance actions ─────────────────────────────────
            msg = apply_team_attendance_action(
                user,
                target,
                on_date,
                action,
                request.POST.get("status", ""),
                check_in_time=request.POST.get("check_in_time"),
                check_out_time=request.POST.get("check_out_time"),
            )
            if any(x in msg.lower() for x in ("invalid", "first", "after", "enter")):
                messages.error(request, msg)
            elif "already" in msg.lower():
                messages.info(request, msg)
            else:
                messages.success(request, msg)
            return self._redirect_with_date(on_date)

        messages.error(request, "Invalid action.")
        return self._redirect_with_date(on_date)

    def _handle_bulk_save(self, request, user, on_date):
        """Apply check-in/out and status edits for every changed row in one save."""
        clear_statuses = (AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.LEAVE)
        changed = 0
        errors = 0
        for uid in request.POST.getlist("uid"):
            target = resolve_attendance_target(user, uid)
            if not target:
                continue

            ci = (request.POST.get(f"checkin_{uid}") or "").strip()
            co = (request.POST.get(f"checkout_{uid}") or "").strip()
            st = (request.POST.get(f"status_{uid}") or "").strip()
            ci0 = (request.POST.get(f"checkin_orig_{uid}") or "").strip()
            co0 = (request.POST.get(f"checkout_orig_{uid}") or "").strip()
            st0 = (request.POST.get(f"status_orig_{uid}") or "").strip()

            times_changed = ci != ci0 or co != co0
            status_changed = bool(st) and st != st0
            if not times_changed and not status_changed:
                continue

            row_changed = False
            # Absent/Leave clears any times — apply status only.
            if status_changed and st in clear_statuses:
                apply_team_attendance_action(user, target, on_date, "set_status", status=st)
                row_changed = True
            else:
                if times_changed and (ci or co):
                    msg = apply_team_attendance_action(
                        user, target, on_date, "set_times",
                        check_in_time=ci or None,
                        check_out_time=co or None,
                    )
                    if any(x in msg.lower() for x in ("after", "first", "enter")):
                        errors += 1
                    else:
                        row_changed = True
                if status_changed:
                    apply_team_attendance_action(user, target, on_date, "set_status", status=st)
                    row_changed = True
            if row_changed:
                changed += 1

        if changed:
            messages.success(request, f"Saved attendance for {changed} member{'s' if changed != 1 else ''}.")
        if errors:
            messages.error(request, f"{errors} row{'s' if errors != 1 else ''} skipped — check-out must be after check-in.")
        if not changed and not errors:
            messages.info(request, "No changes to save.")
        return self._redirect_with_date(on_date)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        on_date = parse_attendance_date(self.request.GET.get("date"))
        context.update(self._base_context(user, on_date))
        context.update(self._team_attendance_context(user, on_date))
        return context


# Backwards-compatible alias (my attendance page)
AttendanceView = MyAttendanceView


class AttendanceCorrectionsView(OrganizationRequiredMixin, TemplateView):
    """HR/Admin/Manager: approve or reject attendance correction requests."""

    template_name = "dashboard/attendance_corrections.html"

    def dispatch(self, request, *args, **kwargs):
        # Let OrganizationRequiredMixin handle anonymous users (redirect to login)
        # before touching role-dependent helpers, which AnonymousUser lacks.
        if request.user.is_authenticated and not can_review_attendance_corrections(request.user):
            messages.error(request, "You do not have access to attendance corrections.")
            return redirect("dashboard:attendance")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        req_id = request.POST.get("request_id")
        action = request.POST.get("action")
        comment = request.POST.get("comment", "")

        try:
            req = AttendanceRegularizationRequest.objects.select_related("user").get(pk=req_id)
        except AttendanceRegularizationRequest.DoesNotExist:
            messages.error(request, "Request not found.")
            return redirect("dashboard:attendance_corrections")

        try:
            if action == "approve":
                approve_regularization(user, req, comment)
                messages.success(request, f"Approved correction for {req.user.display_name}.")
            elif action == "reject":
                reject_regularization(user, req, comment)
                messages.success(request, f"Rejected correction for {req.user.display_name}.")
            else:
                messages.error(request, "Invalid action.")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect("dashboard:attendance_corrections")

    def get_context_data(self, **kwargs):
        from apps.accounts.hierarchy import correction_requests_for_reviewer

        context = super().get_context_data(**kwargs)
        reviewer = self.request.user
        qs = correction_requests_for_reviewer(reviewer)
        context["pending_requests"] = qs.filter(
            status=AttendanceRegularizationRequest.Status.PENDING
        ).order_by("-created_at")
        context["recent_requests"] = qs.exclude(
            status=AttendanceRegularizationRequest.Status.PENDING
        ).order_by("-reviewed_at")[:20]
        context["is_admin"] = reviewer.role == User.Role.ADMIN
        return context


class AttendanceSettingsView(AdminRequiredMixin, TemplateView):
    """Admin: attendance marking rules for HR."""

    template_name = "dashboard/attendance_settings.html"

    def post(self, request, *args, **kwargs):
        from apps.organizations.models import Organization

        org = request.user.organization

        if request.POST.get("action") == "save_mode":
            mode = request.POST.get("attendance_mode")
            if mode not in Organization.AttendanceMode.values:
                mode = Organization.AttendanceMode.TIME_BASED
            org.attendance_mode = mode
            org.save(update_fields=["attendance_mode", "updated_at"])
            messages.success(
                request,
                f"Saved. Attendance tracking method is now {org.get_attendance_mode_display()}.",
            )
            return redirect("dashboard:attendance_settings")

        org.hr_self_in_mark_attendance = request.POST.get("hr_self_in_mark_attendance") == "on"
        org.save(update_fields=["hr_self_in_mark_attendance", "updated_at"])
        label = "shown" if org.hr_self_in_mark_attendance else "hidden"
        messages.success(request, f"Saved. HR self row in mark attendance is now {label}.")
        return redirect("dashboard:attendance_settings")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["organization"] = self.request.user.organization
        return context


class WorkCalendarView(AdminOrHRRequiredMixin, TemplateView):
    """Admin/HR: organization weekend policy and holiday calendar."""

    template_name = "dashboard/work_calendar.html"

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action")

        if action == "save_weekend":
            from .work_calendar_forms import WeekendPolicyForm

            form = WeekendPolicyForm(request.POST, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, "Weekend policy saved.")
            else:
                messages.error(request, "Could not save weekend policy. Check the form.")
            return redirect("dashboard:work_calendar")

        if action == "add_holiday":
            from apps.leaves.forms import HolidayForm

            form = HolidayForm(request.POST, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, f"Holiday published: {form.cleaned_data['name']}.")
            else:
                messages.error(request, "Invalid holiday data.")
            return redirect("dashboard:work_calendar")

        if action == "delete_holiday":
            from apps.leaves.models import Holiday

            hol = Holiday.objects.filter(
                pk=request.POST.get("holiday_id"),
                organization=org,
            ).first()
            if hol:
                name = hol.name
                hol.delete()
                messages.success(request, f"Removed holiday: {name}.")
            return redirect("dashboard:work_calendar")

        messages.error(request, "Invalid action.")
        return redirect("dashboard:work_calendar")

    def get_context_data(self, **kwargs):
        from apps.attendance.work_calendar import calendar_preview, weekend_policy_summary
        from apps.leaves.forms import HolidayForm
        from apps.leaves.models import Holiday

        from .work_calendar_forms import WeekendPolicyForm

        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        today = timezone.localdate()
        cal_year = int(self.request.GET.get("year") or today.year)
        cal_month = int(self.request.GET.get("month") or today.month)
        if cal_month < 1:
            cal_month, cal_year = 12, cal_year - 1
        if cal_month > 12:
            cal_month, cal_year = 1, cal_year + 1

        context.update(
            {
                "organization": org,
                "weekend_form": WeekendPolicyForm(organization=org),
                "holiday_form": HolidayForm(organization=org),
                "org_holidays": list(Holiday.objects.filter(organization=org).order_by("date")),
                "weekend_summary": weekend_policy_summary(org),
                "calendar_weeks": calendar_preview(org, cal_year, cal_month),
                "cal_year": cal_year,
                "cal_month": cal_month,
                "cal_prev": {"year": cal_year if cal_month > 1 else cal_year - 1, "month": cal_month - 1 if cal_month > 1 else 12},
                "cal_next": {"year": cal_year if cal_month < 12 else cal_year + 1, "month": cal_month + 1 if cal_month < 12 else 1},
                "can_manage_calendar": True,
            }
        )
        return context


class AttendanceShiftsView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/attendance_shifts.html"

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        ensure_default_shift(org)
        action = request.POST.get("action", "")

        if action == "create_shift":
            form = WorkShiftForm(request.POST, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, f"Created shift: {form.instance.name}")
            else:
                messages.error(request, "Could not create shift. Check the form.")
        elif action == "set_default":
            try:
                shift = WorkShift.objects.get(pk=request.POST.get("shift_id"), organization=org)
                set_default_shift(org, shift)
                messages.success(request, f"'{shift.name}' is now the default shift for everyone without an assigned shift.")
            except WorkShift.DoesNotExist:
                messages.error(request, "Shift not found.")
        elif action == "assign_shift":
            form = AssignShiftForm(request.POST, organization=org)
            if form.is_valid():
                form.save()
                count = len(form.cleaned_data["users"])
                shift_name = form.cleaned_data["shift"].name
                messages.success(request, f"Updated shift “{shift_name}” for {count} people.")
            else:
                messages.error(request, "Could not assign shift. Select a shift and at least one person.")
        elif action == "clear_shift":
            try:
                user = User.objects.get(
                    pk=request.POST.get("user_id"),
                    organization=org,
                    role__in=[User.Role.HR, User.Role.EMPLOYEE],
                )
                user.work_shift = None
                user.save(update_fields=["work_shift"])
                messages.success(request, f"Cleared shift for {user.choice_label}; they will use the org default.")
            except User.DoesNotExist:
                messages.error(request, "User not found.")
        elif action == "delete_shift":
            try:
                shift = WorkShift.objects.get(pk=request.POST.get("shift_id"), organization=org)
                if shift.is_default:
                    messages.error(request, "Cannot delete the default shift. Set another as default first.")
                else:
                    name = shift.name
                    shift.delete()
                    messages.success(request, f"Deleted shift: {name}")
            except WorkShift.DoesNotExist:
                messages.error(request, "Shift not found.")

        return redirect("dashboard:attendance_shifts")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ensure_default_shift(org)
        context["shifts"] = WorkShift.objects.filter(organization=org)
        context["shift_form"] = WorkShiftForm(organization=org)
        selected_shift = self.request.GET.get("shift", "")
        context["assign_form"] = AssignShiftForm(
            organization=org,
            selected_shift_id=selected_shift or None,
        )
        context["staff_assign_list"] = list(
            _staff_for_shift_assign(org).select_related("work_shift")
        )
        preselected = set()
        if selected_shift:
            preselected = set(
                User.objects.filter(organization=org, work_shift_id=selected_shift).values_list(
                    "pk", flat=True
                )
            )
        context["preselected_staff_ids"] = list(preselected)
        context["assignment_roster"] = get_shift_assignment_roster(org)
        context["default_shift"] = WorkShift.objects.filter(organization=org, is_default=True).first()
        return context


class AttendanceChartDataView(OrganizationRequiredMixin, View):
    """JSON endpoint for attendance chart data. Supports team and individual views."""

    def get(self, request, *args, **kwargs):
        from django.http import JsonResponse
        from datetime import date as date_cls
        from collections import defaultdict

        user = request.user
        chart_type = request.GET.get("type", "team_trend")
        date_str = request.GET.get("date", timezone.localdate().isoformat())
        try:
            on_date = date_cls.fromisoformat(date_str)
        except ValueError:
            on_date = timezone.localdate()

        days = min(int(request.GET.get("days", "30") or "30"), 90)

        is_admin_or_hr = user.role in (User.Role.ADMIN, User.Role.HR)

        if chart_type == "team_day":
            if not is_admin_or_hr:
                return JsonResponse({"error": "Forbidden"}, status=403)
            return JsonResponse(self._team_day(user, on_date))

        if chart_type == "team_trend":
            if not is_admin_or_hr:
                return JsonResponse({"error": "Forbidden"}, status=403)
            return JsonResponse(self._team_trend(user, on_date, days))

        if chart_type == "employee":
            user_id = request.GET.get("user_id")
            if user_id and is_admin_or_hr:
                target = User.objects.filter(pk=user_id, organization=user.organization).first()
                if not target:
                    return JsonResponse({"error": "Not found"}, status=404)
            else:
                target = user
            return JsonResponse(self._employee(target, on_date, days))

        return JsonResponse({"error": "Invalid type"}, status=400)

    def _get_org_employees(self, user):
        if user.role == User.Role.ADMIN:
            return User.objects.filter(
                organization=user.organization,
                role__in=[User.Role.HR, User.Role.EMPLOYEE],
                is_active=True,
            )
        return User.objects.filter(
            organization=user.organization,
            assigned_hr=user,
            is_active=True,
        )

    def _team_day(self, user, on_date):
        employees = self._get_org_employees(user)
        total = employees.count()
        records = AttendanceRecord.objects.filter(user__in=employees, date=on_date)
        counts = {"PRESENT": 0, "ABSENT": 0, "HALF_DAY": 0, "LEAVE": 0, "WFH": 0}
        for rec in records:
            if rec.status in counts:
                counts[rec.status] += 1
        marked = sum(counts.values())
        return {
            "type": "team_day",
            "date": on_date.isoformat(),
            "labels": ["Present", "Absent", "Half Day", "Leave", "WFH", "Unmarked"],
            "values": [
                counts["PRESENT"], counts["ABSENT"], counts["HALF_DAY"],
                counts["LEAVE"], counts["WFH"], max(0, total - marked),
            ],
            "total": total,
        }

    def _team_trend(self, user, on_date, days):
        from collections import defaultdict
        employees = self._get_org_employees(user)
        start = on_date - timedelta(days=days - 1)
        records = AttendanceRecord.objects.filter(
            user__in=employees, date__gte=start, date__lte=on_date
        ).values("date", "status")
        by_date = defaultdict(lambda: defaultdict(int))
        for r in records:
            by_date[r["date"]][r["status"]] += 1
        labels, present, absent, half_day, leave, wfh = [], [], [], [], [], []
        for i in range(days):
            d = start + timedelta(days=i)
            c = by_date.get(d, {})
            labels.append(d.strftime("%d %b"))
            present.append(c.get("PRESENT", 0))
            absent.append(c.get("ABSENT", 0))
            half_day.append(c.get("HALF_DAY", 0))
            leave.append(c.get("LEAVE", 0))
            wfh.append(c.get("WFH", 0))
        return {
            "type": "team_trend",
            "labels": labels,
            "present": present,
            "absent": absent,
            "half_day": half_day,
            "leave": leave,
            "wfh": wfh,
        }

    def _employee(self, target, on_date, days):
        from django.utils import timezone as tz
        start = on_date - timedelta(days=days - 1)
        records = {
            r.date: r
            for r in AttendanceRecord.objects.filter(
                user=target, date__gte=start, date__lte=on_date
            )
        }
        labels, hours, check_ins, check_outs, statuses = [], [], [], [], []
        for i in range(days):
            d = start + timedelta(days=i)
            rec = records.get(d)
            labels.append(d.strftime("%d %b"))
            if rec:
                ci = tz.localtime(rec.check_in) if rec.check_in else None
                co = tz.localtime(rec.check_out) if rec.check_out else None
                if ci and co:
                    mins = max(0, int((co - ci).total_seconds() // 60) - (rec.break_minutes or 0))
                    hours.append(round(mins / 60, 2))
                else:
                    hours.append(0)
                check_ins.append(ci.strftime("%H:%M") if ci else None)
                check_outs.append(co.strftime("%H:%M") if co else None)
                statuses.append(rec.status)
            else:
                hours.append(None)
                check_ins.append(None)
                check_outs.append(None)
                statuses.append(None)
        return {
            "type": "employee",
            "user_id": str(target.pk),
            "name": target.display_name,
            "labels": labels,
            "hours": hours,
            "check_ins": check_ins,
            "check_outs": check_outs,
            "statuses": statuses,
        }


class AttendanceReportView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "dashboard/attendance_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        date_from = parse_attendance_date(self.request.GET.get("from") or str(today.replace(day=1)))
        date_to = parse_attendance_date(self.request.GET.get("to") or str(today))
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        member_id = self.request.GET.get("member", "")
        rows = get_attendance_report_queryset(user, date_from, date_to, member_id or None)
        context["report_rows"] = rows
        context["report_summary"] = summarize_report_rows(rows)
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["selected_member"] = member_id
        context["team_members"] = attendance_team_for(user)
        context["is_admin"] = user.role == User.Role.ADMIN
        selected_label = ""
        if member_id:
            member = context["team_members"].filter(pk=member_id).first()
            if member:
                selected_label = member.choice_label
        context["selected_member_label"] = selected_label
        return context

