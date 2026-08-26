"""
reports — Reportes con agregaciones (QuerySet) y exportación CSV.

Todas las vistas de reporte exigen rol gerente/admin (core.mixins.role_required).
Las claves de contexto están alineadas con templates/reports/*.html.
"""
import csv
from datetime import datetime
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.mixins import role_required
from inventory.models import Product
from sales.models import Sale, SaleItem
from tables.models import Order, OrderItem

REPORT_ROLES = ("gerente", "admin")


def _date_range(request):
    """Rango de fechas desde query params start_date/end_date (default: hoy)."""
    today = timezone.localdate()
    start_raw = request.GET.get("start_date") or request.GET.get("date_from") or today.isoformat()
    end_raw = request.GET.get("end_date") or request.GET.get("date_to") or today.isoformat()
    try:
        start = datetime.strptime(start_raw, "%Y-%m-%d").date()
        end = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except ValueError:
        start = end = today
    if start > end:
        start, end = end, start
    return start, end


def safe_cell(value):
    """SEC-02: sanitiza una celda CSV contra inyección de fórmulas.

    Si el valor es str y arranca con =, +, -, @ o contiene tab/CR/LF,
    lo prefija con un apóstrofo para que Excel/Sheets lo trate como texto.
    """
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")) or any(ch in value for ch in ("\t", "\r", "\n")):
        return "'" + value
    return value


def _csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Ventas por período
# ---------------------------------------------------------------------------
@role_required(*REPORT_ROLES)
def sales_report(request):
    start, end = _date_range(request)
    sales = Sale.objects.filter(
        status=Sale.Status.COMPLETADA,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )
    total_amount = sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    total_sales = sales.count()
    average_ticket = total_amount / total_sales if total_sales else Decimal("0")

    # Ventas agrupadas por día.
    by_day = (
        sales.values("created_at__date")
        .annotate(count=Count("id"), total=Sum("total"))
        .order_by("created_at__date")
    )
    rows = []
    for row in by_day:
        count = row["count"]
        total = row["total"] or Decimal("0")
        rows.append(
            {
                "period": row["created_at__date"].strftime("%d/%m/%Y"),
                "count": count,
                "total": total,
                "average": total / count if count else Decimal("0"),
            }
        )

    by_payment = list(
        sales.values("payment_method")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("payment_method")
    )
    by_user = list(
        sales.values("user__username")
        .annotate(total=Sum("total"), count=Count("id"))
        .order_by("-total")
    )
    orders_by_table = list(
        OrderItem.objects.filter(
            order__status=Order.Status.PAGADA,
            order__closed_at__date__gte=start,
            order__closed_at__date__lte=end,
        )
        .values("order__table__number", "order__table__zone")
        .annotate(
            orders=Count("order", distinct=True),
            total=Sum(F("quantity") * F("unit_price")),
        )
        .order_by("order__table__zone", "order__table__number")
    )
    return render(
        request,
        "reports/sales_report.html",
        {
            "date_from": start,
            "date_to": end,
            "total_amount": total_amount,
            "total_sales": total_sales,
            "average_ticket": average_ticket,
            "rows": rows,
            "by_payment": by_payment,
            "by_user": by_user,
            "orders_by_table": orders_by_table,
        },
    )


@role_required(*REPORT_ROLES)
def sales_report_csv(request):
    start, end = _date_range(request)
    sales = Sale.objects.filter(
        status=Sale.Status.COMPLETADA,
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).select_related("user", "table", "customer").order_by("created_at")
    response = _csv_response(f"ventas_{start}_{end}.csv")
    writer = csv.writer(response)
    writer.writerow(
        ["Ticket", "Fecha", "Vendedor", "Mesa", "Cliente", "Método", "Subtotal", "Descuento", "Total", "Estado"]
    )
    for s in sales:
        writer.writerow(
            [
                safe_cell(s.ticket_number),
                s.created_at.strftime("%Y-%m-%d %H:%M"),
                safe_cell(s.user.username),
                safe_cell(str(s.table.number)) if s.table_id else "",
                safe_cell(s.customer.name) if s.customer_id else "",
                safe_cell(s.payment_method),
                s.subtotal,
                s.discount,
                s.total,
                safe_cell(s.status),
            ]
        )
    return response


# ---------------------------------------------------------------------------
# Productos más vendidos
# ---------------------------------------------------------------------------
@role_required(*REPORT_ROLES)
def products_report(request):
    start, end = _date_range(request)
    try:
        top = int(request.GET.get("limit") or request.GET.get("top") or 10)
    except ValueError:
        top = 10
    top = max(1, min(top, 100))
    items = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETADA,
        sale__created_at__date__gte=start,
        sale__created_at__date__lte=end,
    )
    totals = items.aggregate(
        total_quantity=Sum("quantity"),
        total_revenue=Sum("subtotal"),
    )
    rows = [
        {"product": r["product__name"], "quantity": r["qty"], "revenue": r["revenue"]}
        for r in items.values("product__name")
        .annotate(qty=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-qty")[:top]
    ]
    return render(
        request,
        "reports/products_report.html",
        {
            "date_from": start,
            "date_to": end,
            "top": top,
            "rows": rows,
            "total_quantity": totals["total_quantity"] or Decimal("0"),
            "total_revenue": totals["total_revenue"] or Decimal("0"),
        },
    )


@role_required(*REPORT_ROLES)
def products_report_csv(request):
    start, end = _date_range(request)
    rows = (
        SaleItem.objects.filter(
            sale__status=Sale.Status.COMPLETADA,
            sale__created_at__date__gte=start,
            sale__created_at__date__lte=end,
        )
        .values("product__name")
        .annotate(qty=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-qty")
    )
    response = _csv_response(f"productos_{start}_{end}.csv")
    writer = csv.writer(response)
    writer.writerow(["Producto", "Cantidad vendida", "Ingresos"])
    for r in rows:
        writer.writerow([safe_cell(r["product__name"]), r["qty"], r["revenue"]])
    return response


# ---------------------------------------------------------------------------
# Ganancia bruta por período
# ---------------------------------------------------------------------------
@role_required(*REPORT_ROLES)
def profit_report(request):
    start, end = _date_range(request)
    items = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETADA,
        sale__created_at__date__gte=start,
        sale__created_at__date__lte=end,
    )
    aggregated = list(
        items.values("product__name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum("subtotal"),
            cost=Sum(F("quantity") * F("product__purchase_price")),
            profit=Sum(F("subtotal") - F("quantity") * F("product__purchase_price")),
        )
        .order_by("-profit")
    )
    rows = [
        {
            "product": r["product__name"],
            "quantity": r["qty"],
            "revenue": r["revenue"],
            "cost": r["cost"],
            "profit": r["profit"],
        }
        for r in aggregated
    ]
    total_revenue = sum(r["revenue"] or 0 for r in rows)
    total_cost = sum(r["cost"] or 0 for r in rows)
    total_profit = total_revenue - total_cost
    return render(
        request,
        "reports/profit_report.html",
        {
            "date_from": start,
            "date_to": end,
            "rows": rows,
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "total_profit": total_profit,
        },
    )


@role_required(*REPORT_ROLES)
def profit_report_csv(request):
    start, end = _date_range(request)
    rows = (
        SaleItem.objects.filter(
            sale__status=Sale.Status.COMPLETADA,
            sale__created_at__date__gte=start,
            sale__created_at__date__lte=end,
        )
        .values("product__name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum("subtotal"),
            cost=Sum(F("quantity") * F("product__purchase_price")),
            profit=Sum(F("subtotal") - F("quantity") * F("product__purchase_price")),
        )
        .order_by("-profit")
    )
    response = _csv_response(f"ganancia_{start}_{end}.csv")
    writer = csv.writer(response)
    writer.writerow(["Producto", "Cantidad", "Ingresos", "Costo", "Ganancia bruta"])
    for r in rows:
        writer.writerow(
            [safe_cell(r["product__name"]), r["qty"], r["revenue"], r["cost"], r["profit"]]
        )
    return response


# ---------------------------------------------------------------------------
# Valor del inventario
# ---------------------------------------------------------------------------
@role_required(*REPORT_ROLES)
def inventory_value_report(request):
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .annotate(value=F("stock_current") * F("purchase_price"))
        .order_by("-value")
    )
    rows = [
        {
            "category": p.category.name,
            "product": p.name,
            "stock": p.stock_current,
            "unit_cost": p.purchase_price,
            "value": p.value,
        }
        for p in products
    ]
    by_category = list(
        Product.objects.filter(is_active=True)
        .values("category__name")
        .annotate(value=Sum(F("stock_current") * F("purchase_price")))
        .order_by("-value")
    )
    total_value = sum(r["value"] or 0 for r in by_category)
    product_count = Product.objects.filter(is_active=True).count()
    return render(
        request,
        "reports/inventory_value_report.html",
        {
            "rows": rows,
            "by_category": by_category,
            "total_value": total_value,
            "product_count": product_count,
        },
    )


@role_required(*REPORT_ROLES)
def inventory_value_report_csv(request):
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .annotate(value=F("stock_current") * F("purchase_price"))
        .order_by("-value")
    )
    response = _csv_response("valor_inventario.csv")
    writer = csv.writer(response)
    writer.writerow(["Producto", "Categoría", "Stock", "Costo unitario", "Valor"])
    for p in products:
        writer.writerow(
            [
                safe_cell(p.name),
                safe_cell(p.category.name),
                p.stock_current,
                p.purchase_price,
                p.value,
            ]
        )
    return response
