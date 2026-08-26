"""
purchases — URLs del módulo compras.
"""
from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("proveedores/", views.SupplierListView.as_view(), name="supplier_list"),
    path("proveedores/crear/", views.SupplierCreateView.as_view(), name="supplier_create"),
    path("proveedores/<int:pk>/editar/", views.SupplierUpdateView.as_view(), name="supplier_update"),
    path("proveedores/<int:pk>/eliminar/", views.SupplierDeleteView.as_view(), name="supplier_delete"),
    path("", views.PurchaseListView.as_view(), name="purchase_list"),
    path("crear/", views.PurchaseCreateView.as_view(), name="purchase_create"),
    path("<int:pk>/editar/", views.PurchaseUpdateView.as_view(), name="purchase_update"),
    path("<int:pk>/", views.PurchaseDetailView.as_view(), name="purchase_detail"),
    path("<int:pk>/recibir/", views.PurchaseReceiveView.as_view(), name="purchase_receive"),
    path("<int:pk>/cancelar/", views.PurchaseCancelView.as_view(), name="purchase_cancel"),
]
