"""
core — URLs del módulo core (dashboard, home).
"""
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Login personalizado (reutiliza las vistas de auth de Django)
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
