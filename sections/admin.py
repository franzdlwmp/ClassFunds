from django.contrib import admin
from .models import Course, Section

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "treasurer", "is_active")
    list_filter = ("course", "is_active")

    def has_delete_permission(self, request, obj =None):
        return False
