from django.contrib.auth import login as django_login

# Primary backend for session login (must match settings.AUTHENTICATION_BACKENDS)
LOGIN_BACKEND = "apps.accounts.backends.EmailOrUsernameBackend"


def login_user(request, user) -> None:
    """Log in a user when multiple AUTHENTICATION_BACKENDS are configured."""
    django_login(request, user, backend=LOGIN_BACKEND)
