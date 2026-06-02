from django.contrib import admin

from .models import Holiday, LeaveApproval, LeaveBalance, LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "annual_quota", "is_active")
    list_filter = ("organization", "is_active")


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "holiday_type", "organization", "branch")
    list_filter = ("organization", "holiday_type")


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "leave_type", "year", "allocated", "used", "carried_forward")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "leave_type", "start_date", "end_date", "total_days", "status")
    list_filter = ("status", "leave_type")


@admin.register(LeaveApproval)
class LeaveApprovalAdmin(admin.ModelAdmin):
    list_display = ("leave_request", "step", "step_label", "approver", "status")
