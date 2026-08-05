from django.contrib import admin

from .models import Rule, RuleApprovalRequest, RuleAuditLog, RuleExecutionLog


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "trigger_event", "status", "priority", "updated_at")
    list_filter = ("trigger_event", "status", "organization")
    search_fields = ("name", "description")


@admin.register(RuleExecutionLog)
class RuleExecutionLogAdmin(admin.ModelAdmin):
    list_display = ("rule_name_snapshot", "organization", "trigger_event", "matched", "is_test_run", "created_at")
    list_filter = ("trigger_event", "matched", "is_test_run", "organization")
    search_fields = ("rule_name_snapshot", "subject_type", "subject_id")


@admin.register(RuleAuditLog)
class RuleAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "organization", "actor", "summary", "created_at")
    list_filter = ("action", "organization")
    search_fields = ("summary",)


@admin.register(RuleApprovalRequest)
class RuleApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("subject_type", "subject_id", "requested_for", "approver", "status", "created_at")
    list_filter = ("status", "organization")
