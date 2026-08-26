"""
purchases — Vistas de proveedores y órdenes de compra.
"""
import json
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import RoleRequiredMixin
from inventory.models import Product

from .forms import PurchaseOrderForm, SupplierForm
from .models import PurchaseItem, PurchaseOrder, Supplier

PURCHASES_ROLES = ["gerente", "admin"]


def _parse_items(payload, allow_empty=False):
    """Parsea ítems JSON de una OC: [{"product_id": 1, "quantity": 2, "unit_cost": 350}, ...].

    Con allow_empty=True, un payload vacío/ausente devuelve [] (la OC se crea
    solo con proveedor; los ítems pueden cargarse después vía purchase_update).
    """
    if not payload:
        return [] if allow_empty else None
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("Formato de ítems inválido.") from exc
    if not isinstance(data, list) or not data:
        if allow_empty:
            return []
        raise ValidationError("La orden debe tener al menos un ítem.")
    items = []
    for entry in data:
        product_id = entry.get("product_id") or entry.get("product")
        quantity = entry.get("quantity")
        unit_cost = entry.get("unit_cost")
        try:
            product = Product.objects.get(pk=int(product_id), is_active=True)
            qty = Decimal(str(quantity))
            cost = Decimal(str(unit_cost))
        except (TypeError, ValueError, Product.DoesNotExist) as exc:
            raise ValidationError("Hay un ítem inválido en la orden.") from exc
        if qty <= 0:
            raise ValidationError("Las cantidades deben ser mayores a cero.")
        if cost < 0:
            raise ValidationError("El costo unitario no puede ser negativo.")
        items.append((product, qty, cost))
    return items


class SupplierListView(RoleRequiredMixin, ListView):
    model = Supplier
    template_name = "purchases/supplier_list.html"
    context_object_name = "suppliers"
    roles = PURCHASES_ROLES

    def get_queryset(self):
        return Supplier.objects.filter(is_active=True).order_by("name")


class SupplierCreateView(RoleRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "purchases/supplier_form.html"
    success_url = reverse_lazy("purchases:supplier_list")
    roles = PURCHASES_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Proveedor creado.")
        return super().form_valid(form)


class SupplierUpdateView(RoleRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "purchases/supplier_form.html"
    success_url = reverse_lazy("purchases:supplier_list")
    roles = PURCHASES_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Proveedor actualizado.")
        return super().form_valid(form)


class SupplierDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva el proveedor (solo POST)."""

    model = Supplier
    success_url = reverse_lazy("purchases:supplier_list")
    roles = PURCHASES_ROLES
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, f"Proveedor '{self.object}' desactivado.")
        return HttpResponseRedirect(self.get_success_url())


class PurchaseListView(RoleRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = "purchases/purchase_list.html"
    context_object_name = "purchases"
    roles = PURCHASES_ROLES

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related("supplier", "ordered_by").order_by("-created_at")
        status = self.request.GET.get("status")
        if status in dict(PurchaseOrder.Status.choices):
            qs = qs.filter(status=status)
        return qs


class PurchaseCreateView(RoleRequiredMixin, View):
    """Crea una OC con proveedor + ítems JSON."""

    roles = PURCHASES_ROLES

    def get(self, request):
        return render(
            request,
            "purchases/purchase_form.html",
            {"form": PurchaseOrderForm(), "object": None, "existing_items_json": "[]"},
        )

    def post(self, request):
        form = PurchaseOrderForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Datos de la orden inválidos.")
            return redirect("purchases:purchase_create")
        try:
            items = _parse_items(request.POST.get("items", ""), allow_empty=True) or []
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("purchases:purchase_create")
        with transaction.atomic():
            order = form.save(commit=False)
            order.number = PurchaseOrder.next_number()
            order.ordered_by = request.user
            order.save()
            order.total = self._save_items(order, items)
            order.save(update_fields=["total"])
        messages.success(request, f"Orden de compra {order.number} creada.")
        return redirect("purchases:purchase_detail", pk=order.pk)

    @staticmethod
    def _save_items(order, items):
        total = Decimal("0")
        for product, qty, cost in items:
            subtotal = qty * cost
            total += subtotal
            PurchaseItem.objects.create(
                order=order, product=product, quantity=qty, unit_cost=cost, subtotal=subtotal
            )
        return total


class PurchaseUpdateView(RoleRequiredMixin, View):
    """Edita una OC pendiente (reemplaza los ítems)."""

    roles = PURCHASES_ROLES

    def get(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        if order.status != PurchaseOrder.Status.PENDIENTE:
            messages.error(request, "Solo se pueden editar órdenes pendientes.")
            return redirect("purchases:purchase_detail", pk=order.pk)
        existing = [
            {
                "product_id": item.product_id,
                "quantity": str(item.quantity),
                "unit_cost": str(item.unit_cost),
            }
            for item in order.items.all()
        ]
        return render(
            request,
            "purchases/purchase_form.html",
            {
                "object": order,
                "form": PurchaseOrderForm(instance=order),
                "existing_items_json": json.dumps(existing),
            },
        )

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        if order.status != PurchaseOrder.Status.PENDIENTE:
            messages.error(request, "Solo se pueden editar órdenes pendientes.")
            return redirect("purchases:purchase_detail", pk=order.pk)
        form = PurchaseOrderForm(request.POST, instance=order)
        if not form.is_valid():
            messages.error(request, "Datos de la orden inválidos.")
            return redirect("purchases:purchase_update", pk=order.pk)
        try:
            items = _parse_items(request.POST.get("items", ""), allow_empty=True) or []
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("purchases:purchase_update", pk=order.pk)
        with transaction.atomic():
            order = form.save(commit=False)
            order.save()
            order.items.all().delete()
            order.total = PurchaseCreateView._save_items(order, items)
            order.save(update_fields=["total"])
        messages.success(request, f"Orden {order.number} actualizada.")
        return redirect("purchases:purchase_detail", pk=order.pk)


class PurchaseDetailView(RoleRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = "purchases/purchase_detail.html"
    context_object_name = "object"
    roles = PURCHASES_ROLES

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("supplier", "ordered_by").prefetch_related(
            "items__product"
        )


class PurchaseReceiveView(RoleRequiredMixin, View):
    """Recibe la OC: página de confirmación (GET) + recepción (POST)."""

    roles = PURCHASES_ROLES

    def get(self, request, pk):
        order = get_object_or_404(
            PurchaseOrder.objects.select_related("supplier", "ordered_by").prefetch_related(
                "items__product"
            ),
            pk=pk,
        )
        return render(request, "purchases/purchase_receive.html", {"purchase": order})

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            order.receive(user=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            messages.success(request, f"Orden {order.number} recibida: stock y precios actualizados.")
        return redirect("purchases:purchase_detail", pk=order.pk)


class PurchaseCancelView(RoleRequiredMixin, View):
    """Cancela una OC pendiente (solo POST)."""

    roles = PURCHASES_ROLES

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        try:
            order.cancel()
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            messages.success(request, f"Orden {order.number} cancelada.")
        return redirect("purchases:purchase_list")
