from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        TREASURER = "treasurer", "Treasurer"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TREASURER)
    must_change_pass = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:          # superusers are always administrators
            self.role = self.Role.ADMIN
            if self._state.adding:
                self.must_change_pass = False
        super().save(*args, **kwargs)


class ContactSettings(models.Model):
    """One row only: the contact details shown in the login page's Contact admin box."""
    email = models.EmailField()
    messenger = models.URLField(max_length=200)

    class Meta:
        verbose_name_plural = "contact settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        found = cls.objects.filter(pk=1).first()
        if found:
            return found
        return cls(
            pk=1,
            email=getattr(settings, "ADMIN_CONTACT_EMAIL", ""),
            messenger=getattr(settings, "ADMIN_CONTACT_MESSENGER", ""),
        )