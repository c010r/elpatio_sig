"""
accounts — Vistas de gestión de usuarios (solo admin).

Seguridad Fase 2 (SECURITY.md §8.2):
- F2-02: se bloquea la auto-desactivación/auto-democión y la
  desactivación/democión del ÚLTIMO administrador activo (evita lockout total).
- F2-03: eventos de auditoría (logger "audit") en crear/editar/toggle.
"""
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import RoleRequiredMixin

from .forms import UserCreateForm, UserUpdateForm

audit = logging.getLogger("audit")
User = get_user_model()


def _is_admin_user(user):
    """True si el usuario es administrador (superuser o grupo 'admin')."""
    return user.is_superuser or user.groups.filter(name="admin").exists()


def _count_active_admins():
    """Cantidad de usuarios activos que son administradores (sin duplicar)."""
    by_group = set(
        User.objects.filter(is_active=True, groups__name="admin").values_list("pk", flat=True)
    )
    superusers = set(
        User.objects.filter(is_active=True, is_superuser=True).values_list("pk", flat=True)
    )
    return len(by_group | superusers)


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
        group = form.cleaned_data.get("group")
        audit.info(
            "usuario_creado por=%s usuario=%s grupo=%s",
            self.request.user.username, form.cleaned_data["username"],
            group.name if group else "ninguno",
        )
        messages.success(self.request, "Usuario creado.")
        return super().form_valid(form)


class UserUpdateView(RoleRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
    roles = ["admin"]

    def form_valid(self, form):
        user = self.object
        new_group = form.cleaned_data.get("group")
        will_be_active = form.cleaned_data.get("is_active", user.is_active)
        will_be_admin = user.is_superuser or (new_group is not None and new_group.name == "admin")
        is_admin_now = _is_admin_user(user)
        active_admins = _count_active_admins()

        # F2-02: no auto-desactivación ni auto-democión.
        if user.pk == self.request.user.pk and (not will_be_active or (is_admin_now and not will_be_admin)):
            audit.warning(
                "usuario_auto_demote_bloqueado por=%s usuario=%s",
                self.request.user.username, user.username,
            )
            messages.error(self.request, "No podés desactivarte ni quitarte el rol de admin a vos mismo.")
            return redirect("accounts:user_list")

        # F2-02: no demotar ni desactivar al último administrador activo.
        if is_admin_now and active_admins <= 1:
            if will_be_active and not will_be_admin:
                audit.warning(
                    "usuario_ultimo_admin_demote_bloqueado por=%s usuario=%s",
                    self.request.user.username, user.username,
                )
                messages.error(self.request, "No podés demotar al último administrador activo.")
                return redirect("accounts:user_list")
            if not will_be_active:
                audit.warning(
                    "usuario_ultimo_admin_desactivacion_bloqueada por=%s usuario=%s",
                    self.request.user.username, user.username,
                )
                messages.error(self.request, "No podés desactivar al último administrador activo.")
                return redirect("accounts:user_list")

        audit.info(
            "usuario_editado por=%s usuario=%s grupo=%s activo=%s",
            self.request.user.username, user.username,
            new_group.name if new_group else "ninguno", will_be_active,
        )
        messages.success(self.request, "Usuario actualizado.")
        return super().form_valid(form)


class UserToggleActiveView(RoleRequiredMixin, View):
    """Activa/desactiva un usuario (solo POST)."""

    roles = ["admin"]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # F2-02: no auto-desactivación.
        if user.pk == request.user.pk:
            audit.warning(
                "usuario_toggle_auto_bloqueado por=%s usuario=%s",
                request.user.username, user.username,
            )
            messages.error(request, "No podés desactivarte a vos mismo.")
            return redirect("accounts:user_list")

        # F2-02: no desactivar al último administrador activo.
        if user.is_active and _is_admin_user(user) and _count_active_admins() <= 1:
            audit.warning(
                "usuario_toggle_ultimo_admin_bloqueado por=%s usuario=%s",
                request.user.username, user.username,
            )
            messages.error(request, "No podés desactivar al último administrador activo.")
            return redirect("accounts:user_list")

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        audit.info(
            "usuario_toggle por=%s usuario=%s activo=%s",
            request.user.username, user.username, user.is_active,
        )
        state = "activado" if user.is_active else "desactivado"
        messages.success(request, f"Usuario '{user.username}' {state}.")
        return redirect("accounts:user_list")
