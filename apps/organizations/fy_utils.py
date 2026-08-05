"""Utility to resolve the selected Financial Year from a request."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def get_selected_fy(request: "HttpRequest") -> dict | None:
    """Return the active FY dict for the request's user/session.

    Resolution order:
      1. session['selected_fy_id']  (user explicitly switched)
      2. is_default=True FY for the org
      3. Latest active FY
      4. Latest FY (any status)
      5. None  (no FY records exist yet)

    The returned dict matches FinancialYear.as_dict():
      {id, start_year, end_year, label, date_from, date_to, is_active, is_default}
    """
    org = getattr(getattr(request, "user", None), "organization", None)
    if not org:
        return None

    try:
        from apps.organizations.models import FinancialYear

        selected_id = request.session.get("selected_fy_id")
        if selected_id:
            fy = FinancialYear.objects.filter(pk=selected_id, organization=org).first()
            if fy:
                return fy.as_dict()

        fy = (
            FinancialYear.objects.filter(organization=org, is_default=True).first()
            or FinancialYear.objects.filter(organization=org, is_active=True).order_by("-start_date").first()
            or FinancialYear.objects.filter(organization=org).order_by("-start_date").first()
        )
        return fy.as_dict() if fy else None

    except Exception:
        return None
