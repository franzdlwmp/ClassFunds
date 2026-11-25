from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout", views.logout_view, name="logout"),
    path("password/", views.AppPasswordChangeView.as_view(), name="password_change"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
]