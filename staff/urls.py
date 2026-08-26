"""
staff — URLs del módulo empleados.
"""
from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("", views.EmployeeListView.as_view(), name="employee_list"),
    path("crear/", views.EmployeeCreateView.as_view(), name="employee_create"),
    path("<int:pk>/editar/", views.EmployeeUpdateView.as_view(), name="employee_update"),
    path("<int:pk>/eliminar/", views.EmployeeDeleteView.as_view(), name="employee_delete"),
    path("turnos/", views.ShiftListView.as_view(), name="shift_list"),
    path("turnos/crear/", views.ShiftCreateView.as_view(), name="shift_create"),
    path("turnos/<int:pk>/editar/", views.ShiftUpdateView.as_view(), name="shift_update"),
    path("turnos/<int:pk>/eliminar/", views.ShiftDeleteView.as_view(), name="shift_delete"),
    path("mi-turno/", views.MyShiftView.as_view(), name="my_shift"),
]
