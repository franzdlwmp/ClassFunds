from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from sections.models import Course, Section

User = get_user_model()

class TreasurerForm(forms.ModelForm):
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(), required=True, empty_label="Select a course",
        label="Course (optional)",
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.none(), required=False, empty_label="No section yet",
        label="Section (optional)",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]
        labels = {"email": "Email (optional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["course"].queryset = Course.objects.filter(is_active=True).order_by("code")
        self.fields["course"].label_from_instance = lambda c: f"{c.code} · {c.name}"
        self.fields["section"].queryset = Section.objects.filter(is_active=True).filter(
            Q(treasurer__isnull=True) | Q(treasurer__is_active=False)
        ).select_related("course", "treasurer")

        def section_label(s):
            text = f"{s.name} ({s.course.code})"
            if s.treasurer_id:
                text += f", replaces {s.treasurer.get_full_name() or s.treasurer.username} (inactive)"
            return text

        self.fields["section"].label_from_instance = section_label
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        data = super().clean()
        course, section = data.get("course"), data.get("section")
        if section and course and section.course_id != course.pk:
            self.add_error("section", "That section belongs to a different course.")
        return data

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "name"]
        labels = {"code": "Course code", "name": "Full course name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["course", "name", "treasurer"]
        labels = {"name": "Section name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance
        if current.pk:
            courses = Course.objects.filter(Q(is_active=True) | Q(pk=current.course_id))
        else:
            courses = Course.objects.filter(is_active=True)
        self.fields["course"].queryset = courses
        self.fields["course"].label_from_instance = lambda c: f"{c.code} · {c.name}"
        available = Q(is_active=True, section__isnull=True)
        if current.treasurer_id:
            available |= Q(pk=current.treasurer_id)
        self.fields["treasurer"].queryset = User.objects.filter(role=User.Role.TREASURER).filter(available)
        self.fields["treasurer"].empty_label = "No treasurer yet"
        self.fields["treasurer"].label_from_instance = lambda u: f"{u.get_full_name() or u.username} ({u.username})"
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "input"


class SectionEditForm(SectionForm):
    class Meta(SectionForm.Meta):
        fields = ["course", "name", "treasurer", "is_active"]
        labels = {"name": "Section name", "is_active": "Active"}