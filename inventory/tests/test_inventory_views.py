"""
inventory — Tests de VISTAS y permisos (se saltan hasta que el backend
implemente las URLs/vistas de inventory).

Matriz de permisos del contrato:
- Gerente/Admin: CRUD categorías, CRUD productos, movimientos de stock.
- Bartender: solo VER stock (product_list, stock_low). NO crear/editar/borrar.
- Anónimo: redirect a login.
"""
import pytest
from django.urls import NoReverseMatch, reverse

try:
    from inventory.models import Category, Product, StockMovement
    reverse("inventory:product_list")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de inventory no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

from decimal import Decimal  # noqa: E402

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Acceso básico
# ---------------------------------------------------------------------------

def test_product_list_gerente_200(client_gerente):
    assert client_gerente.get(reverse("inventory:product_list")).status_code == 200


def test_product_list_muestra_moneda_uyu(client_gerente, product):
    """Los precios en el listado de productos usan el formato UYU ($U)."""
    response = client_gerente.get(reverse("inventory:product_list"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    # Precio del fixture: 150.00
    assert "$U 150,00" in content
    assert "USD" not in content


def test_product_list_bartender_200_ver_stock(client_bartender):
    assert client_bartender.get(reverse("inventory:product_list")).status_code == 200


def test_stock_low_gerente_200(client_gerente):
    assert client_gerente.get(reverse("inventory:stock_low")).status_code == 200


def test_stock_low_bartender_200_ver_stock(client_bartender):
    assert client_bartender.get(reverse("inventory:stock_low")).status_code == 200


def test_product_list_anon_redirect(client):
    response = client.get(reverse("inventory:product_list"))
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Permisos: bartender NO puede crear/editar/borrar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_name", ["product_create", "product_update", "product_delete",
                                      "category_create", "category_update", "category_delete",
                                      "stock_movement_create"])
def test_bartender_denegado_en_gestion(client_bartender, url_name):
    kwargs = {"pk": 1} if "update" in url_name or "delete" in url_name else {}
    assert_access_denied(client_bartender.get(reverse(f"inventory:{url_name}", kwargs=kwargs)))


# ---------------------------------------------------------------------------
# CRUD con gerente
# ---------------------------------------------------------------------------

def test_product_create_gerente_crea_producto(client_gerente, category):
    response = client_gerente.post(
        reverse("inventory:product_create"),
        {
            "name": "Fernet 750ml",
            "category": category.id,
            "unit": "botella",
            "purchase_price": "120.00",
            "sale_price": "250.00",
            "stock_current": "10",
            "stock_min": "2",
        },
    )
    assert response.status_code == 302, "La creación de producto debería redirigir tras guardar"
    assert Product.objects.filter(name="Fernet 750ml").exists()


def test_category_create_gerente_crea_categoria(client_gerente):
    response = client_gerente.post(
        reverse("inventory:category_create"),
        {"name": "Tragos", "description": "Cócteles y tragos largos"},
    )
    assert response.status_code == 302
    assert Category.objects.filter(name="Tragos").exists()


def test_stock_movement_create_gerente_genera_movimiento(client_gerente, product):
    stock_inicial = product.stock_current
    response = client_gerente.post(
        reverse("inventory:stock_movement_create"),
        {
            "product": product.id,
            "quantity": "5",
            "movement_type": "entrada",
            "reference": "Test de reposición",
        },
    )
    assert response.status_code == 302
    product.refresh_from_db()
    assert product.stock_current == stock_inicial + 5


# ---------------------------------------------------------------------------
# Productos elaborados (recetas)
# ---------------------------------------------------------------------------

def test_stock_low_excluye_elaborados(client_gerente, category):
    """Los productos is_composed no figuran en stock bajo: su stock es la
    materia prima, controlada por los ingredientes."""
    Product.objects.create(
        name="Elab bajo", category=category, sale_price=Decimal("50"),
        stock_current=Decimal("1"), stock_min=Decimal("5"), is_composed=True,
    )
    response = client_gerente.get(reverse("inventory:stock_low"))
    assert response.status_code == 200
    names = [p.name for p in response.context["low_products"]]
    assert "Elab bajo" not in names


def test_product_form_rechaza_elaborado_sin_receta(category):
    """is_composed=True sin ningún RecipeItem → error de formulario."""
    from inventory.forms import ProductForm

    form = ProductForm(
        data={
            "name": "Elab sin receta", "category": category.id, "unit": "unidad",
            "sale_price": "50", "is_composed": True,
        }
    )
    assert not form.is_valid()
    assert "is_composed" in form.errors
