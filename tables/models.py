"""
tables — Modelos de mesas y comandas.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum
from django.utils import timezone


class Table(models.Model):
    """Mesa del local, agrupada por zona."""

    class Zone(models.TextChoices):
        BARRA = "barra", "barra"
        SALON = "salón", "salón"
        TERRAZA = "terraza", "terraza"
        PRIVADO = "privado", "privado"

    class Status(models.TextChoices):
        LIBRE = "libre", "libre"
        OCUPADA = "ocupada", "ocupada"
        RESERVADA = "reservada", "reservada"
        LIMPIEZA = "limpieza", "limpieza"

    number = models.PositiveSmallIntegerField("número", unique=True)
    capacity = models.PositiveSmallIntegerField("capacidad", default=2)
    zone = models.CharField("zona", max_length=20, choices=Zone.choices, default=Zone.SALON)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.LIBRE)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mesa"
        verbose_name_plural = "mesas"
        ordering = ["zone", "number"]

    def __str__(self):
        return f"Mesa {self.number} ({self.get_zone_display()})"

    @property
    def open_order(self):
        """Comanda abierta de esta mesa, o None si no tiene."""
        return Order.objects.filter(table=self, status=Order.Status.ABIERTA).first()


class Order(models.Model):
    """Comanda abierta sobre una mesa."""

    class Status(models.TextChoices):
        ABIERTA = "abierta", "abierta"
        CERRADA = "cerrada", "cerrada"
        PAGADA = "pagada", "pagada"
        CANCELADA = "cancelada", "cancelada"

    table = models.ForeignKey(
        Table, on_delete=models.PROTECT, related_name="orders", verbose_name="mesa"
    )
    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="mozo",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ABIERTA)
    note = models.TextField("nota", blank=True)
    opened_at = models.DateTimeField("abierta el", auto_now_add=True)
    closed_at = models.DateTimeField("cerrada el", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "comanda"
        verbose_name_plural = "comandas"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Comanda {self.pk} - Mesa {self.table.number} ({self.get_status_display()})"

    @property
    def total(self):
        """Total derivado: suma de quantity * unit_price de sus ítems."""
        return self.items.aggregate(total=Sum(F("quantity") * F("unit_price")))["total"] or Decimal("0")

    @transaction.atomic
    def close_to_sale(self, *, user, payment_method="efectivo", cash_received=None,
                      cash_register=None, discount=Decimal("0"), tip=Decimal("0")):
        """Cierra la comanda generando una Sale ligada a la mesa.

        Cobra los ítems con estado 'entregado', descuenta stock (vía
        Sale.complete_sale), marca la comanda como pagada y libera la mesa.
        """
        from sales.models import Sale

        order = Order.objects.select_for_update().get(pk=self.pk)
        if order.status != Order.Status.ABIERTA:
            raise ValidationError("La comanda no está abierta.")
        items = [
            (item.product, item.quantity)
            for item in order.items.select_related("product").filter(status=OrderItem.Status.ENTREGADO)
        ]
        if not items:
            raise ValidationError("La comanda no tiene ítems entregados para cobrar.")
        sale = Sale.complete_sale(
            user=user,
            items=items,
            cash_register=cash_register,
            table=order.table,
            payment_method=payment_method,
            cash_received=cash_received,
            discount=discount,
            tip=tip,
        )
        order.status = Order.Status.PAGADA
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])
        order.table.status = Table.Status.LIBRE
        order.table.save(update_fields=["status"])
        return sale


class OrderItem(models.Model):
    """Ítem de una comanda."""

    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "pendiente"
        ENTREGADO = "entregado", "entregado"
        CANCELADO = "cancelado", "cancelado"

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="comanda"
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="producto",
    )
    quantity = models.DecimalField("cantidad", max_digits=10, decimal_places=2)
    unit_price = models.DecimalField("precio unitario", max_digits=10, decimal_places=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDIENTE)
    note = models.CharField("nota", max_length=250, blank=True)
    requested_at = models.DateTimeField("solicitado el", auto_now_add=True)

    class Meta:
        verbose_name = "ítem de comanda"
        verbose_name_plural = "ítems de comanda"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        """Subtotal del ítem (quantity * unit_price)."""
        return self.quantity * self.unit_price
