from datetime import timedelta
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

MAX_PIN_ATTEMPTS = 5
LOCK_MINUTES = 15

class Student(models.Model):
    section = models.ForeignKey("sections.Section", on_delete=models.PROTECT, related_name="students")
    student_number = models.CharField(max_length=30)
    last_name = models.CharField(max_length=60)
    first_name = models.CharField(max_length=60)
    pin_hash = models.CharField(max_length=128)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        unique_together = ("section", "student_number")

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

    @property
    def has_pin(self):
        return bool(self.pin_hash)

    @property
    def is_locked(self):
        return self.locked_until is not None and self.locked_until > timezone.now()

    def set_pin(self, raw_pin):
        if not (raw_pin.isdigit() and len(raw_pin) == 6):
            raise ValueError("The PIN must be exactly six digits.")
        self.pin_hash = make_password(raw_pin)
        self.failed_attempts = 0
        self.locked_until = None
        self.save()

    def reset_pin(self):
        """The treasurer resets it; the student sets a new one at the next payment."""
        self.pin_hash = ""
        self.failed_attempts = 0
        self.locked_until = None
        self.save()

    def check_pin(self, raw_pin):
        """True if correct. Wrong tries are counted, and five in a row lock the PIN."""
        if self.is_locked or not self.has_pin:
            return False
        if check_password(raw_pin, self.pin_hash):
            if self.failed_attempts:
                self.failed_attempts = 0
                self.save(update_fields=["failed_attempts"])
            return True
        self.failed_attempts += 1
        if self.failed_attempts >= MAX_PIN_ATTEMPTS:
            self.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
            self.failed_attempts = 0
        self.save(update_fields=["failed_attempts", "locked_until"])
        return False
