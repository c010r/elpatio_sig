"""
core — Tests del filter de template `money` (moneda del pub: Peso Uruguayo UYU).

Formato del contrato: "$U 1.234,56" (millares con punto, decimales con coma,
símbolo "$U" con espacio). El filter vive en core/templatetags/money.py.
"""
from decimal import Decimal

import pytest

try:
    from core.templatetags.money import money
except ImportError:
    pytest.skip("Filter money (core/templatetags/money.py) no implementado aún",
                allow_module_level=True)


def test_formato_basico():
    assert money(Decimal("1234.56")) == "$U 1.234,56"


def test_formato_sin_millares():
    assert money(Decimal("150.00")) == "$U 150,00"


def test_formato_centavos_redondeo():
    assert money(Decimal("1.999")) == "$U 2,00"
    assert money(Decimal("1.234")) == "$U 1,23"


def test_formato_cero():
    assert money(Decimal("0")) == "$U 0,00"


def test_formato_negativo():
    assert money(Decimal("-1234.56")) == "$U -1.234,56"


def test_formato_float():
    assert money(1234.56) == "$U 1.234,56"


def test_formato_none_e_invalido():
    assert money(None) == "$U 0,00"
    assert money("") == "$U 0,00"
    assert money("no-es-un-numero") == "$U 0,00"
