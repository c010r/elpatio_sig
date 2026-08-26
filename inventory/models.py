"""
inventory — Modelos de categorías, productos y movimientos de stock.
"""
from django.conf import settings
from django.db import models, transaction


class Category(models.Model):
    """Categoría de productos (maestro, borrado lógico vía is_active)."""

    name = models.CharField("nombre", max_length=100, unique=True)
    description = models.TextField("descripción", blank=True)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Producto con precio de compra/venta y stock actual/mínimo."""

    class Unit(models.TextChoices):
        UNIDAD = "unidad", "unidad"
        BOTELLA = "botella", "botella"
        JARRA = "jarra", "jarra"
        PORCION = "porción", "porción"
        KG = "kg", "kg"
        L = "l", "l"

    name = models.CharField("nombre", max_length=150)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="categoría",
    )
    unit = models.CharField("unidad", max_length=20, choices=Unit.choices, default=Unit.UNIDAD)
    purchase_price = models.DecimalField("precio de compra", max_digits=10, decimal_places=2, default=0)
    sale_price = models.DecimalField("precio de venta", max_digits=10, decimal_places=2)
    stock_current = models.DecimalField("stock actual", max_digits=10, decimal_places=2, default=0)
    stock_min = models.DecimalField("stock mínimo", max_digits=10, decimal_places=2, default=0)
    barcode = models.CharField("código de barras", max_length=50, unique=True, null=True, blank=True)
    image = models.ImageField("imagen", upload_to="products/", null=True, blank=True)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        """True si el stock actual está por debajo o igual al mínimo."""
        return self.stock_current <= self.stock_min


class StockMovement(models.Model):
    """Movimiento de stock con cantidad con signo. apply() actualiza stock_current."""

    class MovementType(models.TextChoices):
        ENTRADA = "entrada", "entrada"
        SALIDA = "salida", "salida"
        AJUSTE = "ajuste", "ajuste"
        VENTA = "venta", "venta"
        COMPRA = "compra", "compra"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="producto",
    )
    quantity = models.DecimalField(
        "cantidad",
        max_digits=10,
        decimal_places=2,
        help_text="Positiva para entradas/compras, negativa para salidas/ventas.",
    )
    movement_type = models.CharField("tipo de movimiento", max_length=20, choices=MovementType.choices)
    reference = models.CharField("referencia", max_length=200, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
        verbose_name="usuario",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de stock"
        verbose_name_plural = "movimientos de stock"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} de {self.product}"

    @transaction.atomic
    def apply(self):
        """Aplica el movimiento al stock del producto de forma transaccional.

        La cantidad se suma al stock actual; si el resultado fuera negativo
        (stock insuficiente) se rechaza con ValueError y se revierte todo.
        """
        product = Product.objects.select_for_update().get(pk=self.product_id)
        new_stock = product.stock_current + self.quantity
        if new_stock < 0:
            raise ValueError(
                f"Stock insuficiente para {product.name}: "
                f"disponible {product.stock_current}, requerido {-self.quantity}."
            )
        product.stock_current = new_stock
        product.save(update_fields=["stock_current"])
        return self
