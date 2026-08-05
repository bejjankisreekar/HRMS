"""Shared payroll run-workflow POST actions.

Extracted from the old monolithic PayrollManagementView so both the Dashboard
(quick actions) and the dedicated Runs page can trigger the same workflow
transitions without duplicating logic.
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

from .models import PayrollAuditLog, PayrollRun
from .services import (
    approve_payroll_run,
    generate_payslip_numbers,
    get_or_create_payroll_run,
    lock_payroll_run,
    mark_payroll_paid,
    process_payroll_run,
    record_payroll_action,
)


class PayrollActionMixin:
    """POST-action handlers for the payroll run workflow (calculate → approve →
    mark paid → lock → generate payslips) plus the payroll pay-policy toggle.

    Views using this mixin should call `self.post_payroll_action(request, org)`
    from their `post()` and return its result if not None.
    """

    action_redirect_url_name = "payroll:runs"

    def _redirect_back(self, request):
        y = request.POST.get("year") or request.GET.get("year")
        m = request.POST.get("month") or request.GET.get("month")
        url = reverse(self.action_redirect_url_name)
        if y and m:
            return redirect(f"{url}?year={y}&month={m}")
        return redirect(url)

    def _filters_from_request(self, request):
        from .analytics import PayrollFilters

        if request.method == "POST" and (request.POST.get("year") or request.POST.get("month")):
            today = timezone.localdate()
            year = int(request.POST.get("year") or today.year)
            month = int(request.POST.get("month") or today.month)
            return PayrollFilters(year=year, month=month)
        return PayrollFilters.from_request(request)

    def _get_run(self, request, org):
        filters = self._filters_from_request(request)
        return PayrollRun.objects.filter(
            organization=org, year=filters.year, month=filters.month
        ).first()

    def _run_required_error(self, request):
        messages.error(
            request,
            "No payroll run exists for this period yet. Use 'Calculate' to create it first.",
        )
        return self._redirect_back(request)

    def post_payroll_action(self, request, org):
        """Dispatch a payroll workflow POST action.

        Returns an HttpResponse if `action` was handled, else None (caller
        should fall through to its own action handling or a 400).
        """
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
        if action == "save_payroll_policy" and user.role == User.Role.ADMIN:
            return self._save_payroll_policy(request, org)
        return None

    def _run_payroll(self, request, org):
        filters = self._filters_from_request(request)
        run = get_or_create_payroll_run(org, filters.year, filters.month)
        msg = process_payroll_run(run, request.user)
        record_payroll_action(
            org, request.user, PayrollAuditLog.Action.PROCESSED,
            f"Payroll processed for {run.period_label}",
            period=run.period_label, request=request, employees=run.employee_count,
        )
        messages.success(request, msg)
        return self._redirect_back(request)

    def _approve_payroll(self, request, org):
        run = self._get_run(request, org)
        if run is None:
            return self._run_required_error(request)
        msg = approve_payroll_run(run, request.user, request.POST.get("comment", ""))
        messages.success(request, msg)
        return self._redirect_back(request)

    def _mark_paid(self, request, org):
        from apps.dashboard.notification_service import send_notification

        run = self._get_run(request, org)
        if run is None:
            return self._run_required_error(request)
        msg = mark_payroll_paid(run)
        for slip in run.payslips.select_related("user"):
            send_notification(
                slip.user,
                source_key=f"payroll_paid_{run.pk}",
                title="Payroll completed",
                message=f"Your salary for {run.period_label} has been processed and marked paid.",
                url=reverse("payroll:payslips"),
                icon="wallet",
            )
        record_payroll_action(
            org, request.user, PayrollAuditLog.Action.PROCESSED,
            f"Payroll marked paid for {run.period_label}",
            period=run.period_label, request=request,
        )
        messages.success(request, msg)
        return self._redirect_back(request)

    def _lock_payroll(self, request, org):
        run = self._get_run(request, org)
        if run is None:
            return self._run_required_error(request)
        msg = lock_payroll_run(run)
        record_payroll_action(
            org, request.user, PayrollAuditLog.Action.PROCESSED,
            f"Payroll locked for {run.period_label}",
            period=run.period_label, request=request,
        )
        messages.warning(request, msg)
        return self._redirect_back(request)

    def _generate_payslips(self, request, org):
        from apps.dashboard.notification_service import send_notification

        run = self._get_run(request, org)
        if run is None:
            return self._run_required_error(request)
        count = generate_payslip_numbers(run)
        for slip in run.payslips.filter(generated_at__isnull=False).select_related("user"):
            send_notification(
                slip.user,
                source_key=f"payslip_generated_{slip.pk}",
                title="Payslip generated",
                message=f"Your payslip for {run.period_label} is ready to view.",
                url=reverse("payroll:payslips"),
                icon="file-text",
            )
        record_payroll_action(
            org, request.user, PayrollAuditLog.Action.GENERATED,
            f"Generated {count} payslip(s) for {run.period_label}",
            period=run.period_label, request=request, count=count,
        )
        messages.success(request, f"Generated {count} payslip(s).")
        return self._redirect_back(request)

    def _save_payroll_policy(self, request, org):
        from apps.organizations.models import Organization

        policy = request.POST.get("payroll_lop_policy")
        if policy in Organization.PayrollLopPolicy.values:
            org.payroll_lop_policy = policy
            org.save(update_fields=["payroll_lop_policy", "updated_at"])
            messages.success(request, "Payroll pay policy updated.")
        else:
            messages.error(request, "Invalid payroll policy.")
        return self._redirect_back(request)
