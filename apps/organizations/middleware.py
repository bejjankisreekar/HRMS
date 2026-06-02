from django.utils.deprecation import MiddlewareMixin



from apps.accounts.models import User



from .utils import set_schema_search_path



# Routes that only use shared (public) tables — never tenant search_path.

_PLATFORM_SCHEMA_PREFIXES = (

    "/dashboard/super",

    "/dashboard/superadmin/",

    "/admin/",

)





class TenantSchemaMiddleware(MiddlewareMixin):

    """

    Sets PostgreSQL search_path per request:

    - tenant schema + public for authenticated tenant users

    - public for anonymous / platform users



    Platform and Super Admin routes always use public (storage, billing, org registry).

    """



    def process_request(self, request):

        path = request.path or ""

        if any(path.startswith(prefix) for prefix in _PLATFORM_SCHEMA_PREFIXES):

            set_schema_search_path(None)

            return



        user = getattr(request, "user", None)

        if getattr(user, "is_authenticated", False):

            if getattr(user, "role", None) == User.Role.SUPER_ADMIN:

                set_schema_search_path(None)

                return



        schema = None

        if getattr(user, "is_authenticated", False):

            org = getattr(user, "organization", None)

            if org and getattr(org, "schema_name", None):

                schema = org.schema_name

            elif request.session.get("tenant_schema"):

                schema = request.session["tenant_schema"]

        set_schema_search_path(schema)



    def process_response(self, request, response):

        # Reset to public to avoid leakage across re-used connections.

        try:

            set_schema_search_path(None)

        except Exception:

            pass

        return response


