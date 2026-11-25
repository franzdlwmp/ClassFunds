from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import ContactSettings, User


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
        self.fields["username"].widget.attrs["autofocus"] = True


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"email": "Email (optional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


class ContactSettingsForm(forms.ModelForm):
    class Meta:
        model = ContactSettings
        fields = ["email", "messenger"]
        labels = {"email": "Admin email", "messenger": "Messenger link"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"