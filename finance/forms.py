from django import forms
from django.utils import timezone
from students.models import LOCK_MINUTES, MAX_PIN_ATTEMPTS
from .models import CashOut, Collection, Expense, Obligation, Payment, Remittance, last_day_of_period
from .services import amount_paid, section_balance, to_remit, wallet_left


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["name", "kind", "default_amount", "months", "deadline", "description"]
        labels = {"kind": "Type", "default_amount": "Amount per student", "months": "Runs for"}
        widgets = {
            "months": forms.Select(choices=[(i, f"{i} month{'s' if i > 1 else ''}") for i in range(1, 13)]),
            "deadline": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"
        self.fields["description"].widget.attrs["style"] = "height:auto;padding:10px 12px"

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        if kind == Collection.FIXED and not data.get("default_amount"):
            self.add_error("default_amount", "Enter the amount for a fixed collection.")
        months = data.get("months") or 1
        if kind != Collection.FIXED:
            data["months"] = 1
        elif months > 1:
            data["deadline"] = last_day_of_period(timezone.localdate(), months)
        return data


class PaymentForm(forms.ModelForm):
    pin = forms.CharField(required=False)
    pin_confirm = forms.CharField(required=False)
    manual_no_pin = forms.BooleanField(required=False)

    class Meta:
        model = Payment
        fields = ["student", "collection", "period", "amount", "method", "reference", "no_pin_note"]
        widgets = {
            "no_pin_note": forms.Textarea(attrs={"rows": 2}),
            "period": forms.Select(choices=[(i, str(i)) for i in range(1, 13)]),
        }
        labels = {"period": "Month"}

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = section.students.filter(is_active=True)
        self.fields["student"].label_from_instance = (
            lambda s: f"{s.last_name}, {s.first_name} ({s.student_number})"
        )
        self.fields["collection"].queryset = section.collections.filter(is_open=True)
        for name in ("student", "collection", "period", "amount", "method", "reference", "no_pin_note"):
            self.fields[name].widget.attrs["class"] = "input"
        self.fields["no_pin_note"].widget.attrs["style"] = "height:auto;padding:10px 12px"

    def clean(self):
        data = super().clean()
        student = data.get("student")
        collection = data.get("collection")
        amount = data.get("amount")
        method = data.get("method")
        reference = (data.get("reference") or "").strip()
        data["reference"] = reference

        period = data.get("period") or 1
        if collection and collection.months == 1:
            period = data["period"] = 1
        if collection and not 1 <= period <= collection.months:
            self.add_error("period", "Choose a month within this collection.")
        elif student and collection and amount:
            obligation = Obligation.objects.filter(collection=collection, student=student).first()
            if obligation is None:
                self.add_error("student", "This student has no obligation in that collection.")
            else:
                remaining = collection.period_due(obligation) - amount_paid(student, collection, period)
                if remaining <= 0:
                    where = "this month" if collection.months > 1 else "this collection"
                    self.add_error("collection", f"This student has nothing left to pay for {where}.")
                elif amount > remaining:
                    self.add_error("amount", f"That is more than what is left to pay (₱{remaining:,.2f}).")

        if method and method != Payment.CASH:
            if not reference:
                self.add_error("reference", "A reference number is required for non-cash payments.")
            elif Payment.objects.filter(
                method=method, reference__iexact=reference, voided_at__isnull=True
            ).exists():
                self.add_error("reference", "This reference number was already used for this method.")

        # The PIN is only checked when everything else is valid, so form mistakes don't burn PIN tries.
        if student and not self.errors:
            if data.get("manual_no_pin"):
                if not (data.get("no_pin_note") or "").strip():
                    self.add_error("no_pin_note", "A note is required when recording without a PIN.")
            else:
                self.check_pin(student, data.get("pin", ""), data.get("pin_confirm", ""))
        return data

    def check_pin(self, student, pin, confirm):
        if not student.has_pin:
            if not (pin.isdigit() and len(pin) == 6):
                self.add_error("pin", "Create a six-digit PIN.")
            elif pin != confirm:
                self.add_error("pin", "The two PINs don't match.")
        elif student.is_locked:
            until = timezone.localtime(student.locked_until)
            self.add_error("pin", f"This PIN is locked until {until:%I:%M %p}. Reset the PIN or try again later.")
        elif not student.check_pin(pin):
            if student.is_locked:
                self.add_error("pin", f"Too many wrong tries. This PIN is now locked for {LOCK_MINUTES} minutes.")
            else:
                left = MAX_PIN_ATTEMPTS - student.failed_attempts
                self.add_error("pin", f"Wrong PIN. {left} tries left.")

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["description", "amount", "method", "receipt_note"]
        labels = {"method": "Paid with"}

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        data = super().clean()
        amount = data.get("amount")
        if amount:
            balance = section_balance(self.section)
            if amount > balance:
                self.add_error("amount", f"That is more than the available balance (₱{balance:,.2f}).")
        return data

class CashOutForm(forms.ModelForm):
    class Meta:
        model = CashOut
        fields = ["wallet", "amount", "reference"]
        labels = {"wallet": "E-wallet", "reference": "Reference number (optional)"}

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        data = super().clean()
        wallet, amount = data.get("wallet"), data.get("amount")
        if wallet and amount:
            left = wallet_left(self.section, wallet)
            if amount > left:
                self.add_error("amount", f"That is more than what is left in this wallet (₱{left:,.2f}).")
        return data


class RemittanceForm(forms.ModelForm):
    class Meta:
        model = Remittance
        fields = ["collection", "amount", "note"]
        labels = {"note": "Note (optional)"}

    def __init__(self, *args, section, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collection"].queryset = section.collections.all()
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"

    def clean(self):
        data = super().clean()
        collection, amount = data.get("collection"), data.get("amount")
        if collection and amount:
            left = to_remit(collection)
            if left <= 0:
                self.add_error("collection", "Nothing is left to remit for this collection.")
            elif amount > left:
                self.add_error("amount", f"That is more than what is left to remit (₱{left:,.2f}).")
        return data