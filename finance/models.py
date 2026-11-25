from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

def last_day_of_period(start, months):
    """Last day of the final month of a period that starts in start's month (that month counts as month 1)."""
    index = start.year * 12 + (start.month - 1) + (months - 1)
    year, month = divmod(index, 12)
    first_of_next = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return first_of_next - timedelta(days=1)

class Collection(models.Model):
    FIXED = "fixed"
    VARIABLE = "variable"
    KIND_CHOICES = [(FIXED, "Fixed"), (VARIABLE, "Variable")]

    section = models.ForeignKey("sections.Section", on_delete=models.PROTECT, related_name="collections")
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=FIXED)
    default_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    months = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    deadline = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total_amount(self):
        """What each student owes in total: the monthly amount times the months (Fixed only)."""
        if self.kind == self.FIXED and self.default_amount:
            return self.default_amount * self.months
        return self.default_amount

    @property
    def start_date(self):
        return timezone.localdate(self.created_at)

    def month_label(self, n):
        """Name of month number n of this collection, for example 'Nov 2026'."""
        start = self.start_date
        year, month = divmod(start.year * 12 + (start.month - 1) + (n - 1), 12)
        return date(year, month + 1, 1).strftime("%b %Y")

    @property
    def month_choices(self):
        return [(n, self.month_label(n)) for n in range(1, self.months + 1)]

    def current_period(self):
        """Which month of the collection we are in now, kept between 1 and the last month."""
        today, start = timezone.localdate(), self.start_date
        n = (today.year - start.year) * 12 + (today.month - start.month) + 1
        return max(1, min(n, self.months))

    def period_due(self, obligation):
        """What a student owes for one month of this collection."""
        if self.kind == self.FIXED and self.months > 1 and self.default_amount:
            return self.default_amount
        return obligation.amount_due

    @property
    def period_label(self):
        if self.kind != self.FIXED or self.months < 2:
            return ""
        start = timezone.localdate(self.created_at)
        end = last_day_of_period(start, self.months)
        return f"{start:%b %Y} to {end:%b %Y}"

    def __str__(self):
        return self.name


class Obligation(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT, related_name="obligations")
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="obligations")
    amount_due = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )

    class Meta:
        unique_together = ("collection", "student")
        ordering = ["student__last_name", "student__first_name"]

    def __str__(self):
        return f"{self.student} - {self.collection}"

class Payment(models.Model):
    CASH = "cash"
    GCASH = "gcash"
    MAYA = "maya"
    BANK = "bank"
    OTHER = "other"
    METHOD_CHOICES = [
        (CASH, "Cash"),
        (GCASH, "GCash"),
        (MAYA, "Maya"),
        (BANK, "Bank transfer"),
        (OTHER, "Other e-wallet"),
    ]

    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="payments")
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT, related_name="payments")
    period = models.PositiveSmallIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=CASH)
    reference = models.CharField(max_length=60, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    pin_verified = models.BooleanField(default=False)
    no_pin_note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_payments")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="voided_payments"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-paid_at"]

    @property
    def is_void(self):
        return self.voided_at is not None

    def __str__(self):
        return f"{self.student} - {self.collection} - {self.amount}"

class Expense(models.Model):
    section = models.ForeignKey("sections.Section", on_delete=models.PROTECT, related_name="expenses")
    description = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=10, choices=Payment.METHOD_CHOICES, default=Payment.CASH)
    spent_at = models.DateTimeField(default=timezone.now)
    receipt_note = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_expenses")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="voided_expenses"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-spent_at"]

    @property
    def is_void(self):
        return self.voided_at is not None

    def __str__(self):
        return f"{self.description} - {self.amount}"

class CashOut(models.Model):
    WALLET_CHOICES = [
        (Payment.GCASH, "GCash"),
        (Payment.MAYA, "Maya"),
        (Payment.OTHER, "Other e-wallet"),
    ]

    section = models.ForeignKey("sections.Section", on_delete=models.PROTECT, related_name="cash_outs")
    wallet = models.CharField(max_length=10, choices=WALLET_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reference = models.CharField(max_length=60, blank=True)
    cashed_out_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_cash_outs")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="voided_cash_outs"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-cashed_out_at"]

    @property
    def is_void(self):
        return self.voided_at is not None

    def __str__(self):
        return f"{self.get_wallet_display()} cash-out {self.amount}"


class Remittance(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT, related_name="remittances")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    remitted_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=120, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_remittances")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="voided_remittances"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-remitted_at"]

    @property
    def is_void(self):
        return self.voided_at is not None

    def __str__(self):
        return f"Remittance {self.amount} for {self.collection}"