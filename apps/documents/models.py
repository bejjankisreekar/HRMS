from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class DocumentTemplate(models.Model):
    class TemplateType(models.TextChoices):
        OFFER = "OFFER", "Offer Letter"
        APPOINTMENT = "APPOINTMENT", "Appointment Letter"
        EXPERIENCE = "EXPERIENCE", "Experience Letter"
        RELIEVING = "RELIEVING", "Relieving Letter"
        PROMOTION = "PROMOTION", "Promotion Letter"
        INCREMENT = "INCREMENT", "Increment Letter"
        WARNING = "WARNING", "Warning Letter"
        SALARY_CERT = "SALARY_CERT", "Salary Certificate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="document_templates",
    )
    template_type = models.CharField(max_length=30, choices=TemplateType.choices)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True)
    body = models.TextField(help_text="HTML body with {{placeholders}}")
    is_active = models.BooleanField(default=True)
    include_logo = models.BooleanField(default=True)
    include_signature_placeholder = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_templates_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_templates_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["template_type", "name"]

    def __str__(self) -> str:
        return f"{self.get_template_type_display()} – {self.name}"

    def save_version(self, saved_by=None):
        DocumentTemplateVersion.objects.create(
            template=self,
            version=self.version,
            body=self.body,
            saved_by=saved_by,
        )

    @staticmethod
    def available_placeholders() -> list[dict]:
        return [
            {"key": "{{employee_name}}", "label": "Employee Full Name"},
            {"key": "{{employee_id}}", "label": "Employee ID"},
            {"key": "{{joining_date}}", "label": "Joining Date"},
            {"key": "{{last_working_day}}", "label": "Last Working Day"},
            {"key": "{{salary}}", "label": "Current Salary (CTC)"},
            {"key": "{{new_salary}}", "label": "New Salary (after hike)"},
            {"key": "{{designation}}", "label": "Designation"},
            {"key": "{{new_designation}}", "label": "New Designation"},
            {"key": "{{department}}", "label": "Department"},
            {"key": "{{company_name}}", "label": "Company Name"},
            {"key": "{{date}}", "label": "Today's Date"},
            {"key": "{{effective_date}}", "label": "Effective Date"},
            {"key": "{{reporting_manager}}", "label": "Reporting Manager"},
            {"key": "{{email}}", "label": "Employee Email"},
            {"key": "{{employment_type}}", "label": "Employment Type"},
        ]


class DocumentTemplateVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    body = models.TextField()
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_versions_saved",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"v{self.version} of {self.template_id}"


class GeneratedDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="generated_documents",
    )
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_documents",
    )
    template_type = models.CharField(max_length=30, choices=DocumentTemplate.TemplateType.choices)
    template_name = models.CharField(max_length=200)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_documents",
    )
    resolved_body = models.TextField()
    pdf_file = models.FileField(upload_to="documents/generated/%Y/%m/", blank=True)
    extra_context = models.JSONField(default=dict, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_generated_by",
    )
    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return f"{self.template_name} for {self.employee_id}"


class DocumentPermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="document_permissions",
    )
    # Which roles can manage (create/edit/delete) templates
    admin_can_manage = models.BooleanField(default=True)
    hr_can_manage = models.BooleanField(default=True)
    # Which roles can generate documents
    admin_can_generate = models.BooleanField(default=True)
    hr_can_generate = models.BooleanField(default=True)
    employee_can_generate = models.BooleanField(default=False)
    # Which roles can view all generated docs
    admin_can_view_all = models.BooleanField(default=True)
    hr_can_view_all = models.BooleanField(default=True)
    # Employees always see their own docs only

    class Meta:
        verbose_name = "Document Permission"

    def can_manage(self, role: str) -> bool:
        from apps.accounts.models import User
        if role == User.Role.ADMIN:
            return self.admin_can_manage
        if role == User.Role.HR:
            return self.hr_can_manage
        return False

    def can_generate(self, role: str) -> bool:
        from apps.accounts.models import User
        if role == User.Role.ADMIN:
            return self.admin_can_generate
        if role == User.Role.HR:
            return self.hr_can_generate
        if role == User.Role.EMPLOYEE:
            return self.employee_can_generate
        return False

    def can_view_all(self, role: str) -> bool:
        from apps.accounts.models import User
        if role == User.Role.ADMIN:
            return self.admin_can_view_all
        if role == User.Role.HR:
            return self.hr_can_view_all
        return False


class DocumentAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE_TEMPLATE = "CREATE_TEMPLATE", "Created template"
        EDIT_TEMPLATE = "EDIT_TEMPLATE", "Edited template"
        DELETE_TEMPLATE = "DELETE_TEMPLATE", "Deleted template"
        RESTORE_VERSION = "RESTORE_VERSION", "Restored version"
        GENERATE_DOC = "GENERATE_DOC", "Generated document"
        DOWNLOAD_DOC = "DOWNLOAD_DOC", "Downloaded document"
        DELETE_DOC = "DELETE_DOC", "Deleted document"
        UPDATE_PERMISSIONS = "UPDATE_PERMISSIONS", "Updated permissions"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="document_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_audit_logs",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    summary = models.CharField(max_length=500)
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    document = models.ForeignKey(
        GeneratedDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id}"


def record_doc_action(
    org,
    actor,
    action: str,
    summary: str,
    template=None,
    document=None,
    request=None,
) -> DocumentAuditLog:
    ip = None
    if request:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
    return DocumentAuditLog.objects.create(
        organization=org,
        actor=actor,
        action=action,
        summary=summary,
        template=template,
        document=document,
        ip_address=ip,
    )
