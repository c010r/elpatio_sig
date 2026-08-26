"""
reservations — Tests de VISTAS y permisos (se saltan hasta que el backend
implemente las URLs/vistas de reservations).

Matriz de permisos del contrato:
- Gerente/Admin: CRUD de reservas, agenda de hoy, confirmar/cancelar.
- Bartender: NO gestiona reservas.
- Anónimo: redirect a login.
"""
import pytest
from django.urls import NoReverseMatch, reverse

try:
    from reservations.models import Reservation
    reverse("reservations:reservation_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de reservations no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("url_name", [
    "reservation_list", "reservation_create", "reservation_update", "reservation_delete",
    "reservation_today", "reservation_confirm", "reservation_cancel",
])
def test_bartender_denegado(client_bartender, url_name):
    kwargs = {"pk": 1} if any(k in url_name for k in ("update", "delete", "confirm", "cancel")) else {}
    assert_access_denied(client_bartender.get(reverse(f"reservations:{url_name}", kwargs=kwargs)))


def test_reservation_today_gerente_200(client_gerente):
    assert client_gerente.get(reverse("reservations:reservation_today")).status_code == 200


def test_reservation_create_gerente_crea_reserva(client_gerente, table, gerente_user):
    from datetime import time

    from django.utils import timezone

    response = client_gerente.post(
        reverse("reservations:reservation_create"),
        {
            "table": table.id,
            "name": "Mesa para dos",
            "phone": "+54 11 5555-2222",
            "date": timezone.localdate().isoformat(),
            "start_time": time(21, 0).strftime("%H:%M"),
            "party_size": "2",
            "status": "pendiente",
        },
    )
    assert response.status_code == 302
    assert Reservation.objects.filter(name="Mesa para dos", table=table).exists()
