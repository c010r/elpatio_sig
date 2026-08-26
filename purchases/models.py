"""
purchases — Modelos de proveedores y órdenes de compra.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone


class Supplier(models.Model):
    """Proveedor (maestro, borrado lógico vía is_active)."""

    name = models.CharField("nombre", max_length=150)
    contact_name = models.CharField("persona de contacto", max_length=150, blank=True)
    phone = models.CharField("teléfono", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    address = models.CharField("dirección", max_length=250, blank=True)
    cuit = models.CharField("CUIT", max_length=20, blank=True)
    notes = models.TextField("notas", blank=True)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """Orden de compra a un proveedor (OC-####)."""

    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "pendiente"
        RECIBIDA = "recibida", "recibida"
        CANCELADA = "cancelada", "cancelada"

    number = models.CharField("número", max_length=20, unique=True, editable=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders", verbose_name="proveedor"
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDIENTE)
    total = models.DecimalField("total", max_digits=10, decimal_places=2, default=Decimal("0"))
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name="solicitada por",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField("recibida el", null=True, blank=True)

    class Meta:
        verbose_name = "orden de compra"
        verbose_name_plural = "órdenes de compra"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OC {self.number} - {self.supplier.name}"

    @classmethod
    def next_number(cls):
        """Número de OC secuencial: OC-#### (llamar dentro de transaction.atomic)."""
        prefix = "OC-"
        for _ in range(10):
            try:
                with transaction.atomic():
                    last = cls.objects.select_for_update().order_by("-number").first()
                    seq = int(last.number[len(prefix):]) + 1 if last else 1
                    return f"{prefix}{seq:04d}"
            except IntegrityError:
                continue
        raise RuntimeError("No se pudo generar un número de OC único.")

    @transaction.atomic
    def receive(self, user):
        """Recibe la orden: genera movimientos de stock (compra) y actualiza precios de compra."""
        if self.status != self.Status.PENDIENTE:
            raise ValidationError("Solo se pueden recibir órdenes pendientes.")

        from inventory.models import StockMovement

        for item in self.items.select_related("product"):
            product = item.product
            StockMovement.objects.create(
                product=product,
                quantity=item.quantity,
                movement_type=StockMovement.MovementType.COMPRA,
                reference=f"OC {self.number}",
                user=user,
            ).apply()
            product.purchase_price = item.unit_cost
            product.save(update_fields=["purchase_price"])
        self.status = self.Status.RECIBIDA
        self.received_at = timezone.now()
        self.save(update_fields=["status", "received_at"])

    def cancel(self):
        """Cancela la orden de compra."""
        if self.status != self.Status.PENDIENTE:
            raise ValidationError("Solo se pueden cancelar órdenes pendientes.")
        self.status = self.Status.CANCELADA
        self.save(update_fields=["status"])


class PurchaseItem(models.Model):
    """Ítem de una orden de compra."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items", verbose_name="orden"
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="purchase_items",
        verbose_name="producto",
    )
    quantity = models.DecimalField("cantidad", max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField("costo unitario", max_digits=10, decimal_places=2)
    subtotal = models.DecimalField("subtotal", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "ítem de orden de compra"
        verbose_name_plural = "ítems de orden de compra"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"
