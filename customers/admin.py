"""
customers — Admin de clientes y configuración de fidelización.
"""
from django.contrib import admin

from .models import Customer, LoyaltyConfig


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "email", "dni", "points", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "phone", "dni", "email"]


@admin.register(LoyaltyConfig)
class LoyaltyConfigAdmin(admin.ModelAdmin):
    list_display = [
        "points_per_currency", "points_required_for_discount", "discount_amount",
    ]

    def has_add_permission(self, request):
        return not LoyaltyConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
