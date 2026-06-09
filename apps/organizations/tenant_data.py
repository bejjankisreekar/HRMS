"""Schema-per-tenant data layer (shared users + isolated operational data).

Shared (public): User, Organization, subscriptions/plans/billing, super-admin, audit.
Per-tenant schema: all operational data (attendance, payroll, salary, leave,
departments, grades, lifecycle, orgchart, storage, notifications).

This module owns:
  * the tenant model set,
  * org-row resolution (find each model's path to its Organization),
  * schema table cloning,
  * org data copy + count validation.

It is migration tooling — it never runs during normal requests.
"""
from __future__ import annotations

from django.apps import apps as django_apps
from django.db import connection

from .models import Organization
from .utils import SCHEMA_RE, TenantSchemaError, create_tenant_schema, drop_tenant_schema, schema_exists

# Whole apps whose models are tenant-scoped operational data.
TENANT_APP_LABELS = {
    "attendance", "leaves", "payroll", "grades", "lifecycle", "orgchart", "storage",
}
# Tenant models that live inside otherwise-shared apps.
TENANT_EXTRA_MODELS = [
    ("organizations", "Department"),
    ("dashboard", "DashboardNotification"),
]


def tenant_models() -> list:
    models: list = []
    for label in sorted(TENANT_APP_LABELS):
        try:
            cfg = django_apps.get_app_config(label)
        except LookupError:
            continue
        models.extend(cfg.get_models())
    for app_label, name in TENANT_EXTRA_MODELS:
        try:
            models.append(django_apps.get_model(app_label, name))
        except LookupError:
            pass
    seen, out = set(), []
    for m in models:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


_TENANT_SET = None


def _tenant_set() -> set:
    global _TENANT_SET
    if _TENANT_SET is None:
        _TENANT_SET = set(tenant_models())
    return _TENANT_SET


def resolve_org_path(model, _depth: int = 0):
    """ORM lookup string from `model` to its Organization (or None if unresolvable)."""
    if _depth > 6:
        return None
    User = django_apps.get_model("accounts", "User")

    def _is_fk(field):
        return getattr(field, "many_to_one", False) or getattr(field, "one_to_one", False)

    # 1) direct organization FK
    try:
        f = model._meta.get_field("organization")
        if _is_fk(f) and f.related_model is Organization:
            return "organization"
    except Exception:
        pass

    # 2) a FK to User -> user.organization
    for fname in ("user", "target_user", "employee", "staff", "member", "owner", "approved_by"):
        try:
            f = model._meta.get_field(fname)
        except Exception:
            continue
        if _is_fk(f) and f.related_model is User:
            return f"{fname}__organization"

    # 3) a FK to another tenant model -> walk the parent chain
    for f in model._meta.get_fields():
        if _is_fk(f) and f.related_model in _tenant_set() and f.related_model is not model:
            sub = resolve_org_path(f.related_model, _depth + 1)
            if sub:
                return f"{f.name}__{sub}"
    return None


def clone_tenant_tables(schema_name: str) -> list[str]:
    """Create empty copies of every tenant table inside `schema_name`."""
    if not SCHEMA_RE.match(schema_name):
        raise TenantSchemaError("Invalid schema name.")
    create_tenant_schema(schema_name)
    cloned = []
    with connection.cursor() as cursor:
        for model in tenant_models():
            table = model._meta.db_table
            cursor.execute(
                f'CREATE TABLE IF NOT EXISTS "{schema_name}"."{table}" '
                f'(LIKE "public"."{table}" INCLUDING ALL)'
            )
            cloned.append(table)
    return cloned


def copy_org_data(org: Organization, schema_name: str) -> list[dict]:
    """Copy this org's rows from public into its schema; return per-table report."""
    report = []
    with connection.cursor() as cursor:
        for model in tenant_models():
            table = model._meta.db_table
            pk_col = model._meta.pk.column
            path = resolve_org_path(model)
            if path is None:
                report.append({"table": table, "status": "SKIP", "expected": 0, "copied": 0,
                               "note": "no org path"})
                continue
            pks = list(model._base_manager.filter(**{path: org}).values_list("pk", flat=True))
            expected = len(pks)
            if expected:
                cursor.execute(
                    f'INSERT INTO "{schema_name}"."{table}" '
                    f'SELECT * FROM "public"."{table}" WHERE "{pk_col}" = ANY(%s) '
                    f'ON CONFLICT DO NOTHING',
                    [pks],
                )
            cursor.execute(f'SELECT count(*) FROM "{schema_name}"."{table}"')
            copied = cursor.fetchone()[0]
            report.append({
                "table": table,
                "status": "OK" if copied == expected else "MISMATCH",
                "expected": expected,
                "copied": copied,
                "path": path,
            })
    return report


def provision_org_schema(org: Organization, *, reset: bool = False) -> list[dict]:
    """Full provision: (re)create schema, clone tables, copy + validate org data."""
    schema = org.schema_name
    if not schema:
        raise TenantSchemaError(f"Organization {org.organization_code} has no schema_name.")
    if reset and schema_exists(schema):
        drop_tenant_schema(schema)
    clone_tenant_tables(schema)
    return copy_org_data(org, schema)
