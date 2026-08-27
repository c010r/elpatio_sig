"""
inventory — Modelos de categorías, productos y movimientos de stock.
"""
from decimal import Decimal

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
    promo_price = models.DecimalField(
        "precio promo", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Precio promocional (se usa si promo activa; no se acumula con happy hour).",
    )
    promo_active = models.BooleanField("promo activa", default=False)
    is_composed = models.BooleanField(
        "elaborado (con receta)", default=False,
        help_text="Si está activo, al vender se descuenta la materia prima (RecipeItem).",
    )
    is_raw_material = models.BooleanField(
        "materia prima", default=False,
        help_text="Marca el producto como materia prima (se lista en Materiales).",
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["name"]
        constraints = [
            # F2-12: si la promo está activa, el precio promo debe existir y ser > 0.
            models.CheckConstraint(
                condition=models.Q(promo_active=False)
                | models.Q(promo_price__isnull=False, promo_price__gt=0),
                name="promo_active_requires_price",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        """True si el stock actual está por debajo o igual al mínimo."""
        return self.stock_current <= self.stock_min

    @property
    def recipe_cost(self):
        """Costo de la receta por 1 unidad: suma de cantidad × precio de compra
        de cada ingrediente. 0 si no tiene receta."""
        total = Decimal("0")
        for item in self.recipe_items.select_related("ingredient"):
            total += item.quantity * item.ingredient.purchase_price
        return total


class RecipeItem(models.Model):
    """Ingrediente de la receta de un producto elaborado (is_composed=True).

    `product` es el producto terminado; `ingredient` la materia prima. La
    `quantity` es la cantidad de ingrediente necesaria por 1 unidad del
    producto terminado.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name="recipe_items", verbose_name="producto elaborado",
    )
    ingredient = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name="used_in_recipes", verbose_name="ingrediente",
    )
    quantity = models.DecimalField(
        "cantidad por unidad", max_digits=10, decimal_places=2,
        help_text="Cantidad de ingrediente necesaria por 1 unidad del producto.",
    )

    class Meta:
        verbose_name = "ingrediente de receta"
        verbose_name_plural = "ingredientes de receta"
        unique_together = ("product", "ingredient")

    def __str__(self):
        return f"{self.quantity} de {self.ingredient.name} para {self.product.name}"


def composed_products_with_low_ingredients():
    """Productos elaborados cuya MATERIA PRIMA está baja (<= stock mínimo).

    Devuelve una lista de (product, [ingredientes_bajos]). El stock de un
    elaborado se controla por sus ingredientes, por eso este helper alimenta
    el "stock bajo" y su contador.
    """
    result = []
    products = Product.objects.filter(is_active=True, is_composed=True).prefetch_related(
        "recipe_items__ingredient"
    )
    for p in products:
        low = [
            ri.ingredient
            for ri in p.recipe_items.all()
            if ri.ingredient.is_active and ri.ingredient.stock_current <= ri.ingredient.stock_min
        ]
        if low:
            result.append((p, low))
    return result


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
