from django.contrib import admin

from .models import HierarchyChangeLog, Team, TeamMembership


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "department", "lead", "is_active")
    list_filter = ("organization", "is_active")


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ("team", "user", "joined_at")


@admin.register(HierarchyChangeLog)
class HierarchyChangeLogAdmin(admin.ModelAdmin):
    list_display = ("employee", "previous_manager", "new_manager", "changed_by", "created_at")
    list_filter = ("organization",)
