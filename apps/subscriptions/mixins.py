from django.shortcuts import render
from django.views.generic import TemplateView

from apps.dashboard.mixins import OrganizationRequiredMixin
from apps.subscriptions.services.entitlements import get_upgrade_context, has_feature


class PlanFeatureRequiredMixin(OrganizationRequiredMixin):
    """Block access when the org's plan does not include `required_feature`."""

    required_feature: str = ""

    def dispatch(self, request, *args, **kwargs):
        if not self.required_feature:
            return super().dispatch(request, *args, **kwargs)
        org = request.user.organization
        role = getattr(request.user, "role", None)
        if has_feature(org, self.required_feature, role):
            return super().dispatch(request, *args, **kwargs)
        ctx = get_upgrade_context(org, self.required_feature)
        ctx["page_title"] = f"{ctx['feature_name']} — Upgrade Required"
        return render(request, "dashboard/upgrade_required.html", ctx, status=403)


class UpgradeRequiredView(OrganizationRequiredMixin, TemplateView):
    template_name = "dashboard/upgrade_required.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        feature_key = self.request.GET.get("feature", "")
        org = self.request.user.organization
        ctx.update(get_upgrade_context(org, feature_key))
        ctx["page_title"] = f"{ctx.get('feature_name', 'Feature')} — Upgrade Required"
        return ctx
