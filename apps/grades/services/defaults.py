"""Seed default HR and employee grade structures for new organizations."""

from __future__ import annotations

from apps.grades.models import CareerPathStep, Designation, Grade, GradeCategory, GradePermission
from apps.organizations.models import Organization


DEFAULT_HR_GRADES = [
    ("HR Admin", "HR-ADM", 1, None),
    ("Senior HR Manager", "HR-SM", 2, "HR Admin"),
    ("HR Manager", "HR-MGR", 3, "Senior HR Manager"),
    ("HR Executive", "HR-EXE", 4, "HR Manager"),
    ("Recruiter", "HR-REC", 5, "HR Manager"),
    ("Payroll Executive", "HR-PAY", 5, "HR Manager"),
]

DEFAULT_EMPLOYEE_GRADES = [
    ("Director", "EMP-DIR", 1, None),
    ("Senior Manager", "EMP-SM", 2, "Director"),
    ("Manager", "EMP-MGR", 3, "Senior Manager"),
    ("Assistant Manager", "EMP-AM", 4, "Manager"),
    ("Team Lead", "EMP-TL", 5, "Assistant Manager"),
    ("Senior Associate", "EMP-SA", 6, "Team Lead"),
    ("Associate", "EMP-ASC", 7, "Senior Associate"),
    ("Junior Employee", "EMP-JR", 8, "Associate"),
    ("Intern", "EMP-INT", 9, "Junior Employee"),
]

DEFAULT_DESIGNATIONS = [
    ("Senior HR Manager", "DSG-SHM", "Senior HR Manager", GradeCategory.HR),
    ("HR Executive", "DSG-HRE", "HR Executive", GradeCategory.HR),
    ("Payroll Manager", "DSG-PM", "Payroll Executive", GradeCategory.HR),
    ("Software Engineer", "DSG-SE", "Associate", GradeCategory.EMPLOYEE),
    ("Data Analyst", "DSG-DA", "Associate", GradeCategory.EMPLOYEE),
    ("Team Lead", "DSG-TL", "Team Lead", GradeCategory.EMPLOYEE),
]

GRADE_PERMISSIONS = {
    "HR Admin": [GradePermission.PermissionKey.HR_FULL, GradePermission.PermissionKey.PAYROLL_MANAGE],
    "HR Executive": [GradePermission.PermissionKey.HR_LIMITED, GradePermission.PermissionKey.ATTENDANCE_VIEW],
    "HR Manager": [GradePermission.PermissionKey.HR_LIMITED, GradePermission.PermissionKey.LEAVE_APPROVE],
    "Manager": [GradePermission.PermissionKey.TEAM_APPROVE, GradePermission.PermissionKey.LEAVE_APPROVE],
    "Senior Manager": [GradePermission.PermissionKey.TEAM_APPROVE, GradePermission.PermissionKey.REPORTS],
}


def seed_organization_grades(organization: Organization) -> dict:
    """Create default grades, designations, career paths, and permissions."""
    if Grade.objects.filter(organization=organization).exists():
        return {"grades": 0, "skipped": True}

    grade_map: dict[str, Grade] = {}
    order = 0

    for name, code, level, parent_name in DEFAULT_HR_GRADES:
        order += 1
        grade_map[name] = Grade.objects.create(
            organization=organization,
            name=name,
            code=code,
            level_number=level,
            category=GradeCategory.HR,
            parent_grade=grade_map.get(parent_name) if parent_name else None,
            reporting_grade=grade_map.get(parent_name) if parent_name else None,
            priority_order=order,
        )

    for name, code, level, parent_name in DEFAULT_EMPLOYEE_GRADES:
        order += 1
        grade_map[name] = Grade.objects.create(
            organization=organization,
            name=name,
            code=code,
            level_number=level,
            category=GradeCategory.EMPLOYEE,
            parent_grade=grade_map.get(parent_name) if parent_name else None,
            reporting_grade=grade_map.get(parent_name) if parent_name else None,
            priority_order=order,
        )

    for name, code, grade_name, _cat in DEFAULT_DESIGNATIONS:
        Designation.objects.create(
            organization=organization,
            name=name,
            code=code,
            grade=grade_map.get(grade_name),
        )

    for grade_name, perms in GRADE_PERMISSIONS.items():
        g = grade_map.get(grade_name)
        if not g:
            continue
        for pk in perms:
            GradePermission.objects.get_or_create(grade=g, permission_key=pk)

    # Career path chain for employee grades (bottom-up links)
    employee_chain = [
        "Intern",
        "Junior Employee",
        "Associate",
        "Senior Associate",
        "Team Lead",
        "Assistant Manager",
        "Manager",
        "Senior Manager",
        "Director",
    ]
    for i in range(len(employee_chain) - 1):
        CareerPathStep.objects.create(
            organization=organization,
            from_grade=grade_map[employee_chain[i]],
            to_grade=grade_map[employee_chain[i + 1]],
            sort_order=i + 1,
            requirements="Performance review and tenure criteria apply.",
        )

    return {"grades": len(grade_map), "skipped": False}
