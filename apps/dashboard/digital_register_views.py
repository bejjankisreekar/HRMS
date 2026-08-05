"""Digital Attendance Register views (ADMIN / HR only)."""
from __future__ import annotations

from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .digital_register import (
    LEGEND,
    RegisterFilters,
    build_register,
    build_register_json,
    build_summary_cards,
    export_register_csv,
    export_register_xlsx,
    register_filter_options,
)
from .mixins import AdminOrHRRequiredMixin


class DigitalRegisterView(AdminOrHRRequiredMixin, TemplateView):
    """Register-book style attendance grid."""

    template_name = "dashboard/digital_register.html"
    page_size = 100

    def get(self, request, *args, **kwargs):
        export = request.GET.get("export")
        if export in ("csv", "excel"):
            filters = RegisterFilters.from_request(request)
            if export == "excel":
                return export_register_xlsx(request.user, filters)
            return export_register_csv(request.user, filters)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        filters = RegisterFilters.from_request(self.request)

        try:
            page = int(self.request.GET.get("page") or 1)
        except (TypeError, ValueError):
            page = 1

        register = build_register(user, filters, page=page, page_size=self.page_size)
        summary = build_summary_cards(user, filters)
        options = register_filter_options(user)

        today = timezone.localdate()
        ctx.update(register)
        ctx["summary"] = summary
        ctx["filter_options"] = options
        ctx["legend"] = LEGEND
        ctx["filters"] = filters
        ctx["selected_month"] = filters.start.month
        ctx["selected_year"] = filters.start.year
        ctx["selected_department"] = filters.department_id
        ctx["selected_employee"] = filters.employee_id
        ctx["search_term"] = filters.search
        ctx["start_date"] = filters.start
        ctx["end_date"] = filters.end
        ctx["today"] = today
        ctx["month_choices"] = [
            (i, timezone.datetime(2000, i, 1).strftime("%B")) for i in range(1, 13)
        ]
        ctx["year_choices"] = list(range(today.year - 3, today.year + 2))
        ctx["page_title"] = "Digital Attendance Register"
        ctx["is_admin"] = user.role == user.Role.ADMIN

        # Build a querystring (without page) so pagination links keep filters
        q = self.request.GET.copy()
        q.pop("page", None)
        q.pop("export", None)
        ctx["filter_query"] = q.urlencode()
        return ctx


class DigitalRegisterDataView(AdminOrHRRequiredMixin, View):
    """JSON API matching the documented contract."""

    def get(self, request, *args, **kwargs):
        filters = RegisterFilters.from_request(request)
        try:
            page = int(request.GET.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        payload = build_register_json(request.user, filters, page=page)
        return JsonResponse(payload)
