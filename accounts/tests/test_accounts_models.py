"""
accounts — Tests de MODELOS (ejecutan cuando el backend implementa los modelos).

Reglas del contrato (CONTRACT.md):
- Profile OneToOne con User; rol derivado del grupo principal (role_label).
- Señal post_save crea Profile al crear User.
"""
import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

try:
    from accounts.models import Profile
except ImportError:
    pytest.skip("Backend de accounts no implementado aún", allow_module_level=True)

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_profile_autocreado_al_crear_user():
    user = User.objects.create_user(username="nuevo_usuario", password="test-pass-123")
    assert Profile.objects.filter(user=user).count() == 1


def test_profile_role_label_del_grupo(user_factory, bartender_group):
    user = user_factory("empleado_grupo", group=bartender_group)
    assert user.profile.role_label == "bartender"


def test_profile_role_label_sin_grupo():
    user = User.objects.create_user(username="sin_grupo", password="test-pass-123")
    assert user.profile.role_label == "—"


def test_profile_unico_por_usuario():
    user = User.objects.create_user(username="con_perfil", password="test-pass-123")
    with pytest.raises(IntegrityError):
        Profile.objects.create(user=user)
