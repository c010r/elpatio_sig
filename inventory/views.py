"""
inventory — Vistas de categorías, productos, movimientos de stock y stock bajo.
"""
from django.contrib import messages
from django.db.models import F
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import CategoryForm, ProductForm, StockMovementForm
from .models import Category, Product, StockMovement


class CategoryListView(RoleRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        return Category.objects.all().order_by("name")


class CategoryCreateView(RoleRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("inventory:category_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Categoría creada.")
        return super().form_valid(form)


class CategoryUpdateView(RoleRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("inventory:category_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Categoría actualizada.")
        return super().form_valid(form)


class CategoryDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva la categoría (solo POST)."""

    model = Category
    success_url = reverse_lazy("inventory:category_list")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, f"Categoría '{self.object}' desactivada.")
        return HttpResponseRedirect(self.get_success_url())


class ProductListView(RoleRequiredMixin, ListView):
    model = Product
    template_name = "inventory/product_list.html"
    context_object_name = "products"
    roles = ["gerente", "admin", "bartender", "cajero"]

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related("category").order_by("category__name", "name")
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        category_id = self.request.GET.get("category")
        if category_id and category_id.isdigit():
            qs = qs.filter(category_id=int(category_id))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = Category.objects.filter(is_active=True).order_by("name")
        return ctx


class ProductCreateView(RoleRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "inventory/product_form.html"
    success_url = reverse_lazy("inventory:product_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Producto creado.")
        return super().form_valid(form)


class ProductUpdateView(RoleRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "inventory/product_form.html"
    success_url = reverse_lazy("inventory:product_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Producto actualizado.")
        return super().form_valid(form)


class ProductDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva el producto (solo POST)."""

    model = Product
    success_url = reverse_lazy("inventory:product_list")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, f"Producto '{self.object}' desactivado.")
        return HttpResponseRedirect(self.get_success_url())


class StockMovementListView(RoleRequiredMixin, ListView):
    model = StockMovement
    template_name = "inventory/stock_movement_list.html"
    context_object_name = "movements"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        qs = StockMovement.objects.select_related("product", "user").order_by("-created_at")
        movement_type = self.request.GET.get("movement_type")
        if movement_type in dict(StockMovement.MovementType.choices):
            qs = qs.filter(movement_type=movement_type)
        product_id = self.request.GET.get("product")
        if product_id and product_id.isdigit():
            qs = qs.filter(product_id=int(product_id))
        return qs


class StockMovementCreateView(RoleRequiredMixin, CreateView):
    model = StockMovement
    form_class = StockMovementForm
    template_name = "inventory/stock_movement_form.html"
    success_url = reverse_lazy("inventory:stock_movement_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Movimiento de stock aplicado.")
        return super().form_valid(form)


class StockLowView(RoleRequiredMixin, ListView):
    """Productos con stock actual <= stock mínimo."""

    model = Product
    template_name = "inventory/stock_low.html"
    context_object_name = "low_products"
    roles = ["gerente", "admin", "bartender", "cajero"]

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True, stock_current__lte=F("stock_min"))
            .select_related("category")
            .order_by(F("stock_current") - F("stock_min"))
        )
