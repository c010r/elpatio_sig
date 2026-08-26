"""
purchases — Admin de proveedores y órdenes de compra.
"""
from django.contrib import admin

from .models import PurchaseItem, PurchaseOrder, Supplier


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ["subtotal"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "contact_name", "phone", "cuit", "is_active"]
    search_fields = ["name", "contact_name", "cuit"]
    list_filter = ["is_active"]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "status", "total", "ordered_by", "created_at", "received_at"]
    list_filter = ["status"]
    search_fields = ["number", "supplier__name"]
    inlines = [PurchaseItemInline]
