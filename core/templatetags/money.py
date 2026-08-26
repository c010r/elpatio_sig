"""
core.templatetags.money — Filtro de template para moneda (Peso Uruguayo, UYU).

Formato: "$U 1.234,56" (millares con punto, decimales con coma, símbolo "$U" con espacio).
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()

CURRENCY_SYMBOL = "$U"


@register.filter
def money(value):
    """Formatea un Decimal/float como "$U 1.234,56". None o inválido → "$U 0,00"."""
    if value is None or value == "":
        value = Decimal("0")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{amount:,.2f}"
    # "1,234.56" -> "1.234,56"
    s = s.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")
    return f"{CURRENCY_SYMBOL} {s}"
