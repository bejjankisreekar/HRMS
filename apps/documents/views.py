from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from .models import (
    DocumentTemplate,
    DocumentTemplateVersion,
    DocumentAuditLog,
    DocumentPermission,
    GeneratedDocument,
    record_doc_action,
)
from .services import (
    create_generated_document,
    generate_pdf,
    get_default_body,
    render_document_html,
)


def _get_doc_perms(org) -> DocumentPermission:
    perm, _ = DocumentPermission.objects.get_or_create(organization=org)
    return perm


def _require_org(user):
    if not user.organization_id:
        raise Http404


def _require_manage(user):
    _require_org(user)
    perm = _get_doc_perms(user.organization)
    if not perm.can_manage(user.role):
        raise Http404


def _require_generate(user):
    _require_org(user)
    perm = _get_doc_perms(user.organization)
    if not perm.can_generate(user.role):
        raise Http404


# ── Template management ───────────────────────────────────────────────────────

class DocumentManagementView(LoginRequiredMixin, TemplateView):
    template_name = "documents/management.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        _require_org(user)
        perm = _get_doc_perms(user.organization)
        can_manage = perm.can_manage(user.role)
        can_generate = perm.can_generate(user.role)
        can_view_all = perm.can_view_all(user.role)

        if not (can_manage or can_generate or can_view_all):
            # Employees: show their own docs only
            if user.role == User.Role.EMPLOYEE:
                pass
            else:
                raise Http404

        templates_qs = DocumentTemplate.objects.filter(
            organization=user.organization
        ).order_by("template_type", "name")

        # Stats
        active_templates = templates_qs.filter(is_active=True).count()
        total_generated = GeneratedDocument.objects.filter(organization=user.organization).count()
        generated_qs = GeneratedDocument.objects.filter(organization=user.organization)
        if not can_view_all and user.role == User.Role.EMPLOYEE:
            generated_qs = generated_qs.filter(employee=user)

        template_types = dict(DocumentTemplate.TemplateType.choices)
        grouped = {}
        for t in templates_qs:
            grouped.setdefault(t.template_type, []).append(t)

        ctx = self.get_context_data(
            templates=templates_qs,
            grouped_templates=grouped,
            generated_docs=generated_qs.select_related("employee", "template")[:20],
            template_types=template_types,
            can_manage=can_manage,
            can_generate=can_generate,
            can_view_all=can_view_all,
            active_templates=active_templates,
            total_generated=total_generated,
            perm=perm,
            page_title="Document Generator",
        )
        return self.render_to_response(ctx)


class DocumentTemplateCreateView(LoginRequiredMixin, View):
    template_name = "documents/template_form.html"

    def get(self, request):
        _require_manage(request.user)
        from django.shortcuts import render
        template_type = request.GET.get("type", "")
        default_body = get_default_body(template_type) if template_type else ""
        return render(request, self.template_name, {
            "form_title": "Create Document Template",
            "template_types": DocumentTemplate.TemplateType.choices,
            "placeholders": DocumentTemplate.available_placeholders(),
            "selected_type": template_type,
            "default_body": default_body,
            "obj": None,
        })

    def post(self, request):
        _require_manage(request.user)
        name = request.POST.get("name", "").strip()
        template_type = request.POST.get("template_type", "")
        description = request.POST.get("description", "").strip()
        body = request.POST.get("body", "").strip()
        include_logo = request.POST.get("include_logo") == "on"
        include_sig = request.POST.get("include_signature_placeholder") == "on"

        if not name or not template_type or not body:
            messages.error(request, "Name, type, and body are required.")
            return redirect("documents:template_create")

        tmpl = DocumentTemplate.objects.create(
            organization=request.user.organization,
            name=name,
            template_type=template_type,
            description=description,
            body=body,
            include_logo=include_logo,
            include_signature_placeholder=include_sig,
            created_by=request.user,
            updated_by=request.user,
        )
        tmpl.save_version(saved_by=request.user)
        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.CREATE_TEMPLATE,
            summary=f"Created template '{name}'",
            template=tmpl,
            request=request,
        )
        messages.success(request, f"Template '{name}' created.")
        return redirect("documents:management")


class DocumentTemplateEditView(LoginRequiredMixin, View):
    template_name = "documents/template_form.html"

    def get(self, request, pk):
        _require_manage(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)
        from django.shortcuts import render
        return render(request, self.template_name, {
            "form_title": f"Edit Template – {tmpl.name}",
            "template_types": DocumentTemplate.TemplateType.choices,
            "placeholders": DocumentTemplate.available_placeholders(),
            "selected_type": tmpl.template_type,
            "default_body": tmpl.body,
            "obj": tmpl,
        })

    def post(self, request, pk):
        _require_manage(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)

        name = request.POST.get("name", "").strip()
        body = request.POST.get("body", "").strip()
        description = request.POST.get("description", "").strip()
        include_logo = request.POST.get("include_logo") == "on"
        include_sig = request.POST.get("include_signature_placeholder") == "on"
        is_active = request.POST.get("is_active") == "on"

        if not name or not body:
            messages.error(request, "Name and body are required.")
            return redirect("documents:template_edit", pk=pk)

        # Save version snapshot before overwrite
        tmpl.save_version(saved_by=request.user)
        tmpl.version += 1
        tmpl.name = name
        tmpl.description = description
        tmpl.body = body
        tmpl.include_logo = include_logo
        tmpl.include_signature_placeholder = include_sig
        tmpl.is_active = is_active
        tmpl.updated_by = request.user
        tmpl.save()

        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.EDIT_TEMPLATE,
            summary=f"Edited template '{name}' (v{tmpl.version})",
            template=tmpl,
            request=request,
        )
        messages.success(request, "Template updated.")
        return redirect("documents:management")


class DocumentTemplateDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        _require_manage(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)
        name = tmpl.name
        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.DELETE_TEMPLATE,
            summary=f"Deleted template '{name}'",
            request=request,
        )
        tmpl.delete()
        messages.success(request, f"Template '{name}' deleted.")
        return redirect("documents:management")


class DocumentTemplateVersionsView(LoginRequiredMixin, TemplateView):
    template_name = "documents/template_versions.html"

    def get(self, request, pk):
        _require_manage(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)
        versions = tmpl.versions.select_related("saved_by").all()
        return self.render_to_response(self.get_context_data(
            tmpl=tmpl,
            versions=versions,
            page_title=f"Versions – {tmpl.name}",
        ))


class DocumentTemplateVersionRestoreView(LoginRequiredMixin, View):
    def post(self, request, pk, vpk):
        _require_manage(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)
        ver = get_object_or_404(DocumentTemplateVersion, pk=vpk, template=tmpl)

        tmpl.save_version(saved_by=request.user)
        tmpl.version += 1
        tmpl.body = ver.body
        tmpl.updated_by = request.user
        tmpl.save()

        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.RESTORE_VERSION,
            summary=f"Restored template '{tmpl.name}' to v{ver.version}",
            template=tmpl,
            request=request,
        )
        messages.success(request, f"Template restored to version {ver.version}.")
        return redirect("documents:template_versions", pk=pk)


# ── Document generation ───────────────────────────────────────────────────────

class DocumentGenerateView(LoginRequiredMixin, View):
    template_name = "documents/generate.html"

    def get(self, request):
        _require_generate(request.user)
        from django.shortcuts import render
        org = request.user.organization
        templates = DocumentTemplate.objects.filter(organization=org, is_active=True)

        # Employee list: HR/Admin see all, employee sees self only
        if request.user.role in (User.Role.ADMIN, User.Role.HR):
            employees = User.objects.filter(organization=org, is_active=True).exclude(
                role=User.Role.SUPER_ADMIN
            ).order_by("first_name", "last_name")
        else:
            employees = User.objects.filter(pk=request.user.pk)

        preselect_emp = request.GET.get("employee")
        preselect_tmpl = request.GET.get("template")

        return render(request, self.template_name, {
            "templates": templates,
            "employees": employees,
            "template_types": DocumentTemplate.TemplateType.choices,
            "preselect_employee": preselect_emp,
            "preselect_template": preselect_tmpl,
            "page_title": "Generate Document",
        })

    def post(self, request):
        _require_generate(request.user)
        org = request.user.organization

        template_pk = request.POST.get("template")
        employee_pk = request.POST.get("employee")

        tmpl = get_object_or_404(DocumentTemplate, pk=template_pk, organization=org, is_active=True)

        # Permission: employee can only generate for themselves
        if request.user.role == User.Role.EMPLOYEE:
            employee = request.user
        else:
            employee = get_object_or_404(User, pk=employee_pk, organization=org)

        extra = {
            "last_working_day": request.POST.get("last_working_day", ""),
            "effective_date": request.POST.get("effective_date", ""),
            "new_salary": request.POST.get("new_salary", ""),
            "new_designation": request.POST.get("new_designation", ""),
        }
        extra = {k: v for k, v in extra.items() if v}

        doc = create_generated_document(
            template=tmpl,
            employee=employee,
            actor=request.user,
            extra_context=extra,
            request=request,
        )
        messages.success(request, "Document generated successfully.")
        return redirect("documents:generated_detail", pk=doc.pk)


class DocumentPreviewView(LoginRequiredMixin, View):
    def get(self, request, pk):
        _require_org(request.user)
        doc = self._get_doc(request, pk)
        html = render_document_html(
            template=doc.template,
            employee=doc.employee,
            extra_context=doc.extra_context,
        ) if doc.template else doc.resolved_body
        return HttpResponse(html)

    @staticmethod
    def _get_doc(request, pk):
        perm = _get_doc_perms(request.user.organization)
        qs = GeneratedDocument.objects.filter(organization=request.user.organization)
        if not perm.can_view_all(request.user.role):
            qs = qs.filter(employee=request.user)
        return get_object_or_404(qs.select_related("template", "employee"), pk=pk)


class DocumentTemplatePreviewView(LoginRequiredMixin, View):
    """Live preview of a template (with dummy data)."""
    def get(self, request, pk):
        _require_org(request.user)
        tmpl = get_object_or_404(DocumentTemplate, pk=pk, organization=request.user.organization)
        html = render_document_html(
            template=tmpl,
            employee=request.user,
            extra_context={
                "last_working_day": "31 December 2025",
                "effective_date": "01 January 2026",
                "new_salary": "800000",
                "new_designation": "Senior Engineer",
            },
            include_logo=True,
        )
        return HttpResponse(html)


class DocumentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        _require_org(request.user)
        doc = DocumentPreviewView._get_doc(request, pk)

        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.DOWNLOAD_DOC,
            summary=f"Downloaded {doc.template_name} for {doc.employee.display_name}",
            document=doc,
            request=request,
        )

        if doc.pdf_file:
            try:
                response = HttpResponse(doc.pdf_file.read(), content_type="application/pdf")
                fname = f"{doc.template_type.lower()}_{doc.employee.employee_id or str(doc.employee.pk)[:8]}.pdf"
                response["Content-Disposition"] = f'attachment; filename="{fname}"'
                return response
            except Exception:
                pass

        # Regenerate on the fly
        html = render_document_html(
            template=doc.template,
            employee=doc.employee,
            extra_context=doc.extra_context,
        ) if doc.template else doc.resolved_body
        pdf_bytes = generate_pdf(html)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        fname = f"{doc.template_type.lower()}_{doc.employee.employee_id or str(doc.employee.pk)[:8]}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response


class GeneratedDocumentDetailView(LoginRequiredMixin, TemplateView):
    template_name = "documents/generated_detail.html"

    def get(self, request, pk):
        _require_org(request.user)
        doc = DocumentPreviewView._get_doc(request, pk)
        return self.render_to_response(self.get_context_data(
            doc=doc,
            page_title=f"{doc.template_name}",
            can_download=True,
        ))


class GeneratedDocumentDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        _require_manage(request.user)
        doc = get_object_or_404(GeneratedDocument, pk=pk, organization=request.user.organization)
        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.DELETE_DOC,
            summary=f"Deleted {doc.template_name} for {doc.employee.display_name}",
            document=doc,
            request=request,
        )
        doc.delete()
        messages.success(request, "Document deleted.")
        return redirect("documents:management")


class DocumentAuditView(LoginRequiredMixin, TemplateView):
    template_name = "documents/audit.html"

    def get(self, request):
        _require_org(request.user)
        if request.user.role not in (User.Role.ADMIN, User.Role.HR):
            raise Http404
        logs = DocumentAuditLog.objects.filter(
            organization=request.user.organization
        ).select_related("actor", "template", "document").order_by("-created_at")[:200]
        return self.render_to_response(self.get_context_data(
            logs=logs,
            page_title="Document Audit Log",
        ))


class DocumentPermissionsView(LoginRequiredMixin, View):
    template_name = "documents/permissions.html"

    def get(self, request):
        if request.user.role != User.Role.ADMIN:
            raise Http404
        _require_org(request.user)
        perm = _get_doc_perms(request.user.organization)
        from django.shortcuts import render
        return render(request, self.template_name, {
            "perm": perm,
            "page_title": "Document Permissions",
        })

    def post(self, request):
        if request.user.role != User.Role.ADMIN:
            raise Http404
        _require_org(request.user)
        perm = _get_doc_perms(request.user.organization)

        perm.admin_can_manage = request.POST.get("admin_can_manage") == "on"
        perm.hr_can_manage = request.POST.get("hr_can_manage") == "on"
        perm.admin_can_generate = request.POST.get("admin_can_generate") == "on"
        perm.hr_can_generate = request.POST.get("hr_can_generate") == "on"
        perm.employee_can_generate = request.POST.get("employee_can_generate") == "on"
        perm.admin_can_view_all = request.POST.get("admin_can_view_all") == "on"
        perm.hr_can_view_all = request.POST.get("hr_can_view_all") == "on"
        perm.save()

        record_doc_action(
            org=request.user.organization,
            actor=request.user,
            action=DocumentAuditLog.Action.UPDATE_PERMISSIONS,
            summary="Updated document permissions",
            request=request,
        )
        messages.success(request, "Permissions updated.")
        return redirect("documents:permissions")


class DocumentDefaultBodyAPIView(LoginRequiredMixin, View):
    def get(self, request):
        _require_manage(request.user)
        t = request.GET.get("type", "")
        return JsonResponse({"body": get_default_body(t)})
