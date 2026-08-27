"""
core — Context processors globales.
Inyectan datos disponibles en TODOS los templates (navbar, sidebar, etc.).
"""
from django.db.models import F
from django.utils import timezone


def global_context(request):
    """Datos globales para todos los templates."""
    ctx = {}

    # Caja abierta actual (para mostrar estado en la navbar)
    if request.user.is_authenticated:
        try:
            from sales.models import CashRegister

            ctx["open_cash_register"] = (
                CashRegister.objects.filter(status="abierta").order_by("-opened_at").first()
            )
        except Exception:
            ctx["open_cash_register"] = None

        # Stock bajo (contador para el sidebar): productos simples por debajo
        # del mínimo + elaborados cuya materia prima está baja. Coincide con
        # StockLowView (que lista ambos).
        try:
            from inventory.models import Product, composed_products_with_low_ingredients

            ctx["low_stock_count"] = (
                Product.objects.filter(
                    is_active=True, is_composed=False, stock_current__lte=F("stock_min")
                ).count()
                + len(composed_products_with_low_ingredients())
            )
        except Exception:
            ctx["low_stock_count"] = 0

        ctx["today"] = timezone.localdate()
    return ctx
