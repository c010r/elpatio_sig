"""
sales — Admin de cajas, ventas e ítems.
"""
from django.contrib import admin

from .models import CashRegister, Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ["unit_price", "subtotal"]


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = [
        "id", "opened_by", "opened_at", "closed_at", "opening_amount",
        "expected_amount", "actual_amount", "status",
    ]
    list_filter = ["status"]
    readonly_fields = ["opened_at", "closed_at", "expected_amount"]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        "ticket_number", "user", "table", "customer", "subtotal",
        "discount", "total", "payment_method", "status", "created_at",
    ]
    list_filter = ["status", "payment_method", "created_at"]
    search_fields = ["ticket_number"]
    readonly_fields = ["ticket_number", "created_at", "voided_by", "voided_at"]
    inlines = [SaleItemInline]
