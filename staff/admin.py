"""
staff — Admin de empleados y turnos.
"""
from django.contrib import admin

from .models import Employee, Shift


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["user", "position", "hire_date", "hourly_rate", "is_active"]
    list_filter = ["position", "is_active"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["employee", "date", "start_time", "end_time", "worked_hours"]
    list_filter = ["date"]
    search_fields = ["employee__user__username"]
