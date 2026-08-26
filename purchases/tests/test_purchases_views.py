"""
purchases — Tests de VISTAS y permisos (se saltan hasta que el backend
implemente las URLs/vistas de purchases).

Matriz de permisos del contrato:
- Gerente/Admin: proveedores y órdenes de compra (CRUD + recibir/cancelar).
- Bartender: NO accede a compras.
- Anónimo: redirect a login.
"""
import json

import pytest
from django.urls import NoReverseMatch, reverse

try:
    from purchases.models import PurchaseOrder, PurchaseItem, Supplier
    reverse("purchases:purchase_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de purchases no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("url_name", [
    "supplier_list", "supplier_create", "supplier_update", "supplier_delete",
    "purchase_list", "purchase_create", "purchase_receive", "purchase_cancel",
])
def test_bartender_denegado(client_bartender, url_name):
    kwargs = {"pk": 1} if any(k in url_name for k in ("update", "delete", "receive", "cancel")) else {}
    assert_access_denied(client_bartender.get(reverse(f"purchases:{url_name}", kwargs=kwargs)))


def test_supplier_create_gerente_crea_proveedor(client_gerente):
    response = client_gerente.post(
        reverse("purchases:supplier_create"),
        {"name": "Distribuidora Sur", "cuit": "30-99999999-9"},
    )
    assert response.status_code == 302
    assert Supplier.objects.filter(name="Distribuidora Sur").exists()


def test_purchase_create_gerente_crea_orden(client_gerente, supplier, product):
    # El form real espera `supplier` + `items` (JSON: [{product_id, quantity, unit_cost}]).
    response = client_gerente.post(
        reverse("purchases:purchase_create"),
        {
            "supplier": supplier.id,
            "items": json.dumps(
                [{"product_id": product.id, "quantity": 2, "unit_cost": "70.00"}]
            ),
        },
    )
    assert response.status_code == 302
    order = PurchaseOrder.objects.filter(supplier=supplier).first()
    assert order is not None
    assert order.total == 140  # 2 × 70


def test_purchase_receive_gerente(client_gerente, supplier, gerente_user, product):
    order = PurchaseOrder.objects.create(
        number="OC-0001", supplier=supplier, status=PurchaseOrder.Status.PENDIENTE,
        ordered_by=gerente_user,
    )
    PurchaseItem.objects.create(
        order=order, product=product, quantity=1, unit_cost=10, subtotal=10,
    )
    response = client_gerente.post(reverse("purchases:purchase_receive", args=[order.id]))
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == PurchaseOrder.Status.RECIBIDA
    product.refresh_from_db()
    assert product.stock_current == 21
