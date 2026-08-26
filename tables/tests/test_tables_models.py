"""
tables — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- Comanda con total derivado (suma quantity × unit_price).
- Cerrar comanda genera Sale (descuenta stock) y libera la mesa.
- Estados: abierta → cerrada/pagada/cancelada.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

try:
    from tables.models import Order, OrderItem, Table
except ImportError:
    pytest.skip("Backend de tables no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


def _abrir_comanda(table, waiter, **kwargs):
    kwargs.setdefault("status", Order.Status.ABIERTA)
    return Order.objects.create(table=table, waiter=waiter, **kwargs)


def _agregar_item(order, product, quantity, status=OrderItem.Status.PENDIENTE, unit_price=None):
    return OrderItem.objects.create(
        order=order,
        product=product,
        quantity=Decimal(str(quantity)),
        unit_price=unit_price if unit_price is not None else product.sale_price,
        status=status,
    )


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------

def test_table_por_defecto_libre(table):
    assert table.status == Table.Status.LIBRE


def test_table_numero_unico(table):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        Table.objects.create(number=1, capacity=4, zone="salón")


# ---------------------------------------------------------------------------
# Order / OrderItem
# ---------------------------------------------------------------------------

def test_order_total_derivado(table, bartender_user, product):
    order = _abrir_comanda(table, bartender_user)
    _agregar_item(order, product, 2)          # 2 × 150 = 300
    _agregar_item(order, product, 1)          # 1 × 150 = 150
    assert order.total == Decimal("450.00")


def test_order_total_cero_sin_items(table, bartender_user):
    order = _abrir_comanda(table, bartender_user)
    assert order.total == Decimal("0")


def test_comanda_solo_items_entregados_se_cobran(table, bartender_user, product):
    """Cerrar comanda cobra únicamente los ítems con estado 'entregado'."""
    order = _abrir_comanda(table, bartender_user)
    _agregar_item(order, product, 2, status=OrderItem.Status.ENTREGADO)
    _agregar_item(order, product, 1, status=OrderItem.Status.PENDIENTE)
    sale = order.close_to_sale(
        user=bartender_user,
        cash_register=None,
        payment_method="efectivo",
        cash_received=Decimal("400"),
    )
    assert sale.total == Decimal("300.00")  # solo los 2 entregados
    assert sale.table == table


def test_cerrar_comanda_genera_sale_y_libera_mesa(table, bartender_user, product):
    order = _abrir_comanda(table, bartender_user)
    _agregar_item(order, product, 2, status=OrderItem.Status.ENTREGADO)

    stock_inicial = product.stock_current
    sale = order.close_to_sale(
        user=bartender_user, cash_register=None, cash_received=Decimal("400")
    )

    assert sale is not None
    # ticket con formato YYYYMMDD-#### (validado en detalle en sales)
    from django.utils import timezone

    prefijo = timezone.localdate().strftime("%Y%m%d") + "-"
    assert sale.ticket_number.startswith(prefijo)
    # stock descontado (vía Sale.complete_sale)
    product.refresh_from_db()
    assert product.stock_current == stock_inicial - Decimal("2")
    # comanda pagada y mesa liberada
    order.refresh_from_db()
    assert order.status == Order.Status.PAGADA
    assert order.closed_at is not None
    table.refresh_from_db()
    assert table.status == Table.Status.LIBRE


def test_cerrar_comanda_no_abierta_rechazada(table, bartender_user, product):
    order = _abrir_comanda(table, bartender_user, status=Order.Status.CERRADA)
    with pytest.raises(ValidationError):
        order.close_to_sale(user=bartender_user, cash_register=None)


def test_cerrar_comanda_sin_items_entregados_rechazada(table, bartender_user, product):
    order = _abrir_comanda(table, bartender_user)
    _agregar_item(order, product, 1, status=OrderItem.Status.PENDIENTE)
    with pytest.raises(ValidationError):
        order.close_to_sale(user=bartender_user, cash_register=None)


def test_estados_comanda_validos(table, bartender_user):
    order = _abrir_comanda(table, bartender_user)
    assert order.status == Order.Status.ABIERTA
    order.status = Order.Status.CERRADA
    order.save()
    order.status = Order.Status.PAGADA
    order.save()
    order.status = Order.Status.CANCELADA
    order.save()
