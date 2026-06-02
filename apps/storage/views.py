"""Super Admin storage hub views."""

from __future__ import annotations

import json

from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.organizations.models import Organization
from apps.storage.analytics import (
    _format_size,
    _storage_limit_bytes,
    build_org_storage_context,
    build_platform_storage_context,
)
from apps.storage.models import StorageAuditLog, StoredFile, UserStorageQuota
from apps.storage.scanner import sync_all_organizations, sync_organization_files


STORAGE_NAV = [
    ("hub", "Storage overview", "hard-drive", "dashboard:storage:hub"),
    ("resources", "Resources", "cpu", "dashboard:storage:resources"),
    ("file_audits", "File audits", "shield-check", "dashboard:storage:file_audits"),
    ("usage", "Plan usage", "gauge", "dashboard:storage:usage"),
]


class StorageContextMixin(SuperAdminRequiredMixin):
    section = "hub"

    def get_storage_nav(self):
        current = self.section
        return [
            {
                "id": sid,
                "label": label,
                "icon": icon,
                "url": reverse(url_name),
                "active": sid == current,
            }
            for sid, label, icon, url_name in STORAGE_NAV
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["storage_nav"] = self.get_storage_nav()
        ctx["storage_section"] = self.section
        ctx["storage_api"] = reverse("dashboard:storage:api_action")
        return ctx


class StorageHubView(StorageContextMixin, TemplateView):
    template_name = "dashboard/storage/platform_hub.html"
    section = "hub"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(build_platform_storage_context())
        return ctx


class ResourcesHubView(StorageContextMixin, TemplateView):
    template_name = "dashboard/storage/resources_hub.html"
    section = "resources"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        platform = build_platform_storage_context()
        ctx.update(platform)
        ctx["resource_metrics"] = {
            "storage_label": platform["total_label"],
            "file_count": platform["file_count"],
            "org_count": platform["org_count"],
            "api_calls_today": "—",
            "active_sessions": User.objects.filter(
                is_active=True,
                last_login__gte=timezone.now() - timezone.timedelta(days=1),
            ).count(),
            "db_size": "—",
            "cpu_usage": "—",
        }
        return ctx


class FileAuditHubView(StorageContextMixin, TemplateView):
    template_name = "dashboard/storage/file_audit_hub.html"
    section = "file_audits"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["large_files"] = (
            StoredFile.objects.filter(is_active=True)
            .select_related("organization", "uploaded_by")
            .order_by("-file_size_bytes")[:50]
        )
        ctx["audit_logs"] = StorageAuditLog.objects.select_related(
            "organization", "actor", "target_user"
        ).order_by("-created_at")[:50]
        ctx["duplicate_count"] = (
            StoredFile.objects.filter(is_active=True)
            .exclude(content_hash="")
            .values("content_hash")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .count()
        )
        return ctx


class UsageComparisonHubView(StorageContextMixin, TemplateView):
    template_name = "dashboard/storage/usage_hub.html"
    section = "usage"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for org in Organization.objects.filter(is_active=True).order_by("name")[:30]:
            used = (
                StoredFile.objects.filter(organization=org, is_active=True).aggregate(
                    s=Sum("file_size_bytes")
                )["s"]
                or 0
            )
            limit = _storage_limit_bytes(org)
            pct = min(100, int(used / limit * 100)) if limit else 0
            sub = getattr(org, "subscription", None)
            plan = sub.plan.name if sub else org.get_subscription_plan_display()
            emp_count = User.objects.filter(organization=org, is_active=True).exclude(
                role=User.Role.SUPER_ADMIN
            ).count()
            emp_limit = sub.plan.employee_limit if sub else org.max_users_allowed
            rows.append(
                {
                    "organization": org,
                    "used_bytes": used,
                    "used_label": _format_size(used),
                    "limit_label": _format_size(limit),
                    "usage_percent": pct,
                    "plan": plan,
                    "employees": emp_count,
                    "employee_limit": emp_limit or "Unlimited",
                    "overusage": pct >= 90,
                }
            )
        ctx["org_usage"] = rows
        return ctx


class StorageActionAPIView(SuperAdminRequiredMixin, View):
    def post(self, request):
        body = json.loads(request.body.decode() or "{}")
        action = body.get("action")

        if action == "sync_org":
            org = get_object_or_404(Organization, pk=body.get("organizationId"))
            count = sync_organization_files(org)
            StorageAuditLog.objects.create(
                organization=org,
                actor=request.user,
                action=StorageAuditLog.Action.SYNC,
                summary=f"Storage index synced ({count} files)",
            )
            return JsonResponse({"ok": True, "count": count})

        if action == "sync_all":
            count = sync_all_organizations()
            return JsonResponse({"ok": True, "count": count})

        if action == "restrict_uploads":
            user = get_object_or_404(User, pk=body.get("userId"))
            quota, _ = UserStorageQuota.objects.get_or_create(
                organization=user.organization, user=user
            )
            quota.uploads_restricted = bool(body.get("restricted", True))
            quota.save()
            StorageAuditLog.objects.create(
                organization=user.organization,
                actor=request.user,
                target_user=user,
                action=StorageAuditLog.Action.RESTRICT,
                summary="Upload restriction updated",
            )
            return JsonResponse({"ok": True})

        if action == "set_quota":
            user = get_object_or_404(User, pk=body.get("userId"))
            quota, _ = UserStorageQuota.objects.get_or_create(
                organization=user.organization, user=user
            )
            quota.quota_mb = int(body.get("quotaMb") or 0)
            quota.save()
            StorageAuditLog.objects.create(
                organization=user.organization,
                actor=request.user,
                target_user=user,
                action=StorageAuditLog.Action.QUOTA_CHANGE,
                summary=f"Quota set to {quota.quota_mb} MB",
            )
            return JsonResponse({"ok": True})

        if action == "deactivate_file":
            f = get_object_or_404(StoredFile, pk=body.get("fileId"))
            f.is_active = False
            f.save(update_fields=["is_active"])
            StorageAuditLog.objects.create(
                organization=f.organization,
                actor=request.user,
                stored_file=f,
                action=StorageAuditLog.Action.DELETE,
                summary=f"File marked inactive: {f.file_name}",
            )
            return JsonResponse({"ok": True})

        return JsonResponse({"ok": False, "error": "Unknown action"}, status=400)
