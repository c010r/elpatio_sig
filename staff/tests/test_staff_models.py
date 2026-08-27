"""
staff — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- Employee OneToOne con User; position (bartender, camarero, cajero, gerente, admin).
- Shift con worked_hours calculado (None si no tiene fin; soporta turnos nocturnos).
"""
from datetime import date, time

import pytest
from django.db import IntegrityError

try:
    from staff.models import Employee, Shift
except ImportError:
    pytest.skip("Backend de staff no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


def test_employee_un_usuario_por_empleado(bartender_user):
    Employee.objects.create(
        user=bartender_user, position=Employee.Position.BARTENDER, hire_date=date(2026, 1, 1)
    )
    with pytest.raises(IntegrityError):
        Employee.objects.create(
            user=bartender_user, position=Employee.Position.CAMARERO, hire_date=date(2026, 1, 1)
        )


def test_employee_estado_por_defecto(bartender_user):
    emp = Employee.objects.create(
        user=bartender_user, position=Employee.Position.BARTENDER, hire_date=date(2026, 1, 1)
    )
    assert emp.is_active is True
    assert emp.hourly_rate == 0


def test_shift_worked_hours(bartender_user):
    emp = Employee.objects.create(
        user=bartender_user, position=Employee.Position.BARTENDER, hire_date=date(2026, 1, 1)
    )
    shift = Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(9, 0), end_time=time(17, 0)
    )
    assert shift.worked_hours == 8.0


def test_shift_worked_hours_sin_fin_es_none(bartender_user):
    emp = Employee.objects.create(
        user=bartender_user, position=Employee.Position.BARTENDER, hire_date=date(2026, 1, 1)
    )
    shift = Shift.objects.create(employee=emp, date=date(2026, 8, 1), start_time=time(9, 0))
    assert shift.worked_hours is None


def test_shift_worked_hours_nocturno(bartender_user):
    emp = Employee.objects.create(
        user=bartender_user, position=Employee.Position.BARTENDER, hire_date=date(2026, 1, 1)
    )
    shift = Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(22, 0), end_time=time(2, 0)
    )
    assert shift.worked_hours == 4.0


# ---------------------------------------------------------------------------
# Liquidaciones diarias (horas × tarifa)
# ---------------------------------------------------------------------------

def _crear_empleado(user, hourly_rate="150.00"):
    return Employee.objects.create(
        user=user, position=Employee.Position.BARTENDER,
        hire_date=date(2026, 1, 1), hourly_rate=hourly_rate,
    )


def test_liquidacion_calcula_horas_por_tarifa(bartender_user):
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(9, 0), end_time=time(15, 0),
    )
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(16, 0), end_time=time(20, 0),
    )
    liqui, created = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert created is True
    assert liqui.hours_worked == Decimal("10.00")  # 6 + 4
    assert liqui.hourly_rate == Decimal("150.00")
    assert liqui.gross_amount == Decimal("1500.00")  # 10 × 150
    assert liqui.status == Liquidacion.Status.BORRADOR


def test_liquidacion_horas_cero_sin_turnos(bartender_user):
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    liqui, _ = Liquidacion.build_or_update(emp, date(2026, 8, 2))
    assert liqui.hours_worked == Decimal("0.00")
    assert liqui.gross_amount == Decimal("0.00")


def test_liquidacion_no_duplica_unique_employee_date(bartender_user):
    from django.db import IntegrityError

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(9, 0), end_time=time(11, 0),
    )
    liqui1, created1 = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    liqui2, created2 = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert created1 is True and created2 is False
    assert liqui1.pk == liqui2.pk
    assert Liquidacion.objects.filter(employee=emp, date=date(2026, 8, 1)).count() == 1
    # El unique_together está a nivel DB
    with pytest.raises(IntegrityError):
        Liquidacion.objects.create(
            employee=emp, date=date(2026, 8, 1),
            hours_worked="2", hourly_rate="150", gross_amount="300",
        )


def test_liquidacion_regeneracion_borrador_actualiza(bartender_user):
    """Si existe y está en borrador, regenerar actualiza horas/bruto."""
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(9, 0), end_time=time(11, 0),
    )
    liqui, _ = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert liqui.hours_worked == Decimal("2.00")
    # agrega más horas y regenera
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(12, 0), end_time=time(15, 0),
    )
    liqui2, created = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert created is False
    assert liqui2.pk == liqui.pk
    assert liqui2.hours_worked == Decimal("5.00")
    assert liqui2.gross_amount == Decimal("750.00")


def test_liquidacion_no_regenera_si_liquidada_o_pagada(bartender_user):
    """Si la liquidación salió de borrador, regenerar NO toca sus valores."""
    from decimal import Decimal

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(9, 0), end_time=time(11, 0),
    )
    liqui, _ = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    liqui.marcar_liquidada()
    Shift.objects.create(
        employee=emp, date=date(2026, 8, 1), start_time=time(12, 0), end_time=time(15, 0),
    )
    liqui2, created = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert created is False
    assert liqui2.hours_worked == Decimal("2.00")  # no se actualizó


def test_liquidacion_transiciones_estado(bartender_user):
    from django.core.exceptions import ValidationError

    from staff.models import Liquidacion

    emp = _crear_empleado(bartender_user)
    liqui, _ = Liquidacion.build_or_update(emp, date(2026, 8, 1))
    assert liqui.status == Liquidacion.Status.BORRADOR

    liqui.marcar_liquidada()
    liqui.refresh_from_db()
    assert liqui.status == Liquidacion.Status.LIQUIDADA
    assert liqui.paid_at is None

    liqui.marcar_pagada()
    liqui.refresh_from_db()
    assert liqui.status == Liquidacion.Status.PAGADA
    assert liqui.paid_at is not None

    # Transiciones inválidas
    with pytest.raises(ValidationError):
        liqui.marcar_liquidada()  # ya no está en borrador
    with pytest.raises(ValidationError):
        liqui.marcar_pagada()  # ya está pagada
