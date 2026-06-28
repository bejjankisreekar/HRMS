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
        "selected_fy_start_year": None,
    }

    org = getattr(request.user, "organization", None)
    if org:
        try:
            from apps.organizations.financial_year import (
                get_current_financial_year,
                get_fy_range,
                fy_year_choices,
            )

            # Determine which FY the user has selected (session > default=current)
            calendar_fy = get_current_financial_year(org)
            raw_year = request.session.get("selected_fy_start_year")
            if raw_year:
                try:
                    active_fy = get_fy_range(org, int(raw_year))
                except Exception:
                    active_fy = calendar_fy
            else:
                active_fy = calendar_fy

            choices = fy_year_choices(org, n=5)

            ctx["current_fy"] = active_fy
            ctx["fy_label"] = active_fy["label"]
            ctx["fy_choices"] = choices
            ctx["selected_fy_start_year"] = active_fy["start_year"]
        except Exception:
            pass

    return ctx
