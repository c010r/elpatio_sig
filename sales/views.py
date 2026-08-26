"""
sales — Vistas de POS, ventas, tickets y caja.
"""
import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from core.mixins import RoleRequiredMixin
from customers.models import Customer
from inventory.models import Product

from .forms import CashRegisterCloseForm, CashRegisterOpenForm, HappyHourConfigForm, SaleForm
from .models import CashRegister, HappyHourConfig, Sale, is_happy_hour_active

audit = logging.getLogger("audit")

SALES_ROLES = ["cajero", "gerente", "admin"]
# La mayoría de las ventas del pub son en barra: el bartender también puede
# cobrar en el POS. La gestión de caja (abrir/cerrar) queda en SALES_ROLES.
BAR_SALES_ROLES = ["bartender", "cajero", "gerente", "admin"]


def _happy_hour_context():
    """Datos del happy hour para los banners de POS y comanda."""
    config = HappyHourConfig.get_solo()
    return {
        "enabled": config.enabled,
        "active": is_happy_hour_active(),
        "name": config.name,
        "discount_percent": config.discount_percent,
        "end_time": config.end_time,
    }


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
    """POS: grilla de productos + carrito + cobro (también para bartender)."""

    roles = BAR_SALES_ROLES

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
            "happy_hour": _happy_hour_context(),
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
        # F2-05: sin caja abierta no se puede cobrar (las ventas deben quedar
        # dentro del arqueo esperado).
        if register is None:
            audit.warning("pos_cobro_sin_caja_bloqueado por=%s", request.user.username)
            messages.error(request, "No hay una caja abierta. Abrí la caja antes de cobrar.")
            return redirect("sales:pos")
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
                tip=form.cleaned_data.get("tip") or Decimal("0"),
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return redirect("sales:pos")

        messages.success(request, f"Venta {sale.ticket_number} registrada.")
        # ?auto=1: el ticket imprime y vuelve solo al POS (flujo de barra).
        return redirect(reverse("sales:sale_detail", args=[sale.pk]) + "?auto=1")


class SaleListView(RoleRequiredMixin, ListView):
    model = Sale
    template_name = "sales/sale_list.html"
    context_object_name = "sales"
    roles = BAR_SALES_ROLES

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
    roles = BAR_SALES_ROLES

    def get_queryset(self):
        return Sale.objects.select_related(
            "user", "table", "customer", "cash_register"
        ).prefetch_related("items__product")


class SaleVoidView(RoleRequiredMixin, View):
    """Anula una venta y repone stock (solo POST).

    F2-06: solo el autor de la venta o gerente/admin; motivo obligatorio;
    evento de auditoría. Con el bartender habilitado, puede anular SOLO sus
    propias ventas (el chequeo de autor aplica antes que el de rol).
    """

    roles = BAR_SALES_ROLES

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        reason = request.POST.get("reason", "").strip()

        is_author = sale.user_id == request.user.pk
        is_manager = request.user.groups.filter(name__in=["gerente", "admin"]).exists()
        if not (is_author or is_manager):
            audit.warning(
                "venta_anulacion_denegada por=%s venta=%s autor=%s",
                request.user.username, sale.ticket_number, sale.user.username,
            )
            messages.error(
                request, "Solo el autor de la venta o un gerente/admin pueden anularla."
            )
            return redirect("sales:sale_detail", pk=sale.pk)

        if not reason:
            messages.error(request, "El motivo de anulación es obligatorio.")
            return redirect("sales:sale_detail", pk=sale.pk)

        try:
            sale.void(user=request.user, reason=reason)
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        else:
            audit.info(
                "venta_anulada por=%s venta=%s motivo=%s",
                request.user.username, sale.ticket_number, reason,
            )
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
        # F2-07: apertura atómica — se bloquea la caja abierta existente para
        # evitar doble apertura concurrente (SEC-10).
        with transaction.atomic():
            if CashRegister.objects.select_for_update().filter(
                status=CashRegister.Status.ABIERTA
            ).exists():
                audit.warning("caja_apertura_duplicada_bloqueada por=%s", self.request.user.username)
                messages.error(self.request, "Ya hay una caja abierta.")
                return redirect("sales:pos")
            register = form.save(commit=False)
            register.opened_by = self.request.user
            register.save()
        audit.info("caja_abierta por=%s id=%s", self.request.user.username, register.pk)
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["register"] = self.get_open_register()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        register = self.get_open_register()
        ctx["register"] = register
        # Esperado por método (ventas completadas del período abierto).
        ctx["expected_by_method"] = register.expected_by_method()
        return ctx

    def form_valid(self, form):
        register = self.get_open_register()
        register.close(
            counted_cash=form.cleaned_data["counted_cash"],
            counted_card=form.cleaned_data["counted_card"],
            counted_transfer=form.cleaned_data["counted_transfer"],
            counted_other=form.cleaned_data["counted_other"],
            notes=form.cleaned_data.get("notes", ""),
        )
        diff = register.difference
        if diff:
            messages.success(
                self.request,
                f"Caja cerrada. Diferencia: {diff:.2f} UYU.",
            )
        else:
            messages.success(self.request, "Caja cerrada y cuadrada.")
        return super().form_valid(form)


class HappyHourConfigView(RoleRequiredMixin, FormView):
    """Edición de la configuración de happy hour (solo admin/gerente). F2-11."""

    template_name = "sales/happy_hour_config.html"
    form_class = HappyHourConfigForm
    success_url = reverse_lazy("sales:happy_hour_config")
    roles = ["gerente", "admin"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = HappyHourConfig.get_solo()
        return kwargs

    def form_valid(self, form):
        config = form.save()
        audit.info(
            "happy_hour_config_editada por=%s enabled=%s discount=%s%%",
            self.request.user.username, config.enabled, config.discount_percent,
        )
        messages.success(self.request, "Configuración de happy hour actualizada.")
        return super().form_valid(form)
