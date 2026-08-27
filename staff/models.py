"""
staff — Modelos de empleados, turnos y liquidaciones.
"""
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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


class Liquidacion(models.Model):
    """Liquidación DIARIA de un empleado por horas trabajadas (horas × tarifa).

    La tarifa se congela al generarse (hourly_rate del Employee en ese
    momento). Estados: borrador → liquidada → pagada.
    """

    class Status(models.TextChoices):
        BORRADOR = "borrador", "borrador"
        LIQUIDADA = "liquidada", "liquidada"
        PAGADA = "pagada", "pagada"

    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        related_name="liquidaciones", verbose_name="empleado",
    )
    date = models.DateField("fecha")
    hours_worked = models.DecimalField("horas trabajadas", max_digits=10, decimal_places=2)
    hourly_rate = models.DecimalField("tarifa por hora", max_digits=10, decimal_places=2)
    gross_amount = models.DecimalField("monto bruto", max_digits=10, decimal_places=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.BORRADOR)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="liquidaciones_generadas", verbose_name="generada por",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField("pagada el", null=True, blank=True)

    class Meta:
        verbose_name = "liquidación"
        verbose_name_plural = "liquidaciones"
        ordering = ["-date", "employee__user__username"]
        unique_together = ("employee", "date")

    def __str__(self):
        return f"Liquidación {self.employee} - {self.date} ({self.get_status_display()})"

    @classmethod
    def hours_for(cls, employee, date):
        """Horas trabajadas del empleado en la fecha (suma de Shift.worked_hours
        de turnos con fin registrado)."""
        total = Decimal("0")
        for shift in Shift.objects.filter(employee=employee, date=date, end_time__isnull=False):
            hours = shift.worked_hours
            if hours is not None:
                total += Decimal(str(hours))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def build_or_update(cls, employee, date, generated_by=None):
        """Crea la liquidación del empleado en la fecha (horas × tarifa) o
        regenera la existente SI está en borrador (nunca duplica)."""
        hours = cls.hours_for(employee, date)
        rate = Decimal(employee.hourly_rate)  # coacción: instancias creadas con str
        gross = (hours * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        liqui, created = cls.objects.get_or_create(
            employee=employee,
            date=date,
            defaults={
                "hours_worked": hours,
                "hourly_rate": rate,
                "gross_amount": gross,
                "generated_by": generated_by,
            },
        )
        if not created and liqui.status == cls.Status.BORRADOR:
            liqui.hours_worked = hours
            liqui.hourly_rate = rate
            liqui.gross_amount = gross
            liqui.generated_by = generated_by
            liqui.save(update_fields=["hours_worked", "hourly_rate", "gross_amount", "generated_by"])
        return liqui, created

    @property
    def created_by(self):
        """Alias de generated_by para el template liquidacion_detail.

        Si no se registró quién generó la liquidación (None), cae al usuario
        del empleado para evitar resoluciones inválidas en el template
        (`generated_by.username` con None crashea en filtros de template).
        """
        return self.generated_by or self.employee.user

    def marcar_liquidada(self, user=None):
        """Transición borrador → liquidada."""
        if self.status != self.Status.BORRADOR:
            raise ValidationError("Solo las liquidaciones en borrador pueden marcarse como liquidadas.")
        self.status = self.Status.LIQUIDADA
        self.save(update_fields=["status"])

    def marcar_pagada(self, user=None):
        """Transición liquidada → pagada (registra paid_at)."""
        if self.status != self.Status.LIQUIDADA:
            raise ValidationError("Solo las liquidaciones liquidadas pueden marcarse como pagadas.")
        self.status = self.Status.PAGADA
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])
