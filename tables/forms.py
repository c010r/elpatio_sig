"""
tables — Formularios de mesas, comandas e ítems.
"""
from decimal import Decimal

from django import forms

from inventory.models import Product
from sales.models import Sale

from .models import Order, OrderItem, Table


class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ["number", "capacity", "zone", "status", "is_active"]


class OrderForm(forms.ModelForm):
    """Abre una comanda: solo mesas libres y sin comanda abierta."""

    class Meta:
        model = Order
        fields = ["table", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = Table.objects.filter(
            is_active=True, status=Table.Status.LIBRE
        )

    def clean_table(self):
        table = self.cleaned_data["table"]
        if table.status != Table.Status.LIBRE:
            raise forms.ValidationError("La mesa no está libre.")
        if Order.objects.filter(table=table, status=Order.Status.ABIERTA).exists():
            raise forms.ValidationError("La mesa ya tiene una comanda abierta.")
        return table


class OrderItemForm(forms.ModelForm):
    """Agrega un ítem a una comanda (toma el precio de venta del producto)."""

    class Meta:
        model = OrderItem
        fields = ["product", "quantity", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["quantity"].initial = Decimal("1")

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor a cero.")
        return quantity

    def save(self, commit=True):
        item = super().save(commit=False)
        item.unit_price = item.product.sale_price
        if commit:
            item.save()
        return item


class OrderCloseForm(forms.Form):
    """Cobro y cierre de comanda."""

    payment_method = forms.ChoiceField(
        label="Método de pago",
        choices=Sale.PaymentMethod.choices,
        initial=Sale.PaymentMethod.EFECTIVO,
    )
    cash_received = forms.DecimalField(
        label="Efectivo recibido", max_digits=10, decimal_places=2, required=False
    )
    discount = forms.DecimalField(
        label="Descuento", max_digits=10, decimal_places=2, required=False, initial=Decimal("0")
    )

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("payment_method") == Sale.PaymentMethod.EFECTIVO
            and cleaned.get("cash_received") is None
        ):
            self.add_error("cash_received", "Indicá el efectivo recibido para pagos en efectivo.")
        return cleaned
