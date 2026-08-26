"""
El Patio SIG — Settings base (comunes a desarrollo y producción).

Los valores sensibles se leen desde variables de entorno (.env vía python-dotenv).
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Cargar .env si existe (no falla si no está)
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Lee una variable de entorno como booleano."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    """Lee una variable de entorno como lista separada por comas."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Seguridad básica
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # django.contrib.admin está DESHABILITADO: la administración se hace con
    # pantallas propias del sistema (decisión del dueño del pub).
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "django_bootstrap5",
    # Aplicaciones del sistema
    "core",
    "accounts",
    "inventory",
    "sales",
    "tables",
    "staff",
    "customers",
    "purchases",
    "reservations",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.global_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos: SQLite (dev) o PostgreSQL (prod) según DB_ENGINE
# ---------------------------------------------------------------------------
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").strip().lower()

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "elpatio"),
            "USER": os.getenv("DB_USER", "elpatio"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("DB_NAME", "db.sqlite3"),
        }
    }

# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "core:login"
# IMPORTANTE: usar los names completos ("core:...") porque las URLs de core
# viven bajo app_name="core". reverse("dashboard") falla (NoReverseMatch) y
# rompería el login con un 500. Ver SECURITY.md SEC-21.
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:login"

# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos y media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Django Bootstrap 5
# ---------------------------------------------------------------------------
BOOTSTRAP5 = {
    "css_url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
    "javascript_url": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
    "theme_url": None,
    "success_css_class": "",
    "error_css_class": "is-invalid",
}

# Mensajes → clases de alerta de Bootstrap
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {
    messages.DEBUG: "alert-secondary",
    messages.INFO: "alert-info",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
