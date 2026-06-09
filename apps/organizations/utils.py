import re
import secrets
from dataclasses import dataclass
from functools import lru_cache

from django.db import connection, transaction

try:
    from psycopg2 import sql  # type: ignore
except Exception:  # pragma: no cover
    sql = None  # fallback; we still validate names strictly


SCHEMA_RE = re.compile(r"^[a-z0-9_]{1,63}$")


class TenantSchemaError(RuntimeError):
    pass


def generate_organization_code() -> str:
    """
    Generate an 8-char uppercase hexadecimal code.
    Example: secrets.token_hex(4).upper() -> 'A1F93B2C'
    """
    return secrets.token_hex(4).upper()


def normalize_schema_name(organization_code: str) -> str:
    schema = (organization_code or "").strip().lower()
    if not SCHEMA_RE.match(schema):
        raise TenantSchemaError("Invalid schema name generated.")
    return schema


def schema_exists(schema_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        return cursor.fetchone() is not None


def create_tenant_schema(schema_name: str) -> None:
    """
    Create PostgreSQL schema safely.
    Uses Identifier quoting when available.
    """
    if not SCHEMA_RE.match(schema_name):
        raise TenantSchemaError("Invalid schema name.")

    with connection.cursor() as cursor:
        if sql is not None:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name))
            )
        else:
            # Extremely strict validation above prevents injection
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")


def drop_tenant_schema(schema_name: str) -> None:
    """Drop a tenant PostgreSQL schema and all objects in it."""
    if not SCHEMA_RE.match(schema_name):
        raise TenantSchemaError("Invalid schema name.")
    if schema_name == "public":
        raise TenantSchemaError("Cannot drop public schema.")

    with connection.cursor() as cursor:
        if sql is not None:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
            )
        else:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")


@lru_cache(maxsize=256)
def tenant_schema_has_user_table(schema_name: str) -> bool:
    """True when the tenant schema contains its own accounts_user table."""
    if not schema_name or not SCHEMA_RE.match(schema_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'accounts_user'
            """,
            [schema_name],
        )
        return cursor.fetchone() is not None


# A representative tenant table — its presence means the schema is provisioned.
_TENANT_MARKER_TABLE = "payroll_salarycomponent"


@lru_cache(maxsize=256)
def tenant_schema_is_provisioned(schema_name: str) -> bool:
    """True when the tenant schema has its isolated operational tables cloned in."""
    if not schema_name or not SCHEMA_RE.match(schema_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            [schema_name, _TENANT_MARKER_TABLE],
        )
        return cursor.fetchone() is not None


def schema_routing_enabled() -> bool:
    """Tenant request routing is opt-in (enable only after all orgs are migrated)."""
    from django.conf import settings

    return bool(getattr(settings, "TENANT_SCHEMA_ROUTING", False))


def set_schema_search_path(schema_name: str | None) -> None:
    """
    Set search_path for the current DB connection.

    Shared tables (accounts_user, organizations_organization, subscriptions/plans,
    super-admin) always resolve in `public`. When routing is enabled AND the tenant
    schema is provisioned, operational tables resolve to the tenant schema first;
    anything not cloned there falls through to `public`.
    """
    if schema_name and schema_routing_enabled():
        if not SCHEMA_RE.match(schema_name):
            raise TenantSchemaError("Invalid schema name.")
        with connection.cursor() as cursor:
            if tenant_schema_is_provisioned(schema_name):
                cursor.execute("SET search_path TO %s, public", [schema_name])
            else:
                cursor.execute("SET search_path TO public")
    else:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

