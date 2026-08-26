"""
reservations — Modelo de reservas de mesas.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Reservation(models.Model):
    """Reserva de una mesa para una fecha/hora."""

    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "pendiente"
        CONFIRMADA = "confirmada", "confirmada"
        CANCELADA = "cancelada", "cancelada"
        COMPLETADA = "completada", "completada"

    # Duración asumida de una reserva para detectar solapamientos.
    DURATION = timedelta(hours=2)

    table = models.ForeignKey(
        "tables.Table",
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name="mesa",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
        verbose_name="cliente",
    )
    name = models.CharField("nombre", max_length=150)
    phone = models.CharField("teléfono", max_length=50, blank=True)
    date = models.DateField("fecha")
    start_time = models.TimeField("hora de inicio")
    party_size = models.PositiveSmallIntegerField("cantidad de personas", default=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDIENTE)
    note = models.TextField("nota", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name="creada por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "reserva"
        verbose_name_plural = "reservas"
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.name} - Mesa {self.table.number} ({self.date} {self.start_time:%H:%M})"

    def clean(self):
        """Valida que la mesa no esté ocupada/reservada en el mismo horario."""
        super().clean()
        today = timezone.localdate()
        if self.date and self.date < today:
            raise ValidationError({"date": "La fecha de la reserva no puede estar en el pasado."})
        if self.date and self.start_time:
            start = datetime.combine(self.date, self.start_time)
            end = start + self.DURATION
            conflicts = Reservation.objects.filter(
                table_id=self.table_id,
                date=self.date,
                status__in=[self.Status.PENDIENTE, self.Status.CONFIRMADA],
            ).exclude(pk=self.pk)
            for other in conflicts:
                other_start = datetime.combine(other.date, other.start_time)
                other_end = other_start + self.DURATION
                if start < other_end and other_start < end:
                    raise ValidationError("La mesa ya está reservada en ese horario.")
            if self.date == today and self.table_id:
                from tables.models import Table

                table_status = Table.objects.get(pk=self.table_id).status
                if table_status == Table.Status.OCUPADA:
                    raise ValidationError("La mesa está ocupada en este momento y no puede reservarse.")
