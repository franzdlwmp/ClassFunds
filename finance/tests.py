from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from finance.models import Collection, Obligation, Payment
from finance.services import collection_progress
from sections.models import Course, Section
from students.models import Student


class CollectionProgressTests(TestCase):
    def setUp(self):
        course = Course.objects.create(code="TEST", name="Test course")
        self.section = Section.objects.create(course=course, name="Test section")
        self.student = Student.objects.create(
            section=self.section,
            student_number="TEST-001",
            last_name="Student",
            first_name="Test",
            pin_hash="",
        )
        self.user = get_user_model().objects.create_user(
            username="treasurer",
            password="test-password",
            role="treasurer",
        )

    def test_multi_month_fixed_collection_progress_uses_total_due(self):
        collection = Collection.objects.create(
            section=self.section,
            name="Three-month collection",
            kind=Collection.FIXED,
            default_amount=Decimal("100.00"),
            months=3,
        )
        Obligation.objects.create(
            collection=collection,
            student=self.student,
            amount_due=Decimal("100.00"),
        )
        Payment.objects.create(
            collection=collection,
            student=self.student,
            period=1,
            amount=Decimal("100.00"),
            recorded_by=self.user,
        )

        progress = collection_progress(self.section)[0]

        self.assertEqual(progress["due"], Decimal("300.00"))
        self.assertEqual(progress["collected"], Decimal("100.00"))
        self.assertEqual(progress["percent"], 33)

    def test_single_month_fixed_collection_progress_is_unchanged(self):
        collection = Collection.objects.create(
            section=self.section,
            name="One-month collection",
            kind=Collection.FIXED,
            default_amount=Decimal("100.00"),
            months=1,
        )
        Obligation.objects.create(
            collection=collection,
            student=self.student,
            amount_due=Decimal("100.00"),
        )
        Payment.objects.create(
            collection=collection,
            student=self.student,
            amount=Decimal("100.00"),
            recorded_by=self.user,
        )

        progress = collection_progress(self.section)[0]

        self.assertEqual(progress["due"], Decimal("100.00"))
        self.assertEqual(progress["percent"], 100)
