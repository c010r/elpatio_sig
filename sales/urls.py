"""
sales — URLs del módulo ventas.
"""
from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("pos/", views.PosView.as_view(), name="pos"),
    # Sin prefijo "ventas/" repetido: la app ya está montada en /ventas/.
    path("", views.SaleListView.as_view(), name="sale_list"),
    path("<int:pk>/", views.SaleDetailView.as_view(), name="sale_detail"),
    path("<int:pk>/anular/", views.SaleVoidView.as_view(), name="sale_void"),
    path("caja/abrir/", views.CashRegisterOpenView.as_view(), name="cash_register_open"),
    path("caja/cerrar/", views.CashRegisterCloseView.as_view(), name="cash_register_close"),
    path("happy-hour/", views.HappyHourConfigView.as_view(), name="happy_hour_config"),
    path("configuracion/", views.SaleConfigView.as_view(), name="sale_config"),
]
