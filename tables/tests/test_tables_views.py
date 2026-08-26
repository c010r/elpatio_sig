"""
tables — Tests de VISTAS y permisos (se saltan hasta que el backend implemente
las URLs/vistas de tables).

Matriz de permisos del contrato:
- Bartender: mapa de mesas, abrir mesa, agregar ítems, marcar entregado,
  cerrar comanda.
- Gerente/Admin: además CRUD de mesas.
- Anónimo: redirect a login.
"""
from decimal import Decimal

import pytest
from django.urls import NoReverseMatch, reverse

try:
    from tables.models import Order, OrderItem, Table
    reverse("tables:table_map")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de tables no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Acceso por rol
# ---------------------------------------------------------------------------

def test_table_map_bartender_200(client_bartender):
    assert client_bartender.get(reverse("tables:table_map")).status_code == 200


def test_table_map_anon_redirect(client):
    assert client.get(reverse("tables:table_map")).status_code == 302


@pytest.mark.parametrize("url_name", ["table_create", "table_update", "table_delete"])
def test_bartender_denegado_crud_mesas(client_bartender, url_name):
    kwargs = {"pk": 1} if "update" in url_name or "delete" in url_name else {}
    assert_access_denied(client_bartender.get(reverse(f"tables:{url_name}", kwargs=kwargs)))


# ---------------------------------------------------------------------------
# Flujo de comanda (bartender)
# ---------------------------------------------------------------------------

def test_abrir_mesa_crea_comanda_y_ocupa_mesa(client_bartender, table, bartender_user):
    # La URL de order_create recibe table_pk (mesas/comandas/crear/<table_pk>/).
    response = client_bartender.post(
        reverse("tables:order_create", args=[table.id]), {"table": table.id, "note": ""}
    )
    assert response.status_code == 302
    assert Order.objects.filter(table=table, status=Order.Status.ABIERTA).exists()
    table.refresh_from_db()
    assert table.status == Table.Status.OCUPADA


def test_agregar_items_a_comanda(client_bartender, table, bartender_user, product):
    order = Order.objects.create(table=table, waiter=bartender_user, status=Order.Status.ABIERTA)
    response = client_bartender.post(
        reverse("tables:order_add_item", args=[order.id]),
        {"product": product.id, "quantity": "2"},
    )
    assert response.status_code == 302
    assert OrderItem.objects.filter(order=order, product=product, quantity=Decimal("2")).exists()


def test_cerrar_comanda_via_vista(client_bartender, table, bartender_user, product):
    order = Order.objects.create(table=table, waiter=bartender_user, status=Order.Status.ABIERTA)
    OrderItem.objects.create(
        order=order, product=product, quantity=Decimal("1"), unit_price=product.sale_price,
        status=OrderItem.Status.ENTREGADO,
    )
    response = client_bartender.post(
        reverse("tables:order_close", args=[order.id]),
        {"payment_method": "efectivo", "cash_received": "200.00"},
    )
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == Order.Status.PAGADA
