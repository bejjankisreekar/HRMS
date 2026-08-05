from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, UpdateView, View

from apps.organizations.models import FinancialYear

from .financial_year_forms import FinancialYearForm
from .mixins import AdminRequiredMixin


class FinancialYearMasterView(AdminRequiredMixin, CreateView):
    """List all FYs and inline-create a new one on the same page."""

    template_name = "dashboard/financial_year_master.html"
    form_class = FinancialYearForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["org"] = self.request.user.organization
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["financial_years"] = (
            FinancialYear.objects.filter(organization=org).order_by("-start_date")
        )
        ctx["fy_count"] = ctx["financial_years"].count()
        return ctx

    def form_valid(self, form):
        fy = form.save()
        messages.success(self.request, f"Financial year '{fy.label}' created successfully.")
        return redirect("dashboard:financial_year_master")

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field != "__all__" else ""
                messages.error(self.request, f"{label}: {error}" if label else error)
        return self.render_to_response(self.get_context_data(form=form))


class FinancialYearEditView(AdminRequiredMixin, UpdateView):
    """Edit an existing financial year."""

    template_name = "dashboard/financial_year_master.html"
    form_class = FinancialYearForm

    def get_queryset(self):
        return FinancialYear.objects.filter(organization=self.request.user.organization)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["org"] = self.request.user.organization
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["financial_years"] = (
            FinancialYear.objects.filter(organization=org).order_by("-start_date")
        )
        ctx["fy_count"] = ctx["financial_years"].count()
        ctx["editing"] = self.object
        return ctx

    def form_valid(self, form):
        fy = form.save()
        messages.success(self.request, f"Financial year '{fy.label}' updated.")
        return redirect("dashboard:financial_year_master")

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                label = form.fields[field].label if field != "__all__" else ""
                messages.error(self.request, f"{label}: {error}" if label else error)
        return self.render_to_response(self.get_context_data(form=form))


class FinancialYearToggleActiveView(AdminRequiredMixin, View):
    """POST: toggle is_active for a financial year."""

    def post(self, request, pk):
        fy = get_object_or_404(
            FinancialYear, pk=pk, organization=request.user.organization
        )
        fy.is_active = not fy.is_active
        fy.save(update_fields=["is_active", "updated_at"])
        status = "activated" if fy.is_active else "deactivated"
        messages.success(request, f"'{fy.label}' {status}.")
        return redirect("dashboard:financial_year_master")


class FinancialYearSetDefaultView(AdminRequiredMixin, View):
    """POST: mark a financial year as the default."""

    def post(self, request, pk):
        org = request.user.organization
        fy = get_object_or_404(FinancialYear, pk=pk, organization=org)
        FinancialYear.objects.filter(organization=org).update(is_default=False)
        fy.is_default = True
        fy.save(update_fields=["is_default", "updated_at"])
        messages.success(request, f"'{fy.label}' set as default financial year.")
        return redirect("dashboard:financial_year_master")


class FinancialYearDeleteView(AdminRequiredMixin, View):
    """POST: delete a financial year (guard: cannot delete default)."""

    def post(self, request, pk):
        fy = get_object_or_404(
            FinancialYear, pk=pk, organization=request.user.organization
        )
        if fy.is_default:
            messages.error(
                request,
                "Cannot delete the default financial year. Set another FY as default first.",
            )
            return redirect("dashboard:financial_year_master")
        label = fy.label
        fy.delete()
        messages.success(request, f"Financial year '{label}' deleted.")
        return redirect("dashboard:financial_year_master")


class SetFinancialYearView(LoginRequiredMixin, View):
    """POST-only: persist the selected Financial Year (by id) in the user's session."""

    def post(self, request, *args, **kwargs):
        org = getattr(request.user, "organization", None)
        if org:
            fy_id = request.POST.get("fy_id", "").strip()
            if fy_id:
                try:
                    fy = FinancialYear.objects.get(pk=fy_id, organization=org)
                    request.session["selected_fy_id"] = str(fy.id)
                    # Keep legacy key in sync so payroll/attendance views still work
                    request.session["selected_fy_start_year"] = fy.start_date.year
                except FinancialYear.DoesNotExist:
                    pass

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
        return redirect(next_url)
