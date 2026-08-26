"""
accounts — Vistas de gestión de usuarios (solo admin).
"""
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import UserCreateForm, UserUpdateForm


class UserListView(RoleRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    roles = ["admin"]

    def get_queryset(self):
        return User.objects.all().order_by("username")


class UserCreateView(RoleRequiredMixin, CreateView):
    form_class = UserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
    roles = ["admin"]

    def form_valid(self, form):
        messages.success(self.request, "Usuario creado.")
        return super().form_valid(form)


class UserUpdateView(RoleRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
    roles = ["admin"]

    def form_valid(self, form):
        messages.success(self.request, "Usuario actualizado.")
        return super().form_valid(form)


class UserToggleActiveView(RoleRequiredMixin, View):
    """Activa/desactiva un usuario (solo POST)."""

    roles = ["admin"]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "activado" if user.is_active else "desactivado"
        messages.success(request, f"Usuario '{user.username}' {state}.")
        return redirect("accounts:user_list")
