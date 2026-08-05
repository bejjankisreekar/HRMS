from django.contrib import admin
from .models import DocumentTemplate, DocumentTemplateVersion, GeneratedDocument, DocumentPermission, DocumentAuditLog


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "template_type", "organization", "version", "is_active", "created_at"]
    list_filter = ["template_type", "is_active"]
    search_fields = ["name", "organization__name"]


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ["template_name", "employee", "organization", "generated_at"]
    list_filter = ["template_type"]
    search_fields = ["template_name", "employee__email"]


@admin.register(DocumentAuditLog)
class DocumentAuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "summary", "created_at"]
    list_filter = ["action"]
    readonly_fields = ["created_at"]
