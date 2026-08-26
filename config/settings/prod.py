"""
El Patio SIG — Settings de PRODUCCIÓN.

Requiere: DJANGO_DEBUG=False, DJANGO_SECRET_KEY segura, DJANGO_ALLOWED_HOSTS
completos, DB_ENGINE=postgres con credenciales. Endurecimiento por defecto.
"""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, Path, env_bool, env_list, os

# DEBUG debe ser False en producción. Si se setea True, Django lanza advertencia.
DEBUG = env_bool("DJANGO_DEBUG", False)

assert not DEBUG, "DJANGO_DEBUG=True está prohibido en producción."

# Fail-closed: no arrancar con el SECRET_KEY placeholder de desarrollo
# ("django-insecure-dev-only-change-me" de base.py). Ver SECURITY.md SEC-01.
assert SECRET_KEY and not SECRET_KEY.startswith("django-insecure"), (
    "DJANGO_SECRET_KEY debe configurarse con un valor aleatorio en producción."
)

# Hosts explícitos (obligatorio en producción)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "")

# ---------------------------------------------------------------------------
# Seguridad de transporte (detrás de nginx/TLS)
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
# IMPORTANTE: usar solo detrás de un proxy (nginx) que SOBREESCRIBA
# X-Forwarded-Proto con $scheme (proxy_set_header X-Forwarded-Proto $scheme).
# Si el proxy reenvía el header tal cual llega, un cliente podría falsificarlo.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies solo por HTTPS
SESSION_COOKIE_SECURE = env_bool("DJANGO_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_COOKIE_SECURE", True)

# HSTS
if env_bool("DJANGO_SECURE_HSTS", True):
    SECURE_HSTS_SECONDS = 31536000  # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Frame/clickjacking y otros headers. Varios ya son el default de Django 5.x
# (X_FRAME_OPTIONS="DENY", nosniff, referrer same-origin) pero se fijan acá de
# forma explícita para que el endurecimiento sea evidente y no dependa de
# cambios de default en futuras versiones.
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True              # X-Content-Type-Options: nosniff
SECURE_REFERRER_POLICY = "same-origin"          # no filtrar la URL completa a terceros
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# CSRF confiable (dominios de producción). Vacío = solo same-origin, correcto
# cuando frontend y backend comparten dominio (ver SECURITY.md SEC-05).
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Cookie CSRF: HttpOnly (el token se lee del input oculto del form, NUNCA desde
# JS; el POS debe usar {% csrf_token %} / el input, no leer la cookie) y
# SameSite=Lax (default de Django, explícito por claridad).
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.security_views.csrf_failure"

# Sesiones: la terminal del bar es COMPARTIDA entre bartenders/camareros.
# - SESSION_EXPIRE_AT_BROWSER_CLOSE: la sesión muere al cerrar el navegador.
# - SESSION_COOKIE_AGE = 8 h: expira aunque el navegador quede abierto (un turno).
# - SESSION_SAVE_EVERY_REQUEST: renueva la expiración con actividad.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60           # 8 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# ---------------------------------------------------------------------------
# Base de datos: en producción SIEMPRE PostgreSQL
# ---------------------------------------------------------------------------
if env_bool("FORCE_SQLITE_IN_PROD", False):
    # Escape para demos puntuales; no usar en un despliegue real.
    pass

# ---------------------------------------------------------------------------
# Límites de request (anti-DoS)
# ---------------------------------------------------------------------------
# 2 MB para POST (POS manda el carrito en JSON; subir si se adjuntan imágenes
# por formulario). El default de Django es 2.5 MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# ---------------------------------------------------------------------------
# Correo (password reset, alertas a ADMINS, SERVER_EMAIL)
# ---------------------------------------------------------------------------
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
SERVER_EMAIL = os.getenv("DJANGO_SERVER_EMAIL", "no-reply@elpatio.local")
DEFAULT_FROM_EMAIL = SERVER_EMAIL
# DJANGO_ADMINS="admin@dominio.com,otro@dominio.com" (reciben mails de errores 5xx)
ADMINS = [(addr, addr) for addr in env_list("DJANGO_ADMINS")]

if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    # ADVERTENCIA: sin DJANGO_EMAIL_HOST los mails (reset de password, alertas)
    # se imprimen en consola y NO se envían. Configurar en producción.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Logging: app + errores + pista de auditoría (eventos financieros)
# ---------------------------------------------------------------------------
LOG_DIR = Path(os.getenv("DJANGO_LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} pid={process} {message}",
            "style": "{",
        },
        "simple": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "file_app": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "elpatio.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
        },
        "file_audit": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "audit.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["file_app"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["file_app"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["file_app"], "level": "WARNING", "propagate": False},
        "audit": {"handlers": ["file_audit"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console", "file_app"], "level": "INFO"},
}
