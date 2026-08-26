"""
sales — Formularios de caja y venta (POS).
"""
from decimal import Decimal

from django import forms

from .models import CashRegister, Sale


class CashRegisterOpenForm(forms.ModelForm):
    """Abre una caja. Valida que no exista otra caja abierta."""

    class Meta:
        model = CashRegister
        fields = ["opening_amount", "notes"]

    def clean(self):
        cleaned = super().clean()
        if CashRegister.objects.filter(status=CashRegister.Status.ABIERTA).exists():
            raise forms.ValidationError(
                "Ya hay una caja abierta. Hay que cerrarla antes de abrir otra."
            )
        return cleaned


class CashRegisterCloseForm(forms.Form):
    """Cierra la caja: monto de cierre (esperado vs. contado)."""

    closing_amount = forms.DecimalField(label="Monto de cierre", max_digits=10, decimal_places=2)
    actual_amount = forms.DecimalField(label="Monto real contado", max_digits=10, decimal_places=2)
    notes = forms.CharField(label="Notas", widget=forms.Textarea, required=False)

    def clean(self):
        cleaned = super().clean()
        closing = cleaned.get("closing_amount")
        actual = cleaned.get("actual_amount")
        if closing is not None and actual is not None and closing != actual:
            self.add_error(
                "actual_amount",
                "El monto real no coincide con el monto de cierre (se registra la diferencia).",
            )
        return cleaned


class SaleForm(forms.Form):
    """Payload del POS.

    El carrito viaja como arrays de formulario `product_id[]` y `quantity[]`
    (el campo `items` JSON se mantiene solo por compatibilidad).
    """

    items = forms.CharField(widget=forms.HiddenInput, required=False)
    customer_id = forms.IntegerField(required=False, min_value=1)
    payment_method = forms.ChoiceField(
        choices=Sale.PaymentMethod.choices, initial=Sale.PaymentMethod.EFECTIVO
    )
    cash_received = forms.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount = forms.DecimalField(max_digits=10, decimal_places=2, required=False, initial=Decimal("0"))

    def clean_discount(self):
        discount = self.cleaned_data["discount"] or Decimal("0")
        if discount < 0:
            raise forms.ValidationError("El descuento no puede ser negativo.")
        return discount
