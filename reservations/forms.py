"""
reservations — Formularios de reservas.
"""
from django import forms

from customers.models import Customer
from tables.models import Table

from .models import Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = [
            "table", "customer", "name", "phone", "date",
            "start_time", "party_size", "status", "note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = Table.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["customer"].required = False
