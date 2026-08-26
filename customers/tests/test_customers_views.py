"""
customers — Tests de VISTAS y permisos (se saltan hasta que el backend
implemente las URLs/vistas de customers).

Matriz de permisos del contrato:
- Cajero/Gerente/Admin: listado, CRUD, detalle y canje de puntos de clientes.
- Bartender: NO accede a clientes.
- Anónimo: redirect a login.
"""
import pytest
from django.urls import NoReverseMatch, reverse

try:
    from customers.models import Customer, LoyaltyConfig
    reverse("customers:customer_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de customers no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("url_name", ["customer_list", "customer_create"])
def test_cajero_200(client_cajero, url_name):
    assert client_cajero.get(reverse(f"customers:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["customer_list", "customer_create"])
def test_gerente_200(client_gerente, url_name):
    assert client_gerente.get(reverse(f"customers:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["customer_list", "customer_create", "customer_detail",
                                      "customer_redeem"])
def test_bartender_denegado(client_bartender, url_name):
    kwargs = {"pk": 1} if url_name in ("customer_detail", "customer_redeem") else {}
    assert_access_denied(client_bartender.get(reverse(f"customers:{url_name}", kwargs=kwargs)))


def test_customer_create_cajero_crea_cliente(client_cajero):
    # CustomerForm expone "points" como campo obligatorio (detalle de diseño
    # a revisar por el backend); se envía 0 para el alta.
    response = client_cajero.post(
        reverse("customers:customer_create"),
        {"name": "Nuevo Cliente", "phone": "+54 11 5555-9999", "dni": "40222333", "points": "0"},
    )
    assert response.status_code == 302
    assert Customer.objects.filter(name="Nuevo Cliente").exists()


def test_customer_redeem_descuenta_puntos(client_cajero, customer):
    customer.points = 250
    customer.save(update_fields=["points"])
    response = client_cajero.post(reverse("customers:customer_redeem", args=[customer.id]))
    assert response.status_code == 302
    customer.refresh_from_db()
    # canje: descuenta points_required_for_discount (100 por defecto)
    assert customer.points == 150
