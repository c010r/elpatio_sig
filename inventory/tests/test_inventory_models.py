"""
inventory — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- StockMovement.apply() suma/resta stock de forma transaccional.
- stock bajo: stock_current <= stock_min (Product.is_low_stock).
- Categoría única por nombre; barcode único opcional; borrado lógico is_active.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError

try:
    from inventory.models import Category, Product, StockMovement
except ImportError:
    pytest.skip("Backend de inventory no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# StockMovement.apply()
# ---------------------------------------------------------------------------

def test_apply_entrada_suma_stock(product, gerente_user):
    StockMovement.objects.create(
        product=product,
        quantity=Decimal("10"),
        movement_type=StockMovement.MovementType.ENTRADA,
        reference="Compra OC-0001",
        user=gerente_user,
    ).apply()
    product.refresh_from_db()
    assert product.stock_current == Decimal("30")


def test_apply_salida_resta_stock(product, gerente_user):
    StockMovement.objects.create(
        product=product,
        quantity=Decimal("-5"),
        movement_type=StockMovement.MovementType.SALIDA,
        reference="Merma",
        user=gerente_user,
    ).apply()
    product.refresh_from_db()
    assert product.stock_current == Decimal("15")


def test_apply_venta_resta_stock(product, gerente_user):
    StockMovement.objects.create(
        product=product,
        quantity=Decimal("-2"),
        movement_type=StockMovement.MovementType.VENTA,
        reference="Venta T-20260101-0001",
        user=gerente_user,
    ).apply()
    product.refresh_from_db()
    assert product.stock_current == Decimal("18")


def test_apply_stock_insuficiente_rechaza_y_no_modifica(product, gerente_user):
    """Un movimiento que deja el stock negativo debe rechazarse (ValueError) y
    no alterar el stock (rollback transaccional)."""
    with pytest.raises(ValueError):
        StockMovement.objects.create(
            product=product,
            quantity=Decimal("-999"),
            movement_type=StockMovement.MovementType.SALIDA,
            reference="Imposible",
            user=gerente_user,
        ).apply()
    product.refresh_from_db()
    assert product.stock_current == Decimal("20")


def test_apply_crea_registro_de_movimiento(product, gerente_user):
    StockMovement.objects.create(
        product=product,
        quantity=Decimal("3"),
        movement_type=StockMovement.MovementType.AJUSTE,
        reference="Conteo",
        user=gerente_user,
    ).apply()
    assert StockMovement.objects.filter(product=product, movement_type="ajuste").count() == 1


# ---------------------------------------------------------------------------
# Product / Category
# ---------------------------------------------------------------------------

def test_is_low_stock(product, category):
    """stock bajo: stock_current <= stock_min."""
    assert product.is_low_stock is False  # 20 > 5
    bajo = Product.objects.create(
        name="Vino Tinto",
        category=category,
        unit="botella",
        sale_price=Decimal("350.00"),
        stock_current=Decimal("2"),
        stock_min=Decimal("10"),
    )
    assert bajo.is_low_stock is True


def test_category_nombre_unico(category):
    with pytest.raises(IntegrityError):
        Category.objects.create(name="Bebidas", description="duplicada")


def test_product_barcode_unico(category):
    Product.objects.create(
        name="Con código de barras", category=category, sale_price=Decimal("10.00"),
        barcode="7790000000001",
    )
    with pytest.raises(IntegrityError):
        Product.objects.create(
            name="Duplicado de código", category=category, sale_price=Decimal("10.00"),
            barcode="7790000000001",
        )


def test_producto_sin_barcode_ok(category):
    p = Product.objects.create(
        name="Sin código", category=category, sale_price=Decimal("10.00")
    )
    assert p.barcode is None


def test_is_active_default_true(category):
    p = Product.objects.create(name="Activo por defecto", category=category, sale_price=Decimal("5"))
    assert p.is_active is True


def test_unidades_permitidas(category):
    p = Product.objects.create(name="Jarra", category=category, unit="jarra", sale_price=Decimal("80"))
    assert p.get_unit_display() == "jarra"


# ---------------------------------------------------------------------------
# Recetas (RecipeItem) / productos elaborados
# ---------------------------------------------------------------------------

def test_recipe_cost_suma_ingredientes(category):
    """recipe_cost = suma(cantidad × precio_compra) de los ingredientes."""
    from inventory.models import RecipeItem

    ing1 = Product.objects.create(
        name="ICosto1", category=category, sale_price=Decimal("10"),
        purchase_price=Decimal("4"), stock_current=Decimal("10"),
    )
    ing2 = Product.objects.create(
        name="ICosto2", category=category, sale_price=Decimal("10"),
        purchase_price=Decimal("6"), stock_current=Decimal("10"),
    )
    comp = Product.objects.create(
        name="CCosto", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    RecipeItem.objects.create(product=comp, ingredient=ing1, quantity=Decimal("2"))
    RecipeItem.objects.create(product=comp, ingredient=ing2, quantity=Decimal("1"))
    assert comp.recipe_items.count() == 2
    assert comp.recipe_cost == Decimal("14")  # 2×4 + 1×6


def test_recipe_item_unique_por_producto_ingrediente(category):
    """No se puede repetir el mismo ingrediente en la misma receta."""
    from inventory.models import RecipeItem

    ing = Product.objects.create(
        name="IUnique", category=category, sale_price=Decimal("10"), stock_current=Decimal("10"),
    )
    comp = Product.objects.create(
        name="CUnique", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    RecipeItem.objects.create(product=comp, ingredient=ing, quantity=Decimal("1"))
    with pytest.raises(IntegrityError):
        RecipeItem.objects.create(product=comp, ingredient=ing, quantity=Decimal("2"))
