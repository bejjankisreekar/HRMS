from django.db import transaction

from apps.accounts.models import User

from .models import Organization
from .utils import (
    TenantSchemaError,
    create_tenant_schema,
    drop_tenant_schema,
    generate_organization_code,
    normalize_schema_name,
    schema_exists,
)


class OrganizationSignupError(RuntimeError):
    pass


@transaction.atomic
def create_organization_with_tenant_schema_and_admin(*, org_data: dict, admin_data: dict):
    """
    Creates:
    - Organization with unique organization_code + schema_name
    - PostgreSQL schema for the tenant
    - Tenant admin user

    Any failure rolls back the Organization/User creation.
    """
    # 1) Generate unique organization_code and schema_name
    for _ in range(50):
        code = generate_organization_code()
        if Organization.objects.filter(organization_code=code).exists():
            continue
        schema_name = normalize_schema_name(code)
        if schema_exists(schema_name):
            continue
        break
    else:
        raise OrganizationSignupError("Unable to allocate a unique organization code.")

    # 2) Create organization
    org = Organization.objects.create(
        organization_code=code,
        schema_name=schema_name,
        **org_data,
    )

    # 3) Create schema (if this fails, transaction will roll back org/admin)
    try:
        create_tenant_schema(schema_name)
    except Exception as exc:
        raise OrganizationSignupError(f"Failed to create tenant schema: {exc}") from exc

    # 4) Create admin user
    admin = User.objects.create_user(
        email=admin_data["email"],
        password=admin_data["password"],
        username=admin_data["username"],
        first_name=admin_data.get("first_name", ""),
        last_name=admin_data.get("last_name", ""),
        phone=admin_data.get("mobile_number", "") or "",
        designation=admin_data.get("designation", "") or "",
        profile_picture=admin_data.get("profile_picture"),
        terms_accepted=bool(admin_data.get("terms_accepted")),
        privacy_policy_accepted=bool(admin_data.get("privacy_policy_accepted")),
        role=User.Role.ADMIN,
        organization=org,
        is_staff=True,
    )

    seed_organization_defaults(org)

    return org, admin


def seed_organization_defaults(org: Organization) -> None:
    from apps.grades.services.defaults import seed_organization_grades

    seed_organization_grades(org)


@transaction.atomic
def delete_organization_and_tenant(org: Organization) -> None:
    """
    Remove organization record, deactivate its users, and drop tenant schema.
    """
    schema_name = org.schema_name
    User.objects.filter(organization=org).update(is_active=False, organization=None)
    org.delete()
    if schema_name and schema_exists(schema_name):
        try:
            drop_tenant_schema(schema_name)
        except Exception as exc:
            raise OrganizationSignupError(f"Failed to drop tenant schema: {exc}") from exc

