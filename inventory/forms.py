"""
inventory — Formularios de categorías, productos y movimientos de stock.
"""
from django import forms

from .models import Category, Product, StockMovement


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "is_active"]


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "category", "unit", "purchase_price", "sale_price",
            "stock_current", "stock_min", "barcode", "image", "is_active",
        ]

    def clean_sale_price(self):
        sale_price = self.cleaned_data["sale_price"]
        if sale_price < 0:
            raise forms.ValidationError("El precio de venta no puede ser negativo.")
        return sale_price

    def clean_purchase_price(self):
        purchase_price = self.cleaned_data["purchase_price"]
        if purchase_price < 0:
            raise forms.ValidationError("El precio de compra no puede ser negativo.")
        return purchase_price


class StockMovementForm(forms.ModelForm):
    """Entrada/salida/ajuste manual de stock. El signo define la dirección."""

    class Meta:
        model = StockMovement
        fields = ["product", "movement_type", "quantity", "reference"]

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity == 0:
            raise forms.ValidationError("La cantidad no puede ser cero.")
        return quantity

    def clean(self):
        cleaned = super().clean()
        movement_type = cleaned.get("movement_type")
        quantity = cleaned.get("quantity")
        product = cleaned.get("product")
        if movement_type and quantity is not None:
            if movement_type in (
                StockMovement.MovementType.ENTRADA,
                StockMovement.MovementType.COMPRA,
            ) and quantity < 0:
                self.add_error("quantity", "Las entradas/compras deben tener cantidad positiva.")
            if movement_type == StockMovement.MovementType.SALIDA and quantity > 0:
                self.add_error("quantity", "Las salidas deben tener cantidad negativa.")
            if (
                movement_type in (StockMovement.MovementType.SALIDA, StockMovement.MovementType.VENTA)
                and quantity < 0
                and product
                and product.stock_current + quantity < 0
            ):
                self.add_error(
                    "quantity", f"Stock insuficiente (disponible: {product.stock_current})."
                )
        return cleaned

    def save(self, commit=True):
        movement = super().save(commit=False)
        if commit:
            movement.save()
            movement.apply()
        return movement
