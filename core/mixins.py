"""
core — Mixins y utilidades compartidas por todos los módulos.
"""
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class RoleRequiredMixin(LoginRequiredMixin):
    """Requiere login y pertenencia a al menos uno de los grupos indicados.

    El módulo admin de Django está deshabilitado: los superusuarios (creados
    con createsuperuser o desde pantallas propias) pasan siempre, ya que no
    tienen grupos asignados por defecto.
    """

    roles: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if self.roles and not (
            request.user.is_superuser
            or request.user.groups.filter(name__in=self.roles).exists()
        ):
            messages.error(request, "No tenés permisos para acceder a esta sección.")
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(LoginRequiredMixin):
    """Requiere usuario activo y con staff (para admin del sitio)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Necesitás permisos de administración.")
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)


def role_required(*roles):
    """Decorador para vistas función: login + pertenencia a al menos un grupo.

    Los superusuarios pasan siempre (módulo admin deshabilitado).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(settings.LOGIN_URL)
            if roles and not (
                request.user.is_superuser
                or request.user.groups.filter(name__in=roles).exists()
            ):
                messages.error(request, "No tenés permisos para acceder a esta sección.")
                return redirect("core:dashboard")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
