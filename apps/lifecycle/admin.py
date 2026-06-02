from django.contrib import admin

from .models import (
    AssetAllocation,
    ClearanceApproval,
    EmployeeDocument,
    ExitInterview,
    GeneratedLetter,
    OffboardingWorkflow,
    OnboardingTask,
    OnboardingWorkflow,
    OrientationSession,
    PolicyAcceptance,
    SettlementRecord,
)


@admin.register(OnboardingWorkflow)
class OnboardingWorkflowAdmin(admin.ModelAdmin):
    list_display = ("user", "joining_date", "status", "progress_percent")


@admin.register(OffboardingWorkflow)
class OffboardingWorkflowAdmin(admin.ModelAdmin):
    list_display = ("user", "last_working_day", "status", "progress_percent")


admin.site.register(EmployeeDocument)
admin.site.register(OnboardingTask)
admin.site.register(AssetAllocation)
admin.site.register(PolicyAcceptance)
admin.site.register(OrientationSession)
admin.site.register(ExitInterview)
admin.site.register(ClearanceApproval)
admin.site.register(SettlementRecord)
admin.site.register(GeneratedLetter)
