"""
customers — Formularios de clientes.
"""
from django import forms

from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        # "points" queda fuera del form: los puntos se ganan con las ventas y
        # se canjean por descuento (un cajero no debe poder setearlos a mano).
        fields = ["name", "phone", "email", "dni", "birth_date", "notes", "is_active"]
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}

    def clean_dni(self):
        dni = self.cleaned_data["dni"]
        if dni:
            qs = Customer.objects.filter(dni=dni)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Ya existe un cliente con ese DNI.")
        return dni
