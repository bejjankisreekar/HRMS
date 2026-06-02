"""Super Admin financial / billing views."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.organizations.models import Organization
from apps.subscriptions.models import (
    AddOnCatalog,
    FinancialAuditLog,
    Invoice,
    Payment,
    Plan,
)
from apps.subscriptions.services.analytics import (
    get_financial_dashboard_context,
    get_revenue_analytics_context,
    get_subscriptions_page_context,
    get_usage_page_context,
)
from apps.subscriptions.services.billing import (
    activate_subscription,
    add_credit,
    apply_coupon,
    extend_trial,
    generate_invoice,
    record_manual_payment,
    suspend_subscription,
    toggle_org_addon,
    upgrade_plan,
)


FINANCIAL_NAV = [
    ("dashboard", "Overview", "layout-dashboard", "dashboard:financials:hub"),
    ("subscriptions", "Subscriptions", "building-2", "dashboard:financials:subscriptions"),
    ("plans", "Plans", "layers", "dashboard:financials:plans"),
    ("addons", "Add-ons", "puzzle", "dashboard:financials:addons"),
    ("payments", "Payments", "credit-card", "dashboard:financials:payments"),
    ("invoices", "Invoices", "file-text", "dashboard:financials:invoices"),
    ("analytics", "Analytics", "bar-chart-3", "dashboard:financials:analytics"),
    ("usage", "Usage", "gauge", "dashboard:financials:usage"),
    ("audit", "Audit log", "shield", "dashboard:financials:audit"),
]


class FinancialContextMixin(SuperAdminRequiredMixin):
    section = "dashboard"

    def get_financial_nav(self):
        current = self.section
        return [
            {
                "id": sid,
                "label": label,
                "icon": icon,
                "url": reverse(url_name),
                "active": sid == current,
            }
            for sid, label, icon, url_name in FINANCIAL_NAV
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["financial_nav"] = self.get_financial_nav()
        ctx["financial_section"] = self.section
        return ctx


class FinancialDashboardView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/dashboard.html"
    section = "dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = get_financial_dashboard_context()
        ctx.update(data)
        ctx["revenue_chart_json"] = json.dumps(data["revenue_chart"])
        ctx["subscription_chart_json"] = json.dumps(data["subscription_chart"])
        ctx["plan_breakdown_json"] = json.dumps(data["plan_breakdown"])
        return ctx


class FinancialSubscriptionsView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/subscriptions.html"
    section = "subscriptions"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = {
            "status": self.request.GET.get("status", ""),
            "plan": self.request.GET.get("plan", ""),
            "q": self.request.GET.get("q", ""),
        }
        ctx.update(get_subscriptions_page_context(filters))
        return ctx


class FinancialPlansView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/plans.html"
    section = "plans"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plans"] = Plan.objects.annotate(
            sub_count=models.Count("subscriptions")
        ).order_by("sort_order", "name")
        return ctx


class FinancialAddonsView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/addons.html"
    section = "addons"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["addons"] = AddOnCatalog.objects.all().order_by("sort_order", "name")
        return ctx


class FinancialPaymentsView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/payments.html"
    section = "payments"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["payments"] = Payment.objects.select_related("organization", "invoice").order_by("-created_at")[:100]
        ctx["pending_count"] = Payment.objects.filter(status="PENDING").count()
        ctx["failed_count"] = Payment.objects.filter(status="FAILED").count()
        return ctx


class FinancialInvoicesView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/invoices.html"
    section = "invoices"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status = self.request.GET.get("status", "")
        qs = Invoice.objects.select_related("organization", "subscription__plan").order_by("-created_at")
        if status:
            qs = qs.filter(status=status)
        ctx["invoices"] = qs[:100]
        ctx["status_filter"] = status
        return ctx


class FinancialAnalyticsView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/analytics.html"
    section = "analytics"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = get_revenue_analytics_context()
        ctx.update(data)
        ctx["revenue_chart_json"] = json.dumps(data["revenue_chart"])
        ctx["subscription_chart_json"] = json.dumps(data["subscription_chart"])
        ctx["plan_breakdown_json"] = json.dumps(data["plan_breakdown"])
        ctx["forecast_json"] = json.dumps(data["forecast"])
        return ctx


class FinancialUsageView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/usage.html"
    section = "usage"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["usage_rows"] = get_usage_page_context()
        return ctx


class FinancialAuditView(FinancialContextMixin, TemplateView):
    template_name = "dashboard/financials/audit.html"
    section = "audit"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = FinancialAuditLog.objects.select_related("organization", "actor").order_by("-created_at")[:200]
        return ctx


class FinancialActionAPIView(SuperAdminRequiredMixin, View):
    """POST JSON actions for subscription/billing management."""

    def post(self, request):
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        action = body.get("action")
        org_id = body.get("organizationId")
        org = get_object_or_404(Organization, pk=org_id) if org_id else None

        try:
            if action == "upgrade_plan":
                plan = get_object_or_404(Plan, pk=body.get("planId"))
                upgrade_plan(org=org, plan=plan, actor=request.user, billing_interval=body.get("interval"))
            elif action == "suspend":
                suspend_subscription(org=org, actor=request.user)
            elif action == "activate":
                activate_subscription(org=org, actor=request.user)
            elif action == "extend_trial":
                extend_trial(org=org, days=int(body.get("days", 14)), actor=request.user)
            elif action == "generate_invoice":
                inv = generate_invoice(org=org, actor=request.user)
                return JsonResponse({"ok": True, "invoiceId": str(inv.pk), "invoiceNumber": inv.invoice_number})
            elif action == "record_payment":
                amount = Decimal(str(body.get("amount", "0")))
                inv = None
                if body.get("invoiceId"):
                    inv = get_object_or_404(Invoice, pk=body["invoiceId"])
                record_manual_payment(
                    org=org,
                    amount_inr=amount,
                    actor=request.user,
                    invoice=inv,
                    method=body.get("method", "MANUAL"),
                    reference_id=body.get("referenceId", ""),
                    notes=body.get("notes", ""),
                )
            elif action == "add_credit":
                add_credit(org=org, amount_inr=Decimal(str(body.get("amount", "0"))), actor=request.user)
            elif action == "apply_coupon":
                apply_coupon(org=org, coupon_code=body.get("code", ""), actor=request.user)
            elif action == "toggle_addon":
                addon = get_object_or_404(AddOnCatalog, pk=body.get("addonId"))
                toggle_org_addon(org=org, addon=addon, active=bool(body.get("active")), actor=request.user)
            elif action == "toggle_plan":
                plan = get_object_or_404(Plan, pk=body.get("planId"))
                plan.is_active = bool(body.get("active"))
                plan.save(update_fields=["is_active"])
            elif action == "toggle_addon_catalog":
                addon = get_object_or_404(AddOnCatalog, pk=body.get("addonId"))
                addon.is_active = bool(body.get("active"))
                addon.save(update_fields=["is_active"])
            else:
                return JsonResponse({"ok": False, "error": f"Unknown action: {action}"}, status=400)
        except (InvalidOperation, ValueError) as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse({"ok": True})


class InvoicePDFView(SuperAdminRequiredMixin, View):
    """Simple printable invoice (PDF via browser print)."""

    def get(self, request, pk):
        inv = get_object_or_404(Invoice.objects.select_related("organization", "subscription__plan"), pk=pk)
        from django.template.loader import render_to_string

        html = render_to_string(
            "dashboard/financials/invoice_print.html",
            {"invoice": inv, "organization": inv.organization},
        )
        return HttpResponse(html)
