"""
purchases — Formularios de proveedores y órdenes de compra.
"""
from django import forms

from inventory.models import Product

from .models import PurchaseItem, PurchaseOrder, Supplier


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact_name", "phone", "email", "address", "cuit", "notes", "is_active"]


class PurchaseOrderForm(forms.ModelForm):
    """Formulario base de OC: proveedor + ítems (los ítems van en JSON en `items`)."""

    class Meta:
        model = PurchaseOrder
        fields = ["supplier"]


class PurchaseItemForm(forms.ModelForm):
    """Ítem de OC (también usado por el frontend para filas dinámicas)."""

    class Meta:
        model = PurchaseItem
        fields = ["product", "quantity", "unit_cost"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor a cero.")
        return quantity

    def clean_unit_cost(self):
        unit_cost = self.cleaned_data["unit_cost"]
        if unit_cost < 0:
            raise forms.ValidationError("El costo unitario no puede ser negativo.")
        return unit_cost

    def save(self, commit=True):
        item = super().save(commit=False)
        item.subtotal = item.quantity * item.unit_cost
        if commit:
            item.save()
        return item
