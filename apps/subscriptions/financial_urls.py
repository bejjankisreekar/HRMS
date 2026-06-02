from django.urls import path

from .financial_views import (
    FinancialActionAPIView,
    FinancialAddonsView,
    FinancialAnalyticsView,
    FinancialAuditView,
    FinancialDashboardView,
    FinancialInvoicesView,
    FinancialPaymentsView,
    FinancialPlansView,
    FinancialSubscriptionsView,
    FinancialUsageView,
    InvoicePDFView,
)

app_name = "financials"

urlpatterns = [
    path("", FinancialDashboardView.as_view(), name="hub"),
    path("subscriptions/", FinancialSubscriptionsView.as_view(), name="subscriptions"),
    path("plans/", FinancialPlansView.as_view(), name="plans"),
    path("addons/", FinancialAddonsView.as_view(), name="addons"),
    path("payments/", FinancialPaymentsView.as_view(), name="payments"),
    path("invoices/", FinancialInvoicesView.as_view(), name="invoices"),
    path("analytics/", FinancialAnalyticsView.as_view(), name="analytics"),
    path("usage/", FinancialUsageView.as_view(), name="usage"),
    path("audit/", FinancialAuditView.as_view(), name="audit"),
    path("api/action/", FinancialActionAPIView.as_view(), name="api_action"),
    path("invoices/<uuid:pk>/pdf/", InvoicePDFView.as_view(), name="invoice_pdf"),
]
