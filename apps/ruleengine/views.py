"""Server-rendered Rule Engine pages (Admin/HR only).

Mutations (create/update/enable-disable/delete/reorder/test) go through the
JSON APIs in ``api.py`` via fetch calls from ``static/ruleengine.js`` — these
views are read-only render + context, mirroring the payroll dashboard pages.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import AdminOrHRRequiredMixin

from .models import Rule, RuleAuditLog, RuleExecutionLog
from .registry import OPERATOR_LABELS, OPERATORS_BY_TYPE
from .serializers import actions_metadata, facts_metadata, rule_to_dict


class RuleManagementView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "ruleengine/management.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["rules"] = Rule.objects.filter(organization=org).order_by("priority", "created_at")
        return ctx


class RuleBuilderView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "ruleengine/builder.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        pk = kwargs.get("pk")
        rule = get_object_or_404(Rule, organization=org, pk=pk) if pk else None
        ctx["rule"] = rule
        # Rendered via the |json_script filter (not inlined into an HTML attribute) so
        # values containing double quotes can't prematurely terminate x-data="...".
        ctx["rule_data"] = rule_to_dict(rule) if rule else None
        ctx["facts_data"] = facts_metadata()
        ctx["actions_data"] = actions_metadata()
        ctx["operators_data"] = {"labels": OPERATOR_LABELS, "by_type": OPERATORS_BY_TYPE}
        ctx["triggers_data"] = list(Rule.Trigger.choices)
        ctx["statuses_data"] = list(Rule.Status.choices)
        return ctx


class RuleTestView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "ruleengine/test.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["rules"] = Rule.objects.filter(organization=org).order_by("name")
        ctx["employees"] = User.objects.filter(organization=org, is_active=True).order_by("first_name")[:300]
        return ctx


class RuleLogsView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "ruleengine/logs.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["execution_logs"] = (
            RuleExecutionLog.objects.filter(organization=org).select_related("rule")[:200]
        )
        ctx["audit_logs"] = RuleAuditLog.objects.filter(organization=org).select_related("actor")[:200]
        ctx["rules"] = Rule.objects.filter(organization=org).order_by("name")
        return ctx
