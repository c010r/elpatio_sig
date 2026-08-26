"""
purchases — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- Número de OC secuencial único (OC-####).
- Recibir orden → StockMovement tipo compra (entrada) + actualiza stock y
  purchase_price. Solo se reciben órdenes pendientes.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

try:
    from inventory.models import StockMovement
    from purchases.models import PurchaseItem, PurchaseOrder, Supplier
except ImportError:
    pytest.skip("Backend de purchases no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


def _crear_orden(supplier, gerente_user, number="OC-0001"):
    return PurchaseOrder.objects.create(
        number=number, supplier=supplier, status=PurchaseOrder.Status.PENDIENTE,
        ordered_by=gerente_user,
    )


# ---------------------------------------------------------------------------
# PurchaseOrder
# ---------------------------------------------------------------------------

def test_next_number_secuencial(supplier, gerente_user):
    """next_number() calcula el siguiente número sin persistirlo; el ordenante
    lo usa al crear la OC."""
    PurchaseOrder.objects.create(
        number=PurchaseOrder.next_number(), supplier=supplier, ordered_by=gerente_user
    )
    assert PurchaseOrder.next_number() == "OC-0002"


def test_number_unico(supplier, gerente_user):
    _crear_orden(supplier, gerente_user, number="OC-0042")
    with pytest.raises(IntegrityError):
        _crear_orden(supplier, gerente_user, number="OC-0042")


# ---------------------------------------------------------------------------
# Recibir orden
# ---------------------------------------------------------------------------

def test_recibir_orden_entrada_stock_y_precio(supplier, gerente_user, product):
    order = _crear_orden(supplier, gerente_user)
    PurchaseItem.objects.create(
        order=order, product=product, quantity=Decimal("10"),
        unit_cost=Decimal("70.00"), subtotal=Decimal("700.00"),
    )
    stock_inicial = product.stock_current  # 20

    order.receive(gerente_user)

    # stock actualizado (20 + 10)
    product.refresh_from_db()
    assert product.stock_current == Decimal("30")
    # purchase_price actualizado al último costo
    assert product.purchase_price == Decimal("70.00")
    # movimiento de compra registrado
    mov = StockMovement.objects.filter(product=product, movement_type=StockMovement.MovementType.COMPRA)
    assert mov.count() == 1
    assert mov[0].quantity == Decimal("10")
    # estado de la orden
    order.refresh_from_db()
    assert order.status == PurchaseOrder.Status.RECIBIDA
    assert order.received_at is not None


def test_recibir_orden_solo_pendiente(supplier, gerente_user, product):
    order = _crear_orden(supplier, gerente_user)
    order.receive(gerente_user)
    with pytest.raises(ValidationError):
        order.receive(gerente_user)


def test_cancelar_orden(supplier, gerente_user):
    order = _crear_orden(supplier, gerente_user)
    order.cancel()
    order.refresh_from_db()
    assert order.status == PurchaseOrder.Status.CANCELADA
    with pytest.raises(ValidationError):
        order.cancel()


def test_total_orden_default_cero(supplier, gerente_user):
    order = _crear_orden(supplier, gerente_user)
    assert order.total == Decimal("0")
