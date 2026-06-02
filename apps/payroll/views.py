import calendar
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import OrganizationRequiredMixin
from apps.organizations.module_utils import ensure_module, plan_includes_module

from .analytics import (
    PayrollFilters,
    approval_steps,
    build_charts,
    build_insights,
    build_summary,
    export_csv,
    filter_options,
    filtered_payslips,
    get_current_run,
    pending_reimbursements,
    recent_revisions,
    salary_components_panel,
    structures_panel,
    table_rows,
)
from .forms import ReimbursementForm, SalaryRevisionForm
from .models import Payslip, PayrollRun, Reimbursement, SalaryRevision
from .services import (
    approve_payroll_run,
    ensure_payroll_setup,
    generate_payslip_numbers,
    get_or_create_payroll_run,
    lock_payroll_run,
    mark_payroll_paid,
    process_payroll_run,
)


class PayrollManagementView(OrganizationRequiredMixin, TemplateView):
    template_name = "payroll/payroll_management.html"
    paginate_by = 20

    def _redirect_back(self, request):
        y = request.POST.get("year") or request.GET.get("year")
        m = request.POST.get("month") or request.GET.get("month")
        url = reverse("payroll:management")
        if y and m:
            return redirect(f"{url}?year={y}&month={m}")
        return redirect(url)

    def dispatch(self, request, *args, **kwargs):
        org = request.user.organization
        if org:
            active, synced = ensure_module(org, "payroll", getattr(request.user, "role", None))
            if synced:
                messages.info(request, "Payroll has been enabled for your organization.")
            elif not active:
                if plan_includes_module(org, "payroll"):
                    messages.warning(
                        request,
                        "Payroll is disabled for your organization. "
                        "An admin can re-enable it under Settings → HR modules.",
                    )
                else:
                    messages.warning(request, "Payroll is not included in your subscription plan.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            filters = PayrollFilters.from_request(request)
            rows = table_rows(filtered_payslips(request.user, filters))
            return export_csv(rows)
        if request.GET.get("payslip"):
            return self._payslip_preview(request)
        return super().get(request, *args, **kwargs)

    def _payslip_preview(self, request):
        slip = get_object_or_404(
            Payslip.objects.select_related("user", "payroll_run").prefetch_related("lines"),
            pk=request.GET.get("payslip"),
            user__organization=request.user.organization,
        )
        if request.user.role == User.Role.EMPLOYEE and slip.user_id != request.user.pk:
            messages.error(request, "You can only view your own payslip.")
            return redirect("payroll:management")
        return render(
            request,
            "payroll/payslip_preview.html",
            {"payslip": slip, "organization": request.user.organization},
        )

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action")
        user = request.user

        if action == "run_payroll" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._run_payroll(request, org)
        if action == "approve_payroll" and user.role == User.Role.ADMIN:
            return self._approve_payroll(request, org)
        if action == "mark_paid" and user.role == User.Role.ADMIN:
            return self._mark_paid(request, org)
        if action == "lock_payroll" and user.role == User.Role.ADMIN:
            return self._lock_payroll(request, org)
        if action == "generate_payslips" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._generate_payslips(request, org)
        if action == "add_reimbursement":
            return self._add_reimbursement(request)
        if action == "approve_reimbursement" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._approve_reimbursement(request)
        if action == "reject_reimbursement" and user.role in (User.Role.ADMIN, User.Role.HR):
            return self._reject_reimbursement(request)
        if action == "salary_revision" and user.role == User.Role.ADMIN:
            return self._salary_revision(request)

        messages.error(request, "Invalid action.")
        return self._redirect_back(request)

    def _filters_from_request(self, request) -> PayrollFilters:
        if request.method == "POST" and (request.POST.get("year") or request.POST.get("month")):
            today = timezone.localdate()
            year = int(request.POST.get("year") or today.year)
            month = int(request.POST.get("month") or today.month)
            return PayrollFilters(year=year, month=month)
        return PayrollFilters.from_request(request)

    def _run_payroll(self, request, org):
        filters = self._filters_from_request(request)
        run = get_or_create_payroll_run(org, filters.year, filters.month)
        msg = process_payroll_run(run, request.user)
        messages.success(request, msg)
        return self._redirect_back(request)

    def _approve_payroll(self, request, org):
        run = self._get_run(request, org)
        msg = approve_payroll_run(run, request.user, request.POST.get("comment", ""))
        messages.success(request, msg)
        return self._redirect_back(request)

    def _mark_paid(self, request, org):
        run = self._get_run(request, org)
        msg = mark_payroll_paid(run)
        messages.success(request, msg)
        return self._redirect_back(request)

    def _lock_payroll(self, request, org):
        run = self._get_run(request, org)
        msg = lock_payroll_run(run)
        messages.warning(request, msg)
        return self._redirect_back(request)

    def _generate_payslips(self, request, org):
        run = self._get_run(request, org)
        count = generate_payslip_numbers(run)
        messages.success(request, f"Generated {count} payslip(s).")
        return self._redirect_back(request)

    def _get_run(self, request, org) -> PayrollRun:
        filters = self._filters_from_request(request)
        return get_object_or_404(
            PayrollRun,
            organization=org,
            year=filters.year,
            month=filters.month,
        )

    def _add_reimbursement(self, request):
        if request.user.role == User.Role.ADMIN:
            messages.error(request, "Admins approve reimbursements; submit as HR or employee.")
            return self._redirect_back(request)
        form = ReimbursementForm(request.POST, request.FILES)
        if form.is_valid():
            reimb = form.save(commit=False)
            reimb.user = request.user
            reimb.save()
            messages.success(request, "Reimbursement claim submitted.")
        else:
            messages.error(request, "Invalid reimbursement form.")
        return self._redirect_back(request)

    def _approve_reimbursement(self, request):
        reimb = get_object_or_404(Reimbursement, pk=request.POST.get("reimbursement_id"))
        reimb.status = Reimbursement.Status.APPROVED
        reimb.reviewed_by = request.user
        reimb.reviewed_at = timezone.now()
        reimb.save()
        messages.success(request, "Reimbursement approved.")
        return self._redirect_back(request)

    def _reject_reimbursement(self, request):
        reimb = get_object_or_404(Reimbursement, pk=request.POST.get("reimbursement_id"))
        reimb.status = Reimbursement.Status.REJECTED
        reimb.reviewed_by = request.user
        reimb.reviewed_at = timezone.now()
        reimb.save()
        messages.warning(request, "Reimbursement rejected.")
        return self._redirect_back(request)

    def _salary_revision(self, request):
        target = get_object_or_404(User, pk=request.POST.get("user_id"), organization=request.user.organization)
        form = SalaryRevisionForm(request.POST)
        if form.is_valid():
            from .services import get_active_salary

            profile = get_active_salary(target)
            rev = form.save(commit=False)
            rev.user = target
            rev.previous_ctc = profile.monthly_ctc
            rev.status = SalaryRevision.Status.APPROVED
            rev.approved_by = request.user
            rev.save()
            profile.monthly_ctc = rev.new_ctc
            profile.save(update_fields=["monthly_ctc"])
            messages.success(request, f"Salary revised for {target.choice_label}.")
        else:
            messages.error(request, "Invalid salary revision.")
        return self._redirect_back(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        ensure_payroll_setup(org)

        filters = PayrollFilters.from_request(self.request)
        run = get_current_run(org, filters)
        qs = filtered_payslips(user, filters)
        paginator = Paginator(table_rows(qs), self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page") or 1)

        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("export", None)
        query.pop("payslip", None)

        charts = build_charts(user, filters)
        is_admin = user.role == User.Role.ADMIN
        is_finance = user.role in (User.Role.ADMIN, User.Role.HR)

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
                "payroll_run": run,
                "approval_steps": approval_steps(run),
                "salary_components": salary_components_panel(org),
                "salary_structures": structures_panel(org),
                "pending_reimbursements": pending_reimbursements(user),
                "recent_revisions": recent_revisions(org),
                "reimbursement_form": ReimbursementForm(),
                "is_admin": is_admin,
                "is_finance": is_finance,
                "can_process": is_finance,
                "can_employee_claim": user.role in (User.Role.HR, User.Role.EMPLOYEE),
                "today": timezone.localdate(),
                "month_choices": [(i, calendar.month_name[i]) for i in range(1, 13)],
            }
        )
        return context
