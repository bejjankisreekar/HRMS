from django.contrib import admin

from .models import AttendanceRecord, AttendanceRegularizationRequest, WorkShift


@admin.register(WorkShift)
class WorkShiftAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "start_time", "end_time", "grace_minutes", "is_default")
    list_filter = ("organization", "is_default")


@admin.register(AttendanceRegularizationRequest)
class AttendanceRegularizationRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "status", "created_at", "reviewed_by")
    list_filter = ("status", "date")
    search_fields = ("user__email", "user__username", "reason")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "status", "check_in", "check_out")
    list_filter = ("status", "date")
    search_fields = ("user__email", "user__username", "user__employee_id")
    date_hierarchy = "date"
