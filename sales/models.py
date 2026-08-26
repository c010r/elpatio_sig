"""
sales — Modelos de ventas: caja registradora, ventas y ítems de venta.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Sum
from django.utils import timezone


class CashRegister(models.Model):
    """Caja registradora. Regla: una sola caja abierta por vez."""

    class Status(models.TextChoices):
        ABIERTA = "abierta", "abierta"
        CERRADA = "cerrada", "cerrada"

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_registers",
        verbose_name="abierta por",
    )
    opened_at = models.DateTimeField("apertura", auto_now_add=True)
    closed_at = models.DateTimeField("cierre", null=True, blank=True)
    opening_amount = models.DecimalField(
        "monto de apertura", max_digits=10, decimal_places=2, default=Decimal("0")
    )
    closing_amount = models.DecimalField(
        "monto de cierre", max_digits=10, decimal_places=2, null=True, blank=True
    )
    expected_amount = models.DecimalField(
        "monto esperado", max_digits=10, decimal_places=2, null=True, blank=True
    )
    actual_amount = models.DecimalField(
        "monto real", max_digits=10, decimal_places=2, null=True, blank=True
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ABIERTA)
    notes = models.TextField("notas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "caja registradora"
        verbose_name_plural = "cajas registradoras"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Caja del {self.opened_at:%d/%m/%Y %H:%M} ({self.get_status_display()})"

    @classmethod
    def get_open(cls):
        """Devuelve la caja abierta actual o None."""
        return cls.objects.filter(status=cls.Status.ABIERTA).first()

    def close(self, closing_amount, actual_amount, notes=""):
        """Cierra la caja: calcula el esperado (apertura + ventas) y guarda el cierre."""
        sales_total = (
            self.sales.filter(status=Sale.Status.COMPLETADA).aggregate(total=Sum("total"))["total"]
            or Decimal("0")
        )
        self.expected_amount = self.opening_amount + sales_total
        self.closing_amount = closing_amount
        self.actual_amount = actual_amount
        self.notes = notes
        self.status = self.Status.CERRADA
        self.closed_at = timezone.now()
        self.save(
            update_fields=[
                "expected_amount", "closing_amount", "actual_amount", "notes", "status", "closed_at",
            ]
        )


class Sale(models.Model):
    """Venta completada/anulada con ticket secuencial por día (YYYYMMDD-####)."""

    class PaymentMethod(models.TextChoices):
        EFECTIVO = "efectivo", "efectivo"
        TARJETA = "tarjeta", "tarjeta"
        TRANSFERENCIA = "transferencia", "transferencia"
        OTRO = "otro", "otro"

    class Status(models.TextChoices):
        COMPLETADA = "completada", "completada"
        ANULADA = "anulada", "anulada"

    ticket_number = models.CharField("número de ticket", max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name="vendedor",
    )
    cash_register = models.ForeignKey(
        CashRegister, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales", verbose_name="caja",
    )
    table = models.ForeignKey(
        "tables.Table", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales", verbose_name="mesa",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales", verbose_name="cliente",
    )
    subtotal = models.DecimalField("subtotal", max_digits=10, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField("descuento", max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=10, decimal_places=2, default=Decimal("0"))
    payment_method = models.CharField(
        "método de pago", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.EFECTIVO
    )
    cash_received = models.DecimalField(
        "efectivo recibido", max_digits=10, decimal_places=2, null=True, blank=True
    )
    change = models.DecimalField("vuelto", max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.COMPLETADA)
    created_at = models.DateTimeField(auto_now_add=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="voided_sales", verbose_name="anulada por",
    )
    voided_at = models.DateTimeField("anulada el", null=True, blank=True)
    void_reason = models.CharField("motivo de anulación", max_length=250, blank=True)

    class Meta:
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Venta {self.ticket_number}"

    @classmethod
    def _compute_next_ticket_number(cls):
        """Ticket secuencial por día: YYYYMMDD-#### (llamar dentro de transaction.atomic)."""
        prefix = timezone.localdate().strftime("%Y%m%d") + "-"
        last = (
            cls.objects.select_for_update()
            .filter(ticket_number__startswith=prefix)
            .order_by("-ticket_number")
            .first()
        )
        seq = int(last.ticket_number.split("-")[1]) + 1 if last else 1
        return f"{prefix}{seq:04d}"

    @classmethod
    @transaction.atomic
    def complete_sale(cls, *, user, items, cash_register=None, table=None, customer=None,
                      payment_method=PaymentMethod.EFECTIVO, cash_received=None, discount=Decimal("0")):
        """Crea una venta completada: ticket, ítems, descuento de stock y puntos.

        `items` es una lista de tuplas (Product, quantity Decimal).
        """
        if not items:
            raise ValidationError("La venta no tiene ítems.")
        if discount is None:
            discount = Decimal("0")
        if discount < 0:
            raise ValidationError("El descuento no puede ser negativo.")

        # Ticket único con reintento ante colisiones por concurrencia.
        sale = None
        for _ in range(10):
            try:
                with transaction.atomic():
                    sale = cls.objects.create(
                        ticket_number=cls._compute_next_ticket_number(),
                        user=user,
                        cash_register=cash_register,
                        table=table,
                        customer=customer,
                        payment_method=payment_method,
                    )
                    break
            except IntegrityError:
                continue
        if sale is None:
            raise ValidationError("No se pudo generar un número de ticket único.")

        subtotal = Decimal("0")
        for product, quantity in items:
            if quantity <= 0:
                raise ValidationError("Las cantidades deben ser mayores a cero.")
            line_subtotal = product.sale_price * quantity
            subtotal += line_subtotal
            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=product.sale_price,
                subtotal=line_subtotal,
            )
            # Descuento de stock por venta (cantidad negativa).
            from inventory.models import StockMovement

            StockMovement.objects.create(
                product=product,
                quantity=-quantity,
                movement_type=StockMovement.MovementType.VENTA,
                reference=f"Venta {sale.ticket_number}",
                user=user,
            ).apply()

        sale.subtotal = subtotal
        sale.total = subtotal - discount
        if sale.total < 0:
            raise ValidationError("El descuento no puede superar el subtotal.")

        if payment_method == cls.PaymentMethod.EFECTIVO:
            if cash_received is None:
                raise ValidationError("Para pagos en efectivo hay que indicar el efectivo recibido.")
            if cash_received < sale.total:
                raise ValidationError("El efectivo recibido es menor al total.")
            sale.cash_received = cash_received
            sale.change = cash_received - sale.total
        sale.save(update_fields=["subtotal", "discount", "total", "cash_received", "change"])

        if customer:
            customer.earn_points(sale.total)
        return sale

    @transaction.atomic
    def void(self, user, reason=""):
        """Anula la venta y repone el stock de todos sus ítems."""
        if self.status != self.Status.COMPLETADA:
            raise ValidationError("Solo se pueden anular ventas completadas.")

        from inventory.models import StockMovement

        for item in self.items.select_related("product"):
            StockMovement.objects.create(
                product=item.product,
                quantity=item.quantity,
                movement_type=StockMovement.MovementType.VENTA,
                reference=f"Anulación {self.ticket_number}",
                user=user,
            ).apply()
        self.status = self.Status.ANULADA
        self.voided_by = user
        self.voided_at = timezone.now()
        self.void_reason = reason
        self.save(update_fields=["status", "voided_by", "voided_at", "void_reason"])


class SaleItem(models.Model):
    """Ítem de una venta."""

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items", verbose_name="venta")
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="sale_items",
        verbose_name="producto",
    )
    quantity = models.DecimalField("cantidad", max_digits=10, decimal_places=2)
    unit_price = models.DecimalField("precio unitario", max_digits=10, decimal_places=2)
    subtotal = models.DecimalField("subtotal", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "ítem de venta"
        verbose_name_plural = "ítems de venta"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"
