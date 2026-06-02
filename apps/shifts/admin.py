from django.contrib import admin

from .models import OvertimeRecord, ShiftApproval, ShiftAssignment, ShiftRotation, ShiftRotationStep, ShiftSwapRequest


class ShiftRotationStepInline(admin.TabularInline):
    model = ShiftRotationStep
    extra = 1


@admin.register(ShiftRotation)
class ShiftRotationAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "cycle_unit", "is_active")
    inlines = [ShiftRotationStepInline]


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "shift", "date", "status")
    list_filter = ("status", "date")


@admin.register(ShiftSwapRequest)
class ShiftSwapRequestAdmin(admin.ModelAdmin):
    list_display = ("requester", "date", "status", "created_at")
    list_filter = ("status",)


@admin.register(OvertimeRecord)
class OvertimeRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "minutes", "status")


@admin.register(ShiftApproval)
class ShiftApprovalAdmin(admin.ModelAdmin):
    list_display = ("approval_type", "status", "created_at")
