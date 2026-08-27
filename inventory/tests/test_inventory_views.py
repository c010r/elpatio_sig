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


def _payload_elaborado(category, name, **extra):
    """Payload base del form de producto (elaborado)."""
    data = {
        "name": name, "category": category.id, "unit": "unidad",
        "purchase_price": "0", "sale_price": "50",
        "stock_current": "0", "stock_min": "0",
        "is_composed": "on",
    }
    data.update(extra)
    return data


def test_create_elaborado_con_receta_guarda_recipeitems(client_gerente, category):
    """POST crear producto is_composed con ingredient_id[]/quantity[] → se
    persisten los RecipeItem."""
    from inventory.models import RecipeItem

    ing = Product.objects.create(
        name="Ing Cr", category=category, sale_price=Decimal("10"),
        stock_current=Decimal("50"),
    )
    response = client_gerente.post(
        reverse("inventory:product_create"),
        _payload_elaborado(category, "Elab Cr", ingredient_id=[str(ing.pk)], quantity=["2"]),
    )
    assert response.status_code == 302
    composed = Product.objects.get(name="Elab Cr")
    assert composed.is_composed is True
    assert composed.recipe_items.count() == 1
    ri = composed.recipe_items.get()
    assert ri.ingredient == ing
    assert ri.quantity == Decimal("2")


def test_update_elaborado_reemplaza_receta_sin_duplicar(client_gerente, category):
    """POST editar cambiando los ingredientes → receta reemplazada (no duplica)."""
    from inventory.models import RecipeItem

    ing1 = Product.objects.create(
        name="Ing U1", category=category, sale_price=Decimal("10"), stock_current=Decimal("50"),
    )
    ing2 = Product.objects.create(
        name="Ing U2", category=category, sale_price=Decimal("10"), stock_current=Decimal("50"),
    )
    composed = Product.objects.create(
        name="Elab U", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    RecipeItem.objects.create(product=composed, ingredient=ing1, quantity=Decimal("1"))

    response = client_gerente.post(
        reverse("inventory:product_update", args=[composed.pk]),
        _payload_elaborado(
            category, "Elab U", sale_price="55",
            ingredient_id=[str(ing2.pk)], quantity=["3"],
        ),
    )
    assert response.status_code == 302
    composed.refresh_from_db()
    assert composed.recipe_items.count() == 1
    ri = composed.recipe_items.get()
    assert ri.ingredient == ing2
    assert ri.quantity == Decimal("3")


def test_update_elaborado_desmarcado_borra_receta(client_gerente, category):
    """Desmarcar is_composed → se elimina la receta (cleanup)."""
    from inventory.models import RecipeItem

    ing = Product.objects.create(
        name="Ing D", category=category, sale_price=Decimal("10"), stock_current=Decimal("50"),
    )
    composed = Product.objects.create(
        name="Elab D", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    RecipeItem.objects.create(product=composed, ingredient=ing, quantity=Decimal("1"))

    payload = _payload_elaborado(category, "Elab D")
    payload["is_composed"] = ""  # checkbox desmarcado
    response = client_gerente.post(
        reverse("inventory:product_update", args=[composed.pk]), payload
    )
    assert response.status_code == 302
    composed.refresh_from_db()
    assert composed.is_composed is False
    assert composed.recipe_items.count() == 0


def test_create_elaborado_ignora_propio_como_ingrediente(client_gerente, category):
    """El propio producto como ingrediente → se ignora (no se auto-referencia)."""
    from inventory.models import RecipeItem

    ing = Product.objects.create(
        name="Ing S", category=category, sale_price=Decimal("10"), stock_current=Decimal("50"),
    )
    response = client_gerente.post(
        reverse("inventory:product_create"),
        _payload_elaborado(
            category, "Elab Self",
            ingredient_id=[str(ing.pk), "999999"], quantity=["1", "1"],
        ),
    )
    assert response.status_code == 302
    composed = Product.objects.get(name="Elab Self")
    # 999999 no existe → se ignora; solo queda el ingrediente válido
    assert composed.recipe_items.count() == 1
    # Update: el propio producto como ingrediente → ignorado
    response = client_gerente.post(
        reverse("inventory:product_update", args=[composed.pk]),
        _payload_elaborado(
            category, "Elab Self",
            ingredient_id=[str(composed.pk)], quantity=["1"],
        ),
    )
    composed.refresh_from_db()
    assert composed.recipe_items.count() == 0


def test_create_elaborado_sin_filas_error(client_gerente, category):
    """is_composed sin filas de ingrediente → error de form (200, no se crea)."""
    response = client_gerente.post(
        reverse("inventory:product_create"),
        _payload_elaborado(category, "Elab Sin Filas"),
    )
    assert response.status_code == 200  # re-render con error
    assert not Product.objects.filter(name="Elab Sin Filas").exists()


def test_product_form_contexto_ingredient_products(client_gerente, category):
    """El editor de receta aparece: GET create/update expone ingredient_products."""
    response = client_gerente.get(reverse("inventory:product_create"))
    assert response.status_code == 200
    assert "ingredient_products" in response.context

    composed = Product.objects.create(
        name="Elab Ctx", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    response = client_gerente.get(reverse("inventory:product_update", args=[composed.pk]))
    assert response.status_code == 200
    ids = [p.pk for p in response.context["ingredient_products"]]
    assert composed.pk not in ids  # el propio producto no es un ingrediente posible


# ---------------------------------------------------------------------------
# Separación materia prima / productos vendibles
# ---------------------------------------------------------------------------

def test_product_list_no_muestra_materia_prima(client_gerente, category):
    """product_list solo muestra productos vendibles (is_raw_material=False)."""
    Product.objects.create(
        name="Vendible", category=category, sale_price=Decimal("50"), is_active=True,
    )
    Product.objects.create(
        name="Materia X", category=category, sale_price=Decimal("10"),
        is_active=True, is_raw_material=True,
    )
    response = client_gerente.get(reverse("inventory:product_list"))
    names = [p.name for p in response.context["products"]]
    assert "Vendible" in names
    assert "Materia X" not in names


def test_material_list_muestra_solo_materia_prima(client_gerente, category):
    """material_list lista solo is_raw_material=True (con stock/costo)."""
    Product.objects.create(
        name="Vendible", category=category, sale_price=Decimal("50"), is_active=True,
    )
    Product.objects.create(
        name="Harina", category=category, sale_price=Decimal("10"),
        purchase_price=Decimal("8"), stock_current=Decimal("20"),
        stock_min=Decimal("5"), is_raw_material=True,
    )
    response = client_gerente.get(reverse("inventory:material_list"))
    assert response.status_code == 200
    names = [m.name for m in response.context["materials"]]
    assert names == ["Harina"]
    assert "Vendible" not in names
    assert response.context["materials"][0].stock_current == Decimal("20")


def test_material_list_permisos(gerente_user, bartender_user, cajero_user, category):
    """material_list: gerente y bartender OK; cajero denegado."""
    from django.test import Client

    c = Client()
    c.force_login(gerente_user)
    assert c.get(reverse("inventory:material_list")).status_code == 200

    c2 = Client()
    c2.force_login(bartender_user)
    assert c2.get(reverse("inventory:material_list")).status_code == 200

    c3 = Client()
    c3.force_login(cajero_user)
    assert_access_denied(c3.get(reverse("inventory:material_list")))


def test_product_form_rechaza_elaborado_y_materia_prima(category):
    """Un producto NO puede ser a la vez elaborado (receta) y materia prima."""
    from inventory.forms import ProductForm

    form = ProductForm(
        data={
            "name": "Imposible", "category": category.id, "unit": "unidad",
            "sale_price": "50", "is_composed": True, "is_raw_material": True,
            "ingredient_id": ["1"], "quantity": ["1"],
        }
    )
    assert not form.is_valid()
    assert "is_raw_material" in form.errors


def test_seed_demo_marca_materia_prima(category):
    """seed_demo marca como materia prima: Fernet, Coca, Masa, Salsa, Muzzarella."""
    from django.core.management import call_command

    for name in ("Fernet", "Gaseosa cola 500ml", "Masa de pizza",
                 "Salsa de tomate", "Muzzarella"):
        Product.objects.filter(name=name).update(is_raw_material=False)

    call_command("seed_demo", verbosity=0)

    for name in ("Fernet", "Gaseosa cola 500ml", "Masa de pizza",
                 "Salsa de tomate", "Muzzarella"):
        product = Product.objects.get(name=name)
        assert product.is_raw_material is True, name
    # Los elaborados NO son materia prima
    assert Product.objects.get(name="Fernet con coca").is_raw_material is False
    assert Product.objects.get(name="Pizza muzarella").is_raw_material is False
