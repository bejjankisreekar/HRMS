from __future__ import annotations

from apps.storage.models import FileCategory

EXT_MAP = {
    ".pdf": FileCategory.PDF,
    ".jpg": FileCategory.IMAGE,
    ".jpeg": FileCategory.IMAGE,
    ".png": FileCategory.IMAGE,
    ".gif": FileCategory.IMAGE,
    ".webp": FileCategory.IMAGE,
    ".mp4": FileCategory.VIDEO,
    ".mov": FileCategory.VIDEO,
    ".avi": FileCategory.VIDEO,
    ".doc": FileCategory.DOCUMENT,
    ".docx": FileCategory.DOCUMENT,
    ".xls": FileCategory.DOCUMENT,
    ".xlsx": FileCategory.DOCUMENT,
    ".txt": FileCategory.DOCUMENT,
    ".csv": FileCategory.DOCUMENT,
}


def categorize_path(path: str, source_field: str = "") -> str:
    lower = (path or "").lower()
    if "reimbursement" in lower or "payroll" in lower or "payslip" in lower:
        return FileCategory.PAYROLL
    if "profile_picture" in source_field or "org_logos" in lower:
        return FileCategory.IMAGE
    if "leave_attachment" in lower:
        return FileCategory.EMPLOYEE
    if "recruitment" in lower or "resume" in lower:
        return FileCategory.EMPLOYEE
    if "onboarding" in lower:
        return FileCategory.EMPLOYEE
    for ext, cat in EXT_MAP.items():
        if lower.endswith(ext):
            return cat
    return FileCategory.OTHER
