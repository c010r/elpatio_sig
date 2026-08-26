"""
inventory — Tests FASE 2 (CONTRACT-PHASE2.md): promos en el formulario de
productos.

- promo_active=True sin promo_price → error de validación.
- promo_price debe ser > 0.
"""
import pytest

try:
    from inventory.forms import ProductForm
except ImportError:
    pytest.skip("Fase 2 de inventory no implementada aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


def _data(category, **overrides):
    data = {
        "name": "Producto con promo",
        "category": category.id,
        "unit": "unidad",
        "purchase_price": "80.00",
        "sale_price": "150.00",
        "stock_current": "10",
        "stock_min": "2",
    }
    data.update(overrides)
    return data


def test_promo_active_sin_precio_invalido(category):
    form = ProductForm(data=_data(category, promo_active="on"))
    assert not form.is_valid()
    assert "promo_price" in form.errors


def test_promo_active_con_precio_valido(category):
    form = ProductForm(data=_data(category, promo_active="on", promo_price="100.00"))
    assert form.is_valid(), form.errors


def test_promo_precio_cero_o_negativo_invalido(category):
    form = ProductForm(data=_data(category, promo_active="on", promo_price="0"))
    assert not form.is_valid()
    assert "promo_price" in form.errors
    form = ProductForm(data=_data(category, promo_active="on", promo_price="-5"))
    assert not form.is_valid()
    assert "promo_price" in form.errors


def test_promo_inactiva_sin_precio_ok(category):
    form = ProductForm(data=_data(category))
    assert form.is_valid(), form.errors
