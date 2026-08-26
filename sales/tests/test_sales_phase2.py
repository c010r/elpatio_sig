"""
sales — Tests FASE 2 (CONTRACT-PHASE2.md): happy hour, promos, propinas,
descuentos manuales y arqueo de caja.

- Happy hour: effective_price() aplica descuento dentro de la franja (incl.
  franja nocturna start>end); NO se acumula con promo; el precio se congela
  al agregar el ítem; banner en contexto del POS.
- Promo: promo_price cuando promo_active; la venta lo usa como precio.
- Propina: total = subtotal - discount + tip; el ticket la muestra; el POS la
  acepta.
- Descuento: tope max_discount_percent (50) server-side; negativos o > subtotal
  rechazados.
- Arqueo: expected_by_method() excluye anuladas; cierre con diferencia sin
  confirmación → error; con confirmación → OK; closing_amount = suma contado.
"""
from datetime import time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse

try:
    from sales.models import (
        CashRegister, HappyHourConfig, Sale, effective_price,
    )
    reverse("sales:pos")
except (ImportError, NoReverseMatch):
    pytest.skip("Fase 2 de sales no implementada aún", allow_module_level=True)

from tables.forms import OrderItemForm  # noqa: E402
from tables.models import Order  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpiar_cache_config():
    """HappyHourConfig y LoyaltyConfig cachean en LocMemCache (no transaccional)."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _habilitar_happy_hour(start="00:00", end="23:59", percent="15", enabled=True):
    cfg = HappyHourConfig.get_solo()
    cfg.enabled = enabled
    cfg.start_time = time.fromisoformat(start)
    cfg.end_time = time.fromisoformat(end)
    cfg.discount_percent = Decimal(percent)
    cfg.save()
    return cfg


# ---------------------------------------------------------------------------
# Happy hour: effective_price()
# ---------------------------------------------------------------------------

def test_hh_deshabilitado_precio_regular(product):
    _habilitar_happy_hour(enabled=False)
    assert effective_price(product, time(19, 0)) == Decimal("150.00")


def test_hh_dentro_franja_aplica_descuento(product):
    _habilitar_happy_hour(start="18:00", end="21:00", percent="15")
    assert effective_price(product, time(19, 0)) == Decimal("127.50")  # 150 - 15%


def test_hh_fuera_franja_precio_regular(product):
    _habilitar_happy_hour(start="18:00", end="21:00", percent="15")
    assert effective_price(product, time(12, 0)) == Decimal("150.00")


def test_hh_franja_nocturna_start_mayor_end(product):
    _habilitar_happy_hour(start="22:00", end="02:00", percent="10")
    assert effective_price(product, time(23, 0)) == Decimal("135.00")
    assert effective_price(product, time(1, 0)) == Decimal("135.00")
    assert effective_price(product, time(12, 0)) == Decimal("150.00")


def test_hh_no_acumula_con_promo(product):
    product.promo_active = True
    product.promo_price = Decimal("100.00")
    product.save(update_fields=["promo_active", "promo_price"])
    _habilitar_happy_hour(start="18:00", end="21:00", percent="15")
    assert effective_price(product, time(19, 0)) == Decimal("100.00")


# ---------------------------------------------------------------------------
# Precio congelado al agregar el ítem
# ---------------------------------------------------------------------------

def test_precio_congelado_venta_durante_happy_hour(product, cajero_user, open_cash_register):
    _habilitar_happy_hour(percent="15")
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    item = sale.items.get()
    assert item.unit_price == Decimal("127.50")
    assert sale.total == Decimal("127.50")


def test_precio_congelado_al_agregar_item_comanda(table, bartender_user, product):
    _habilitar_happy_hour(percent="15")
    order = Order.objects.create(table=table, waiter=bartender_user)
    form = OrderItemForm({"product": product.id, "quantity": "1"})
    assert form.is_valid(), form.errors
    item = form.save(commit=False)
    item.order = order
    item.save()
    assert item.unit_price == Decimal("127.50")
    # Se apaga el happy hour: el precio del ítem NO se recalcula.
    _habilitar_happy_hour(enabled=False)
    item.refresh_from_db()
    assert item.unit_price == Decimal("127.50")


# ---------------------------------------------------------------------------
# Banner de happy hour en el contexto del POS
# ---------------------------------------------------------------------------

def test_pos_context_happy_hour(client_cajero):
    _habilitar_happy_hour(enabled=False)
    response = client_cajero.get(reverse("sales:pos"))
    assert response.status_code == 200
    hh = response.context.get("happy_hour")
    assert hh is not None
    for key in ("enabled", "active", "name", "discount_percent", "end_time"):
        assert key in hh


def test_pos_banner_happy_hour_activo(client_cajero):
    _habilitar_happy_hour(percent="15")
    response = client_cajero.get(reverse("sales:pos"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Happy hour" in content


# ---------------------------------------------------------------------------
# Promo
# ---------------------------------------------------------------------------

def test_promo_precio_usado_en_venta(product, cajero_user, open_cash_register):
    product.promo_active = True
    product.promo_price = Decimal("100.00")
    product.save(update_fields=["promo_active", "promo_price"])
    _habilitar_happy_hour(percent="15")  # la promo NO se acumula con happy hour
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("2"))],
        cash_register=open_cash_register, cash_received=Decimal("250"),
    )
    item = sale.items.get()
    assert item.unit_price == Decimal("100.00")
    assert sale.total == Decimal("200.00")


def test_promo_inactiva_usa_precio_regular(product):
    product.promo_price = Decimal("100.00")  # promo_price cargado pero promo_active=False
    product.save(update_fields=["promo_price"])
    assert effective_price(product) == Decimal("150.00")


# ---------------------------------------------------------------------------
# Propina
# ---------------------------------------------------------------------------

def test_venta_con_propina_total(product, cajero_user, open_cash_register):
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"), tip=Decimal("20"),
    )
    assert sale.subtotal == Decimal("150.00")
    assert sale.tip == Decimal("20.00")
    assert sale.total == Decimal("170.00")  # subtotal - discount + tip


def test_venta_con_descuento_y_propina(product, cajero_user, open_cash_register):
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
        discount=Decimal("30"), tip=Decimal("15"),
    )
    assert sale.total == Decimal("135.00")  # 150 - 30 + 15


def test_propina_negativa_rechazada(product, cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        Sale.complete_sale(
            user=cajero_user, items=[(product, Decimal("1"))],
            cash_register=open_cash_register, cash_received=Decimal("200"), tip=Decimal("-5"),
        )


def test_ticket_muestra_propina(client_cajero, product, cajero_user, open_cash_register):
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"), tip=Decimal("20"),
    )
    response = client_cajero.get(reverse("sales:sale_detail", args=[sale.id]))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Propina" in content
    assert "$U 20,00" in content


def test_pos_post_con_propina(client_cajero, product, open_cash_register):
    response = client_cajero.post(
        reverse("sales:pos"),
        {
            "product_id": [str(product.id)],
            "quantity": ["1"],
            "payment_method": "efectivo",
            "cash_received": "200.00",
            "tip": "20.00",
        },
    )
    assert response.status_code == 302
    sale = Sale.objects.get()
    assert sale.tip == Decimal("20.00")
    assert sale.total == Decimal("170.00")


# ---------------------------------------------------------------------------
# Descuento manual: tope 50% (LoyaltyConfig.max_discount_percent)
# ---------------------------------------------------------------------------

def test_descuento_supera_tope_50_rechazado(product, cajero_user, open_cash_register):
    # subtotal 150 → tope 50% = 75; 80 excede el tope
    with pytest.raises(ValidationError):
        Sale.complete_sale(
            user=cajero_user, items=[(product, Decimal("1"))],
            cash_register=open_cash_register, cash_received=Decimal("200"), discount=Decimal("80"),
        )


def test_descuento_al_tope_ok(product, cajero_user, open_cash_register):
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"), discount=Decimal("75"),
    )
    assert sale.total == Decimal("75.00")


def test_descuento_mayor_subtotal_rechazado(product, cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        Sale.complete_sale(
            user=cajero_user, items=[(product, Decimal("1"))],
            cash_register=open_cash_register, cash_received=Decimal("200"), discount=Decimal("160"),
        )


def test_descuento_negativo_rechazado(product, cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        Sale.complete_sale(
            user=cajero_user, items=[(product, Decimal("1"))],
            cash_register=open_cash_register, cash_received=Decimal("200"), discount=Decimal("-10"),
        )


# ---------------------------------------------------------------------------
# Arqueo de caja (modelo)
# ---------------------------------------------------------------------------

def test_expected_by_method_por_metodo(open_cash_register, cajero_user, product):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, payment_method=Sale.PaymentMethod.TARJETA,
    )
    expected = open_cash_register.expected_by_method()
    assert expected["efectivo"] == Decimal("150.00")
    assert expected["tarjeta"] == Decimal("150.00")


def test_expected_by_method_excluye_anuladas(open_cash_register, cajero_user, product):
    sale = Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    sale.void(cajero_user, reason="prueba")
    assert open_cash_register.expected_by_method() == {}


def test_close_counted_suma_y_diferencia_cero(open_cash_register, cajero_user, product):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    reg = open_cash_register
    reg.close(
        counted_cash=Decimal("1150"), counted_card=Decimal("0"),
        counted_transfer=Decimal("0"), counted_other=Decimal("0"),
    )
    reg.refresh_from_db()
    assert reg.counted_cash == Decimal("1150.00")
    assert reg.closing_amount == Decimal("1150.00")  # suma de lo contado
    assert reg.actual_amount == Decimal("1150.00")
    assert reg.expected_amount == Decimal("1150.00")  # apertura 1000 + venta 150
    assert reg.difference == Decimal("0.00")


def test_close_diferencia_negativa(open_cash_register, cajero_user, product):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    reg = open_cash_register
    reg.close(counted_cash=Decimal("1000"))
    reg.refresh_from_db()
    assert reg.closing_amount == Decimal("1000.00")
    assert reg.difference == Decimal("-150.00")


def test_difference_none_sin_cierre(open_cash_register):
    assert open_cash_register.difference is None


# ---------------------------------------------------------------------------
# Arqueo de caja (vista + formulario)
# ---------------------------------------------------------------------------

def test_cierre_diferencia_sin_confirmacion_error(client_cajero, open_cash_register, product, cajero_user):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_cajero.post(
        reverse("sales:cash_register_close"), {"counted_cash": "1000.00"}
    )
    assert response.status_code == 200  # formulario re-renderizado con error
    open_cash_register.refresh_from_db()
    assert open_cash_register.status == CashRegister.Status.ABIERTA


def test_cierre_diferencia_con_confirmacion_ok(client_cajero, open_cash_register, product, cajero_user):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_cajero.post(
        reverse("sales:cash_register_close"),
        {"counted_cash": "1000.00", "confirmed": "on"},
    )
    assert response.status_code == 302
    open_cash_register.refresh_from_db()
    assert open_cash_register.status == CashRegister.Status.CERRADA
    assert open_cash_register.difference == Decimal("-150.00")


def test_cierre_cuadrado_ok(client_cajero, open_cash_register, product, cajero_user):
    Sale.complete_sale(
        user=cajero_user, items=[(product, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_cajero.post(
        reverse("sales:cash_register_close"), {"counted_cash": "1150.00"}
    )
    assert response.status_code == 302
    open_cash_register.refresh_from_db()
    assert open_cash_register.status == CashRegister.Status.CERRADA
    assert open_cash_register.difference == Decimal("0.00")
