"""
sales — Vistas de POS, ventas, tickets y caja.
"""
import json
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from core.mixins import RoleRequiredMixin
from customers.models import Customer
from inventory.models import Product

from .forms import CashRegisterCloseForm, CashRegisterOpenForm, SaleForm
from .models import CashRegister, Sale

SALES_ROLES = ["cajero", "gerente", "admin"]


def _parse_items(payload):
    """Parsea el carrito JSON del POS: [{"product_id": 1, "quantity": 2}, ...] (compatibilidad)."""
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("Formato de ítems inválido.") from exc
    if not isinstance(data, list) or not data:
        raise ValidationError("El carrito está vacío.")
    items = []
    for entry in data:
        product_id = entry.get("product_id") or entry.get("product")
        quantity = entry.get("quantity")
        try:
            product = Product.objects.get(pk=int(product_id), is_active=True)
            qty = Decimal(str(quantity))
        except (TypeError, ValueError, Product.DoesNotExist) as exc:
            raise ValidationError("Hay un ítem inválido en el carrito.") from exc
        if qty <= 0:
            raise ValidationError("Las cantidades deben ser mayores a cero.")
        items.append((product, qty))
    return items


def _parse_cart(post):
    """Parsea el carrito enviado por el frontend.

    Formato principal: arrays de formulario `product_id[]` y `quantity[]`.
    Compatibilidad: JSON en el campo `items`.
    """
    product_ids = post.getlist("product_id")
    quantities = post.getlist("quantity")
    if product_ids or quantities:
        if len(product_ids) != len(quantities):
            raise ValidationError("El carrito está incompleto (producto/cantidad desparejados).")
        items = []
        for raw_id, raw_qty in zip(product_ids, quantities):
            try:
                product = Product.objects.get(pk=int(raw_id), is_active=True)
                qty = Decimal(str(raw_qty))
            except (TypeError, ValueError, Product.DoesNotExist) as exc:
                raise ValidationError("Hay un ítem inválido en el carrito.") from exc
            if qty <= 0:
                raise ValidationError("Las cantidades deben ser mayores a cero.")
            items.append((product, qty))
        if not items:
            raise ValidationError("El carrito está vacío.")
        return items
    return _parse_items(post.get("items", ""))


class PosView(RoleRequiredMixin, View):
    """POS: grilla de productos + carrito + cobro."""

    roles = SALES_ROLES

    def get(self, request):
        context = {
            "products": (
                Product.objects.filter(is_active=True)
                .select_related("category")
                .order_by("category__name", "name")
            ),
            "customers": Customer.objects.filter(is_active=True).order_by("name"),
            "form": SaleForm(),
            "open_cash_register": CashRegister.get_open(),
        }
        return render(request, "sales/pos.html", context)

    def post(self, request):
        form = SaleForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Datos de cobro inválidos. Revisá el carrito y el pago.")
            return redirect("sales:pos")
        try:
            items = _parse_cart(request.POST)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("sales:pos")

        customer = None
        if form.cleaned_data.get("customer_id"):
            customer = Customer.objects.filter(
                pk=form.cleaned_data["customer_id"], is_active=True
            ).first()
        register = CashRegister.get_open()
        discount = form.cleaned_data.get("discount") or Decimal("0")

        # Descuento por canje de puntos pendiente (solo si coincide el cliente).
        redeemed = request.session.get("redeemed_discount")
        redeemed_customer_id = request.session.get("redeemed_customer_id")
        if redeemed is not None and customer is not None and redeemed_customer_id == customer.pk:
            request.session.pop("redeemed_discount", None)
            request.session.pop("redeemed_customer_id", None)
            discount += Decimal(str(redeemed))

        try:
            sale = Sale.complete_sale(
                user=request.user,
                items=items,
                cash_register=register,
                table=None,
                customer=customer,
                payment_method=form.cleaned_data["payment_method"],
                cash_received=form.cleaned_data.get("cash_received"),
                discount=discount,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("sales:pos")

        messages.success(request, f"Venta {sale.ticket_number} registrada.")
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleListView(RoleRequiredMixin, ListView):
    model = Sale
    template_name = "sales/sale_list.html"
    context_object_name = "sales"
    roles = SALES_ROLES

    def get_queryset(self):
        qs = Sale.objects.select_related("user", "table", "customer").order_by("-created_at")
        status = self.request.GET.get("status")
        if status in dict(Sale.Status.choices):
            qs = qs.filter(status=status)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(ticket_number__icontains=search)
        return qs


class SaleDetailView(RoleRequiredMixin, DetailView):
    """Detalle/ticket imprimible de una venta."""

    model = Sale
    template_name = "sales/sale_detail.html"
    context_object_name = "sale"
    roles = SALES_ROLES

    def get_queryset(self):
        return Sale.objects.select_related(
            "user", "table", "customer", "cash_register"
        ).prefetch_related("items__product")


class SaleVoidView(RoleRequiredMixin, View):
    """Anula una venta y repone stock (solo POST)."""

    roles = SALES_ROLES

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        reason = request.POST.get("reason", "").strip()
        try:
            sale.void(user=request.user, reason=reason)
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            messages.success(request, f"Venta {sale.ticket_number} anulada y stock repuesto.")
        return redirect("sales:sale_detail", pk=sale.pk)


class CashRegisterOpenView(RoleRequiredMixin, FormView):
    template_name = "sales/cash_register_open.html"
    form_class = CashRegisterOpenForm
    success_url = reverse_lazy("sales:pos")
    roles = SALES_ROLES

    def dispatch(self, request, *args, **kwargs):
        if CashRegister.get_open():
            messages.info(request, "Ya hay una caja abierta.")
            return redirect("sales:pos")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        register = form.save(commit=False)
        register.opened_by = self.request.user
        register.save()
        messages.success(self.request, "Caja abierta.")
        return super().form_valid(form)


class CashRegisterCloseView(RoleRequiredMixin, FormView):
    template_name = "sales/cash_register_close.html"
    form_class = CashRegisterCloseForm
    success_url = reverse_lazy("sales:pos")
    roles = SALES_ROLES

    def get_open_register(self):
        return CashRegister.get_open()

    def dispatch(self, request, *args, **kwargs):
        if not self.get_open_register():
            messages.info(request, "No hay ninguna caja abierta.")
            return redirect("sales:pos")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["register"] = self.get_open_register()
        return ctx

    def form_valid(self, form):
        register = self.get_open_register()
        register.close(
            closing_amount=form.cleaned_data["closing_amount"],
            actual_amount=form.cleaned_data["actual_amount"],
            notes=form.cleaned_data.get("notes", ""),
        )
        messages.success(self.request, "Caja cerrada.")
        return super().form_valid(form)
