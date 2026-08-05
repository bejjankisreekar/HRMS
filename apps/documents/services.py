from __future__ import annotations

import io
import os
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.organizations.models import Organization
    from .models import DocumentTemplate, GeneratedDocument

# ── Placeholder resolution ────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _resolve_placeholders(body: str, employee: "User", org: "Organization", extra: dict) -> str:
    from apps.payroll.services import get_active_salary

    def _date(d):
        if not d:
            return ""
        try:
            return d.strftime("%d %B %Y")
        except Exception:
            return str(d)

    annual_ctc = get_active_salary(employee).monthly_ctc * 12

    def _money(value):
        if not value:
            return ""
        if value == value.to_integral_value():
            return f"{value:.0f}"
        return f"{value:f}"

    mapping = {
        "employee_name": employee.display_name,
        "employee_id": (employee.employee_id or ""),
        "joining_date": _date(employee.date_of_joining),
        "salary": _money(annual_ctc),
        "designation": (
            employee.org_designation.name
            if getattr(employee, "org_designation", None)
            else (employee.designation or "")
        ),
        "department": (employee.department.name if employee.department else ""),
        "company_name": org.name,
        "date": _date(timezone.localdate()),
        "email": employee.email,
        "employment_type": employee.get_employment_type_display() if employee.employment_type else "",
        "reporting_manager": (
            employee.reporting_manager.display_name if employee.reporting_manager else ""
        ),
        **extra,
    }

    def replace(m):
        key = m.group(1)
        return str(mapping.get(key, m.group(0)))

    return _PLACEHOLDER_RE.sub(replace, body)


# ── PDF generation ────────────────────────────────────────────────────────────

def _get_logo_base64(org: "Organization") -> str | None:
    if not org.logo:
        return None
    try:
        import base64
        with open(org.logo.path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(org.logo.path)[1].lstrip(".").lower()
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "svg": "svg+xml"}.get(ext, "png")
        return f"data:image/{mime};base64,{data}"
    except Exception:
        return None


def render_document_html(
    template: "DocumentTemplate",
    employee: "User",
    extra_context: dict,
    include_logo: bool = True,
) -> str:
    org = employee.organization
    resolved_body = _resolve_placeholders(template.body, employee, org, extra_context)

    logo_src = None
    if include_logo and template.include_logo:
        logo_src = _get_logo_base64(org)

    ctx = {
        "body": resolved_body,
        "org": org,
        "employee": employee,
        "logo_src": logo_src,
        "include_signature": template.include_signature_placeholder,
        "template_type": template.get_template_type_display(),
        "generated_date": timezone.localdate().strftime("%d %B %Y"),
        "site_url": getattr(settings, "SITE_URL", ""),
    }
    return render_to_string("documents/_pdf_body.html", ctx)


def generate_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa

    buf = io.BytesIO()
    pisa.CreatePDF(html.encode("utf-8"), dest=buf, encoding="utf-8")
    return buf.getvalue()


def create_generated_document(
    template: "DocumentTemplate",
    employee: "User",
    actor: "User",
    extra_context: dict,
    request=None,
) -> "GeneratedDocument":
    from .models import GeneratedDocument, record_doc_action, DocumentAuditLog

    org = employee.organization
    resolved_body = _resolve_placeholders(template.body, employee, org, extra_context)

    doc = GeneratedDocument(
        organization=org,
        template=template,
        template_type=template.template_type,
        template_name=template.name,
        employee=employee,
        resolved_body=resolved_body,
        extra_context=extra_context,
        generated_by=actor,
    )

    # Generate PDF
    logo_src = _get_logo_base64(org) if template.include_logo else None
    html = render_to_string("documents/_pdf_body.html", {
        "body": resolved_body,
        "org": org,
        "employee": employee,
        "logo_src": logo_src,
        "include_signature": template.include_signature_placeholder,
        "template_type": template.get_template_type_display(),
        "generated_date": timezone.localdate().strftime("%d %B %Y"),
    })
    pdf_bytes = generate_pdf(html)
    filename = f"{template.template_type.lower()}_{employee.employee_id or str(employee.pk)[:8]}.pdf"
    doc.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    doc.save()

    record_doc_action(
        org=org,
        actor=actor,
        action=DocumentAuditLog.Action.GENERATE_DOC,
        summary=f"Generated {template.get_template_type_display()} for {employee.display_name}",
        template=template,
        document=doc,
        request=request,
    )

    # Notification to employee
    try:
        from apps.dashboard.notification_service import send_notification
        from django.urls import reverse
        send_notification(
            employee,
            channels=("in_app",),
            source_key=f"docgen:{doc.pk}",
            title=f"New document: {template.get_template_type_display()}",
            message=f"A {template.get_template_type_display()} has been generated for you.",
            url=reverse("documents:generated_detail", kwargs={"pk": doc.pk}),
            icon="file-text",
            notification_type="document",
            force_unread=True,
        )
    except Exception:
        pass

    return doc


def get_default_body(template_type: str) -> str:
    """Return a starter HTML body for each document type."""
    from .models import DocumentTemplate as DT
    today = timezone.localdate().strftime("%d %B %Y")

    bases = {
        DT.TemplateType.OFFER: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>We are pleased to offer you the position of <strong>{{designation}}</strong> at {{company_name}}.</p>
<p>Your employment will commence on <strong>{{joining_date}}</strong> with a CTC of <strong>₹{{salary}}</strong> per annum.</p>
<p>Please sign and return a copy of this letter to confirm your acceptance.</p>
<p>We look forward to welcoming you to the team.</p>
<p>Warm regards,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.APPOINTMENT: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>This is to formally appoint you as <strong>{{designation}}</strong> in the <strong>{{department}}</strong> department at {{company_name}}, effective <strong>{{joining_date}}</strong>.</p>
<p>Your annual CTC will be <strong>₹{{salary}}</strong>. You will report to <strong>{{reporting_manager}}</strong>.</p>
<p>This appointment is subject to the terms and conditions of employment as communicated separately.</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.EXPERIENCE: """<p>To Whom It May Concern,</p>
<p>This is to certify that <strong>{{employee_name}}</strong> (Employee ID: {{employee_id}}) was employed with {{company_name}} as <strong>{{designation}}</strong> in the <strong>{{department}}</strong> department from <strong>{{joining_date}}</strong> to <strong>{{last_working_day}}</strong>.</p>
<p>During their tenure, they demonstrated professionalism and dedication. We wish them the very best in their future endeavours.</p>
<p>Issued on: {{date}}</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.RELIEVING: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>This is to acknowledge that you have been relieved from your duties as <strong>{{designation}}</strong> at {{company_name}} effective <strong>{{last_working_day}}</strong>.</p>
<p>All your dues have been settled as per company policy. We thank you for your contributions and wish you success in your future career.</p>
<p>Issued on: {{date}}</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.PROMOTION: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>We are delighted to inform you that you have been promoted to the position of <strong>{{new_designation}}</strong>, effective <strong>{{effective_date}}</strong>.</p>
<p>Your revised CTC will be <strong>₹{{new_salary}}</strong> per annum. This recognition reflects your outstanding performance and commitment to {{company_name}}.</p>
<p>Congratulations on this well-deserved achievement!</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.INCREMENT: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>We are pleased to inform you that your CTC has been revised to <strong>₹{{new_salary}}</strong> per annum, effective <strong>{{effective_date}}</strong>.</p>
<p>This increment is in recognition of your valuable contributions to {{company_name}}. We appreciate your hard work and look forward to your continued excellence.</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.WARNING: """<p>Dear <strong>{{employee_name}}</strong>,</p>
<p>This letter serves as a formal warning regarding your conduct/performance as observed on {{date}}.</p>
<p>You are required to immediately address the concern raised and ensure this does not recur. Failure to do so may result in further disciplinary action.</p>
<p>Please acknowledge receipt of this letter by signing below.</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",

        DT.TemplateType.SALARY_CERT: """<p>To Whom It May Concern,</p>
<p>This is to certify that <strong>{{employee_name}}</strong> (Employee ID: {{employee_id}}) is employed with {{company_name}} as <strong>{{designation}}</strong> in the <strong>{{department}}</strong> department since <strong>{{joining_date}}</strong>.</p>
<p>Their current gross CTC is <strong>₹{{salary}}</strong> per annum.</p>
<p>This certificate is issued upon request for official purposes.</p>
<p>Issued on: {{date}}</p>
<p>Sincerely,</p>
<p><strong>Human Resources</strong></p>
<p>{{company_name}}</p>""",
    }
    return bases.get(template_type, "<p>Start writing your document here...</p>")
