"""
sales — Tests de VISTAS y permisos (se saltan hasta que el backend implemente
las URLs/vistas de sales).

Matriz de permisos del contrato:
- Cajero/Gerente/Admin: POS, caja, listado de ventas.
- Bartender: POS, ventas y tickets (venta en barra) PERO NO gestiona caja;
  solo anula SUS propias ventas (F2-06: autor o gerente/admin, motivo obligatorio).
- Gerente: anular ventas (cualquiera).
- Anónimo: redirect a login.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

try:
    from sales.models import CashRegister, Sale, SaleItem
    reverse("sales:pos")
    reverse("sales:cash_register_open")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de sales no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpiar_cache():
    """Los singletons (LoyaltyConfig/HappyHourConfig/SaleConfig) cachean en
    LocMemCache (no transaccional); se limpia entre tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Acceso por rol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_name", ["pos", "sale_list", "cash_register_open"])
def test_cajero_200(client_cajero, url_name):
    assert client_cajero.get(reverse(f"sales:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["pos", "sale_list", "cash_register_open"])
def test_gerente_200(client_gerente, url_name):
    assert client_gerente.get(reverse(f"sales:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["pos", "sale_list"])
def test_bartender_200_ventas(client_bartender, url_name):
    """Venta en barra: el bartender accede al POS y al listado de ventas."""
    assert client_bartender.get(reverse(f"sales:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["cash_register_open", "cash_register_close"])
def test_bartender_denegado_gestion_caja(client_bartender, url_name):
    """La gestión de caja (abrir/cerrar) sigue siendo solo cajero/gerente/admin."""
    assert_access_denied(client_bartender.get(reverse(f"sales:{url_name}")))


def test_bartender_pos_checkout_crea_venta(client_bartender, product, open_cash_register):
    """El bartender puede cobrar en barra: crea la venta y descuenta stock."""
    stock_inicial = product.stock_current
    response = client_bartender.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id)],
            "quantity": ["1"],
            "payment_method": "efectivo",
            "cash_received": "200.00",
        },
    )
    assert response.status_code == 302
    sale = Sale.objects.order_by("-pk").first()
    assert sale is not None and sale.user.username == "bartender_user"
    product.refresh_from_db()
    assert product.stock_current == stock_inicial - Decimal("1")


def test_pos_interruptor_imprimir_ticket(client_cajero, product, open_cash_register):
    """Interruptor del POS: con print_ticket -> ticket auto-print; sin él -> POS directo."""
    # Con el interruptor activado: redirige al ticket con ?auto=1
    response = client_cajero.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id)],
            "quantity": ["1"],
            "payment_method": "efectivo",
            "print_ticket": "on",
        },
    )
    assert response.status_code == 302
    assert response.get("Location", "").endswith("?auto=1")
    # Sale detail quedó en /ventas/<pk>/ (sin el prefijo repetido)
    assert "/ventas/" in response.get("Location", "") and "pos" not in response.get("Location", "")

    # Sin el interruptor: vuelve directo al POS, sin página de ticket
    response = client_cajero.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id)],
            "quantity": ["1"],
            "payment_method": "efectivo",
        },
    )
    assert response.status_code == 302
    assert response.get("Location") == reverse("sales:pos")


def test_bartender_sale_detail_200(client_bartender, product, cajero_user, open_cash_register):
    """El bartender ve el ticket de sus ventas."""
    sale = Sale.complete_sale(
        user=User.objects.get(username="bartender_user"), items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_bartender.get(reverse("sales:sale_detail", args=[sale.id]))
    assert response.status_code == 200


def test_bartender_no_anula_venta_ajena(client_bartender, product, cajero_user, open_cash_register):
    """F2-06: el bartender no puede anular la venta de otro cajero."""
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_bartender.post(reverse("sales:sale_void", args=[sale.id]),
                                     {"reason": "error de cobro"})
    assert response.status_code == 302
    sale.refresh_from_db()
    assert sale.status == Sale.Status.COMPLETADA


def test_bartender_anula_su_venta_con_motivo(client_bartender, product, open_cash_register):
    """F2-06: el bartender anula SU propia venta con motivo obligatorio."""
    sale = Sale.complete_sale(
        user=User.objects.get(username="bartender_user"), items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_bartender.post(reverse("sales:sale_void", args=[sale.id]),
                                     {"reason": "pedido equivocado"})
    assert response.status_code == 302
    sale.refresh_from_db()
    assert sale.status == Sale.Status.ANULADA


def test_bartender_no_anula_sin_motivo(client_bartender, product, open_cash_register):
    """F2-06: el motivo es obligatorio incluso para el autor."""
    sale = Sale.complete_sale(
        user=User.objects.get(username="bartender_user"), items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_bartender.post(reverse("sales:sale_void", args=[sale.id]), {"reason": ""})
    assert response.status_code == 302
    sale.refresh_from_db()
    assert sale.status == Sale.Status.COMPLETADA


def test_pos_anon_redirect(client):
    assert client.get(reverse("sales:pos")).status_code == 302


# ---------------------------------------------------------------------------
# Apertura/cierre de caja
# ---------------------------------------------------------------------------

def test_abrir_caja_crea_registro(client_cajero):
    response = client_cajero.post(
        reverse("sales:cash_register_open"), {"opening_amount": "1000.00"}
    )
    assert response.status_code == 302
    assert CashRegister.get_open() is not None


def test_no_abre_segunda_caja_si_hay_una_abierta(client_cajero, open_cash_register):
    """Regla UNA caja abierta: la vista no debe dejar abrir otra."""
    response = client_cajero.post(
        reverse("sales:cash_register_open"), {"opening_amount": "500.00"}
    )
    # Se acepta redirect (con mensaje de error) o 200 con error de formulario,
    # pero NUNCA debe quedar una segunda caja abierta.
    assert response.status_code in (200, 302)
    assert CashRegister.objects.filter(status=CashRegister.Status.ABIERTA).count() == 1


def test_cerrar_caja(client_cajero, open_cash_register):
    # El form exige closing_amount == actual_amount (valida diferencias).
    response = client_cajero.post(
        reverse("sales:cash_register_close"),
        {"closing_amount": "1000.00", "actual_amount": "1000.00"},
    )
    assert response.status_code == 302
    open_cash_register.refresh_from_db()
    assert open_cash_register.status == CashRegister.Status.CERRADA


# ---------------------------------------------------------------------------
# POS checkout
# ---------------------------------------------------------------------------

def test_pos_checkout_crea_venta_y_descuenta_stock(client_cajero, product, open_cash_register):
    stock_inicial = product.stock_current
    # Formato canónico del POS final: arrays product_id[] / quantity[].
    response = client_cajero.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id)],
            "quantity": ["2"],
            "payment_method": "efectivo",
            "cash_received": "400.00",
        },
    )
    assert response.status_code == 302
    assert Sale.objects.count() == 1
    product.refresh_from_db()
    assert product.stock_current == stock_inicial - Decimal("2")


def test_pos_carrito_incompleto_rechazado(client_cajero, product, open_cash_register):
    """product_id[] y quantity[] desparejados → error (no crea venta)."""
    response = client_cajero.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id), str(product.id)],
            "quantity": ["1"],
            "payment_method": "efectivo",
            "cash_received": "200.00",
        },
    )
    assert response.status_code == 302  # redirect con mensaje de error
    assert Sale.objects.count() == 0


def test_sale_void_gerente_anula(client_gerente, product, cajero_user, open_cash_register):
    sale = Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_gerente.post(reverse("sales:sale_void", args=[sale.id]),
                                   {"reason": "error de cobro"})
    assert response.status_code == 302
    sale.refresh_from_db()
    assert sale.status == Sale.Status.ANULADA
    product.refresh_from_db()
    assert product.stock_current == Decimal("20")


def test_ticket_muestra_moneda_uyu(client_cajero, product, cajero_user, open_cash_register):
    """El ticket (sale_detail) muestra importes en UYU con el formato $U (no '$' crudo)."""
    sale = Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_cajero.get(reverse("sales:sale_detail", args=[sale.id]))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    # Precio del producto fixture: 150.00 → "$U 150,00"
    assert "$U 150,00" in content
    assert "USD" not in content


# ---------------------------------------------------------------------------
# Config global de ticket del POS (SaleConfig)
# ---------------------------------------------------------------------------

def _pos_payload(product, **extra):
    data = {
        "product_id": [str(product.id)],
        "quantity": ["1"],
        "payment_method": "efectivo",
        "cash_received": "200.00",
    }
    data.update(extra)
    return data


def test_pos_post_persiste_switch_encendido(client_cajero, product, open_cash_register):
    """POS POST con print_ticket → el config global queda True."""
    from sales.models import SaleConfig

    SaleConfig.get_solo().save()  # asegura fila
    response = client_cajero.post(
        reverse("sales:pos"), _pos_payload(product, print_ticket="on")
    )
    assert response.status_code == 302
    assert SaleConfig.get_solo().pos_print_ticket is True


def test_pos_post_persiste_switch_apagado(client_cajero, product, open_cash_register):
    """POS POST sin print_ticket → el config global queda False."""
    from sales.models import SaleConfig

    response = client_cajero.post(reverse("sales:pos"), _pos_payload(product))
    assert response.status_code == 302
    assert SaleConfig.get_solo().pos_print_ticket is False


def test_pos_post_con_print_redirects_ticket_auto(client_cajero, product, open_cash_register):
    """Con print_ticket → redirect a sale_detail?auto=1 (impresión automática)."""
    response = client_cajero.post(
        reverse("sales:pos"), _pos_payload(product, print_ticket="on")
    )
    assert response.status_code == 302
    assert response.url.endswith("?auto=1")
    assert reverse("sales:sale_detail", args=[Sale.objects.order_by("-pk").first().pk]) in response.url


def test_pos_post_sin_print_redirects_pos(client_cajero, product, open_cash_register):
    """Sin print_ticket → vuelta directa al POS (flujo rápido de barra)."""
    response = client_cajero.post(reverse("sales:pos"), _pos_payload(product))
    assert response.status_code == 302
    assert response.url == reverse("sales:pos")


def test_pos_get_refleja_config_persistido(client_cajero, product, open_cash_register):
    """El siguiente GET del POS refleja el valor persistido en el config."""
    from sales.models import SaleConfig

    SaleConfig.get_solo().save()
    response = client_cajero.post(reverse("sales:pos"), _pos_payload(product))
    assert response.status_code == 302
    assert SaleConfig.get_solo().pos_print_ticket is False

    response = client_cajero.get(reverse("sales:pos"))
    assert response.status_code == 200
    assert response.context["pos_print_ticket"] is False


@pytest.mark.parametrize("url_name", ["sale_config"])
def test_sale_config_gerente_200(client_gerente, url_name):
    assert client_gerente.get(reverse(f"sales:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["sale_config"])
def test_sale_config_admin_200(client_admin, url_name):
    assert client_admin.get(reverse(f"sales:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", ["sale_config"])
def test_sale_config_bartender_cajero_denegado(client_bartender, client_cajero, url_name):
    assert_access_denied(client_bartender.get(reverse(f"sales:{url_name}")))
    assert_access_denied(client_cajero.get(reverse(f"sales:{url_name}")))


def test_sale_config_post_actualiza_preferencia(client_gerente):
    """La vista de config persiste pos_print_ticket vía form."""
    from sales.models import SaleConfig

    SaleConfig.get_solo().save()
    response = client_gerente.post(
        reverse("sales:sale_config"), {"pos_print_ticket": "on"}
    )
    assert response.status_code == 302
    assert SaleConfig.get_solo().pos_print_ticket is True

    response = client_gerente.post(reverse("sales:sale_config"), {})
    assert response.status_code == 302
    assert SaleConfig.get_solo().pos_print_ticket is False


# ---------------------------------------------------------------------------
# Productos elaborados (recetas) en el POS
# ---------------------------------------------------------------------------

def test_pos_context_servings_para_elaborados(client_cajero, category):
    """El POS expone is_composed y servings (porciones según el ingrediente
    más limitante) para los productos elaborados."""
    from inventory.models import Product, RecipeItem

    ing1 = Product.objects.create(
        name="Ing Pos 1", category=category, sale_price=Decimal("10"),
        stock_current=Decimal("10"),
    )
    ing2 = Product.objects.create(
        name="Ing Pos 2", category=category, sale_price=Decimal("10"),
        stock_current=Decimal("3"),
    )
    comp = Product.objects.create(
        name="Elab Pos", category=category, sale_price=Decimal("50"), is_composed=True,
    )
    RecipeItem.objects.create(product=comp, ingredient=ing1, quantity=Decimal("2"))  # 10//2 = 5
    RecipeItem.objects.create(product=comp, ingredient=ing2, quantity=Decimal("1"))  # 3//1 = 3

    response = client_cajero.get(reverse("sales:pos"))
    assert response.status_code == 200
    servings = response.context["servings"]
    assert servings[comp.pk] == 3  # min(5, 3)
    comp_obj = next(p for p in response.context["products"] if p.pk == comp.pk)
    assert comp_obj.is_composed is True


def test_pos_excluye_materia_prima(client_cajero, category):
    """El POS no ofrece materia prima para vender directo."""
    from inventory.models import Product

    Product.objects.create(
        name="Vendible Pos", category=category, sale_price=Decimal("50"),
        stock_current=Decimal("10"), is_active=True,
    )
    Product.objects.create(
        name="Materia Pos", category=category, sale_price=Decimal("10"),
        stock_current=Decimal("50"), is_active=True, is_raw_material=True,
    )
    response = client_cajero.get(reverse("sales:pos"))
    assert response.status_code == 200
    names = [p.name for p in response.context["products"]]
    assert "Vendible Pos" in names
    assert "Materia Pos" not in names
