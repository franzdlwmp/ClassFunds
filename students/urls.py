from django.urls import path
from . import views

urlpatterns = [
    path("", views.StudentListView.as_view(), name="students"),
    path("add/", views.StudentCreateView.as_view(), name="student_add"),
    path("<int:pk>/edit/", views.StudentUpdateView.as_view(), name="student_edit"),
    path("<int:pk>/reset-pin/", views.reset_pin, name="student_reset_pin"),
    path("<int:pk>/toggle/", views.toggle_active, name="student_toggle"),
]