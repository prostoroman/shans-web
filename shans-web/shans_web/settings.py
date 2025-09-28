from __future__ import annotations

import os
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, True),
    DEFAULT_RF=(float, 0.03),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])
SITE_DOMAIN = env("SITE_DOMAIN", default="localhost:8000")

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [str(BASE_DIR / "shans_web" / "locale")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    # Third-party
    "rest_framework",
    "django.contrib.humanize",
    "whitenoise.runserver_nostatic",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "crispy_forms",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.data",
    "apps.markets",
    "apps.portfolio",
    "apps.activity",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "shans_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.plan_status",
            ]
        },
    }
]

WSGI_APPLICATION = "shans_web.wsgi.application"

DATABASES = {
    "default": env.db(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATICFILES_DIRS = [str(BASE_DIR / "static")]
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# Allauth
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "optional" if DEBUG else "mandatory"
ACCOUNT_USERNAME_REQUIRED = False
LOGIN_REDIRECT_URL = "/dashboard"
LOGOUT_REDIRECT_URL = "/"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# App-specific
DEFAULT_RF = env.float("DEFAULT_RF", default=0.03)
FMP_API_KEY = env("FMP_API_KEY", default="")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [f"https://{SITE_DOMAIN}", f"http://{SITE_DOMAIN}"]

