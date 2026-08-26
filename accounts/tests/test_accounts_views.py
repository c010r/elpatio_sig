"""
accounts — Tests de VISTAS y permisos (se saltan hasta que el backend
implemente las URLs/vistas de accounts).

Matriz de permisos del contrato:
- Admin (is_staff): gestión de usuarios (listado, crear con grupo, toggle).
- Gerente: NO gestiona usuarios (StaffRequiredMixin redirige a dashboard).
- Anónimo: redirect a login.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

try:
    from accounts.models import Profile
    reverse("accounts:user_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de accounts no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("url_name", ["user_list", "user_create", "user_update", "user_toggle_active"])
def test_gerente_denegado(client_gerente, url_name):
    kwargs = {"pk": 1} if url_name in ("user_update", "user_toggle_active") else {}
    assert_access_denied(client_gerente.get(reverse(f"accounts:{url_name}", kwargs=kwargs)))


def test_user_list_admin_200(client_admin):
    assert client_admin.get(reverse("accounts:user_list")).status_code == 200


def test_user_create_admin_crea_usuario_con_grupo(client_admin, bartender_group):
    # Formulario real: UserCreateForm (username, first_name, last_name, email,
    # is_active) + password + group (ModelChoiceField).
    response = client_admin.post(
        reverse("accounts:user_create"),
        {
            "username": "nuevo_camarero",
            "password": "Clave-Segura-123",
            "group": bartender_group.id,
        },
    )
    assert response.status_code == 302
    user = User.objects.get(username="nuevo_camarero")
    assert user.groups.filter(name="bartender").exists()
    assert Profile.objects.filter(user=user).exists()


def test_user_toggle_active_admin(client_admin, bartender_user):
    response = client_admin.post(reverse("accounts:user_toggle_active", args=[bartender_user.id]))
    assert response.status_code == 302
    bartender_user.refresh_from_db()
    assert bartender_user.is_active is False
