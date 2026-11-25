from django.urls import path
from . import views

urlpatterns =[
    path("", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("treasurers/", views.TreasurerListView.as_view(), name="treasurers"),
    path("treasurers/add/", views.RegisterTreasurerView.as_view(), name="treasurer_add"),
    path("treasurers/<int:pk>/reset/", views.reset_treasurer_password, name="treasurer_reset"),
    path("treasurers/<int:pk>/toggle/", views.toggle_treasurer, name="treasurer_toggle"),
    path("sections/", views.SectionListView.as_view(), name="sections"),
    path("sections/add/", views.SectionCreateView.as_view(), name="section_add"),
    path("sections/<int:pk>/edit/", views.SectionUpdateView.as_view(), name="section_edit"),
    path("courses/add/", views.CourseCreateView.as_view(), name="course_add"),
    path("courses/<int:pk>/toggle/", views.toggle_course, name="course_toggle"),
    path("courses/<int:pk>/edit/", views.CourseUpdateView.as_view(), name="course_edit"),
    path("settings/", views.AdminSettingsView.as_view(), name="admin_settings"),
]