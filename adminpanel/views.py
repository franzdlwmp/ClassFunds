from accounts.forms import ContactSettingsForm
from accounts.models import ContactSettings
from accounts.views import AccountSettingsMixin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from accounts.permissions import AdminRequiredMixin
from sections.models import Course, Section
from students.models import Student

from .forms import CourseForm, SectionEditForm, SectionForm, TreasurerForm

User = get_user_model()

PASSWORD_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def temp_password():
    return get_random_string(10, allowed_chars=PASSWORD_CHARS)

def stash_credentials(request, user, password, title, note):
    """Keep a one-time password in the session so the next page can show it in a modal."""
    request.session["new_credentials"] = {
        "title": title,
        "note": note,
        "name": user.get_full_name() or user.username,
        "username": user.username,
        "password": password,
    }


def pop_credentials(request):
    return request.session.pop("new_credentials", None)


def treasurer_queryset(q=""):
    users = User.objects.filter(role=User.Role.TREASURER)
    for term in q.split():
        users = users.filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(username__icontains=term)
            | Q(section__name__icontains=term)
            | Q(section__course__code__icontains=term)
        )
    return (
        users.select_related("section__course")
        .annotate(student_count=Count("section__students", filter=Q(section__students__is_active=True)))
        .order_by("last_name", "first_name")
    )


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sections = Section.objects.filter(is_active=True)
        ctx.update(
            treasurer_count=User.objects.filter(role=User.Role.TREASURER, is_active=True).count(),
            section_count=sections.count(),
            sections_without=sections.filter(treasurer__isnull=True).count(),
            student_count=Student.objects.filter(is_active=True).count(),
            treasurers=treasurer_queryset()[:6],
        )
        ctx["credentials"] = pop_credentials(self.request)
        return ctx


class TreasurerListView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/treasurers.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        ctx["q"] = q
        ctx["treasurers"] = treasurer_queryset(q)
        ctx["credentials"] = pop_credentials(self.request)
        return ctx


class RegisterTreasurerView(AdminRequiredMixin, FormView):
    form_class = TreasurerForm
    template_name = "adminpanel/register_treasurer.html"
    success_url = reverse_lazy("treasurers")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        free = (
            Section.objects.filter(is_active=True)
            .filter(Q(treasurer__isnull=True) | Q(treasurer__is_active=False))
            .select_related("treasurer")
            .order_by("name")
        )
        by_course = {}
        for s in free:
            label = s.name
            if s.treasurer_id:
                label += f" (replaces {s.treasurer.get_full_name() or s.treasurer.username}, inactive)"
            by_course.setdefault(str(s.course_id), []).append({"id": s.pk, "name": label})
        ctx["sections_by_course"] = by_course
        return ctx

    def form_valid(self, form):
        user = form.save(commit=False)
        user.role = User.Role.TREASURER
        user.must_change_pass = True
        password = temp_password()
        user.set_password(password)
        user.save()
        section = form.cleaned_data["section"]
        if section:
            section.treasurer = user
            section.save(update_fields=["treasurer"])
        stash_credentials(
            self.request, user, password, "Treasurer registered",
            "They can now sign in. They'll be asked to change this password at their first login.",
        )
        return redirect(self.success_url)


def _back(request):
    return redirect("admin_dashboard" if request.POST.get("next") == "admin_dashboard" else "treasurers")


@login_required
@require_POST
def reset_treasurer_password(request, pk):
    if request.user.role != "admin":
        raise PermissionDenied
    user = get_object_or_404(User, pk=pk, role=User.Role.TREASURER)
    password = temp_password()
    user.set_password(password)
    user.must_change_pass = True
    user.save()
    stash_credentials(
        request, user, password, "Password reset",
        "The old password no longer works. They'll be asked to change this one at their next login.",
    )
    return _back(request)


@login_required
@require_POST
def toggle_treasurer(request, pk):
    if request.user.role != "admin":
        raise PermissionDenied
    user = get_object_or_404(User, pk=pk, role=User.Role.TREASURER)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    state = "activated" if user.is_active else "deactivated"
    messages.success(request, f"{user.username} was {state}.")
    return _back(request)

class SectionListView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/sections.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sections = (
            Section.objects.select_related("course", "treasurer")
            .annotate(student_count=Count("students", filter=Q(students__is_active=True)))
            .order_by("course__code", "name")
        )
        course_filter = self.request.GET.get("course", "all")
        if course_filter.isdigit():
            sections = sections.filter(course_id=int(course_filter))
        else:
            course_filter = "all"
        ctx.update(
            courses=Course.objects.annotate(section_count=Count("sections")).order_by("code"),
            sections=sections,
            course_filter=course_filter,
        )
        return ctx


class CourseCreateView(AdminRequiredMixin, FormView):
    form_class = CourseForm
    template_name = "adminpanel/course_form.html"
    success_url = reverse_lazy("sections")

    def form_valid(self, form):
        course = form.save()
        messages.success(self.request, f"Course {course.code} was added.")
        return redirect(self.success_url)


@login_required
@require_POST
def toggle_course(request, pk):
    if request.user.role != "admin":
        raise PermissionDenied
    course = get_object_or_404(Course, pk=pk)
    course.is_active = not course.is_active
    course.save(update_fields=["is_active"])
    state = "activated" if course.is_active else "deactivated"
    messages.success(request, f"Course {course.code} was {state}.")
    return redirect("sections")


class SectionCreateView(AdminRequiredMixin, CreateView):
    form_class = SectionForm
    template_name = "adminpanel/section_form.html"
    success_url = reverse_lazy("sections")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Add section"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Section {self.object.name} was added.")
        return response


class SectionUpdateView(AdminRequiredMixin, UpdateView):
    model = Section
    form_class = SectionEditForm
    template_name = "adminpanel/section_form.html"
    success_url = reverse_lazy("sections")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Edit section"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Section {self.object.name} was updated.")
        return response

class CourseUpdateView(AdminRequiredMixin, UpdateView):
    model = Course
    form_class = CourseForm
    template_name = "adminpanel/course_form.html"
    success_url = reverse_lazy("sections")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Course {self.object.code} was updated.")
        return response

class AdminSettingsView(AccountSettingsMixin, AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/settings.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("contact_form", ContactSettingsForm(instance=ContactSettings.load()))
        return ctx

    def post(self, request, *args, **kwargs):
        if request.POST.get("form") == "contact":
            form = ContactSettingsForm(request.POST, instance=ContactSettings.load())
            if form.is_valid():
                form.save()
                messages.success(request, "Contact details saved.")
                return redirect(request.path)
            return self.render_to_response(self.get_context_data(contact_form=form))
        return super().post(request, *args, **kwargs)