from django.db import models
from django.conf import settings

class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code

class Section(models.Model):
    name = models.CharField(max_length=40)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="sections")
    treasurer = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="section", limit_choices_to={"role": "treasurer"},
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("course", "name")

    @property
    def full_label(self):
        return f"{self.course.name} · {self.name}"

    def __str__(self):
        return self.name

# Create your models here.
