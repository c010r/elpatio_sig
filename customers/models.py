"""
customers — Modelos de clientes y configuración de fidelización.
"""
from decimal import Decimal

from django.core.cache import cache
from django.db import models
from django.db.models import F

CACHE_KEY_LOYALTY = "loyalty_config_solo"


class Customer(models.Model):
    """Cliente con puntos de fidelización."""

    name = models.CharField("nombre", max_length=150)
    phone = models.CharField("teléfono", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    dni = models.CharField("DNI", max_length=20, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    points = models.PositiveIntegerField("puntos de fidelización", default=0)
    notes = models.TextField("notas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def earn_points(self, total):
        """Suma puntos = floor(total / puntos_por_moneda) usando la config singleton."""
        config = LoyaltyConfig.get_solo()
        points = int(total // config.points_per_currency)
        if points > 0:
            Customer.objects.filter(pk=self.pk).update(points=F("points") + points)


class LoyaltyConfig(models.Model):
    """Configuración singleton de fidelización (una sola fila, pk=1, valores cacheados)."""

    points_per_currency = models.DecimalField(
        "puntos por moneda", max_digits=10, decimal_places=2, default=Decimal("1")
    )
    points_required_for_discount = models.PositiveIntegerField("puntos para descuento", default=100)
    discount_amount = models.DecimalField(
        "monto del descuento", max_digits=10, decimal_places=2, default=Decimal("10")
    )

    class Meta:
        verbose_name = "configuración de fidelización"
        verbose_name_plural = "configuración de fidelización"

    def __str__(self):
        return "Configuración de fidelización"

    @classmethod
    def get_solo(cls):
        """Devuelve la config única con caché (5 minutos); la crea si no existe."""
        config = cache.get(CACHE_KEY_LOYALTY)
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_LOYALTY, config, 300)
        return config

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_LOYALTY)
