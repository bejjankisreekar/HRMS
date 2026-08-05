"""Payslip PDF generation — mirrors apps.documents.services.generate_pdf (xhtml2pdf)."""
from __future__ import annotations

import io
from itertools import zip_longest

from django.template.loader import render_to_string
from django.utils import timezone

from .models import Payslip


def generate_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa

    buf = io.BytesIO()
    pisa.CreatePDF(html.encode("utf-8"), dest=buf, encoding="utf-8")
    return buf.getvalue()


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n:
        parts.append(_two_digits(n))
    return " ".join(parts)


def amount_in_words(amount) -> str:
    """Whole-rupee amount to words using the Indian numbering system.

    e.g. 9500 -> "Nine Thousand Five Hundred"; 145803 -> "One Lakh Forty Five
    Thousand Eight Hundred Three".
    """
    try:
        n = int(round(float(amount)))
    except (TypeError, ValueError):
        return ""
    if n == 0:
        return "Zero"
    n = abs(n)
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    hundred = n
    words = []
    if crore:
        words.append(amount_in_words(crore) + " Crore")
    if lakh:
        words.append(_two_digits(lakh) + " Lakh")
    if thousand:
        words.append(_two_digits(thousand) + " Thousand")
    if hundred:
        words.append(_three_digits(hundred))
    return " ".join(w for w in words if w).strip()


def payslip_common_context(payslip: Payslip) -> dict:
    """Context shared by every payslip layout (PDF + on-screen preview).

    Formats may use any of these; see apps.payroll.payslip_formats for the
    per-format template mapping.
    """
    org = payslip.user.organization
    lines = list(payslip.lines.select_related("component").order_by("sort_order"))
    earnings = [l for l in lines if l.line_type == "EARNING"]
    deductions = [l for l in lines if l.line_type == "DEDUCTION"]
    return {
        "payslip": payslip,
        "employee": payslip.user,
        "org": org,
        "organization": org,
        "earnings": earnings,
        "deductions": deductions,
        # Row-aligned pairs for side-by-side 4-column layouts.
        "line_pairs": list(zip_longest(earnings, deductions)),
        "net_in_words": amount_in_words(payslip.net_salary),
    }


def _payslip_format_for(org) -> str:
    """Return the org's configured payslip format code (defaults to CLASSIC)."""
    from .models import PayrollSettings
    from .payslip_formats import DEFAULT_PAYSLIP_FORMAT

    if org is None:
        return DEFAULT_PAYSLIP_FORMAT
    settings_obj = PayrollSettings.objects.filter(organization=org).first()
    return getattr(settings_obj, "payslip_format", None) or DEFAULT_PAYSLIP_FORMAT


def render_payslip_pdf(payslip: Payslip) -> bytes:
    from apps.documents.services import _get_logo_base64

    from .payslip_formats import pdf_template_for

    org = payslip.user.organization
    ctx = payslip_common_context(payslip)
    ctx.update({
        "logo_src": _get_logo_base64(org) if org and org.logo else None,
        "generated_date": timezone.localdate().strftime("%d %B %Y"),
    })
    html = render_to_string(pdf_template_for(_payslip_format_for(org)), ctx)
    return generate_pdf(html)
