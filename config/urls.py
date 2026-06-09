"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import Resolver404, include, path, re_path, resolve
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.views import LandingPageView


def custom_page_not_found(request, exception=None):
    """Render the branded 404 page for unmatched URLs in every environment.

    Django only uses templates/404.html automatically when DEBUG=False, so this
    catch-all makes the styled page show in local development too. Trailing-slash
    redirects (APPEND_SLASH) are preserved so existing links keep working.
    """
    path_info = request.path_info
    if getattr(settings, "APPEND_SLASH", True) and not path_info.endswith("/"):
        try:
            match = resolve(path_info + "/")
        except Resolver404:
            match = None
        # Redirect only if the slashed path maps to a REAL view (not this catch-all).
        if match is not None and match.func is not custom_page_not_found:
            return redirect(path_info + "/")
    return render(request, "404.html", status=404)


urlpatterns = [
    path("", LandingPageView.as_view(), name="landing"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("leave-management/", include("apps.leaves.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("shifts/", include("apps.shifts.urls")),
    path("", include("apps.lifecycle.urls")),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Catch-all: any unmatched URL renders the branded 404 page (must stay last).
urlpatterns += [
    re_path(r"^.*$", custom_page_not_found),
]
