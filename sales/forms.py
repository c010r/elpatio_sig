"""
sales — Formularios de caja y venta (POS).
"""
from decimal import Decimal

from django import forms

from .models import CashRegister, HappyHourConfig, Sale

# F2-08: tope de cordura para montos contados en el arqueo ($U 10.000.000).
MAX_COUNTED_AMOUNT = Decimal("10000000")


class HappyHourConfigForm(forms.ModelForm):
    """Edición de la config de happy hour (solo admin/gerente). F2-11.

    `discount_percent` queda validado 0-100 por los validators del modelo
    (MinValueValidator/MaxValueValidator) y por clean_discount_percent.
    """

    class Meta:
        model = HappyHourConfig
        fields = ["enabled", "name", "start_time", "end_time", "discount_percent"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_discount_percent(self):
        value = self.cleaned_data["discount_percent"]
        if value < 0 or value > 100:
            raise forms.ValidationError("El descuento debe estar entre 0 y 100.")
        return value


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
    """Cierre/arqueo de caja: lo CONTADO por método de pago.

    Compatibilidad Fase 1: si se envían `closing_amount`/`actual_amount` sin
    counted_*, el primero se interpreta como efectivo contado.
    """

    counted_cash = forms.DecimalField(label="Efectivo contado", max_digits=10, decimal_places=2, required=False)
    counted_card = forms.DecimalField(label="Tarjeta contada", max_digits=10, decimal_places=2, required=False)
    counted_transfer = forms.DecimalField(label="Transferencia contada", max_digits=10, decimal_places=2, required=False)
    counted_other = forms.DecimalField(label="Otros contados", max_digits=10, decimal_places=2, required=False)
    notes = forms.CharField(label="Notas", widget=forms.Textarea, required=False)
    confirmed = forms.BooleanField(
        label="Confirmo la diferencia (la caja no cierra cuadrada)",
        required=False,
    )
    # Compatibilidad Fase 1 (test histórico).
    closing_amount = forms.DecimalField(label="Monto de cierre", max_digits=10, decimal_places=2, required=False)
    actual_amount = forms.DecimalField(label="Monto real contado", max_digits=10, decimal_places=2, required=False)

    def __init__(self, *args, register=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.register = register

    def clean(self):
        cleaned = super().clean()
        counted_keys = ("counted_cash", "counted_card", "counted_transfer", "counted_other")

        # Mapeo legacy: closing_amount → efectivo contado si no hay counted_*.
        if all(cleaned.get(k) is None for k in counted_keys) and cleaned.get("closing_amount") is not None:
            cleaned["counted_cash"] = cleaned["closing_amount"]

        for key in counted_keys:
            value = cleaned.get(key)
            if value is None:
                cleaned[key] = Decimal("0")
            elif value < 0:
                self.add_error(key, "El monto contado no puede ser negativo.")
            elif value > MAX_COUNTED_AMOUNT:
                self.add_error(
                    key,
                    f"El monto contado supera el tope de cordura "
                    f"({MAX_COUNTED_AMOUNT:,.0f} UYU).",
                )

        if self.register:
            expected_total = self.register.opening_amount + sum(
                self.register.expected_by_method().values(), Decimal("0")
            )
            closing = sum(cleaned.get(k) or Decimal("0") for k in counted_keys)
            difference = closing - expected_total
            if difference != 0 and not cleaned.get("confirmed"):
                self.add_error(
                    "confirmed",
                    f"La diferencia es {difference:.2f} UYU. Marcá la confirmación para cerrar.",
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
    tip = forms.DecimalField(max_digits=10, decimal_places=2, required=False, initial=Decimal("0"))

    def clean_discount(self):
        discount = self.cleaned_data["discount"] or Decimal("0")
        if discount < 0:
            raise forms.ValidationError("El descuento no puede ser negativo.")
        return discount

    def clean_tip(self):
        tip = self.cleaned_data["tip"] or Decimal("0")
        if tip < 0:
            raise forms.ValidationError("La propina no puede ser negativa.")
        return tip
