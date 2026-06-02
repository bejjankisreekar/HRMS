"""Grade hierarchy tree and analytics."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Sum

from apps.accounts.models import User
from apps.grades.models import CareerPathStep, Designation, Grade, GradeCategory, GradeStatus
from apps.organizations.models import Organization


def build_grade_tree(organization: Organization, category: str | None = None) -> list[dict]:
    qs = Grade.objects.filter(organization=organization, status=GradeStatus.ACTIVE)
    if category:
        qs = qs.filter(category=category)
    grades = list(qs.select_related("parent_grade", "reporting_grade"))
    by_parent: dict[str | None, list[Grade]] = defaultdict(list)
    for g in grades:
        key = str(g.parent_grade_id) if g.parent_grade_id else None
        by_parent[key].append(g)

    def node(g: Grade) -> dict:
        return {
            "id": str(g.pk),
            "name": g.name,
            "code": g.code,
            "category": g.category,
            "level_number": g.level_number,
            "member_count": User.objects.filter(organization=organization, job_grade=g).count(),
            "children": [node(c) for c in sorted(by_parent.get(str(g.pk), []), key=lambda x: x.priority_order)],
        }

    roots = sorted(by_parent.get(None, []), key=lambda x: (x.category, x.level_number, x.priority_order))
    return [node(r) for r in roots]


def build_hierarchy_context(organization: Organization) -> dict:
    trees = {
        cat.value: build_grade_tree(organization, cat.value)
        for cat in GradeCategory
    }
    return {
        "hr_tree": trees.get(GradeCategory.HR, []),
        "employee_tree": trees.get(GradeCategory.EMPLOYEE, []),
        "management_tree": trees.get(GradeCategory.MANAGEMENT, []),
        "all_trees": trees,
    }


def build_analytics_context(organization: Organization) -> dict:
    grades = Grade.objects.filter(organization=organization, status=GradeStatus.ACTIVE)
    by_grade = (
        User.objects.filter(organization=organization, job_grade__isnull=False)
        .values("job_grade__name", "job_grade__category")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    by_dept = (
        User.objects.filter(organization=organization)
        .values("department__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:12]
    )
    category_dist = (
        grades.values("category")
        .annotate(count=Count("id"))
        .order_by("category")
    )
    promotion_count = CareerPathStep.objects.filter(organization=organization, is_active=True).count()
    designation_count = Designation.objects.filter(organization=organization, status=GradeStatus.ACTIVE).count()

    salary_by_grade = []
    for g in grades.filter(salary_band_min__isnull=False)[:10]:
        members = User.objects.filter(organization=organization, job_grade=g).count()
        salary_by_grade.append(
            {
                "name": g.name,
                "min": float(g.salary_band_min or 0),
                "max": float(g.salary_band_max or 0),
                "members": members,
            }
        )

    return {
        "grade_distribution": list(by_grade),
        "dept_distribution": [{"name": r["department__name"] or "Unassigned", "count": r["count"]} for r in by_dept],
        "category_chart": {
            "labels": [GradeCategory(c["category"]).label for c in category_dist],
            "values": [c["count"] for c in category_dist],
        },
        "employee_chart": {
            "labels": [r["job_grade__name"] for r in by_grade[:10]],
            "values": [r["count"] for r in by_grade[:10]],
        },
        "promotion_count": promotion_count,
        "designation_count": designation_count,
        "total_grades": grades.count(),
        "mapped_employees": User.objects.filter(organization=organization, job_grade__isnull=False).count(),
        "salary_by_grade": salary_by_grade,
    }


def get_career_path_for_grade(grade: Grade) -> list[dict]:
    steps = []
    current = grade
    seen = set()
    while current and str(current.pk) not in seen:
        seen.add(str(current.pk))
        nxt = (
            CareerPathStep.objects.filter(organization=grade.organization, from_grade=current, is_active=True)
            .select_related("to_grade")
            .order_by("sort_order")
            .first()
        )
        if not nxt:
            break
        steps.append({"from": current.name, "to": nxt.to_grade.name, "requirements": nxt.requirements})
        current = nxt.to_grade
    return steps


def hub_context(organization: Organization) -> dict:
    grades = Grade.objects.filter(organization=organization)
    return {
        "total_grades": grades.count(),
        "active_grades": grades.filter(status=GradeStatus.ACTIVE).count(),
        "archived_grades": grades.filter(status=GradeStatus.ARCHIVED).count(),
        "designations": Designation.objects.filter(organization=organization).count(),
        "mapped_staff": User.objects.filter(organization=organization, job_grade__isnull=False).count(),
        "unmapped_staff": User.objects.filter(organization=organization, job_grade__isnull=True).exclude(
            role=User.Role.SUPER_ADMIN
        ).count(),
        "categories": list(grades.values("category").annotate(count=Count("id")).order_by("category")),
    }
