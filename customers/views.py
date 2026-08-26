"""
customers — Vistas de clientes, detalle con historial y canje de puntos.
"""
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import RoleRequiredMixin
from sales.models import Sale

from .forms import CustomerForm
from .models import Customer, LoyaltyConfig

CUSTOMER_ROLES = ["cajero", "gerente", "admin"]


class CustomerListView(RoleRequiredMixin, ListView):
    model = Customer
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    roles = CUSTOMER_ROLES

    def get_queryset(self):
        qs = Customer.objects.filter(is_active=True).order_by("name")
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(dni__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["loyalty_config"] = LoyaltyConfig.get_solo()
        return ctx


class CustomerCreateView(RoleRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customers:customer_list")
    roles = CUSTOMER_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Cliente creado.")
        return super().form_valid(form)


class CustomerUpdateView(RoleRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customers:customer_list")
    roles = CUSTOMER_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Cliente actualizado.")
        return super().form_valid(form)


class CustomerDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva el cliente (solo POST)."""

    model = Customer
    success_url = reverse_lazy("customers:customer_list")
    roles = CUSTOMER_ROLES
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, f"Cliente '{self.object}' desactivado.")
        return HttpResponseRedirect(self.get_success_url())


class CustomerDetailView(RoleRequiredMixin, DetailView):
    """Detalle con historial de ventas y puntos de fidelización."""

    model = Customer
    template_name = "customers/customer_detail.html"
    context_object_name = "customer"
    roles = CUSTOMER_ROLES

    def get_queryset(self):
        return Customer.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sales"] = (
            self.object.sales.filter(status=Sale.Status.COMPLETADA)
            .select_related("user")
            .order_by("-created_at")[:20]
        )
        ctx["loyalty_config"] = LoyaltyConfig.get_solo()
        return ctx


class CustomerRedeemView(RoleRequiredMixin, View):
    """Canjea puntos: genera un descuento para el próximo cobro del cliente (solo POST).

    El descuento queda en sesión y el POS lo aplica si el cliente coincide.
    """

    roles = CUSTOMER_ROLES

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk, is_active=True)
        config = LoyaltyConfig.get_solo()
        if customer.points < config.points_required_for_discount:
            messages.error(
                request,
                f"El cliente tiene {customer.points} puntos y necesita "
                f"{config.points_required_for_discount} para canjear.",
            )
            return redirect("customers:customer_detail", pk=customer.pk)
        customer.points -= config.points_required_for_discount
        customer.save(update_fields=["points"])
        request.session["redeemed_discount"] = str(config.discount_amount)
        request.session["redeemed_customer_id"] = customer.pk
        messages.success(
            request,
            f"Se canjearon {config.points_required_for_discount} puntos: descuento de "
            f"{config.discount_amount} aplicado al próximo cobro de este cliente.",
        )
        return redirect("customers:customer_detail", pk=customer.pk)
