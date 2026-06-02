"""Index files from known upload fields into StoredFile."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime

from django.conf import settings
from django.db.models import FileField
from django.utils import timezone

from apps.accounts.models import User
from apps.leaves.models import LeaveRequest
from apps.lifecycle.models import EmployeeDocument
from apps.organizations.models import Organization
from apps.payroll.models import Reimbursement
from apps.storage.categories import categorize_path
from apps.storage.models import StoredFile


def _file_size(path: str) -> int:
    full = os.path.join(settings.MEDIA_ROOT, path)
    try:
        return os.path.getsize(full) if os.path.isfile(full) else 0
    except OSError:
        return 0


def _file_hash(path: str) -> str:
    full = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.isfile(full):
        return ""
    h = hashlib.md5()
    try:
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _upsert_file(
    *,
    organization: Organization,
    uploaded_by: User | None,
    file_field,
    source_model: str,
    source_field: str,
    source_pk: str,
    uploaded_at=None,
) -> StoredFile | None:
    if not file_field or not getattr(file_field, "name", None):
        return None
    path = file_field.name
    size = _file_size(path)
    role = uploaded_by.role if uploaded_by else ""
    dept = uploaded_by.department_name if uploaded_by else ""
    obj, created = StoredFile.objects.update_or_create(
        organization=organization,
        file_path=path,
        defaults={
            "uploaded_by": uploaded_by,
            "uploader_role": role,
            "department_name": dept or "",
            "file_name": os.path.basename(path),
            "file_size_bytes": size,
            "category": categorize_path(path, source_field),
            "source_model": source_model,
            "source_field": source_field,
            "source_pk": str(source_pk),
            "content_hash": _file_hash(path),
            "is_active": size > 0,
        },
    )
    if created and uploaded_at:
        StoredFile.objects.filter(pk=obj.pk).update(uploaded_at=uploaded_at)
    return obj


def sync_organization_files(organization: Organization) -> int:
    count = 0
    org_pk = organization.pk

    for user in User.objects.filter(organization=org_pk).exclude(role=User.Role.SUPER_ADMIN):
        if user.profile_picture:
            _upsert_file(
                organization=organization,
                uploaded_by=user,
                file_field=user.profile_picture,
                source_model="accounts.User",
                source_field="profile_picture",
                source_pk=user.pk,
                uploaded_at=user.date_joined,
            )
            count += 1

    if organization.logo:
        _upsert_file(
            organization=organization,
            uploaded_by=None,
            file_field=organization.logo,
            source_model="organizations.Organization",
            source_field="logo",
            source_pk=org_pk,
            uploaded_at=organization.created_at,
        )
        count += 1

    for lr in LeaveRequest.objects.filter(user__organization=org_pk).select_related("user"):
        if lr.attachment:
            _upsert_file(
                organization=organization,
                uploaded_by=lr.user,
                file_field=lr.attachment,
                source_model="leaves.LeaveRequest",
                source_field="attachment",
                source_pk=lr.pk,
                uploaded_at=lr.applied_at,
            )
            count += 1

    for reimb in Reimbursement.objects.filter(user__organization=org_pk).select_related("user"):
        if reimb.receipt:
            _upsert_file(
                organization=organization,
                uploaded_by=reimb.user,
                file_field=reimb.receipt,
                source_model="payroll.Reimbursement",
                source_field="receipt",
                source_pk=reimb.pk,
            )
            count += 1

    for doc in EmployeeDocument.objects.filter(onboarding__organization=org_pk).select_related(
        "onboarding__user"
    ):
        if doc.file:
            emp = doc.onboarding.user
            _upsert_file(
                organization=organization,
                uploaded_by=emp,
                file_field=doc.file,
                source_model="lifecycle.EmployeeDocument",
                source_field="file",
                source_pk=doc.pk,
            )
            count += 1

    StoredFile.objects.filter(organization=organization, file_size_bytes=0).update(is_active=False)
    return count


def sync_all_organizations() -> int:
    total = 0
    for org in Organization.objects.filter(is_active=True):
        total += sync_organization_files(org)
    return total
