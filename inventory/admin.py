"""
inventory — Admin de categorías, productos y movimientos de stock.
"""
from django.contrib import admin

from .models import Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    search_fields = ["name"]
    list_filter = ["is_active"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name", "category", "unit", "purchase_price", "sale_price",
        "stock_current", "stock_min", "barcode", "is_active",
    ]
    list_filter = ["category", "is_active", "unit"]
    search_fields = ["name", "barcode"]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["product", "movement_type", "quantity", "user", "reference", "created_at"]
    list_filter = ["movement_type"]
    search_fields = ["product__name", "reference"]
    readonly_fields = ["created_at"]
