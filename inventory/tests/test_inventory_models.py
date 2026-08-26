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
