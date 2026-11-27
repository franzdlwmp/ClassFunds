from decimal import Decimal
from django.db.models import Sum
from .models import CashOut, Collection, Expense, Obligation, Payment, Remittance

def starting_amount(collection):
    return collection.default_amount or Decimal("0.00")

def create_collection_obligations(collection):
    amount = starting_amount(collection)
    students = collection.section.students.filter(is_active=True)
    Obligation.objects.bulk_create(
        [Obligation(collection=collection, student=s, amount_due=amount) for s in students]
    )

def add_student_to_open_collections(student):
    for collection in Collection.objects.filter(section=student.section, is_open=True):
        Obligation.objects.get_or_create(
            collection=collection,
            student=student,
            defaults={"amount_due": starting_amount(collection)},
        )

def amount_paid(student, collection, period=None):
    """Total of the student's payments in a collection (or in one month of it), ignoring voided ones."""
    payments = Payment.objects.filter(student=student, collection=collection, voided_at__isnull=True)
    if period is not None:
        payments = payments.filter(period=period)
    return payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

def collected_by_collection(section):
    """{collection id: total collected}, ignoring voided payments."""
    rows = (
        Payment.objects.filter(collection__section=section, voided_at__isnull=True)
        .values("collection_id")
        .annotate(total=Sum("amount"))
    )
    return {r["collection_id"]: r["total"] for r in rows}


def collection_status_rows(collection, period=1):
    """One row per student for one month: required, paid, and a calculated status."""
    paid_by_student = {
        r["student_id"]: r["total"]
        for r in Payment.objects.filter(collection=collection, period=period, voided_at__isnull=True)
        .values("student_id")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for ob in collection.obligations.select_related("student"):
        due = collection.period_due(ob)
        paid = paid_by_student.get(ob.student_id, Decimal("0.00"))
        if due == 0:
            status = "none"
        elif paid >= due:
            status = "paid"
        elif paid > 0:
            status = "partial"
        else:
            status = "unpaid"
        rows.append({"obligation": ob, "student": ob.student, "amount_due": due, "paid": paid, "status": status})
    return rows

def section_balance(section):
    money_in = Payment.objects.filter(
        collection__section=section, voided_at__isnull=True
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    money_out = Expense.objects.filter(
        section=section, voided_at__isnull=True
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    return money_in - money_out

def transaction_rows(section):
    """Payments and expenses as one list, newest first, each with a running balance."""
    rows = []
    payments = Payment.objects.filter(collection__section=section).select_related("student", "collection")
    for p in payments:
        rows.append({
            "kind": "in", "obj": p, "when": p.paid_at,
            "description": (
                f"{p.student.last_name}, {p.student.first_name}, {p.collection.name}"
                + (f" ({p.collection.month_label(p.period)})" if p.collection.months > 1 else "")
            ),
            "method": p.method, "method_label": p.get_method_display(),
            "reference": p.reference, "amount": p.amount,
            "is_void": p.is_void, "void_reason": p.void_reason,
            "check": "PIN verified" if p.pin_verified else "Manual, no PIN",
            "check_muted": not p.pin_verified, "check_note": p.no_pin_note,
        })
    for e in Expense.objects.filter(section=section):
        rows.append({
            "kind": "out", "obj": e, "when": e.spent_at,
            "description": f"{e.description} (expense)",
            "method": e.method, "method_label": e.get_method_display(),
            "reference": "", "amount": e.amount,
            "is_void": e.is_void, "void_reason": e.void_reason,
            "check": e.receipt_note or "No receipt note",
            "check_muted": True, "check_note": "",
        })
    rows.sort(key=lambda r: r["when"])
    running = Decimal("0.00")
    for r in rows:
        if not r["is_void"]:
            running += r["amount"] if r["kind"] == "in" else -r["amount"]
        r["balance"] = running
    rows.reverse()
    return rows

def _total(queryset):
    return queryset.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")


def wallet_summary(section):
    """One row per e-wallet: received, spent, cashed out, and what is still in it."""
    rows = []
    for key, label in CashOut.WALLET_CHOICES:
        received = _total(Payment.objects.filter(collection__section=section, method=key, voided_at__isnull=True))
        spent = _total(Expense.objects.filter(section=section, method=key, voided_at__isnull=True))
        cashed = _total(CashOut.objects.filter(section=section, wallet=key, voided_at__isnull=True))
        rows.append({
            "key": key, "label": label, "received": received,
            "spent": spent, "cashed_out": cashed, "left": received - spent - cashed,
        })
    return rows


def wallet_left(section, wallet):
    for row in wallet_summary(section):
        if row["key"] == wallet:
            return row["left"]
    return Decimal("0.00")


def remitted_total(collection):
    return _total(Remittance.objects.filter(collection=collection, voided_at__isnull=True))


def to_remit(collection):
    collected = _total(Payment.objects.filter(collection=collection, voided_at__isnull=True))
    return collected - remitted_total(collection)


def remittance_rows(section):
    """One row per collection: collected, remitted, still to remit, and a status."""
    collected = collected_by_collection(section)
    remitted = {
        r["collection_id"]: r["total"]
        for r in Remittance.objects.filter(collection__section=section, voided_at__isnull=True)
        .values("collection_id")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for c in section.collections.all():
        got = collected.get(c.pk, Decimal("0.00"))
        sent = remitted.get(c.pk, Decimal("0.00"))
        if got <= 0:
            status = "empty"
        elif sent <= 0:
            status = "none"
        elif sent >= got:
            status = "full"
        else:
            status = "partial"
        rows.append({"collection": c, "collected": got, "remitted": sent, "to_remit": got - sent, "status": status})
    return rows

def dashboard_summary(section):
    paid = Payment.objects.filter(collection__section=section, voided_at__isnull=True)
    spent = Expense.objects.filter(section=section, voided_at__isnull=True)
    collected = _total(paid)
    spent_total = _total(spent)
    return {
        "collected": collected,
        "paying_students": paid.values("student").distinct().count(),
        "spent": spent_total,
        "expense_count": spent.count(),
        "balance": collected - spent_total,
    }

def collection_progress(section):
    """One row per collection: due, collected, remitted, still to remit, and a percentage."""
    collected = collected_by_collection(section)
    due = {
        r["collection_id"]: r["total"]
        for r in Obligation.objects.filter(collection__section=section)
        .values("collection_id")
        .annotate(total=Sum("amount_due"))
    }
    remitted = {
        r["collection_id"]: r["total"]
        for r in Remittance.objects.filter(collection__section=section, voided_at__isnull=True)
        .values("collection_id")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for c in section.collections.all():
        total_due = due.get(c.pk, Decimal("0.00"))
        if c.kind == Collection.FIXED:
            total_due *= c.months
        got = collected.get(c.pk, Decimal("0.00"))
        sent = remitted.get(c.pk, Decimal("0.00"))
        percent = int(min(100, got / total_due * 100)) if total_due > 0 else 0
        rows.append({
            "collection": c, "due": total_due, "collected": got,
            "remitted": sent, "to_remit": got - sent, "percent": percent,
        })
    return rows