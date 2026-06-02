"""Central file index and storage audit trail."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class FileCategory(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Documents"
    IMAGE = "IMAGE", "Images"
    PDF = "PDF", "PDFs"
    VIDEO = "VIDEO", "Videos"
    PAYROLL = "PAYROLL", "Payroll files"
    EMPLOYEE = "EMPLOYEE", "Employee documents"
    OTHER = "OTHER", "Other"


class StoredFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="stored_files",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_files",
    )
    uploader_role = models.CharField(max_length=20, blank=True)
    department_name = models.CharField(max_length=120, blank=True)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, db_index=True)
    file_size_bytes = models.BigIntegerField(default=0)
    category = models.CharField(max_length=20, choices=FileCategory.choices, default=FileCategory.OTHER)
    source_model = models.CharField(max_length=80, blank=True)
    source_field = models.CharField(max_length=80, blank=True)
    source_pk = models.CharField(max_length=64, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["organization", "uploader_role"]),
            models.Index(fields=["organization", "category"]),
        ]

    def __str__(self) -> str:
        return self.file_name


class UserStorageQuota(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="user_quotas",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="storage_quota",
    )
    quota_mb = models.PositiveIntegerField(default=0, help_text="0 = use org default")
    uploads_restricted = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} quota"


class StorageAuditLog(models.Model):
    class Action(models.TextChoices):
        UPLOAD = "UPLOAD", "Upload"
        DELETE = "DELETE", "Delete"
        QUOTA_CHANGE = "QUOTA_CHANGE", "Quota change"
        RESTRICT = "RESTRICT", "Upload restricted"
        SYNC = "SYNC", "Index sync"
        DOWNLOAD = "DOWNLOAD", "Download"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="storage_audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="storage_audit_actions",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="storage_audit_targets",
    )
    stored_file = models.ForeignKey(
        StoredFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
