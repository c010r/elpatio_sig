"""
inventory — Vistas de categorías, productos, movimientos de stock y stock bajo.
"""
from decimal import Decimal

from django.contrib import messages
from django.db.models import F
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import CategoryForm, ProductForm, StockMovementForm
from .models import Category, Product, RecipeItem, StockMovement


def _apply_recipe(request, product):
    """Persiste la receta de un producto desde los arrays paralelos del POST
    (`ingredient_id[]` / `quantity[]`).

    - Borra y recrea la receta (nunca duplica).
    - Solo filas con ingrediente seleccionado, activo y cantidad > 0.
    - El producto no puede usarse a sí mismo como ingrediente.
    - Si `is_composed` quedó desmarcado → se elimina la receta (cleanup).
    """
    product.recipe_items.all().delete()
    if not request.POST.get("is_composed"):
        return
    ingredient_ids = request.POST.getlist("ingredient_id")
    quantities = request.POST.getlist("quantity")
    for raw_id, raw_qty in zip(ingredient_ids, quantities):
        if not raw_id:
            continue
        try:
            ingredient_id = int(raw_id)
            quantity = Decimal(str(raw_qty))
        except (TypeError, ValueError):
            continue
        if ingredient_id == product.pk:
            continue  # no auto-ingrediente
        if quantity <= 0:
            continue
        ingredient = Product.objects.filter(pk=ingredient_id, is_active=True).first()
        if ingredient is None:
            continue
        RecipeItem.objects.create(product=product, ingredient=ingredient, quantity=quantity)


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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ingredient_products"] = (
            Product.objects.filter(is_active=True).order_by("name")
        )
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        _apply_recipe(self.request, self.object)
        messages.success(self.request, "Producto creado.")
        return HttpResponseRedirect(self.get_success_url())


class ProductUpdateView(RoleRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "inventory/product_form.html"
    success_url = reverse_lazy("inventory:product_list")
    roles = ["gerente", "admin"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = Product.objects.filter(is_active=True).order_by("name")
        if self.object and self.object.pk:
            qs = qs.exclude(pk=self.object.pk)  # el propio producto no es ingrediente
        ctx["ingredient_products"] = qs
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        _apply_recipe(self.request, self.object)
        messages.success(self.request, "Producto actualizado.")
        return HttpResponseRedirect(self.get_success_url())


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
        # Excluye elaborados (is_composed): su stock es la materia prima,
        # controlada por los ingredientes de la receta.
        return (
            Product.objects.filter(
                is_active=True, is_composed=False, stock_current__lte=F("stock_min")
            )
            .select_related("category")
            .order_by(F("stock_current") - F("stock_min"))
        )
