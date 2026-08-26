"""
customers — URLs del módulo clientes.
"""
from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("crear/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("<int:pk>/editar/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/eliminar/", views.CustomerDeleteView.as_view(), name="customer_delete"),
    path("<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("<int:pk>/canjear/", views.CustomerRedeemView.as_view(), name="customer_redeem"),
]
