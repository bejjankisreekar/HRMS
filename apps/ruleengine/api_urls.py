"""Rule Engine JSON APIs, mounted at /api/rule-engine/."""

from django.urls import path

from .api import (
    AuditLogListAPI,
    ExecutionLogListAPI,
    RegistryMetadataAPI,
    RuleDetailAPI,
    RuleListCreateAPI,
    RuleReorderAPI,
    RuleStatusAPI,
    RuleTestAPI,
)

app_name = "ruleengine_api"

urlpatterns = [
    path("registry/", RegistryMetadataAPI.as_view(), name="registry"),
    path("rules/", RuleListCreateAPI.as_view(), name="rules"),
    path("rules/reorder/", RuleReorderAPI.as_view(), name="rules_reorder"),
    path("rules/test/", RuleTestAPI.as_view(), name="rules_test"),
    path("rules/<uuid:pk>/", RuleDetailAPI.as_view(), name="rule_detail"),
    path("rules/<uuid:pk>/status/", RuleStatusAPI.as_view(), name="rule_status"),
    path("rules/<uuid:pk>/test/", RuleTestAPI.as_view(), name="rule_test"),
    path("logs/execution/", ExecutionLogListAPI.as_view(), name="execution_logs"),
    path("logs/audit/", AuditLogListAPI.as_view(), name="audit_logs"),
]
