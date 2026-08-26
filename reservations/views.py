"""
reservations — Vistas de reservas: listado, CRUD, agenda de hoy, confirmar/cancelar.
"""
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import ReservationForm
from .models import Reservation


class ReservationListView(RoleRequiredMixin, ListView):
    model = Reservation
    template_name = "reservations/reservation_list.html"
    context_object_name = "reservations"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        qs = (
            Reservation.objects.select_related("table", "customer")
            .order_by("date", "start_time")
        )
        status = self.request.GET.get("status")
        if status in dict(Reservation.Status.choices):
            qs = qs.filter(status=status)
        return qs


class ReservationCreateView(RoleRequiredMixin, CreateView):
    model = Reservation
    form_class = ReservationForm
    template_name = "reservations/reservation_form.html"
    success_url = reverse_lazy("reservations:reservation_list")
    roles = ["gerente", "admin"]

    def get_initial(self):
        return {"date": timezone.localdate()}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Reserva creada.")
        return super().form_valid(form)


class ReservationUpdateView(RoleRequiredMixin, UpdateView):
    model = Reservation
    form_class = ReservationForm
    template_name = "reservations/reservation_form.html"
    success_url = reverse_lazy("reservations:reservation_list")
    roles = ["gerente", "admin"]

    def form_valid(self, form):
        messages.success(self.request, "Reserva actualizada.")
        return super().form_valid(form)


class ReservationDeleteView(RoleRequiredMixin, DeleteView):
    """Elimina una reserva (solo POST)."""

    model = Reservation
    success_url = reverse_lazy("reservations:reservation_list")
    roles = ["gerente", "admin"]
    http_method_names = ["post"]

    def form_valid(self, form):
        messages.success(self.request, "Reserva eliminada.")
        return super().form_valid(form)


class ReservationTodayView(RoleRequiredMixin, ListView):
    """Agenda de reservas de hoy."""

    model = Reservation
    template_name = "reservations/reservation_today.html"
    context_object_name = "reservations"
    roles = ["gerente", "admin"]

    def get_queryset(self):
        return (
            Reservation.objects.filter(date=timezone.localdate())
            .select_related("table", "customer")
            .order_by("start_time")
        )


class ReservationConfirmView(RoleRequiredMixin, View):
    """Confirma una reserva (solo POST)."""

    roles = ["gerente", "admin"]

    def post(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk)
        if reservation.status == Reservation.Status.CANCELADA:
            messages.error(request, "No se puede confirmar una reserva cancelada.")
        else:
            reservation.status = Reservation.Status.CONFIRMADA
            reservation.save(update_fields=["status"])
            messages.success(request, "Reserva confirmada.")
        return redirect("reservations:reservation_list")


class ReservationCancelView(RoleRequiredMixin, View):
    """Cancela una reserva (solo POST)."""

    roles = ["gerente", "admin"]

    def post(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk)
        reservation.status = Reservation.Status.CANCELADA
        reservation.save(update_fields=["status"])
        messages.success(request, "Reserva cancelada.")
        return redirect("reservations:reservation_list")
