from pathlib import Path

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = config("DJANGO_SECRET_KEY", default="change-me-in-env")
DEBUG = config("DJANGO_DEBUG", cast=bool, default=True)

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

# Super Admin bootstrap (created automatically on first migrate)
SUPERADMIN_EMAIL = config("SUPERADMIN_EMAIL", default="superadmin@hrms.com")
SUPERADMIN_PASSWORD = config("SUPERADMIN_PASSWORD", default="Admin@123")
SUPERADMIN_USERNAME = config("SUPERADMIN_USERNAME", default="superadmin")

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
MEDIA_ROOT = BASE_DIR / "media"

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
