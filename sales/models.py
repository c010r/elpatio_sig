"""
sales — Modelos de ventas: caja registradora, ventas, ítems y happy hour.
"""
from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Sum
from django.utils import timezone

CACHE_KEY_HAPPY_HOUR = "happy_hour_config_solo"


class HappyHourConfig(models.Model):
    """Configuración singleton del happy hour (una sola fila, pk=1, con caché)."""

    enabled = models.BooleanField("habilitado", default=False)
    start_time = models.TimeField("inicio", default=time(18, 0))
    end_time = models.TimeField("fin", default=time(21, 0))
    discount_percent = models.DecimalField(
        "descuento (%)", max_digits=5, decimal_places=2, default=Decimal("15"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    name = models.CharField("nombre", max_length=100, default="Happy hour")

    class Meta:
        verbose_name = "configuración de happy hour"
        verbose_name_plural = "configuración de happy hour"

    def __str__(self):
        return self.name or "Happy hour"

    @classmethod
    def get_solo(cls):
        """Devuelve la config única con caché (5 minutos); la crea si no existe."""
        config = cache.get(CACHE_KEY_HAPPY_HOUR)
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_HAPPY_HOUR, config, 300)
        return config

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_HAPPY_HOUR)


def is_happy_hour_active(at_time=None):
    """True si el happy hour está habilitado y `at_time` cae en la franja.

    Soporta franjas nocturnas (start_time > end_time, p. ej. 22:00-02:00).
    """
    config = HappyHourConfig.get_solo()
    if not config.enabled:
        return False
    if at_time is None:
        at_time = timezone.localtime()
    moment = at_time.time() if isinstance(at_time, datetime) else at_time
    if config.start_time <= config.end_time:
        return config.start_time <= moment <= config.end_time
    return moment >= config.start_time or moment <= config.end_time


def effective_price(product, at_time=None):
    """Precio efectivo de un producto en `at_time` (default: ahora).

    Precedencia: promo activa (promo_price) > happy hour (descuento % sobre
    sale_price, redondeo ROUND_HALF_UP) > sale_price. El happy hour NO se
    acumula con promo.
    """
    if product.promo_active and product.promo_price is not None:
        return product.promo_price
    if is_happy_hour_active(at_time):
        config = HappyHourConfig.get_solo()
        factor = Decimal("1") - (config.discount_percent / Decimal("100"))
        return (product.sale_price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return product.sale_price


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
    # Arqueo detallado (Fase 2): lo CONTADO por método al cerrar.
    counted_cash = models.DecimalField(
        "contado efectivo", max_digits=10, decimal_places=2, null=True, blank=True
    )
    counted_card = models.DecimalField(
        "contado tarjeta", max_digits=10, decimal_places=2, null=True, blank=True
    )
    counted_transfer = models.DecimalField(
        "contado transferencia", max_digits=10, decimal_places=2, null=True, blank=True
    )
    counted_other = models.DecimalField(
        "contado otros", max_digits=10, decimal_places=2, null=True, blank=True
    )

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

    def expected_by_method(self):
        """Esperado por método de pago: suma de Sale.total (completadas, no anuladas)
        registradas en esta caja durante el período abierto."""
        rows = (
            self.sales.filter(status=Sale.Status.COMPLETADA)
            .values("payment_method")
            .annotate(total=Sum("total"))
        )
        return {r["payment_method"]: r["total"] or Decimal("0") for r in rows}

    @property
    def difference(self):
        """Diferencia total: contado (cierre) - esperado. None si falta el cierre."""
        if self.closing_amount is None or self.expected_amount is None:
            return None
        return self.closing_amount - self.expected_amount

    def close(self, closing_amount=None, actual_amount=None, notes="",
              counted_cash=None, counted_card=None, counted_transfer=None, counted_other=None):
        """Cierra la caja.

        Fase 2: si se pasan `counted_*`, el cierre es la suma de lo contado por
        método y `closing_amount`/`actual_amount` se derivan de ahí.
        Compatibilidad Fase 1: si no se pasan counted_*, se usan los valores
        `closing_amount`/`actual_amount` directos.
        """
        expected = self.expected_by_method()
        self.expected_amount = self.opening_amount + sum(expected.values(), Decimal("0"))

        counted_provided = any(
            v is not None for v in (counted_cash, counted_card, counted_transfer, counted_other)
        )
        if counted_provided:
            counted = {
                "cash": counted_cash or Decimal("0"),
                "card": counted_card or Decimal("0"),
                "transfer": counted_transfer or Decimal("0"),
                "other": counted_other or Decimal("0"),
            }
            self.counted_cash = counted["cash"]
            self.counted_card = counted["card"]
            self.counted_transfer = counted["transfer"]
            self.counted_other = counted["other"]
            closing = sum(counted.values())
            self.closing_amount = closing
            self.actual_amount = closing
        else:
            self.closing_amount = closing_amount
            self.actual_amount = actual_amount if actual_amount is not None else closing_amount

        self.notes = notes
        self.status = self.Status.CERRADA
        self.closed_at = timezone.now()
        self.save(
            update_fields=[
                "expected_amount", "closing_amount", "actual_amount", "counted_cash",
                "counted_card", "counted_transfer", "counted_other", "notes", "status",
                "closed_at",
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
    tip = models.DecimalField("propina", max_digits=10, decimal_places=2, default=Decimal("0"))
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
                      payment_method=PaymentMethod.EFECTIVO, cash_received=None,
                      discount=Decimal("0"), tip=Decimal("0")):
        """Crea una venta completada: ticket, ítems, descuento de stock y puntos.

        `items` es una lista de tuplas (Product, quantity Decimal).

        Los totales SIEMPRE se recalculan server-side: el subtotal se deriva de
        los ítems con `effective_price()` (precio congelado al momento de la
        venta); el descuento se valida (0 <= d <= subtotal y <=
        max_discount_percent de LoyaltyConfig); la propina debe ser >= 0.
        `total = subtotal - discount + tip`.
        """
        if not items:
            raise ValidationError("La venta no tiene ítems.")
        if discount is None:
            discount = Decimal("0")
        if discount < 0:
            raise ValidationError("El descuento no puede ser negativo.")
        if tip is None:
            tip = Decimal("0")
        if tip < 0:
            raise ValidationError("La propina no puede ser negativa.")

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
            # Precio congelado al momento de la venta (promo / happy hour / regular).
            unit_price = effective_price(product)
            line_subtotal = unit_price * quantity
            subtotal += line_subtotal
            SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
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
        sale.discount = discount
        sale.tip = tip

        # Validación del descuento manual: 0 <= d <= subtotal y tope configurable.
        if discount > subtotal:
            raise ValidationError("El descuento no puede superar el subtotal.")
        from customers.models import LoyaltyConfig

        max_percent = LoyaltyConfig.get_solo().max_discount_percent
        max_discount = (subtotal * Decimal(max_percent) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if discount > max_discount:
            raise ValidationError(
                f"El descuento supera el máximo permitido ({max_percent}% del subtotal)."
            )

        sale.total = subtotal - discount + tip

        if payment_method == cls.PaymentMethod.EFECTIVO:
            if cash_received is None:
                raise ValidationError("Para pagos en efectivo hay que indicar el efectivo recibido.")
            if cash_received < sale.total:
                raise ValidationError("El efectivo recibido es menor al total.")
            sale.cash_received = cash_received
            sale.change = cash_received - sale.total
        sale.save(update_fields=["subtotal", "discount", "tip", "total", "cash_received", "change"])

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
