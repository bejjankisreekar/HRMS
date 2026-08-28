"""HR Analytics dashboard — page, JSON sections and exports."""

from __future__ import annotations

import json

from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.organizations.fy_utils import get_selected_fy

from . import hr_analytics as HA
from .mixins import AdminOrHRRequiredMixin

REPORT_SLUG = "hr_analytics"


def _audit(request, action, export_type: str = "", filters: HA.HRFilters | None = None) -> None:
    """Record dashboard access on the shared report-audit trail (best effort)."""
    try:
        from apps.attendance.models import AttendanceReportAudit, record_report_audit

        record_report_audit(
            request.user.organization,
            request.user,
            action,
            report=REPORT_SLUG,
            export_type=export_type,
            filters=filters.as_dict() if filters else {},
        )
    except Exception:  # pragma: no cover - auditing must never break the page
        pass


class HRAnalyticsView(AdminOrHRRequiredMixin, TemplateView):
    """The HR Analytics workspace. Charts hydrate over AJAX, per section."""

    template_name = "dashboard/hr_analytics.html"

    def get(self, request, *args, **kwargs):
        export = (request.GET.get("export") or "").strip()
        if export:
            filters = HA.HRFilters.from_request(request, fy=get_selected_fy(request))
            org = request.user.organization
            from apps.attendance.models import AttendanceReportAudit

            if export in ("xlsx", "excel"):
                _audit(request, AttendanceReportAudit.Action.EXPORTED, "xlsx", filters)
                return HA.export_scorecard_xlsx(org, filters)
            if export == "csv":
                _audit(request, AttendanceReportAudit.Action.EXPORTED, "csv", filters)
                return HA.export_scorecard_csv(org, filters)
            raise Http404("Unknown export format")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        org = request.user.organization
        filters = HA.HRFilters.from_request(request, fy=get_selected_fy(request))

        query = request.GET.copy()
        query.pop("export", None)

        ctx.update({
            "org": org,
            "organization": org,
            "today": timezone.localdate(),
            "filters": filters,
            "filters_dict": filters.as_dict(),
            "filters_get": request.GET,
            "filter_query": query.urlencode(),
            "options": HA.filter_options(org),
            "currency": (org.currency or "INR") if org else "INR",
            "is_admin": request.user.role == User.Role.ADMIN,
            "period_choices": HA.PERIOD_CHOICES,
            "sections": HA.SECTIONS,
            "boot_json": json.dumps({
                "filters": filters.as_dict(),
                "currency": (org.currency or "INR") if org else "INR",
                "endpoint": "/dashboard/hr-analytics/data/",
            }),
            "page_back_label": "Back to dashboard",
        })
        try:
            from apps.attendance.models import AttendanceReportAudit

            _audit(request, AttendanceReportAudit.Action.VIEWED, filters=filters)
        except Exception:  # pragma: no cover
            pass
        return ctx


class HRAnalyticsDataView(AdminOrHRRequiredMixin, View):
    """JSON for one dashboard section.

    Query params: ``section`` plus any of the HRFilters fields
    (period / from / to / department / employment_type / work_mode / location).
    """

    def get(self, request, *args, **kwargs):
        section = (request.GET.get("section") or "overview").strip()
        if section not in HA.SECTIONS:
            return JsonResponse(
                {"error": "Unknown section", "sections": list(HA.SECTIONS)}, status=400
            )
        filters = HA.HRFilters.from_request(request, fy=get_selected_fy(request))
        refresh = request.GET.get("refresh") == "1"
        payload = HA.get_section(
            request.user.organization, filters, section, use_cache=not refresh
        )
        return JsonResponse({"section": section, "data": payload})
