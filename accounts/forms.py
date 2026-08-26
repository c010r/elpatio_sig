"""
accounts — Formularios de gestión de usuarios (admin).

Seguridad Fase 2 (SECURITY.md §8.2):
- F2-01: contraseña validada contra AUTH_PASSWORD_VALIDATORS (crear y editar).
- F2-04: los grupos se conservan (no se reemplazan todos con `groups.set`).
"""
from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password


class UserCreateForm(forms.ModelForm):
    """Crea un usuario y le asigna grupo/rol."""

    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    group = forms.ModelChoiceField(label="Grupo / rol", queryset=Group.objects.all(), required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def clean_password(self):
        password = self.cleaned_data["password"]
        # F2-01: aplica la política de contraseñas del proyecto.
        validate_password(password, user=self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            group = self.cleaned_data.get("group")
            if group:
                user.groups.add(group)
        return user


class UserUpdateForm(forms.ModelForm):
    """Edita datos, contraseña (opcional) y grupo/rol de un usuario existente."""

    group = forms.ModelChoiceField(label="Grupo / rol", queryset=Group.objects.all(), required=False)
    password = forms.CharField(
        label="Nueva contraseña (opcional)",
        widget=forms.PasswordInput,
        required=False,
        help_text="Dejá vacío para conservar la contraseña actual.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["group"].initial = self.instance.groups.first()
            self._previous_group = self.instance.groups.first()

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        if password:
            # F2-01: aplica la política de contraseñas (con el usuario como contexto).
            validate_password(password, user=self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            password = self.cleaned_data.get("password")
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])
            # F2-04: conserva los grupos existentes; solo cambia el rol principal.
            previous = getattr(self, "_previous_group", None)
            new_group = self.cleaned_data.get("group")
            if new_group and new_group != previous:
                user.groups.add(new_group)
            if previous and new_group != previous:
                user.groups.remove(previous)
        return user
