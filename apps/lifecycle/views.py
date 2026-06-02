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
from apps.lifecycle.analytics import (
    build_insights,
    export_csv,
    filter_options,
    offboarding_charts,
    offboarding_summary,
    offboarding_table_rows,
    onboarding_charts,
    onboarding_summary,
    onboarding_table_rows,
)
from apps.lifecycle.forms import (
    AssetForm,
    DocumentUploadForm,
    ExitInterviewForm,
    OnboardingTaskForm,
    StartOffboardingForm,
    StartOnboardingForm,
)
from apps.lifecycle.models import (
    AssetAllocation,
    ClearanceApproval,
    EmployeeDocument,
    GeneratedLetter,
    OffboardingWorkflow,
    OnboardingTask,
    OnboardingWorkflow,
    PolicyAcceptance,
    SettlementRecord,
)
from apps.lifecycle.services import (
    LifecycleFilters,
    can_manage_lifecycle,
    compute_settlement,
    generate_letter,
    recalc_offboarding_progress,
    recalc_onboarding_progress,
    start_offboarding,
    start_onboarding,
)


class OnboardingManagementView(OrganizationRequiredMixin, TemplateView):
    template_name = "lifecycle/onboarding.html"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            org = request.user.organization
            filters = LifecycleFilters.from_request(request, mode="onboarding")
            rows = onboarding_table_rows(org, filters)
            content = export_csv(
                rows,
                ["employee_id", "name", "department", "joining_date", "status", "progress", "pending_tasks"],
            )
            resp = HttpResponse(content, content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="onboarding-report.csv"'
            return resp
        if request.GET.get("letter"):
            return self._view_letter(request)
        return super().get(request, *args, **kwargs)

    def _view_letter(self, request):
        letter = get_object_or_404(
            GeneratedLetter,
            pk=request.GET.get("letter"),
            offboarding__organization=request.user.organization,
        )
        return render(
            request,
            "lifecycle/letter_preview.html",
            {"letter": letter, "organization": request.user.organization},
        )

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        user = request.user
        action = request.POST.get("action")

        if not can_manage_lifecycle(user) and action not in ("request_offboarding", "upload_document"):
            messages.error(request, "Permission denied.")
            return redirect(request.path)

        handlers = {
            "start_onboarding": self._start_onboarding,
            "start_offboarding": self._start_offboarding,
            "complete_task": self._complete_task,
            "verify_document": self._verify_document,
            "accept_policy": self._accept_policy,
            "send_welcome": self._send_welcome,
            "allocate_asset": self._allocate_asset,
            "approve_clearance": self._approve_clearance,
            "compute_settlement": self._compute_settlement,
            "generate_experience": self._generate_experience,
            "generate_relieving": self._generate_relieving,
            "approve_settlement": self._approve_settlement,
        }
        handler = handlers.get(action)
        if handler:
            return handler(request, org, user)
        messages.error(request, "Invalid action.")
        return redirect(request.path)

    def _redirect(self, request):
        q = request.GET.urlencode()
        return redirect(f"{request.path}?{q}" if q else request.path)

    def _start_onboarding(self, request, org, user):
        form = StartOnboardingForm(request.POST, organization=org)
        if form.is_valid():
            start_onboarding(
                organization=org,
                user=form.cleaned_data["user"],
                joining_date=form.cleaned_data["joining_date"],
                created_by=user,
                branch=form.cleaned_data.get("branch") or "",
            )
            messages.success(request, "Onboarding workflow started.")
        else:
            messages.error(request, "Could not start onboarding.")
        return redirect("lifecycle:onboarding")

    def _start_offboarding(self, request, org, user):
        form = StartOffboardingForm(request.POST, organization=org)
        if form.is_valid():
            start_offboarding(
                organization=org,
                user=form.cleaned_data["user"],
                last_working_day=form.cleaned_data["last_working_day"],
                reason=form.cleaned_data["resignation_reason"],
                created_by=user,
                notes=form.cleaned_data.get("notes") or "",
            )
            messages.success(request, "Offboarding request created.")
        else:
            messages.error(request, "Could not create offboarding.")
        return redirect("lifecycle:offboarding")

    def _complete_task(self, request, org, user):
        task = get_object_or_404(OnboardingTask, pk=request.POST.get("task_id"), onboarding__organization=org)
        task.status = OnboardingTask.Status.DONE
        task.completed_at = timezone.now()
        task.save()
        recalc_onboarding_progress(task.onboarding)
        messages.success(request, "Task marked complete.")
        return self._redirect(request)

    def _verify_document(self, request, org, user):
        doc = get_object_or_404(EmployeeDocument, pk=request.POST.get("doc_id"), onboarding__organization=org)
        doc.verify_status = EmployeeDocument.VerifyStatus.VERIFIED
        doc.verified_by = user
        doc.save()
        recalc_onboarding_progress(doc.onboarding)
        messages.success(request, "Document verified.")
        return self._redirect(request)

    def _accept_policy(self, request, org, user):
        pol = get_object_or_404(
            PolicyAcceptance, pk=request.POST.get("policy_id"), onboarding__organization=org
        )
        pol.accepted = True
        pol.accepted_at = timezone.now()
        pol.signature_note = f"Accepted by {user.display_name}"
        pol.save()
        recalc_onboarding_progress(pol.onboarding)
        messages.success(request, "Policy accepted.")
        return self._redirect(request)

    def _send_welcome(self, request, org, user):
        wf = get_object_or_404(OnboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        wf.welcome_sent = True
        wf.save(update_fields=["welcome_sent"])
        recalc_onboarding_progress(wf)
        messages.success(request, "Welcome workflow marked as sent.")
        return self._redirect(request)

    def _allocate_asset(self, request, org, user):
        wf = get_object_or_404(OnboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        form = AssetForm(request.POST)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.organization = org
            asset.user = wf.user
            asset.onboarding = wf
            asset.status = AssetAllocation.Status.ALLOCATED
            asset.save()
            messages.success(request, "Asset allocated.")
        return self._redirect(request)

    def _approve_clearance(self, request, org, user):
        c = get_object_or_404(
            ClearanceApproval, pk=request.POST.get("clearance_id"), offboarding__organization=org
        )
        c.status = ClearanceApproval.Status.APPROVED
        c.approved_by = user
        c.save()
        recalc_offboarding_progress(c.offboarding)
        messages.success(request, f"{c.get_department_display()} clearance approved.")
        return redirect("lifecycle:offboarding")

    def _compute_settlement(self, request, org, user):
        ob = get_object_or_404(OffboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        compute_settlement(ob)
        messages.success(request, "Settlement calculated.")
        return redirect("lifecycle:offboarding")

    def _approve_settlement(self, request, org, user):
        ob = get_object_or_404(OffboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        s = compute_settlement(ob)
        s.status = SettlementRecord.Status.APPROVED
        s.approved_by = user
        s.save()
        messages.success(request, "Settlement approved.")
        return redirect("lifecycle:offboarding")

    def _generate_experience(self, request, org, user):
        ob = get_object_or_404(OffboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        letter = generate_letter(ob, GeneratedLetter.LetterType.EXPERIENCE, user)
        return redirect(f"{reverse('lifecycle:onboarding')}?letter={letter.pk}")

    def _generate_relieving(self, request, org, user):
        ob = get_object_or_404(OffboardingWorkflow, pk=request.POST.get("workflow_id"), organization=org)
        letter = generate_letter(ob, GeneratedLetter.LetterType.RELIEVING, user)
        return redirect(f"{reverse('lifecycle:offboarding')}?letter={letter.pk}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        user = request.user
        org = user.organization
        filters = LifecycleFilters.from_request(request, mode="onboarding")
        summary = onboarding_summary(org, filters)
        workflows = onboarding_table_rows(org, filters)
        paginator = Paginator(workflows, self.paginate_by)

        active_workflows = OnboardingWorkflow.objects.filter(organization=org).select_related("user")[:12]

        ctx.update(
            {
                "page_mode": "onboarding",
                "organization": org,
                "filters": filters,
                "filters_get": request.GET,
                "filter_options": filter_options(org),
                "summary": summary,
                "insights": build_insights(org, mode="onboarding"),
                "charts_json": json.dumps(onboarding_charts(org, filters)),
                "report_page": paginator.get_page(request.GET.get("page")),
                "active_workflows": active_workflows,
                "start_onboarding_form": StartOnboardingForm(organization=org),
                "start_offboarding_form": StartOffboardingForm(organization=org),
                "can_manage": can_manage_lifecycle(user),
                "filter_query": request.GET.urlencode(),
                "offboarding_url": reverse("lifecycle:offboarding"),
            }
        )
        return ctx


class OffboardingManagementView(OnboardingManagementView):
    template_name = "lifecycle/offboarding.html"

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            org = request.user.organization
            filters = LifecycleFilters.from_request(request, mode="offboarding")
            rows = offboarding_table_rows(org, filters)
            content = export_csv(
                rows,
                ["employee_id", "name", "department", "last_day", "reason", "status", "progress", "clearance"],
            )
            resp = HttpResponse(content, content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="offboarding-report.csv"'
            return resp
        if request.GET.get("letter"):
            return self._view_letter(request)
        return TemplateView.get(self, request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = TemplateView.get_context_data(self, **kwargs)
        request = self.request
        org = request.user.organization
        filters = LifecycleFilters.from_request(request, mode="offboarding")
        summary = offboarding_summary(org, filters)
        rows = offboarding_table_rows(org, filters)
        paginator = Paginator(rows, self.paginate_by)

        active = OffboardingWorkflow.objects.filter(organization=org).select_related(
            "user", "settlement"
        ).prefetch_related("clearances")[:12]

        ctx.update(
            {
                "page_mode": "offboarding",
                "organization": org,
                "filters": filters,
                "filters_get": request.GET,
                "filter_options": filter_options(org),
                "summary": summary,
                "insights": build_insights(org, mode="offboarding"),
                "charts_json": json.dumps(offboarding_charts(org, filters)),
                "report_page": paginator.get_page(request.GET.get("page")),
                "active_workflows": active,
                "start_onboarding_form": StartOnboardingForm(organization=org),
                "start_offboarding_form": StartOffboardingForm(organization=org),
                "can_manage": can_manage_lifecycle(self.request.user),
                "filter_query": request.GET.urlencode(),
                "onboarding_url": reverse("lifecycle:onboarding"),
            }
        )
        return ctx
