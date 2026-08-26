"""
staff — Vistas de empleados, turnos y "mi turno".
"""
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import EmployeeForm, ShiftForm
from .models import Employee, Shift


class EmployeeListView(RoleRequiredMixin, ListView):
    model = Employee
    template_name = "staff/employee_list.html"
    context_object_name = "employees"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        return Employee.objects.select_related("user").order_by("user__username")


class EmployeeCreateView(RoleRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "staff/employee_form.html"
    success_url = reverse_lazy("staff:employee_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Empleado creado.")
        return super().form_valid(form)


class EmployeeUpdateView(RoleRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "staff/employee_form.html"
    success_url = reverse_lazy("staff:employee_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Empleado actualizado.")
        return super().form_valid(form)


class EmployeeDeleteView(RoleRequiredMixin, DeleteView):
    """Borrado lógico: desactiva el empleado (solo POST)."""

    model = Employee
    success_url = reverse_lazy("staff:employee_list")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, "Empleado desactivado.")
        return HttpResponseRedirect(self.get_success_url())


class ShiftListView(RoleRequiredMixin, ListView):
    model = Shift
    template_name = "staff/shift_list.html"
    context_object_name = "shifts"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        qs = Shift.objects.select_related("employee__user").order_by("-date", "-start_time")
        date = self.request.GET.get("date")
        if date:
            qs = qs.filter(date=date)
        return qs


class ShiftCreateView(RoleRequiredMixin, CreateView):
    model = Shift
    form_class = ShiftForm
    template_name = "staff/shift_form.html"
    success_url = reverse_lazy("staff:shift_list")
    roles = ["gerente", "admin"]

    def get_initial(self):
        return {"date": timezone.localdate()}

    def form_valid(self, form):
        messages.success(self.request, "Turno creado.")
        return super().form_valid(form)


class ShiftUpdateView(RoleRequiredMixin, UpdateView):
    model = Shift
    form_class = ShiftForm
    template_name = "staff/shift_form.html"
    success_url = reverse_lazy("staff:shift_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Turno actualizado.")
        return super().form_valid(form)


class ShiftDeleteView(RoleRequiredMixin, DeleteView):
    """Elimina un turno (solo POST)."""

    model = Shift
    success_url = reverse_lazy("staff:shift_list")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        messages.success(self.request, "Turno eliminado.")
        return super().form_valid(form)


class MyShiftView(RoleRequiredMixin, View):
    """Mi turno: turno de hoy (fichar entrada/salida) y turnos recientes."""

    roles = ["bartender", "cajero", "gerente", "admin"]

    def _employee(self, request):
        return Employee.objects.filter(user=request.user).first()

    def get(self, request):
        employee = self._employee(request)
        today = timezone.localdate()
        today_shift = None
        my_shifts = []
        if employee:
            today_shift = (
                Shift.objects.filter(employee=employee, date=today)
                .order_by("-start_time")
                .first()
            )
            my_shifts = Shift.objects.filter(employee=employee).order_by("-date", "-start_time")[:10]
        return render(
            request,
            "staff/my_shift.html",
            {
                "employee": employee,
                "today": today,
                "today_shift": today_shift,
                "my_shifts": my_shifts,
            },
        )

    def post(self, request):
        employee = self._employee(request)
        if employee is None:
            messages.error(request, "No hay un registro de empleado para tu usuario.")
            return redirect("staff:my_shift")
        action = request.POST.get("action")
        now = timezone.localtime().time()
        today = timezone.localdate()
        today_shift = (
            Shift.objects.filter(employee=employee, date=today).order_by("-start_time").first()
        )
        if action == "in":
            if today_shift and today_shift.end_time is None:
                messages.error(request, "Ya tenés un turno abierto.")
            else:
                Shift.objects.create(employee=employee, date=today, start_time=now)
                messages.success(request, "Turno iniciado.")
        elif action == "out":
            if today_shift and today_shift.end_time is None:
                today_shift.end_time = now
                today_shift.save(update_fields=["end_time"])
                messages.success(
                    request, f"Turno finalizado. Horas trabajadas: {today_shift.worked_hours:.2f}"
                )
            else:
                messages.error(request, "No tenés un turno abierto para cerrar.")
        else:
            messages.error(request, "Acción inválida.")
        return redirect("staff:my_shift")
