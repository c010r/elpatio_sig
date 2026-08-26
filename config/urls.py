"""
El Patio SIG — Rutas raíz del proyecto.

El módulo admin de Django está DESHABILITADO por decisión del dueño del pub:
toda la administración se hace con pantallas propias del sistema (usuarios,
CRUD de todos los módulos, reportes). No existe /admin/.
"""
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Autenticación de Django (login, logout, password change)
    path("accounts/", include("django.contrib.auth.urls")),
    # Módulos del sistema
    path("", include("core.urls")),
    path("inventario/", include("inventory.urls")),
    path("ventas/", include("sales.urls")),
    path("mesas/", include("tables.urls")),
    path("empleados/", include("staff.urls")),
    path("clientes/", include("customers.urls")),
    # accounts/urls.py ya usa el prefijo "usuarios/" propio
    path("", include("accounts.urls")),
    path("compras/", include("purchases.urls")),
    path("reservas/", include("reservations.urls")),
    path("reportes/", include("reports.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
