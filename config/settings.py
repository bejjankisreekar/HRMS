import json
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = config("DJANGO_SECRET_KEY", default="change-me-in-env")
DEBUG = config("DJANGO_DEBUG", cast=bool, default=False)

# Schema-per-tenant request routing. OFF until every org has been migrated with
# `manage.py provision_tenant --all`. When True, each request resolves operational
# tables in the tenant's schema (shared tables stay in public).
TENANT_SCHEMA_ROUTING = config("TENANT_SCHEMA_ROUTING", cast=bool, default=False)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv(), default="localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = config(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    cast=Csv(),
    default="http://127.0.0.1:8000,http://localhost:8000",
)

SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# config.json - file-based settings, sitting under the environment.
#
# Precedence: environment variable > config.json > no value.
# Env always wins, so deployments that inject env vars (Render, Docker) work
# without this file ever existing. See config.json.example for the shape.
# ---------------------------------------------------------------------------

CONFIG_JSON_PATH = Path(config("CONFIG_JSON", default=str(BASE_DIR / "config.json")))


def _load_config_json(path: Path) -> dict:
    """Read config.json. Missing is fine; malformed is not - a config file that
    is silently ignored because of a stray comma is worse than a loud failure."""
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ImproperlyConfigured(f"{path} must contain a JSON object at the top level.")
    return data


CONFIG_JSON = _load_config_json(CONFIG_JSON_PATH)


def json_setting(*keys: str, env: str | None = None, default=None):
    """Look up a dotted path in config.json, with the environment overriding it.

    json_setting("superadmin", "email", env="SUPERADMIN_EMAIL")
    """
    if env:
        from_env = config(env, default=None)
        if from_env not in (None, ""):
            return from_env
    node = CONFIG_JSON
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return default if node in (None, "") else node


# Super Admin bootstrap (created automatically on first migrate).
# NOTE: there is deliberately no fallback password here. When none is supplied,
# `apps.accounts.signals.ensure_default_superadmin` returns without creating
# anything - far safer than booting production with a publicly known password.
SUPERADMIN_EMAIL = json_setting("superadmin", "email", env="SUPERADMIN_EMAIL")
SUPERADMIN_PASSWORD = json_setting("superadmin", "password", env="SUPERADMIN_PASSWORD")
SUPERADMIN_USERNAME = json_setting(
    "superadmin", "username", env="SUPERADMIN_USERNAME", default="superadmin"
)

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Local apps
    'apps.organizations',
    'apps.accounts.apps.AccountsConfig',
    'apps.attendance',
    'apps.leaves',
    'apps.payroll',
    'apps.dashboard',
    'apps.orgchart',
    'apps.shifts',
    'apps.lifecycle',
    'apps.subscriptions',
    'apps.storage',
    'apps.leads',
    'apps.grades',
    'apps.team',
    'apps.documents.apps.DocumentsConfig',
    'apps.ruleengine.apps.RuleEngineConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.organizations.middleware.TenantSchemaMiddleware',
    'apps.subscriptions.middleware.SubscriptionPlanMiddleware',
    'apps.subscriptions.feature_middleware.FeatureGateMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.dashboard.context_processors.hrms_sidebar',
                'apps.dashboard.context_processors.plan_identity',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config("DB_NAME", default="hrms"),
        'USER': config("DB_USER", default="postgres"),
        'PASSWORD': config("DB_PASSWORD", default="postgres"),
        'HOST': config("DB_HOST", default="localhost"),
        'PORT': config("DB_PORT", default="5432"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Serve static files via WhiteNoise in production (compressed + hashed names).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

MEDIA_URL = "media/"
# Uploads (payslip PDFs, HR letters, attachments, logos) MUST live on storage that
# survives a redeploy. Containers have ephemeral filesystems, so point MEDIA_ROOT at
# a mounted persistent disk in production - see the disk mount in render.yaml.
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv(), default="")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Contact form — FormSubmit (no SMTP) + optional Gmail SMTP (see .env.example)
CONTACT_INBOX_EMAIL = config("CONTACT_INBOX_EMAIL", default="sreekarbejjanki@gmail.com")
FORMSUBMIT_ENABLED = config("FORMSUBMIT_ENABLED", default=True, cast=bool)
FORMSUBMIT_EMAIL = config("FORMSUBMIT_EMAIL", default=CONTACT_INBOX_EMAIL)
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="sreekarbejjanki@gmail.com")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="").strip()
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="HRMS Suite <sreekarbejjanki@gmail.com>",
)
SALES_INBOX_EMAIL = config("SALES_INBOX_EMAIL", default=CONTACT_INBOX_EMAIL)


# ---------------------------------------------------------------------------
# Security hardening
#
# These stay off while DEBUG is on so local http://127.0.0.1 development works,
# and switch on automatically in production. SECURE_PROXY_SSL_HEADER is required
# behind a TLS-terminating proxy (Render, Heroku, nginx) - without it Django sees
# plain HTTP and SECURE_SSL_REDIRECT would loop forever.
# ---------------------------------------------------------------------------

# Django's test runner forces DEBUG=False, so without this every test-client
# request would be answered with a 301 to https:// and the suite would fail in CI
# (but pass locally, where .env sets DEBUG=True) - a genuinely baffling failure.
TESTING = "test" in sys.argv or "PYTEST_CURRENT_TEST" in os.environ

_SSL_ENABLED = config("DJANGO_SECURE_SSL", cast=bool, default=not DEBUG and not TESTING)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _SSL_ENABLED
SESSION_COOKIE_SECURE = _SSL_ENABLED
CSRF_COOKIE_SECURE = _SSL_ENABLED

# HSTS tells browsers "never use http for this domain again", and is cached hard.
# Start at 0 and raise deliberately once HTTPS is confirmed working on the domain;
# a premature long max-age locks users out of a site that cannot serve TLS yet.
SECURE_HSTS_SECONDS = config("DJANGO_HSTS_SECONDS", cast=int, default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("DJANGO_HSTS_SUBDOMAINS", cast=bool, default=False)
SECURE_HSTS_PRELOAD = config("DJANGO_HSTS_PRELOAD", cast=bool, default=False)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = config(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE", cast=bool, default=False
)
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", cast=int, default=60 * 60 * 12)

# Reuse database connections instead of opening one per request. Keep this below
# the provider's idle-connection timeout.
DATABASES["default"]["CONN_MAX_AGE"] = config("DB_CONN_MAX_AGE", cast=int, default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True


# ---------------------------------------------------------------------------
# Logging - without this, application errors surface only as a 500 page.
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        # Unhandled exceptions in views. Django suppresses these when DEBUG is on.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Fail fast on an unsafe production configuration.
#
# A missing env var should stop the deploy, not silently downgrade security.
# Every check below is skipped while DEBUG is on so local development is
# unaffected. Set DJANGO_ALLOW_UNSAFE_CONFIG=True to bypass (don't).
# ---------------------------------------------------------------------------

if not DEBUG and not TESTING and not config(
    "DJANGO_ALLOW_UNSAFE_CONFIG", cast=bool, default=False
):
    _unsafe = []

    if SECRET_KEY in ("", "change-me-in-env") or len(SECRET_KEY) < 50:
        _unsafe.append(
            "DJANGO_SECRET_KEY is unset, still the placeholder, or shorter than 50 "
            "characters. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:
        _unsafe.append(
            "DJANGO_ALLOWED_HOSTS is unset or still the local default. Set it to the "
            "real hostname(s) this site is served from."
        )

    if DATABASES["default"].get("PASSWORD") in ("", "postgres"):
        _unsafe.append("DB_PASSWORD is unset or the default 'postgres'.")

    # A blank superadmin password is a supported state - it means "do not
    # auto-create a Super Admin". A weak one is not.
    if SUPERADMIN_PASSWORD and len(str(SUPERADMIN_PASSWORD)) < 12:
        _unsafe.append(
            "The configured Super Admin password is shorter than 12 characters. "
            "Set superadmin.password in config.json, or SUPERADMIN_PASSWORD in the "
            "environment, to something strong - this account can reach every tenant."
        )

    if _unsafe:
        raise ImproperlyConfigured(
            "Refusing to start with an unsafe production configuration:\n  - "
            + "\n  - ".join(_unsafe)
        )
