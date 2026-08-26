"""
core — Dashboard con KPIs reales según CONTRACT.md.

KPIs: ventas de hoy, tickets de hoy, mesas ocupadas, stock bajo,
reservas de hoy + top productos del día.
"""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.shortcuts import render
from django.utils import timezone

from inventory.models import Product
from reservations.models import Reservation
from sales.models import Sale, SaleItem
from tables.models import Order, Table


@login_required
def dashboard(request):
    today = timezone.localdate()
    sales_today = Sale.objects.filter(created_at__date=today, status=Sale.Status.COMPLETADA)
    tickets_today = sales_today.count()
    today_sales = sales_today.aggregate(total=Sum("total"))["total"] or Decimal("0")
    occupied_tables = Table.objects.filter(status=Table.Status.OCUPADA).count()
    low_stock_count = Product.objects.filter(is_active=True, stock_current__lte=F("stock_min")).count()
    today_reservations = Reservation.objects.filter(
        date=today, status__in=[Reservation.Status.PENDIENTE, Reservation.Status.CONFIRMADA]
    ).count()
    open_orders_count = Order.objects.filter(status=Order.Status.ABIERTA).count()
    top_products = list(
        SaleItem.objects.filter(
            sale__status=Sale.Status.COMPLETADA, sale__created_at__date=today
        )
        .values("product__name")
        .annotate(quantity=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-quantity")[:5]
    )

    context = {
        "today": today,
        # Claves usadas por templates/dashboard.html
        "today_sales": today_sales,
        "today_tickets": tickets_today,
        "occupied_tables": occupied_tables,
        "low_stock_count": low_stock_count,
        "today_reservations": today_reservations,
        "open_orders_count": open_orders_count,
        "top_products": top_products,
        # Alias de compatibilidad
        "tickets_today": tickets_today,
        "sales_today_total": today_sales,
        "tables_occupied": occupied_tables,
        "reservations_today": today_reservations,
    }
    return render(request, "dashboard.html", context)
