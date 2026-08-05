from apps.dashboard.sidebar_menu import (
    build_sidebar_menu,
    get_dashboard_home_url,
    is_dashboard_home_view,
)
from apps.dashboard.topnav import build_topnav


def hrms_sidebar(request):
    if not request.user.is_authenticated:
        return {
            "sidebar": {
                "groups": [],
                "search_items": [],
                "role_label": "",
                "is_super": False,
                "nav_accent": "",
            },
            "topnav": {},
            "current_fy": None,
            "fy_label": "",
            "fy_choices": [],
            "selected_fy_id": None,
            "selected_fy_start_year": None,
        }

    current = ""
    if request.resolver_match:
        current = request.resolver_match.view_name or ""

    ctx = {
        "sidebar": build_sidebar_menu(request.user, current, request.path),
        "topnav": build_topnav(request.user),
        "dashboard_home_url": get_dashboard_home_url(request.user),
        "page_back_suppress": is_dashboard_home_view(request.user, current),
        "current_fy": None,
        "fy_label": "",
        "fy_choices": [],
        "selected_fy_id": None,
        "selected_fy_start_year": None,
    }

    org = getattr(request.user, "organization", None)
    if not org:
        return ctx

    try:
        from apps.organizations.models import FinancialYear

        fy_qs = list(
            FinancialYear.objects.filter(organization=org).order_by("start_date")
        )

        if not fy_qs:
            # No FYs created yet — signal the topnav to show a "Create FY" CTA
            ctx["fy_choices"] = []
            return ctx

        choices = [fy.as_dict() for fy in fy_qs]

        # Resolve which FY is active: session > default > latest active > latest
        selected_id = request.session.get("selected_fy_id")
        active_obj = None

        if selected_id:
            active_obj = next((f for f in fy_qs if str(f.id) == selected_id), None)

        if not active_obj:
            active_obj = (
                next((f for f in fy_qs if f.is_default), None)
                or next((f for f in reversed(fy_qs) if f.is_active), None)
                or fy_qs[-1]
            )

        active_fy = active_obj.as_dict()
        ctx["current_fy"] = active_fy
        ctx["fy_label"] = active_fy["label"]
        ctx["fy_choices"] = choices
        ctx["selected_fy_id"] = active_fy["id"]
        ctx["selected_fy_start_year"] = active_fy["start_year"]

    except Exception:
        # Graceful fallback — never crash a page because of the FY context
        pass

    return ctx
