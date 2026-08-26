"""
accounts — Admin de perfiles (el User se registra con ProfileInline).
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "first_name", "last_name", "email", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff", "groups"]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "phone", "role_label", "created_at"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "phone"]
