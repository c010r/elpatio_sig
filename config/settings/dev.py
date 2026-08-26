"""
El Patio SIG — Settings de DESARROLLO.

SQLite, DEBUG activo, correo en consola. Nada de esto debe usarse en producción.
"""
from .base import *  # noqa: F401,F403
from .base import env_bool, os

DEBUG = True

# Seguridad relajada solo en desarrollo
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Emails en consola
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# SQLite por defecto en dev (DB_ENGINE=sqlite). Para probar Postgres local:
# set DB_ENGINE=postgres y completar DB_* en .env
