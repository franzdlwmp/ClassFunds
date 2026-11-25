from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomerUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role", "must_change_pass")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Role", {"fields": ("role","must_change_pass")}),)

    def has_delete_permission(self, request, obj = None):
        return False

