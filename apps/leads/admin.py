from django.contrib import admin

from .models import ContactLead, NewsletterSubscriber


@admin.register(ContactLead)
class ContactLeadAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "company_name",
        "work_email",
        "employee_count",
        "status",
        "source",
        "created_at",
    )
    list_filter = ("status", "employee_count", "source", "created_at")
    search_fields = ("full_name", "company_name", "work_email", "phone_number", "message")
    readonly_fields = ("id", "ip_address", "user_agent", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("status", "source", "full_name", "company_name", "work_email", "phone_number")}),
        ("Details", {"fields": ("employee_count", "interested_modules", "message")}),
        ("CRM", {"fields": ("crm_external_id", "notes")}),
        ("Meta", {"fields": ("id", "ip_address", "user_agent", "created_at", "updated_at")}),
    )


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "source", "is_active", "subscribed_at")
    search_fields = ("email",)
    list_filter = ("is_active", "source")
