from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["student_number", "last_name", "first_name"]

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean_student_number(self):
        number = self.cleaned_data["student_number"].strip()
        taken = Student.objects.filter(section=self.section, student_number=number)
        taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("A student with this number is already in your section.")
        return number