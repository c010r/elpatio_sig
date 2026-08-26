"""
reservations — Admin de reservas.
"""
from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        "name", "phone", "table", "date", "start_time", "party_size", "status", "created_at",
    ]
    list_filter = ["status", "date"]
    search_fields = ["name", "phone"]
    readonly_fields = ["created_at"]
