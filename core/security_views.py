"""
core — Vistas de seguridad (propiedad del agente de Seguridad, no tocar desde backend).

Vista personalizada de fallo CSRF (CSRF_FAILURE_VIEW en config/settings/prod.py):
registra el intento en el logger "django.security.csrf" (→ logs/elpatio.log en
producción) y responde 403 con un mensaje amigable. No depende de templates ni
de la base de datos, así que funciona incluso si la sesión o la DB fallan.
"""
import logging

from django.http import HttpResponseForbidden

logger = logging.getLogger("django.security.csrf")


def csrf_failure(request, reason=""):
    """Devuelve 403 y registra el intento CSRF rechazado."""
    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else "anon"
    logger.warning(
        "CSRF rechazado: method=%s path=%s reason=%r user=%s ip=%s ua=%s referer=%s",
        request.method,
        request.path,
        reason,
        user,
        request.META.get("REMOTE_ADDR"),
        (request.META.get("HTTP_USER_AGENT") or "")[:120],
        request.META.get("HTTP_REFERER", ""),
        extra={"status_code": 403},
    )
    return HttpResponseForbidden(
        "Verificación CSRF fallida. Recargá la página e intentá de nuevo. "
        "Si el problema persiste, cerrá sesión y volvé a entrar.",
        content_type="text/plain; charset=utf-8",
    )
