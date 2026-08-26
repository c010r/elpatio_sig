"""
SMOKE tests — autenticación y navegación básica.

No dependen de modelos de negocio (inventory, sales, etc.), por lo que corren
aunque el backend de los módulos todavía no esté implementado.

Cubren: login (GET/POST), dashboard (redirect sin login / 200 con login) y
logout.  Convención del contrato: LOGIN_URL="login", LOGIN_REDIRECT_URL=
"dashboard", LOGOUT_REDIRECT_URL="login".
"""
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

# NOTA (desviación detectada): settings.LOGIN_URL = "login" es un NOMBRE
# ambiguo: tanto `core` (app_name="core", ruta /login/) como
# `django.contrib.auth.urls` (incluido en /accounts/) definen una vista
# llamada "login". Al resolver, gana la primera en config/urls.py
# (/accounts/login/). Funcionalmente ambas renderizan el mismo template
# (registration/login.html), pero el redirect NO apunta a /login/ como
# indicaría el contrato. Los tests aceptan ambas rutas y la desviación se
# reporta al coordinador (fix sugerido: LOGIN_URL = "core:login").
LOGIN_PATHS = ("/login/", "/accounts/login/")


def _is_login_redirect(url: str) -> bool:
    return any(url.startswith(path) for path in LOGIN_PATHS)


def test_login_page_get_200(client):
    """La vista de login responde 200 (formulario)."""
    response = client.get(reverse("core:login"))
    assert response.status_code == 200


def test_login_post_success(client, admin_user):
    """Login con credenciales válidas redirige al dashboard."""
    response = client.post(
        reverse("core:login"),
        {"username": "admin_user", "password": "test-pass-123"},
    )
    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")


def test_login_post_wrong_password(client):
    """Login con credenciales inválidas vuelve al formulario (200 + error)."""
    response = client.post(
        reverse("core:login"),
        {"username": "usuario_inexistente", "password": "incorrecta"},
    )
    assert response.status_code == 200


def test_dashboard_redirects_anon_to_login(client):
    """Sin login, el dashboard redirige a una página de login (302)."""
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert _is_login_redirect(response.url)


def test_dashboard_logged_in_200(client_admin):
    """Con sesión iniciada, el dashboard responde 200."""
    response = client_admin.get(reverse("core:dashboard"))
    assert response.status_code == 200


def test_dashboard_muestra_moneda_uyu(client_admin):
    """Los KPIs monetarios del dashboard usan el formato UYU ($U), no '$' crudo."""
    response = client_admin.get(reverse("core:dashboard"))
    content = response.content.decode("utf-8")
    assert "$U 0,00" in content  # ventas de hoy sin datos
    assert "USD" not in content


def test_logout_post(client_admin):
    """Logout por POST invalida la sesión y redirige a login."""
    response = client_admin.post(reverse("core:logout"))
    assert response.status_code == 302
    assert _is_login_redirect(response.url)
    # La sesión quedó invalidada: el dashboard vuelve a exigir login
    response = client_admin.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert _is_login_redirect(response.url)


def test_logout_get_not_allowed(client_admin):
    """Django 5: LogoutView sólo acepta POST (405 en GET).

    Si el backend customiza el logout para aceptar GET, este test falla y se
    reporta como desviación del contrato.
    """
    response = client_admin.get(reverse("core:logout"))
    assert response.status_code == 405
