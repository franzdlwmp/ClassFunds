from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .forms import LoginForm, ProfileForm, StyledPasswordChangeForm
from .models import ContactSettings, User
from .permissions import TreasurerRequiredMixin


class AppLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contact = ContactSettings.load()
        ctx["admin_email"] = contact.email
        ctx["admin_messenger"] = contact.messenger
        return ctx


class AppPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_pass = False
        self.request.user.save(update_fields=["must_change_pass"])
        messages.success(self.request, "Your password has been changed.")
        return response


class AccountSettingsMixin:
    """The Profile and Change password cards, shared by the treasurer and admin Settings pages."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("profile_form", ProfileForm(instance=self.request.user))
        ctx.setdefault("password_form", StyledPasswordChangeForm(self.request.user))
        return ctx

    def post(self, request, *args, **kwargs):
        which = request.POST.get("form")
        if which == "profile":
            # a fresh copy, so a failed save can't change the name shown in the top bar
            form = ProfileForm(request.POST, instance=User.objects.get(pk=request.user.pk))
            if form.is_valid():
                form.save()
                messages.success(request, "Profile saved.")
                return redirect(request.path)
            return self.render_to_response(self.get_context_data(profile_form=form))
        if which == "password":
            form = StyledPasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, request.user)   # keeps you logged in
                messages.success(request, "Password changed.")
                return redirect(request.path)
            return self.render_to_response(self.get_context_data(password_form=form))
        return redirect(request.path)


class SettingsView(AccountSettingsMixin, TreasurerRequiredMixin, TemplateView):
    template_name = "accounts/settings.html"


@login_required
def home(request):
    if request.user.role == "admin":
        return redirect("admin_dashboard")
    return redirect("dashboard")


def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have logged out.")
    return redirect("login")