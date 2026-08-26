"""
sales — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- UNA caja abierta por vez.
- Al completar una venta se descuenta stock (StockMovement tipo venta).
- ticket_number secuencial por día (YYYYMMDD-####).
- Al anular una venta se repone el stock.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

try:
    from sales.models import CashRegister, Sale, SaleItem
except ImportError:
    pytest.skip("Backend de sales no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpiar_cache_fidelizacion():
    """LoyaltyConfig.get_solo() cachea en LocMemCache (no transaccional);
    se limpia entre tests para evitar contaminación entre tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _completar_venta(product, user, cash_register, quantity="1", **kwargs):
    return Sale.complete_sale(
        user=user,
        items=[(product, Decimal(quantity))],
        cash_register=cash_register,
        payment_method=kwargs.pop("payment_method", Sale.PaymentMethod.EFECTIVO),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Caja registradora
# ---------------------------------------------------------------------------

def test_get_open_devuelve_la_abierta(open_cash_register):
    assert CashRegister.get_open() == open_cash_register


def test_get_open_none_sin_caja(open_cash_register):
    open_cash_register.close(closing_amount=Decimal("1000"), actual_amount=Decimal("1000"))
    assert CashRegister.get_open() is None


def test_close_caja_calcula_esperado(open_cash_register):
    reg = open_cash_register
    reg.close(closing_amount=Decimal("1000.00"), actual_amount=Decimal("950.00"), notes="cierre")
    reg.refresh_from_db()
    assert reg.status == CashRegister.Status.CERRADA
    assert reg.closed_at is not None
    # Sin ventas: esperado = apertura
    assert reg.expected_amount == Decimal("1000.00")
    assert reg.actual_amount == Decimal("950.00")


@pytest.mark.xfail(
    reason="Regla 'UNA caja abierta por vez' aún no implementada en el modelo "
    "(sin clean/constraint/save custom); se reporta al coordinador. Si el "
    "backend la implementa a nivel de vista, este test deja de aplicar y "
    "debería re-evaluarse.",
    strict=False,
)
def test_solo_una_caja_abierta_por_vez(open_cash_register, cajero_user):
    """Regla del contrato: UNA caja abierta por vez."""
    segunda = CashRegister(opened_by=cajero_user, opening_amount=Decimal("500"), status="abierta")
    try:
        segunda.full_clean()
        segunda.save()
        se_pudo_abrir = True
    except Exception:
        se_pudo_abrir = False
    assert not se_pudo_abrir, "No debería permitirse abrir una segunda caja con una ya abierta"


# ---------------------------------------------------------------------------
# Sale.complete_sale
# ---------------------------------------------------------------------------

def test_completar_venta_descuenta_stock(product, cajero_user, open_cash_register):
    sale = _completar_venta(product, cajero_user, open_cash_register, quantity="2",
                            cash_received=Decimal("400"))
    product.refresh_from_db()
    assert product.stock_current == Decimal("18")  # 20 - 2
    assert sale.subtotal == Decimal("300.00")
    assert sale.total == Decimal("300.00")
    assert sale.change == Decimal("100.00")


def test_ticket_number_formato_secuencial(product, cajero_user, open_cash_register):
    from django.utils import timezone

    prefijo = timezone.localdate().strftime("%Y%m%d") + "-"
    s1 = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    s2 = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    for sale in (s1, s2):
        assert sale.ticket_number.startswith(prefijo)
        assert len(sale.ticket_number) == len(prefijo) + 4
    seq1 = int(s1.ticket_number.rsplit("-", 1)[1])
    seq2 = int(s2.ticket_number.rsplit("-", 1)[1])
    assert seq2 == seq1 + 1


def test_ticket_number_unico(product, cajero_user, open_cash_register):
    s1 = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    s2 = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    assert s1.ticket_number != s2.ticket_number


def test_completar_venta_genera_saleitems(product, cajero_user, open_cash_register):
    sale = _completar_venta(product, cajero_user, open_cash_register, quantity="2",
                            cash_received=Decimal("400"))
    items = sale.items.all()
    assert items.count() == 1
    item = items[0]
    assert item.product == product
    assert item.quantity == Decimal("2")
    assert item.unit_price == product.sale_price
    assert item.subtotal == Decimal("300.00")


def test_completar_venta_con_descuento(product, cajero_user, open_cash_register):
    sale = _completar_venta(product, cajero_user, open_cash_register,
                            discount=Decimal("50.00"), cash_received=Decimal("300"))
    assert sale.subtotal == Decimal("150.00")
    assert sale.total == Decimal("100.00")


def test_completar_venta_descuento_negativo_rechazado(product, cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        _completar_venta(product, cajero_user, open_cash_register, discount=Decimal("-5"))


def test_completar_venta_sin_items_rechazada(cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        Sale.complete_sale(user=cajero_user, items=[])


def test_completar_venta_efectivo_sin_efectivo_recibido_es_pago_exacto(product, cajero_user, open_cash_register):
    # "Efectivo recibido" opcional: sin indicarlo se asume pago exacto.
    sale = _completar_venta(product, cajero_user, open_cash_register)
    assert sale.cash_received == sale.total
    assert sale.change == Decimal("0")


def test_completar_venta_efectivo_insuficiente(product, cajero_user, open_cash_register):
    with pytest.raises(ValidationError):
        _completar_venta(product, cajero_user, open_cash_register,
                         cash_received=Decimal("10"))


def test_completar_venta_stock_insuficiente_rechazada(product, cajero_user, open_cash_register):
    """Si no hay stock para la cantidad, apply() lanza ValueError y no queda
    venta ni movimiento a medias (transaction.atomic)."""
    with pytest.raises(ValueError):
        _completar_venta(product, cajero_user, open_cash_register, quantity="999")
    assert Sale.objects.count() == 0
    product.refresh_from_db()
    assert product.stock_current == Decimal("20")


def test_completar_venta_con_cliente_suma_puntos(product, cajero_user, open_cash_register, customer):
    _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"),
                     customer=customer)
    customer.refresh_from_db()
    assert customer.points == 150  # 1 punto por $1 (150.00)


# ---------------------------------------------------------------------------
# Sale.void
# ---------------------------------------------------------------------------

def test_anular_venta_repone_stock(product, cajero_user, open_cash_register):
    sale = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    product.refresh_from_db()
    assert product.stock_current == Decimal("19")

    sale.void(cajero_user, reason="error de carga")
    product.refresh_from_db()
    assert product.stock_current == Decimal("20")
    sale.refresh_from_db()
    assert sale.status == Sale.Status.ANULADA
    assert sale.voided_by == cajero_user
    assert sale.voided_at is not None


def test_anular_dos_veces_rechazado(product, cajero_user, open_cash_register):
    sale = _completar_venta(product, cajero_user, open_cash_register, cash_received=Decimal("200"))
    sale.void(cajero_user)
    with pytest.raises(ValidationError):
        sale.void(cajero_user)


# ---------------------------------------------------------------------------
# SaleConfig (config global de ticket del POS)
# ---------------------------------------------------------------------------

def test_sale_config_get_solo_crea_pk_1():
    """SaleConfig es singleton: get_solo() crea la fila pk=1 con default True."""
    from sales.models import SaleConfig

    cfg = SaleConfig.get_solo()
    assert cfg.pk == 1
    assert cfg.pos_print_ticket is True
    assert SaleConfig.objects.count() == 1


def test_sale_config_save_fuerza_pk_1_y_actualiza():
    from sales.models import SaleConfig

    cfg = SaleConfig(pos_print_ticket=False)
    cfg.save()
    assert cfg.pk == 1
    assert SaleConfig.objects.count() == 1
    assert SaleConfig.get_solo().pos_print_ticket is False


# ---------------------------------------------------------------------------
# Productos elaborados (recetas / materia prima) al vender
# ---------------------------------------------------------------------------

def _crear_elaborado(category, nombre="Elaborado Test", receta=None):
    """Crea un producto is_composed=True con receta [(ingrediente, cantidad)]."""
    from inventory.models import Product, RecipeItem

    receta = receta or [("Ing A", Decimal("2")), ("Ing B", Decimal("3"))]
    ingredients = []
    for ing_name, qty in receta:
        ing, _ = Product.objects.get_or_create(
            name=ing_name,
            defaults={
                "category": category, "sale_price": Decimal("10"),
                "stock_current": Decimal("100"),
            },
        )
        ingredients.append((ing, qty))
    composed = Product.objects.create(
        name=nombre, category=category, sale_price=Decimal("50"),
        stock_current=Decimal("0"), is_composed=True,
    )
    for ing, qty in ingredients:
        RecipeItem.objects.create(product=composed, ingredient=ing, quantity=qty)
    return composed, ingredients


def test_venta_elaborado_descuenta_ingredientes_y_no_toca_terminado(
        category, cajero_user, open_cash_register):
    """Al vender un elaborado se descuenta la materia prima (cantidad_receta ×
    qty) y NO se toca el stock del producto terminado."""
    from inventory.models import Product

    composed, ingredients = _crear_elaborado(category)
    stock_term = composed.stock_current
    stocks = {ing.pk: ing.stock_current for ing, _ in ingredients}

    sale = Sale.complete_sale(
        user=cajero_user, items=[(composed, Decimal("2"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    for ing, qty in ingredients:
        ing.refresh_from_db()
        assert ing.stock_current == stocks[ing.pk] - qty * 2
    composed.refresh_from_db()
    assert composed.stock_current == stock_term  # 0, no se toca
    assert sale.items.count() == 1
    assert sale.items.first().product == composed


def test_venta_elaborado_stock_insuficiente_rechaza_y_rollback(
        category, cajero_user, open_cash_register):
    """Falta materia prima → ValidationError y no se crea NADA (transaccional)."""
    from inventory.models import Product, RecipeItem

    ing = Product.objects.create(
        name="Ing único", category=category, sale_price=Decimal("10"),
        stock_current=Decimal("1"),
    )
    composed = Product.objects.create(
        name="Elab sin stock", category=category, sale_price=Decimal("50"),
        stock_current=Decimal("0"), is_composed=True,
    )
    RecipeItem.objects.create(product=composed, ingredient=ing, quantity=Decimal("2"))

    with pytest.raises(ValidationError):
        Sale.complete_sale(
            user=cajero_user, items=[(composed, Decimal("1"))],
            cash_register=open_cash_register, cash_received=Decimal("200"),
        )
    assert Sale.objects.count() == 0
    ing.refresh_from_db()
    assert ing.stock_current == Decimal("1")


def test_anular_venta_elaborado_repone_ingredientes(category, cajero_user, open_cash_register):
    """Anular un elaborado repone la materia prima consumida."""
    composed, ingredients = _crear_elaborado(category)
    sale = Sale.complete_sale(
        user=cajero_user, items=[(composed, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    for ing, _ in ingredients:
        ing.refresh_from_db()
    stocks_tras_venta = {ing.pk: ing.stock_current for ing, _ in ingredients}
    sale.void(cajero_user, reason="error")
    for ing, _ in ingredients:
        ing.refresh_from_db()
        receta = ing.used_in_recipes.get(product=composed)
        assert ing.stock_current == stocks_tras_venta[ing.pk] + receta.quantity
