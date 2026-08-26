"""
customers — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- 1 punto por cada $1 gastado (redondeo a entero).
- LoyaltyConfig singleton: points_per_currency=1, points_required_for_discount=100,
  discount_amount=10 (defaults, con caché).
"""
from decimal import Decimal

import pytest

try:
    from customers.models import Customer, LoyaltyConfig
except ImportError:
    pytest.skip("Backend de customers no implementado aún", allow_module_level=True)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpiar_cache_fidelizacion():
    """LoyaltyConfig.get_solo() cachea en LocMemCache (no transaccional);
    se limpia entre tests para evitar contaminación entre tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Puntos de fidelización
# ---------------------------------------------------------------------------

def test_earn_points_1_por_1(customer):
    customer.earn_points(Decimal("150.00"))
    customer.refresh_from_db()
    assert customer.points == 150


def test_earn_points_redondea_a_entero(customer):
    customer.earn_points(Decimal("100.50"))
    customer.refresh_from_db()
    assert customer.points == 100  # int(total // 1)


def test_earn_points_menos_de_1_no_acumula(customer):
    customer.earn_points(Decimal("0.90"))
    customer.refresh_from_db()
    assert customer.points == 0


def test_earn_points_acumula(customer):
    customer.earn_points(Decimal("120.00"))
    customer.earn_points(Decimal("30.00"))
    customer.refresh_from_db()
    assert customer.points == 150


# ---------------------------------------------------------------------------
# LoyaltyConfig singleton
# ---------------------------------------------------------------------------

def test_loyalty_config_singleton_misma_fila():
    a = LoyaltyConfig.get_solo()
    b = LoyaltyConfig.get_solo()
    assert a.pk == b.pk == 1
    assert LoyaltyConfig.objects.count() == 1


def test_loyalty_config_defaults_contrato():
    cfg = LoyaltyConfig.get_solo()
    assert cfg.points_per_currency == Decimal("1")
    assert cfg.points_required_for_discount == 100
    assert cfg.discount_amount == Decimal("10")


def test_loyalty_config_save_fuerza_pk_1():
    cfg = LoyaltyConfig(points_per_currency=Decimal("2"))
    cfg.save()
    assert cfg.pk == 1
    assert LoyaltyConfig.objects.count() == 1


def test_earn_points_con_config_personalizada(customer):
    cfg = LoyaltyConfig.get_solo()
    cfg.points_per_currency = Decimal("2")
    cfg.save()
    customer.earn_points(Decimal("150.00"))
    customer.refresh_from_db()
    assert customer.points == 75  # 150 // 2
