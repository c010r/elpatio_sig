"""
tables — URLs del módulo mesas.
"""
from django.urls import path

from . import views

app_name = "tables"

urlpatterns = [
    path("", views.TableMapView.as_view(), name="table_map"),
    path("mesas/crear/", views.TableCreateView.as_view(), name="table_create"),
    path("mesas/<int:pk>/editar/", views.TableUpdateView.as_view(), name="table_update"),
    path("mesas/<int:pk>/eliminar/", views.TableDeleteView.as_view(), name="table_delete"),
    path("comandas/crear/<int:table_pk>/", views.OrderCreateView.as_view(), name="order_create"),
    path("comandas/<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    path("comandas/<int:pk>/agregar-item/", views.OrderAddItemView.as_view(), name="order_add_item"),
    path("comandas/items/<int:pk>/estado/", views.OrderItemStatusView.as_view(), name="order_item_status"),
    path("comandas/<int:pk>/cerrar/", views.OrderCloseView.as_view(), name="order_close"),
]
