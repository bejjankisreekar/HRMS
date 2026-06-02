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
        }
    current = ""
    if request.resolver_match:
        current = request.resolver_match.view_name or ""
    return {
        "sidebar": build_sidebar_menu(
            request.user,
            current,
            request.path,
        ),
        "topnav": build_topnav(request.user),
        "dashboard_home_url": get_dashboard_home_url(request.user),
        "page_back_suppress": is_dashboard_home_view(request.user, current),
    }
