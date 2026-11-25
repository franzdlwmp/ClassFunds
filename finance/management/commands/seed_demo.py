from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from finance.models import CashOut, Collection, Expense, Obligation, Payment, Remittance, last_day_of_period
from finance.services import create_collection_obligations, to_remit, wallet_left
from sections.models import Course, Section
from students.models import Student

User = get_user_model()

DEMO_USERNAME = "demo.treasurer"
DEMO_PASSWORD = "ClassFundsDemo1!"
DEMO_SECTION = "Demo 3-A"
STUDENT_PIN = "123456"

NAMES = [
    ("Aquino", "Bea"), ("Bautista", "Carlo"), ("Castillo", "Dani"), ("Dizon", "Ella"),
    ("Esguerra", "Fritz"), ("Flores", "Gwen"), ("Gonzales", "Harvey"), ("Hernandez", "Isla"),
    ("Ignacio", "Jun"), ("Javier", "Kyla"), ("Katigbak", "Luis"), ("Lacson", "Mica"),
]


def clear_section(section):
    Remittance.objects.filter(collection__section=section).delete()
    Payment.objects.filter(collection__section=section).delete()
    Obligation.objects.filter(collection__section=section).delete()
    Collection.objects.filter(section=section).delete()
    Expense.objects.filter(section=section).delete()
    CashOut.objects.filter(section=section).delete()
    Student.objects.filter(section=section).delete()


class Command(BaseCommand):
    help = "Fill a separate demo section with sample students, collections and payments."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the existing demo data first.")

    @transaction.atomic
    def handle(self, *args, **options):
        course, _ = Course.objects.get_or_create(
            code="BSIT", defaults={"name": "Bachelor of Science in Information Technology"}
        )
        section, _ = Section.objects.get_or_create(course=course, name=DEMO_SECTION)

        user = User.objects.filter(username=DEMO_USERNAME).first()
        if user is None:
            user = User(username=DEMO_USERNAME, first_name="Demo", last_name="Treasurer")
        user.role = User.Role.TREASURER
        user.is_active = True
        user.must_change_pass = False
        user.set_password(DEMO_PASSWORD)
        user.save()
        if section.treasurer_id != user.pk:
            section.treasurer = user
            section.is_active = True
            section.save()

        if section.students.exists():
            if not options["reset"]:
                raise CommandError("Demo data already exists. Run it with --reset to rebuild it.")
            clear_section(section)

        students = []
        for n, (last, first) in enumerate(NAMES, start=1):
            s = Student.objects.create(
                section=section, student_number=f"2024-{n:04d}", last_name=last, first_name=first
            )
            if n <= 8:
                s.set_pin(STUDENT_PIN)
            students.append(s)

        today = timezone.localdate()
        dues = Collection.objects.create(
            section=section, name="Monthly Dues", kind=Collection.FIXED,
            default_amount=Decimal("100.00"), months=5, deadline=last_day_of_period(today, 5),
            description="Class fund, ₱100 a month.",
        )
        shirt = Collection.objects.create(
            section=section, name="Class Shirt", kind=Collection.FIXED,
            default_amount=Decimal("350.00"), months=1, deadline=today + timedelta(days=14),
            description="One class shirt per student.",
        )
        trip = Collection.objects.create(
            section=section, name="Field Trip Fund", kind=Collection.VARIABLE,
            default_amount=Decimal("0.00"), months=1, description="Amount depends on the student.",
        )
        for c in (dues, shirt, trip):
            create_collection_obligations(c)

        trip_amounts = [250, 250, 250, 250, 250, 250, 250, 250, 200, 200, 150, 150]
        by_student = {o.student_id: o for o in trip.obligations.all()}
        for s, amount in zip(students, trip_amounts):
            ob = by_student[s.pk]
            ob.amount_due = Decimal(amount)
            ob.save(update_fields=["amount_due"])

        methods = [Payment.CASH, Payment.GCASH, Payment.MAYA]
        counter = {"n": 0}

        def pay(student, collection, amount, period=1):
            counter["n"] += 1
            n = counter["n"]
            method = methods[n % 3]
            manual = not student.has_pin
            return Payment.objects.create(
                student=student, collection=collection, period=period, amount=Decimal(amount),
                method=method,
                reference="" if method == Payment.CASH else f"{method.upper()}-{4000 + n * 37}",
                paid_at=timezone.now() - timedelta(days=(n * 7) % 10, minutes=n * 13),
                pin_verified=not manual,
                no_pin_note="Paid in person, PIN to be set later." if manual else "",
                recorded_by=user,
            )

        for s in students[:8]:
            pay(s, dues, 100)
        for s in students[:2]:
            pay(s, dues, 100, period=2)
        pay(students[8], dues, 50)
        for s in students[:6]:
            pay(s, shirt, 350)
        pay(students[6], shirt, 200)
        for s in students[:5]:
            pay(s, trip, 250)

        wrong = pay(students[11], dues, 100)
        wrong.voided_at = timezone.now()
        wrong.voided_by = user
        wrong.void_reason = "Recorded under the wrong student."
        wrong.save(update_fields=["voided_at", "voided_by", "void_reason"])

        for description, amount, method, note in [
            ("Printing: orientation posters", "450.00", Payment.CASH, "Receipt attached"),
            ("Cartolina and markers", "180.00", Payment.CASH, "Receipt attached"),
            ("Class meeting snacks", "320.00", Payment.GCASH, ""),
        ]:
            Expense.objects.create(
                section=section, description=description, amount=Decimal(amount), method=method,
                receipt_note=note, recorded_by=user, spent_at=timezone.now() - timedelta(days=3),
            )

        cash_out = min(Decimal("500.00"), wallet_left(section, Payment.GCASH))
        if cash_out > 0:
            CashOut.objects.create(
                section=section, wallet=Payment.GCASH, amount=cash_out,
                reference="GCASH-CO-8821", recorded_by=user,
            )
        remit = min(Decimal("500.00"), to_remit(dues))
        if remit > 0:
            Remittance.objects.create(
                collection=dues, amount=remit, note="Handed to the department treasurer", recorded_by=user,
            )

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write(f"Log in as {DEMO_USERNAME} with password {DEMO_PASSWORD}")
        self.stdout.write(f"Students with a PIN use {STUDENT_PIN}. Students 9 to 12 have none yet.")