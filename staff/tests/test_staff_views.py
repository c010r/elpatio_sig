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


# ---------------------------------------------------------------------------
# Liquidaciones diarias (vistas)
# ---------------------------------------------------------------------------

LIQ_URLS_SIN_PK = ["liquidacion_list", "liquidacion_create", "liquidacion_csv"]


@pytest.mark.parametrize("url_name", LIQ_URLS_SIN_PK)
def test_liquidacion_gerente_200(client_gerente, url_name):
    extra = {"date": "2026-08-01"} if url_name == "liquidacion_create" else {}
    assert client_gerente.get(reverse(f"staff:{url_name}"), extra).status_code == 200


@pytest.mark.parametrize("url_name", LIQ_URLS_SIN_PK)
def test_liquidacion_admin_200(client_admin, url_name):
    extra = {"date": "2026-08-01"} if url_name == "liquidacion_create" else {}
    assert client_admin.get(reverse(f"staff:{url_name}"), extra).status_code == 200


def test_liquidacion_create_sin_parametro_redirige_a_fecha(client_gerente):
    """El template asume ?date=; sin parámetro se redirige a ?date=hoy."""
    response = client_gerente.get(reverse("staff:liquidacion_create"))
    assert response.status_code == 302
    assert "?date=" in response.url


@pytest.mark.parametrize("url_name", ["liquidacion_detail"])
def test_liquidacion_detail_200(client_gerente, client_admin, url_name, bartender_user):
    from datetime import date as date_cls

    from staff.models import Liquidacion

    emp = Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01"
    )
    liqui, _ = Liquidacion.build_or_update(emp, date_cls(2026, 8, 1))
    assert client_gerente.get(reverse(f"staff:{url_name}", args=[liqui.pk])).status_code == 200
    assert client_admin.get(reverse(f"staff:{url_name}", args=[liqui.pk])).status_code == 200


@pytest.mark.parametrize("url_name", LIQ_URLS_SIN_PK + ["liquidacion_detail"])
def test_liquidacion_bartender_cajero_denegado(client_bartender, client_cajero, url_name):
    kwargs = {"pk": 999} if url_name == "liquidacion_detail" else {}
    assert_access_denied(client_bartender.get(reverse(f"staff:{url_name}", kwargs=kwargs)))
    assert_access_denied(client_cajero.get(reverse(f"staff:{url_name}", kwargs=kwargs)))


def test_liquidacion_create_genera_solo_empleados_con_horas(client_gerente, bartender_user, cajero_user):
    """POST generar: crea liquidaciones para empleados con horas > 0 y omite
    los que no trabajaron ese día."""
    from datetime import date as date_cls
    from decimal import Decimal

    from staff.models import Liquidacion

    emp_trabaja = Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01",
        hourly_rate=Decimal("150"),
    )
    Employee.objects.create(
        user=cajero_user, position="cajero", hire_date="2026-01-01",
        hourly_rate=Decimal("170"),
    )
    fecha = date_cls(2026, 8, 10)
    Shift.objects.create(
        employee=emp_trabaja, date=fecha, start_time="09:00", end_time="17:00",
    )

    response = client_gerente.post(reverse("staff:liquidacion_create"), {"date": "2026-08-10"})
    assert response.status_code == 302
    liqs = Liquidacion.objects.filter(date=fecha)
    assert liqs.count() == 1
    assert liqs.first().employee == emp_trabaja
    assert liqs.first().hours_worked == Decimal("8.00")
    assert liqs.first().gross_amount == Decimal("1200.00")


def test_liquidacion_create_no_duplica_al_regenerar(client_gerente, bartender_user):
    from datetime import date as date_cls
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01",
        hourly_rate=Decimal("150"),
    )
    fecha = date_cls(2026, 8, 11)
    Shift.objects.create(employee=emp, date=fecha, start_time="09:00", end_time="12:00")

    client_gerente.post(reverse("staff:liquidacion_create"), {"date": "2026-08-11"})
    client_gerente.post(reverse("staff:liquidacion_create"), {"date": "2026-08-11"})
    assert Liquidacion.objects.filter(employee=emp, date=fecha).count() == 1


def test_liquidacion_detail_transiciones_via_post(client_gerente, bartender_user):
    """POST marcar_liquidada / marcar_pagada desde la vista."""
    from datetime import date as date_cls
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01",
        hourly_rate=Decimal("150"),
    )
    fecha = date_cls(2026, 8, 12)
    Shift.objects.create(employee=emp, date=fecha, start_time="09:00", end_time="12:00")
    liqui, _ = Liquidacion.build_or_update(emp, fecha)

    url = reverse("staff:liquidacion_detail", args=[liqui.pk])
    resp = client_gerente.post(url, {"action": "liquidar"})
    assert resp.status_code == 302
    liqui.refresh_from_db()
    assert liqui.status == Liquidacion.Status.LIQUIDADA

    resp = client_gerente.post(url, {"action": "pagar"})
    assert resp.status_code == 302
    liqui.refresh_from_db()
    assert liqui.status == Liquidacion.Status.PAGADA
    assert liqui.paid_at is not None


def test_liquidacion_csv_exporta_datos(client_gerente, bartender_user):
    from datetime import date as date_cls
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = Employee.objects.create(
        user=bartender_user, position="bartender", hire_date="2026-01-01",
        hourly_rate=Decimal("150"),
    )
    fecha = date_cls(2026, 8, 13)
    Shift.objects.create(employee=emp, date=fecha, start_time="09:00", end_time="12:00")
    liqui, _ = Liquidacion.build_or_update(emp, fecha)

    response = client_gerente.get(reverse("staff:liquidacion_csv"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    content = response.content.decode("utf-8")
    lines = content.splitlines()
    assert lines[0] == "Empleado,Fecha,Horas,Tarifa hora,Bruto,Estado"
    assert any("2026-08-13" in line and "3.00" in line and "450.00" in line for line in lines)
