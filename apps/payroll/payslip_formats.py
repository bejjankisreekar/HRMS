"""Registry of payslip layouts.

Single source of truth for every payslip format the org can choose. Both the
downloadable PDF and the on-screen preview are driven from here.

To ADD A NEW FORMAT (no migration needed — choices are read via a callable):
  1. Create the PDF template:      templates/payroll/payslip_pdf_<code>.html
  2. Create the preview partial:   templates/payroll/preview/_<code>.html
  3. Add one entry to PAYSLIP_FORMATS below (code -> label / pdf / preview).

Both templates receive the same context:
  payslip, employee (== payslip.user), org / organization, earnings, deductions,
  logo_src (PDF only), generated_date (PDF only).
"""
from __future__ import annotations

DEFAULT_PAYSLIP_FORMAT = "CLASSIC"

PAYSLIP_FORMATS: dict[str, dict[str, str]] = {
    "CLASSIC": {
        "label": "Classic — detailed two-column",
        "pdf": "payroll/payslip_pdf.html",
        "preview": "payroll/preview/_classic.html",
    },
    "MODERN": {
        "label": "Modern — accent banner",
        "pdf": "payroll/payslip_pdf_modern.html",
        "preview": "payroll/preview/_modern.html",
    },
    "COMPACT": {
        "label": "Compact — single table",
        "pdf": "payroll/payslip_pdf_compact.html",
        "preview": "payroll/preview/_compact.html",
    },
    "CORPORATE": {
        "label": "Corporate — centered header, boxed",
        "pdf": "payroll/payslip_pdf_corporate.html",
        "preview": "payroll/preview/_corporate.html",
    },
    "STATEMENT": {
        "label": "Statement — 4-column table, amount in words & signatures",
        "pdf": "payroll/payslip_pdf_statement.html",
        "preview": "payroll/preview/_statement.html",
    },
}


def payslip_format_choices():
    """(code, label) pairs for the model field / form select.

    Passed as a *callable* to the model field so adding formats to
    PAYSLIP_FORMATS never requires a new migration.
    """
    return [(code, cfg["label"]) for code, cfg in PAYSLIP_FORMATS.items()]


def _config(code: str) -> dict[str, str]:
    return PAYSLIP_FORMATS.get(code) or PAYSLIP_FORMATS[DEFAULT_PAYSLIP_FORMAT]


def pdf_template_for(code: str) -> str:
    return _config(code)["pdf"]


def preview_template_for(code: str) -> str:
    return _config(code)["preview"]
