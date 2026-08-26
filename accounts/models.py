"""
accounts — Perfil de usuario ligado al User de Django.
"""
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """Datos extra del usuario. El rol se deriva del grupo principal."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="usuario",
    )
    phone = models.CharField("teléfono", max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfiles"

    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.username}"

    @property
    def role_label(self):
        """Rol derivado del grupo principal del usuario."""
        group = self.user.groups.first()
        return group.name if group else "—"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Crea el Profile automáticamente al crear un User."""
    if created:
        Profile.objects.create(user=instance)
