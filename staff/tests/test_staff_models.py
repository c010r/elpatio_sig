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
