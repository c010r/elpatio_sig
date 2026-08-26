"""
staff — Modelos de empleados y turnos.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models


class Employee(models.Model):
    """Empleado del local, ligado 1 a 1 a un usuario."""

    class Position(models.TextChoices):
        BARTENDER = "bartender", "bartender"
        CAMARERO = "camarero", "camarero"
        CAJERO = "cajero", "cajero"
        GERENTE = "gerente", "gerente"
        ADMIN = "admin", "admin"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee",
        verbose_name="usuario",
    )
    position = models.CharField("puesto", max_length=20, choices=Position.choices)
    hire_date = models.DateField("fecha de alta")
    hourly_rate = models.DecimalField("tarifa por hora", max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Shift(models.Model):
    """Turno de trabajo de un empleado."""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="shifts", verbose_name="empleado"
    )
    date = models.DateField("fecha")
    start_time = models.TimeField("inicio")
    end_time = models.TimeField("fin", null=True, blank=True)
    note = models.TextField("nota", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["-date", "-start_time"]

    def __str__(self):
        return f"{self.employee} - {self.date} {self.start_time:%H:%M}"

    @property
    def worked_hours(self):
        """Horas trabajadas (calculado); None si el turno no tiene fin."""
        if not self.end_time:
            return None
        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)
        if end <= start:
            end += timedelta(days=1)
        return (end - start).total_seconds() / 3600
