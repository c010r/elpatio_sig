"""
accounts — Formularios de gestión de usuarios (admin).
"""
from django import forms
from django.contrib.auth.models import Group, User


class UserCreateForm(forms.ModelForm):
    """Crea un usuario y le asigna grupo/rol."""

    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    group = forms.ModelChoiceField(label="Grupo / rol", queryset=Group.objects.all(), required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            group = self.cleaned_data.get("group")
            user.groups.set([group] if group else [])
        return user


class UserUpdateForm(forms.ModelForm):
    """Edita datos y grupo/rol de un usuario existente."""

    group = forms.ModelChoiceField(label="Grupo / rol", queryset=Group.objects.all(), required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["group"].initial = self.instance.groups.first()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            group = self.cleaned_data.get("group")
            user.groups.set([group] if group else [])
        return user
