from django.contrib import admin

from .models import TeamActionAuditLog


@admin.register(TeamActionAuditLog)
class TeamActionAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target_user", "organization", "ip_address")
    list_filter = ("action", "organization")
    search_fields = ("summary", "actor__email", "target_user__email")
    readonly_fields = (
        "id",
        "organization",
        "actor",
        "target_user",
        "action",
        "object_id",
        "summary",
        "details",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
