"""
reservations — URLs del módulo reservas.
"""
from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("", views.ReservationListView.as_view(), name="reservation_list"),
    path("crear/", views.ReservationCreateView.as_view(), name="reservation_create"),
    path("<int:pk>/editar/", views.ReservationUpdateView.as_view(), name="reservation_update"),
    path("<int:pk>/eliminar/", views.ReservationDeleteView.as_view(), name="reservation_delete"),
    path("hoy/", views.ReservationTodayView.as_view(), name="reservation_today"),
    path("<int:pk>/confirmar/", views.ReservationConfirmView.as_view(), name="reservation_confirm"),
    path("<int:pk>/cancelar/", views.ReservationCancelView.as_view(), name="reservation_cancel"),
]
