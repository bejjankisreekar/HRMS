from django.contrib import admin

from .models import Department, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "organization_code", "schema_name", "subscription_status", "is_active", "created_at")
    list_filter = ("subscription_status", "is_active")
    search_fields = ("name", "organization_code", "schema_name", "official_email")
    ordering = ("-created_at",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "code", "is_active", "sort_order", "member_count_display")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "code", "organization__name")
    ordering = ("organization", "sort_order", "name")

    @admin.display(description="Members")
    def member_count_display(self, obj):
        return obj.members.count()
