"""
tables — Admin de mesas y comandas.
"""
from django.contrib import admin

from .models import Order, OrderItem, Table


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["unit_price", "requested_at"]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["number", "capacity", "zone", "status", "is_active"]
    list_filter = ["zone", "status", "is_active"]
    search_fields = ["number"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "table", "waiter", "status", "total", "opened_at", "closed_at"]
    list_filter = ["status"]
    search_fields = ["table__number", "waiter__username"]
    inlines = [OrderItemInline]
