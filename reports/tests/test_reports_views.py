"""
reports — Tests de VISTAS (se saltan hasta que el backend implemente las
URLs/vistas de reports).

Reglas del contrato (CONTRACT.md):
- Reportes: ventas por período, productos más vendidos, ganancia bruta, valor
  de inventario (+ variantes _csv).
- Solo Gerente/Admin acceden (bartender/cajero denegados).
- Export CSV: Content-Type text/csv y celdas SIN inyección de fórmulas
  (las que empiezan con = + - @ deben estar escapadas).
"""
import pytest
from django.urls import NoReverseMatch, reverse

try:
    from inventory.models import Product
    reverse("reports:sales_report")
    reverse("reports:products_report_csv")
except (ImportError, NoReverseMatch):
    pytest.skip("Vistas de reports no implementadas aún", allow_module_level=True)

from conftest import assert_access_denied  # noqa: E402

pytestmark = pytest.mark.django_db

REPORT_URLS = ["sales_report", "products_report", "profit_report", "inventory_value_report"]
CSV_URLS = [f"{name}_csv" for name in REPORT_URLS]


# ---------------------------------------------------------------------------
# Acceso por rol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_name", REPORT_URLS)
def test_reporte_gerente_200(client_gerente, url_name):
    assert client_gerente.get(reverse(f"reports:{url_name}")).status_code == 200


def test_reporte_ventas_muestra_moneda_uyu(client_gerente, product, cajero_user, open_cash_register):
    """Los totales del reporte de ventas se muestran en UYU ($U), no en '$' crudo."""
    from decimal import Decimal

    from sales.models import Sale

    Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_gerente.get(reverse("reports:sales_report"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "$U" in content
    assert "USD" not in content


# ---------------------------------------------------------------------------
# Fase 2: series para gráficos (Chart.js) en el contexto
# ---------------------------------------------------------------------------

def test_sales_report_context_chart_keys(client_gerente, product, cajero_user, open_cash_register):
    from decimal import Decimal

    from sales.models import Sale

    Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_gerente.get(reverse("reports:sales_report"))
    assert response.status_code == 200
    ctx = response.context
    assert "chart_labels" in ctx
    assert "chart_data" in ctx
    assert "chart_payment_labels" in ctx
    assert len(ctx["chart_labels"]) == len(ctx["chart_data"])
    assert isinstance(ctx["chart_labels"], list)


def test_products_report_context_chart_keys(client_gerente, product, cajero_user, open_cash_register):
    from decimal import Decimal

    from sales.models import Sale

    Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_gerente.get(reverse("reports:products_report"))
    assert response.status_code == 200
    ctx = response.context
    assert "chart_labels" in ctx
    assert "chart_data" in ctx
    assert len(ctx["chart_labels"]) == len(ctx["chart_data"])
    assert isinstance(ctx["chart_labels"], list)


def test_profit_report_context_chart_keys(client_gerente, product, cajero_user, open_cash_register):
    from decimal import Decimal

    from sales.models import Sale

    Sale.complete_sale(
        user=cajero_user,
        items=[(product, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("200"),
    )
    response = client_gerente.get(reverse("reports:profit_report"))
    assert response.status_code == 200
    ctx = response.context
    assert "chart_labels" in ctx
    assert "chart_data" in ctx
    assert len(ctx["chart_labels"]) == len(ctx["chart_data"])
    assert isinstance(ctx["chart_labels"], list)


def test_inventory_value_report_context(client_gerente, product):
    """El reporte de valor de inventario expone filas/total (sin series de gráfico)."""
    response = client_gerente.get(reverse("reports:inventory_value_report"))
    assert response.status_code == 200
    ctx = response.context
    for key in ("rows", "by_category", "total_value", "product_count"):
        assert key in ctx
    assert ctx["product_count"] == 1


@pytest.mark.parametrize("url_name", REPORT_URLS)
def test_reporte_admin_200(client_admin, url_name):
    assert client_admin.get(reverse(f"reports:{url_name}")).status_code == 200


@pytest.mark.parametrize("url_name", REPORT_URLS)
def test_reporte_bartender_denegado(client_bartender, url_name):
    assert_access_denied(client_bartender.get(reverse(f"reports:{url_name}")))


@pytest.mark.parametrize("url_name", REPORT_URLS)
def test_reporte_cajero_denegado(client_cajero, url_name):
    assert_access_denied(client_cajero.get(reverse(f"reports:{url_name}")))


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_name", CSV_URLS)
def test_reporte_csv_content_type(client_gerente, url_name):
    response = client_gerente.get(reverse(f"reports:{url_name}"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


def test_csv_sin_inyeccion_de_formulas(client_gerente, category, cajero_user, open_cash_register):
    """Un producto con nombre malicioso vendido debe aparecer ESCAPADO en el CSV.

    Los reportes de productos listan solo lo vendido, por eso se crea una
    venta con el producto malicioso antes de exportar.
    """
    from decimal import Decimal

    from sales.models import Sale

    malicioso = Product.objects.create(
        name="=SUM(A1:A2)", category=category, sale_price=Decimal("10.00"),
        stock_current=Decimal("100"),
    )
    Sale.complete_sale(
        user=cajero_user,
        items=[(malicioso, Decimal("1"))],
        cash_register=open_cash_register,
        cash_received=Decimal("20.00"),
    )
    response = client_gerente.get(reverse("reports:products_report_csv"))
    content = response.content.decode("utf-8")
    assert "SUM(A1:A2)" in content
    for linea in content.splitlines():
        if "SUM(A1:A2)" in linea:
            # la celda debe estar escapada (prefijo ' o espacio)
            assert linea.lstrip().startswith("'"), f"Fórmula no escapada en CSV: {linea}"


def test_profit_report_usa_recipe_cost(client_gerente, category, cajero_user, open_cash_register):
    """El costo de un elaborado en ganancia = recipe_cost (NO purchase_price)."""
    from decimal import Decimal

    from inventory.models import Product, RecipeItem
    from sales.models import Sale

    ing1 = Product.objects.create(
        name="RIng1", category=category, sale_price=Decimal("10"),
        purchase_price=Decimal("4"), stock_current=Decimal("100"),
    )
    ing2 = Product.objects.create(
        name="RIng2", category=category, sale_price=Decimal("10"),
        purchase_price=Decimal("6"), stock_current=Decimal("100"),
    )
    comp = Product.objects.create(
        name="RPizza", category=category, sale_price=Decimal("100"),
        purchase_price=Decimal("999"), stock_current=Decimal("0"), is_composed=True,
    )
    RecipeItem.objects.create(product=comp, ingredient=ing1, quantity=Decimal("2"))
    RecipeItem.objects.create(product=comp, ingredient=ing2, quantity=Decimal("1"))
    assert comp.recipe_cost == Decimal("14")  # 2×4 + 1×6

    Sale.complete_sale(
        user=cajero_user, items=[(comp, Decimal("1"))],
        cash_register=open_cash_register, cash_received=Decimal("200"),
    )
    response = client_gerente.get(reverse("reports:profit_report"))
    assert response.status_code == 200
    rows = response.context["rows"]
    row = next(r for r in rows if r["product"] == "RPizza")
    assert row["cost"] == Decimal("14")
    assert row["profit"] == Decimal("100") - Decimal("14")
