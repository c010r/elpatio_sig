"""
tables — Vistas de mapa de mesas, comandas y cierre de comanda.
"""
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from core.mixins import RoleRequiredMixin
from sales.models import CashRegister

from .forms import OrderCloseForm, OrderForm, OrderItemForm, TableForm
from .models import Order, OrderItem, Table

TABLES_ROLES = ["bartender", "cajero", "gerente", "admin"]


class TableMapView(RoleRequiredMixin, View):
    """Mapa de mesas agrupadas por zona con estados."""

    roles = TABLES_ROLES

    def get(self, request):
        tables = Table.objects.filter(is_active=True).order_by("zone", "number")
        zones = {}
        for table in tables:
            zones.setdefault(table.zone, []).append(table)
        open_orders = {
            o.table_id: o
            for o in Order.objects.filter(status=Order.Status.ABIERTA).select_related("table")
        }
        return render(
            request,
            "tables/table_map.html",
            {
                "object_list": tables,
                "tables": tables,
                "zones": zones,
                "open_orders": open_orders,
            },
        )


class TableCreateView(RoleRequiredMixin, CreateView):
    model = Table
    form_class = TableForm
    template_name = "tables/table_form.html"
    success_url = reverse_lazy("tables:table_map")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Mesa creada.")
        return super().form_valid(form)


class TableUpdateView(RoleRequiredMixin, UpdateView):
    model = Table
    form_class = TableForm
    template_name = "tables/table_form.html"
    success_url = reverse_lazy("tables:table_map")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Mesa actualizada.")
        return super().form_valid(form)


class TableDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva la mesa (solo POST)."""

    model = Table
    success_url = reverse_lazy("tables:table_map")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, f"Mesa {self.object.number} desactivada.")
        return HttpResponseRedirect(self.get_success_url())


class OrderDetailView(RoleRequiredMixin, View):
    """Comanda con ítems, formulario para agregar y formulario de cierre."""

    roles = TABLES_ROLES

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("table", "waiter").prefetch_related("items__product"),
            pk=pk,
        )
        return render(
            request,
            "tables/order_detail.html",
            {
                "object": order,
                "order": order,
                "items": order.items.all(),
                "item_form": OrderItemForm(),
                "close_form": OrderCloseForm(),
                "total": order.total,
            },
        )


class OrderCreateView(RoleRequiredMixin, CreateView):
    """Abre una mesa: crea la comanda y marca la mesa como ocupada."""

    form_class = OrderForm
    template_name = "tables/order_form.html"
    roles = TABLES_ROLES

    def get_initial(self):
        table_pk = self.kwargs.get("table_pk")
        return {"table": table_pk} if table_pk else {}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        table_pk = self.kwargs.get("table_pk")
        ctx["table"] = Table.objects.filter(pk=table_pk).first() if table_pk else None
        return ctx

    def get_success_url(self):
        return reverse("tables:order_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        form.instance.waiter = self.request.user
        table = form.cleaned_data["table"]
        table.status = Table.Status.OCUPADA
        table.save(update_fields=["status"])
        messages.success(self.request, f"Comanda abierta en la mesa {table.number}.")
        return super().form_valid(form)


class OrderAddItemView(RoleRequiredMixin, View):
    """Agrega un ítem a una comanda abierta."""

    roles = TABLES_ROLES

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        return render(
            request,
            "tables/order_form.html",
            {"object": order, "order": order, "form": OrderItemForm()},
        )

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, status=Order.Status.ABIERTA)
        form = OrderItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.order = order
            item.save()
            messages.success(request, "Ítem agregado a la comanda.")
        else:
            messages.error(request, "No se pudo agregar el ítem.")
        return redirect("tables:order_detail", pk=order.pk)


class OrderItemStatusView(RoleRequiredMixin, View):
    """Marca un ítem como entregado/cancelado (solo POST)."""

    roles = TABLES_ROLES

    def post(self, request, pk):
        item = get_object_or_404(OrderItem, pk=pk)
        # El template solo envía el POST sin campo `status`: por defecto "entregado".
        status = request.POST.get("status") or OrderItem.Status.ENTREGADO
        if status in (OrderItem.Status.ENTREGADO, OrderItem.Status.CANCELADO):
            item.status = status
            item.save(update_fields=["status"])
            messages.success(request, f"Ítem marcado como {item.get_status_display()}.")
        else:
            messages.error(request, "Estado inválido.")
        return redirect("tables:order_detail", pk=item.order_id)


class OrderCloseView(RoleRequiredMixin, View):
    """Cierra la comanda: genera la venta (descuenta stock) y libera la mesa."""

    roles = TABLES_ROLES

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, status=Order.Status.ABIERTA)
        form = OrderCloseForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Datos de cobro inválidos.")
            return redirect("tables:order_detail", pk=order.pk)
        register = CashRegister.get_open()
        try:
            sale = order.close_to_sale(
                user=request.user,
                payment_method=form.cleaned_data["payment_method"],
                cash_received=form.cleaned_data.get("cash_received"),
                cash_register=register,
                discount=form.cleaned_data.get("discount") or Decimal("0"),
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("tables:order_detail", pk=order.pk)
        messages.success(
            request,
            f"Comanda cobrada. Ticket {sale.ticket_number} (se cobraron solo los ítems entregados).",
        )
        return redirect("sales:sale_detail", pk=sale.pk)
