"""
reservations — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- No se puede reservar una mesa ocupada/reservada en el mismo horario
  (validación en clean(); duración asumida 2h).
- La fecha no puede ser pasada.
"""
from datetime import date, datetime, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

try:
    from reservations.models import Reservation
except ImportError:
    pytest.skip("Backend de reservations no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


def _reserva(table, gerente_user, start_hour, **kwargs):
    return Reservation(
        table=table,
        name=kwargs.pop("name", "Cliente Reserva"),
        phone="+54 11 5555-0000",
        date=kwargs.pop("date", timezone.localdate()),
        start_time=time(start_hour, 0),
        party_size=2,
        status=Reservation.Status.PENDIENTE,
        created_by=gerente_user,
        **kwargs,
    )


def test_reserva_solapada_misma_mesa_rechazada(table, gerente_user):
    _reserva(table, gerente_user, 20).save()
    solapada = _reserva(table, gerente_user, 21)  # dentro de la duración (20-22)
    with pytest.raises(ValidationError):
        solapada.full_clean()


def test_reserva_no_solapada_ok(table, gerente_user):
    _reserva(table, gerente_user, 20).save()
    otra = _reserva(table, gerente_user, 23)  # 23-01: no se superpone con 20-22
    otra.full_clean()  # no debe lanzar
    otra.save()
    assert Reservation.objects.count() == 2


def test_reserva_fecha_pasada_rechazada(table, gerente_user):
    pasada = _reserva(table, gerente_user, 20, date=timezone.localdate() - timedelta(days=1))
    with pytest.raises(ValidationError):
        pasada.full_clean()


def test_reserva_mesa_ocupada_hoy_rechazada(table, gerente_user):
    table.status = "ocupada"
    table.save(update_fields=["status"])
    reserva = _reserva(table, gerente_user, 20)
    with pytest.raises(ValidationError):
        reserva.full_clean()


def test_reserva_estado_por_defecto_pendiente(table, gerente_user):
    r = _reserva(table, gerente_user, 20)
    r.full_clean()
    r.save()
    assert r.status == Reservation.Status.PENDIENTE


def test_reserva_solapada_se_excluye_a_si_misma(table, gerente_user):
    """Editar una reserva (mismo pk) no debe conflictuar con ella misma."""
    r = _reserva(table, gerente_user, 20)
    r.save()
    r.phone = "+54 11 5555-1111"
    r.full_clean()  # no debe lanzar
    r.save()
