"""
reports — URLs del módulo reportes.
"""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("ventas/", views.sales_report, name="sales_report"),
    path("ventas/csv/", views.sales_report_csv, name="sales_report_csv"),
    path("productos/", views.products_report, name="products_report"),
    path("productos/csv/", views.products_report_csv, name="products_report_csv"),
    path("ganancia/", views.profit_report, name="profit_report"),
    path("ganancia/csv/", views.profit_report_csv, name="profit_report_csv"),
    path("inventario/", views.inventory_value_report, name="inventory_value_report"),
    path("inventario/csv/", views.inventory_value_report_csv, name="inventory_value_report_csv"),
]
