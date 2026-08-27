"""
staff — Vistas de empleados, turnos, "mi turno" y liquidaciones diarias.
"""
import csv
import logging
from datetime import date as date_cls
from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import RoleRequiredMixin
from reports.views import safe_cell

from .forms import EmployeeForm, ShiftForm
from .models import Employee, Liquidacion, Shift

audit = logging.getLogger("audit")

STAFF_ROLES = ["gerente", "admin"]


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


# ---------------------------------------------------------------------------
# Liquidaciones diarias (gerente/admin)
# ---------------------------------------------------------------------------

class LiquidacionListView(RoleRequiredMixin, ListView):
    """Historial de liquidaciones con filtros (fechas, empleado, estado)."""

    model = Liquidacion
    template_name = "staff/liquidacion_list.html"
    context_object_name = "liquidaciones"
    roles = STAFF_ROLES
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Liquidacion.objects.select_related("employee__user", "generated_by")
            .order_by("-date", "employee__user__username")
        )
        start_date = self.request.GET.get("start_date")
        if start_date:
            qs = qs.filter(date__gte=start_date)
        end_date = self.request.GET.get("end_date")
        if end_date:
            qs = qs.filter(date__lte=end_date)
        employee_id = self.request.GET.get("employee")
        if employee_id and employee_id.isdigit():
            qs = qs.filter(employee_id=int(employee_id))
        status = self.request.GET.get("status")
        if status in dict(Liquidacion.Status.choices):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["employee_choices"] = (
            Employee.objects.filter(is_active=True).select_related("user").order_by("user__username")
        )
        ctx["employees"] = ctx["employee_choices"]
        return ctx


class LiquidacionCreateView(RoleRequiredMixin, View):
    """Genera liquidaciones diarias: previsualiza horas × tarifa por empleado
    y crea/actualiza borradores para los empleados con horas > 0."""

    roles = STAFF_ROLES

    def _parse_date(self, request):
        raw = request.GET.get("date") or request.POST.get("date") or timezone.localdate().isoformat()
        try:
            return date_cls.fromisoformat(raw)
        except ValueError:
            return timezone.localdate()

    def _preview(self, date):
        rows = []
        for employee in (
            Employee.objects.filter(is_active=True).select_related("user").order_by("user__username")
        ):
            hours = Liquidacion.hours_for(employee, date)
            rate = Decimal(employee.hourly_rate)
            gross = (hours * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            existing = Liquidacion.objects.filter(employee=employee, date=date).first()
            rows.append(
                {
                    "employee": employee,
                    "hours_worked": hours,
                    "hourly_rate": rate,
                    "gross_amount": gross,
                    "existing": existing,
                }
            )
        return rows

    def get(self, request):
        date = self._parse_date(request)
        if not request.GET.get("date"):
            # El template usa request.GET.date; garantizamos el parámetro.
            return redirect(f"{reverse('staff:liquidacion_create')}?date={date.isoformat()}")
        return render(
            request,
            "staff/liquidacion_create.html",
            {"selected_date": date, "date": date, "rows": self._preview(date)},
        )

    def post(self, request):
        date = self._parse_date(request)
        created = updated = 0
        for employee in Employee.objects.filter(is_active=True):
            hours = Liquidacion.hours_for(employee, date)
            if hours <= 0:
                continue  # solo se liquidan empleados con horas trabajadas > 0
            liqui, was_created = Liquidacion.build_or_update(employee, date, generated_by=request.user)
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
        audit.info(
            "liquidacion_generada por=%s fecha=%s creadas=%s actualizadas=%s",
            request.user.username, date, created, updated,
        )
        if created or updated:
            messages.success(
                request,
                f"Liquidaciones generadas para {date}: {created} creadas, {updated} actualizadas.",
            )
        else:
            messages.info(request, f"Ningún empleado con horas trabajadas el {date}.")
        return redirect("staff:liquidacion_list")


class LiquidacionDetailView(RoleRequiredMixin, DetailView):
    model = Liquidacion
    template_name = "staff/liquidacion_detail.html"
    context_object_name = "liquidacion"
    roles = STAFF_ROLES

    def get_queryset(self):
        return Liquidacion.objects.select_related("employee__user", "generated_by")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")
        try:
            if action == "liquidar":
                self.object.marcar_liquidada(user=request.user)
                audit.info(
                    "liquidacion_marcada_liquidada por=%s id=%s empleado=%s fecha=%s",
                    request.user.username, self.object.pk, self.object.employee_id, self.object.date,
                )
                messages.success(request, "Liquidación marcada como liquidada.")
            elif action == "pagar":
                self.object.marcar_pagada(user=request.user)
                audit.info(
                    "liquidacion_marcada_pagada por=%s id=%s empleado=%s fecha=%s",
                    request.user.username, self.object.pk, self.object.employee_id, self.object.date,
                )
                messages.success(request, "Liquidación marcada como pagada.")
            else:
                messages.error(request, "Acción inválida.")
        except ValidationError as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("staff:liquidacion_detail", pk=self.object.pk)


class LiquidacionCsvView(RoleRequiredMixin, View):
    """Exporta el listado filtrado de liquidaciones a CSV (safe_cell)."""

    roles = STAFF_ROLES

    def get(self, request):
        qs = (
            Liquidacion.objects.select_related("employee__user")
            .order_by("-date", "employee__user__username")
        )
        start_date = request.GET.get("start_date")
        if start_date:
            qs = qs.filter(date__gte=start_date)
        end_date = request.GET.get("end_date")
        if end_date:
            qs = qs.filter(date__lte=end_date)
        employee_id = request.GET.get("employee")
        if employee_id and employee_id.isdigit():
            qs = qs.filter(employee_id=int(employee_id))
        status = request.GET.get("status")
        if status in dict(Liquidacion.Status.choices):
            qs = qs.filter(status=status)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="liquidaciones.csv"'
        writer = csv.writer(response)
        writer.writerow(["Empleado", "Fecha", "Horas", "Tarifa hora", "Bruto", "Estado"])
        for liq in qs:
            writer.writerow(
                [
                    safe_cell(liq.employee.user.get_full_name() or liq.employee.user.username),
                    liq.date.isoformat(),
                    liq.hours_worked,
                    liq.hourly_rate,
                    liq.gross_amount,
                    safe_cell(liq.status),
                ]
            )
        return response
