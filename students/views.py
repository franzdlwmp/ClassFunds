from finance.services import add_student_to_open_collections
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView
from accounts.permissions import TreasurerRequiredMixin
from .forms import StudentForm
from .models import Student


def get_section(user):
    return getattr(user, "section", None)


class SectionRequiredMixin(TreasurerRequiredMixin):
    """A treasurer without a section sees the 'not assigned' page instead."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == "treasurer" \
                and get_section(request.user) is None:
            return render(request, "no_section.html")
        return super().dispatch(request, *args, **kwargs)


class StudentListView(SectionRequiredMixin, ListView):
    template_name = "students/list.html"
    context_object_name = "students"

    def get_queryset(self):
        students = Student.objects.filter(section=get_section(self.request.user))
        q = self.request.GET.get("q", "").strip()
        if q:
            students = students.filter(
                Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(student_number__icontains=q)
            )
        return students

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["section"] = get_section(self.request.user)
        ctx["q"] = self.request.GET.get("q", "").strip()
        return ctx


class StudentFormMixin(SectionRequiredMixin):
    model = Student
    form_class = StudentForm
    template_name = "students/form.html"
    success_url = reverse_lazy("students")

    def get_queryset(self):
        return Student.objects.filter(section=get_section(self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["section"] = get_section(self.request.user)
        return kwargs


class StudentCreateView(StudentFormMixin, CreateView):
    def form_valid(self, form):
        form.instance.section = get_section(self.request.user)
        response = super().form_valid(form)
        add_student_to_open_collections(self.object)
        messages.success(self.request, "Student added. They will set their PIN at their first payment.")
        return response


class StudentUpdateView(StudentFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "Student updated.")
        return super().form_valid(form)


def own_student(request, pk):
    section = get_section(request.user)
    if request.user.role != "treasurer" or section is None:
        raise PermissionDenied
    return get_object_or_404(Student, pk=pk, section=section)


@login_required
@require_POST
def reset_pin(request, pk):
    student = own_student(request, pk)
    student.reset_pin()
    messages.success(request, f"PIN reset for {student}. They will set a new one at their next payment.")
    return redirect("students")


@login_required
@require_POST
def toggle_active(request, pk):
    student = own_student(request, pk)
    student.is_active = not student.is_active
    student.save(update_fields=["is_active"])
    if student.is_active:
        add_student_to_open_collections(student)
    state = "activated" if student.is_active else "deactivated"
    messages.success(request, f"{student} {state}.")
    return redirect("students")