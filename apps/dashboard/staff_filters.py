"""Staff list filtering for admin / HR team pages."""

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_for
from apps.attendance.models import WorkShift
from apps.grades.models import Designation, Grade, GradeStatus
from apps.organizations.models import Department, Organization


def staff_list_base_queryset(user: User) -> QuerySet[User]:
    """Base queryset — HR staff and employees only (org owner/admin excluded)."""
    if not user.organization_id:
        return User.objects.none()
    org_id = user.organization_id
    if user.role == User.Role.ADMIN:
        return User.objects.filter(organization_id=org_id).exclude(
            role__in=(User.Role.SUPER_ADMIN, User.Role.ADMIN)
        )
    if user.role == User.Role.HR:
        return User.objects.filter(
            organization_id=org_id,
            role=User.Role.EMPLOYEE,
            assigned_hr=user,
        )
    return User.objects.none()


def apply_staff_list_filters(
    qs: QuerySet[User],
    params,
    *,
    is_hr_view: bool,
) -> QuerySet[User]:
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(employee_id__icontains=q)
            | Q(department__name__icontains=q)
            | Q(designation__icontains=q)
            | Q(org_designation__name__icontains=q)
            | Q(job_grade__name__icontains=q)
            | Q(work_location__icontains=q)
        )

    role = params.get("role", "").strip()
    if role and not is_hr_view:
        qs = qs.filter(role=role)

    department = params.get("department", "").strip()
    if department:
        qs = qs.filter(department_id=department)

    grade = params.get("grade", "").strip()
    if grade:
        qs = qs.filter(job_grade_id=grade)

    designation = params.get("designation", "").strip()
    if designation:
        qs = qs.filter(org_designation_id=designation)

    manager = params.get("manager", "").strip()
    if manager:
        qs = qs.filter(reporting_manager_id=manager)

    shift = params.get("shift", "").strip()
    if shift == "default":
        qs = qs.filter(work_shift__isnull=True)
    elif shift:
        qs = qs.filter(work_shift_id=shift)

    emp_status = params.get("employment_status", "").strip()
    if emp_status:
        qs = qs.filter(employment_status=emp_status)

    status = params.get("status", "active").strip() or "active"
    if status == "active":
        qs = qs.filter(is_active=True).exclude(employment_status=User.EmploymentStatus.ARCHIVED)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    elif status == "archived":
        qs = qs.filter(employment_status=User.EmploymentStatus.ARCHIVED)

    hr_id = params.get("hr", "").strip()
    if hr_id and not is_hr_view:
        qs = qs.filter(assigned_hr_id=hr_id)

    joined_from = params.get("joined_from", "").strip()
    if joined_from:
        qs = qs.filter(date_of_joining__gte=joined_from)

    joined_to = params.get("joined_to", "").strip()
    if joined_to:
        qs = qs.filter(date_of_joining__lte=joined_to)

    return qs


def staff_filter_options(organization: Organization, is_hr_view: bool) -> dict:
    departments = Department.objects.filter(organization=organization, is_active=True).order_by(
        "sort_order", "name"
    )
    shifts = WorkShift.objects.filter(organization=organization).order_by("-is_default", "name")
    hr_users = []
    managers = []
    if not is_hr_view:
        hr_users = list(
            User.objects.filter(organization=organization, role=User.Role.HR, is_active=True).order_by(
                "first_name", "last_name"
            )
        )
        managers = list(
            User.objects.filter(
                organization=organization,
                role__in=(User.Role.ADMIN, User.Role.HR, User.Role.EMPLOYEE),
                is_active=True,
            )
            .exclude(role=User.Role.SUPER_ADMIN)
            .order_by("first_name", "last_name")[:100]
        )
    grades = Grade.objects.filter(organization=organization, status=GradeStatus.ACTIVE).order_by(
        "category", "level_number"
    )
    designations = Designation.objects.filter(organization=organization, status=GradeStatus.ACTIVE).order_by(
        "name"
    )
    return {
        "departments": departments,
        "shifts": shifts,
        "hr_users": hr_users,
        "managers": managers,
        "grades": grades,
        "designations": designations,
        "role_choices": [
            (User.Role.HR, role_display_for(User.Role.HR, organization)),
            (User.Role.EMPLOYEE, "Employee"),
        ],
        "dept_label": organization.department_label,
        "dept_label_plural": organization.department_label_plural,
    }
