from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import LoginAuditLog, StaffAuditLog, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "role", "organization", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone", "profile_picture")}),
        ("Organization", {"fields": ("organization", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role", "organization", "is_staff", "is_superuser"),
            },
        ),
    )

    readonly_fields = ("date_joined",)
    filter_horizontal = ("groups", "user_permissions")


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ("username_attempt", "portal", "success", "user", "ip_address", "created_at")
    list_filter = ("portal", "success", "created_at")
    search_fields = ("username_attempt", "user__email", "ip_address")
    readonly_fields = (
        "user",
        "username_attempt",
        "portal",
        "success",
        "ip_address",
        "user_agent",
        "failure_reason",
        "created_at",
    )
    date_hierarchy = "created_at"


@admin.register(StaffAuditLog)
class StaffAuditLogAdmin(admin.ModelAdmin):
    list_display = ("summary", "action", "actor", "target_user", "organization", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("summary", "actor__email", "target_user__email")
    readonly_fields = ("organization", "actor", "target_user", "action", "summary", "details", "created_at")
    date_hierarchy = "created_at"
