"""
staff — Tests de VISTAS y permisos (se saltan hasta que el backend implemente
las URLs/vistas de staff).

Matriz de permisos del contrato:
- Gerente/Admin: CRUD empleados y turnos.
- Empleado (cualquier rol): "mi turno" (fichar entrada/salida).
- Bartender (sin empleado asignado): NO gestiona empleados.
- Anónimo: redirect a login.
"""
import pytest
from django.urls import NoReverseMatch, reverse

try:
    from staff.models import Employee, Shift
    reverse("staff:employee_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de staff no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("url_name", [
    "employee_list", "employee_create", "employee_update", "employee_delete",
    "shift_list", "shift_create", "shift_update", "shift_delete",
])
def test_bartender_denegado(client_bartender, url_name):
    kwargs = {"pk": 1} if "update" in url_name or "delete" in url_name else {}
    assert_access_denied(client_bartender.get(reverse(f"staff:{url_name}", kwargs=kwargs)))


def test_employee_list_gerente_200(client_gerente):
    assert client_gerente.get(reverse("staff:employee_list")).status_code == 200


def test_employee_create_gerente_crea_empleado(client_gerente, bartender_user):
    from datetime import date

    response = client_gerente.post(
        reverse("staff:employee_create"),
        {
            "user": bartender_user.id,
            "position": "bartender",
            "hire_date": date(2026, 1, 1).isoformat(),
            "hourly_rate": "1500.00",
        },
    )
    assert response.status_code == 302
    assert Employee.objects.filter(user=bartender_user, position="bartender").exists()


def test_my_shift_empleado_200(client_bartender, bartender_user):
    Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01"
    )
    assert client_bartender.get(reverse("staff:my_shift")).status_code == 200
