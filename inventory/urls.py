"""
inventory — URLs del módulo inventario.
"""
from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("categorias/", views.CategoryListView.as_view(), name="category_list"),
    path("categorias/crear/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categorias/<int:pk>/editar/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("productos/", views.ProductListView.as_view(), name="product_list"),
    path("productos/crear/", views.ProductCreateView.as_view(), name="product_create"),
    path("productos/<int:pk>/editar/", views.ProductUpdateView.as_view(), name="product_update"),
    path("productos/<int:pk>/eliminar/", views.ProductDeleteView.as_view(), name="product_delete"),
    path("movimientos/", views.StockMovementListView.as_view(), name="stock_movement_list"),
    path("movimientos/crear/", views.StockMovementCreateView.as_view(), name="stock_movement_create"),
    path("stock-bajo/", views.StockLowView.as_view(), name="stock_low"),
]
