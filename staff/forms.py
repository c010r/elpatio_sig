"""
staff — Formularios de empleados y turnos.
"""
from django import forms

from .models import Employee, Shift


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["user", "position", "hire_date", "hourly_rate", "is_active"]
        widgets = {"hire_date": forms.DateInput(attrs={"type": "date"})}


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ["employee", "date", "start_time", "end_time", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "El fin debe ser posterior al inicio.")
        return cleaned
