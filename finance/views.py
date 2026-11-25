from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from accounts.permissions import TreasurerRequiredMixin
from students.views import SectionRequiredMixin, get_section

from .forms import CashOutForm, CollectionForm, ExpenseForm, PaymentForm, RemittanceForm
from .models import CashOut, Collection, Expense, Obligation, Payment, Remittance
from .services import (
    collected_by_collection,
    collection_progress,
    collection_status_rows,
    create_collection_obligations,
    dashboard_summary,
    remittance_rows,
    remitted_total,
    section_balance,
    to_remit,
    transaction_rows,
    wallet_summary,
)

class DashboardView(TreasurerRequiredMixin, TemplateView):
    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = getattr(self.request.user, "section", None)
        ctx["section"] = section
        if section:
            ctx.update(dashboard_summary(section))
            progress = collection_progress(section)[:5]
            for p in progress:
                c = p["collection"]
                if c.months > 1:
                    period = c.current_period()
                    month_rows = collection_status_rows(c, period)
                    p["month_name"] = c.month_label(period)
                    p["month_paid"] = sum(1 for r in month_rows if r["status"] == "paid")
                    p["month_total"] = len(month_rows)
            ctx["progress"] = progress
            ctx["recent"] = [r for r in transaction_rows(section) if not r["is_void"]][:5]
        return ctx


class CollectionListView(SectionRequiredMixin, ListView):
    template_name = "finance/collection_list.html"
    context_object_name = "collections"

    def get_queryset(self):
        collections = Collection.objects.filter(section=get_section(self.request.user))
        return collections.annotate(student_count=Count("obligations"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = get_section(self.request.user)
        collected = collected_by_collection(section)
        collections = list(ctx["collections"])
        for c in collections:
            c.collected = collected.get(c.pk, Decimal("0.00"))
        ctx["collections"] = collections
        ctx["section"] = section
        return ctx


class CollectionCreateView(SectionRequiredMixin, CreateView):
    form_class = CollectionForm
    template_name = "finance/collection_form.html"

    def form_valid(self, form):
        form.instance.section = get_section(self.request.user)
        response = super().form_valid(form)
        create_collection_obligations(self.object)
        messages.success(self.request, "Collection created. Every active student now has an obligation.")
        return response

    def get_success_url(self):
        return reverse("collection_detail", args=[self.object.pk])


class CollectionDetailView(SectionRequiredMixin, DetailView):
    template_name = "finance/collection_detail.html"
    context_object_name = "collection"

    def get_queryset(self):
        return Collection.objects.filter(section=get_section(self.request.user))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        collection = self.object
        section = get_section(self.request.user)
        try:
            period = int(self.request.GET.get("month", ""))
        except ValueError:
            period = collection.current_period()
        period = max(1, min(period, collection.months))
        all_rows = collection_status_rows(collection, period)
        flt = self.request.GET.get("status", "all")
        if flt not in ("paid", "partial", "unpaid"):
            flt = "all"
        ctx["section"] = section
        ctx["rows"] = all_rows if flt == "all" else [r for r in all_rows if r["status"] == flt]
        ctx["status_filter"] = flt
        ctx["period"] = period
        ctx["month_choices"] = collection.month_choices if collection.months > 1 else []
        ctx["month_name"] = collection.month_label(period)
        ctx["total_due"] = sum(r["amount_due"] for r in all_rows)
        ctx["collected"] = sum(r["paid"] for r in all_rows)
        ctx["overall_due"] = sum(o.amount_due for o in collection.obligations.all())
        ctx["overall_collected"] = collected_by_collection(section).get(collection.pk, Decimal("0.00"))
        ctx["remitted"] = remitted_total(collection)
        ctx["to_remit"] = to_remit(collection)
        return ctx

    def post(self, request, *args, **kwargs):
        """Save the per-student amounts of a Variable collection."""
        collection = self.get_object()
        if collection.kind != Collection.VARIABLE:
            messages.error(request, "Only Variable collections have per-student amounts.")
            return redirect("collection_detail", pk=collection.pk)
        obligations = list(collection.obligations.all())
        for ob in obligations:
            key = f"amount_{ob.pk}"
            if key not in request.POST:      # a filtered view only sends the rows it shows
                continue
            try:
                amount = Decimal(request.POST[key].strip())
            except InvalidOperation:
                amount = None
            if (amount is None or not amount.is_finite() or amount < 0
                    or amount >= 100000000 or amount.as_tuple().exponent < -2):
                messages.error(
                    request,
                    "Every amount must be a number from 0 with at most two decimals. Nothing was saved.",
                )
                return redirect("collection_detail", pk=collection.pk)
            ob.amount_due = amount
        Obligation.objects.bulk_update(obligations, ["amount_due"])
        messages.success(request, "Amounts saved.")
        return redirect("collection_detail", pk=collection.pk)


@login_required
@require_POST
def toggle_collection(request, pk):
    section = get_section(request.user)
    if request.user.role != "treasurer" or section is None:
        raise PermissionDenied
    collection = get_object_or_404(Collection, pk=pk, section=section)
    collection.is_open = not collection.is_open
    collection.save(update_fields=["is_open"])
    messages.success(request, f"{collection} {'reopened' if collection.is_open else 'closed'}.")
    return redirect("collection_detail", pk=collection.pk)

class TransactionListView(SectionRequiredMixin, TemplateView):
    template_name = "finance/transaction_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = get_section(self.request.user)
        rows = transaction_rows(section)      # the balance is worked out before filtering
        type_filter = self.request.GET.get("type", "all")
        if type_filter not in ("in", "out"):
            type_filter = "all"
        method_filter = self.request.GET.get("method", "all")
        if method_filter != "all" and method_filter not in dict(Payment.METHOD_CHOICES):
            method_filter = "all"
        if type_filter != "all":
            rows = [r for r in rows if r["kind"] == type_filter]
        if method_filter != "all":
            rows = [r for r in rows if r["method"] == method_filter]
        ctx.update(
            section=section, rows=rows, type_filter=type_filter,
            method_filter=method_filter, methods=Payment.METHOD_CHOICES,
        )
        return ctx


class RecordPaymentView(SectionRequiredMixin, FormView):
    form_class = PaymentForm
    template_name = "finance/record_payment.html"
    success_url = reverse_lazy("transactions")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["section"] = get_section(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["section"] = get_section(self.request.user)
        # The page's script uses this to show "Create your PIN" or "Enter your PIN"
        ctx["pin_status"] = {str(s.pk): s.has_pin for s in ctx["form"].fields["student"].queryset}
        ctx["period_info"] = {
            str(c.pk): {"labels": [label for _, label in c.month_choices], "current": c.current_period()}
            for c in ctx["form"].fields["collection"].queryset
        }
        return ctx

    def form_valid(self, form):
        manual = form.cleaned_data["manual_no_pin"]
        with transaction.atomic():
            payment = form.save(commit=False)
            payment.recorded_by = self.request.user
            if manual:
                payment.pin_verified = False
            else:
                payment.no_pin_note = ""
                payment.pin_verified = True
                if not payment.student.has_pin:
                    payment.student.set_pin(form.cleaned_data["pin"])
            payment.save()
        messages.success(self.request, f"Payment of ₱{payment.amount:,.2f} recorded for {payment.student}.")
        return redirect(self.success_url)

def _void(request, item, label, back="transactions"):
    reason = request.POST.get("reason", "").strip()
    if item.is_void:
        messages.error(request, "That transaction is already voided.")
    elif not reason:
        messages.error(request, "A reason is required to void a transaction.")
    else:
        item.voided_at = timezone.now()
        item.voided_by = request.user
        item.void_reason = reason
        item.save(update_fields=["voided_at", "voided_by", "void_reason"])
        messages.success(request, f"{label} was voided.")
    return redirect(back)


@login_required
@require_POST
def void_payment(request, pk):
    if request.user.role != "treasurer":
        raise PermissionDenied
    payment = get_object_or_404(Payment, pk=pk, collection__section=get_section(request.user))
    return _void(request, payment, f"Payment of ₱{payment.amount:,.2f} for {payment.student}")


@login_required
@require_POST
def void_expense(request, pk):
    if request.user.role != "treasurer":
        raise PermissionDenied
    expense = get_object_or_404(Expense, pk=pk, section=get_section(request.user))
    return _void(request, expense, f"Expense of ₱{expense.amount:,.2f} ({expense.description})")


class RecordExpenseView(SectionRequiredMixin, FormView):
    form_class = ExpenseForm
    template_name = "finance/record_expense.html"
    success_url = reverse_lazy("transactions")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["section"] = get_section(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["section"] = get_section(self.request.user)
        ctx["balance"] = section_balance(ctx["section"])
        return ctx

    def form_valid(self, form):
        expense = form.save(commit=False)
        expense.section = get_section(self.request.user)
        expense.recorded_by = self.request.user
        expense.save()
        messages.success(self.request, f"Expense of ₱{expense.amount:,.2f} recorded.")
        return redirect(self.success_url)

class CashOutListView(SectionRequiredMixin, TemplateView):
    template_name = "finance/cashout_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = get_section(self.request.user)
        wallets = wallet_summary(section)
        ctx.update(
            section=section,
            received=sum(w["received"] for w in wallets),
            received_text=", ".join(f"{w['label']} ₱{w['received']:,.2f}" for w in wallets if w["received"]),
            cashed_out=sum(w["cashed_out"] for w in wallets),
            left=sum(w["left"] for w in wallets),
            cashout_count=CashOut.objects.filter(section=section, voided_at__isnull=True).count(),
            cashouts=CashOut.objects.filter(section=section),
            remit_rows=remittance_rows(section),
            remittances=Remittance.objects.filter(collection__section=section).select_related("collection"),
        )
        return ctx


class RecordCashOutView(SectionRequiredMixin, FormView):
    form_class = CashOutForm
    template_name = "finance/record_cashout.html"
    success_url = reverse_lazy("cashouts")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["section"] = get_section(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["section"] = get_section(self.request.user)
        ctx["wallets"] = wallet_summary(ctx["section"])
        return ctx

    def form_valid(self, form):
        cashout = form.save(commit=False)
        cashout.section = get_section(self.request.user)
        cashout.recorded_by = self.request.user
        cashout.save()
        messages.success(self.request, f"Cash-out of ₱{cashout.amount:,.2f} recorded.")
        return redirect(self.success_url)


class RecordRemittanceView(SectionRequiredMixin, FormView):
    form_class = RemittanceForm
    template_name = "finance/record_remittance.html"
    success_url = reverse_lazy("cashouts")

    def get_initial(self):
        return {"collection": self.request.GET.get("collection")}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["section"] = get_section(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["section"] = get_section(self.request.user)
        return ctx

    def form_valid(self, form):
        remittance = form.save(commit=False)
        remittance.recorded_by = self.request.user
        remittance.save()
        messages.success(self.request, f"Remittance of ₱{remittance.amount:,.2f} recorded for {remittance.collection}.")
        return redirect(self.success_url)


@login_required
@require_POST
def void_cashout(request, pk):
    if request.user.role != "treasurer":
        raise PermissionDenied
    cashout = get_object_or_404(CashOut, pk=pk, section=get_section(request.user))
    return _void(request, cashout, f"Cash-out of ₱{cashout.amount:,.2f}", back="cashouts")


@login_required
@require_POST
def void_remittance(request, pk):
    if request.user.role != "treasurer":
        raise PermissionDenied
    remittance = get_object_or_404(Remittance, pk=pk, collection__section=get_section(request.user))
    return _void(request, remittance, f"Remittance of ₱{remittance.amount:,.2f}", back="cashouts")

class ReportsView(SectionRequiredMixin, TemplateView):
    template_name = "finance/reports.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        section = get_section(self.request.user)
        summary = dashboard_summary(section)
        progress = collection_progress(section)

        collections = list(section.collections.all())
        selected = None
        try:
            wanted = int(self.request.GET.get("collection", ""))
        except ValueError:
            wanted = None
        for c in collections:
            if c.pk == wanted:
                selected = c
        if selected is None and collections:
            selected = next((c for c in collections if c.is_open), collections[0])

        rows, period, month_name = [], 1, ""
        if selected:
            try:
                period = int(self.request.GET.get("month", ""))
            except ValueError:
                period = selected.current_period()
            period = max(1, min(period, selected.months))
            month_name = selected.month_label(period)
            for r in collection_status_rows(selected, period):
                if r["status"] in ("unpaid", "partial"):
                    r["left"] = r["amount_due"] - r["paid"]
                    rows.append(r)

        ctx.update(
            section=section,
            today=timezone.localdate(),
            collected=summary["collected"],
            spent=summary["spent"],
            balance=summary["balance"],
            remitted=sum(p["remitted"] for p in progress),
            to_remit=sum(p["to_remit"] for p in progress),
            progress=progress,
            collections=collections,
            selected=selected,
            period=period,
            month_name=month_name,
            month_choices=selected.month_choices if selected and selected.months > 1 else [],
            unpaid=rows,
        )
        return ctx


@login_required
def reports_excel(request):
    section = get_section(request.user)
    if request.user.role != "treasurer" or section is None:
        raise PermissionDenied

    wb = Workbook()
    bold = Font(bold=True)

    def add_sheet(title, header, rows, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(header)
        for cell in ws[1]:
            cell.font = bold
        for row in rows:
            ws.append(row)
        for i, column in enumerate(ws.columns, start=1):
            longest = max(len(str(c.value)) if c.value is not None else 0 for c in column)
            ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 10), 50)

    summary = dashboard_summary(section)
    progress = collection_progress(section)
    add_sheet("Summary", ["Item", "Value"], [
        ["Section", section.full_label],
        ["Generated", timezone.localtime().strftime("%Y-%m-%d %H:%M")],
        ["Collected", float(summary["collected"])],
        ["Spent", float(summary["spent"])],
        ["Balance", float(summary["balance"])],
        ["Remitted", float(sum(p["remitted"] for p in progress))],
        ["Still to remit", float(sum(p["to_remit"] for p in progress))],
    ], first=True)

    add_sheet("Collections", ["Collection", "Type", "Months", "Total due", "Collected", "Remitted", "To remit"], [
        [p["collection"].name, p["collection"].get_kind_display(), p["collection"].months,
         float(p["due"]), float(p["collected"]), float(p["remitted"]), float(p["to_remit"])]
        for p in progress
    ])

    paid = {
        (r["collection_id"], r["student_id"]): r["total"]
        for r in Payment.objects.filter(collection__section=section, voided_at__isnull=True)
        .values("collection_id", "student_id")
        .annotate(total=Sum("amount"))
    }
    balance_rows = []
    obligations = Obligation.objects.filter(collection__section=section).select_related("student", "collection")
    for ob in obligations.order_by("collection__name", "student__last_name", "student__first_name"):
        got = paid.get((ob.collection_id, ob.student_id), Decimal("0.00"))
        left = ob.amount_due - got
        status = "Paid" if left <= 0 and ob.amount_due > 0 else ("Partial" if got > 0 else "Unpaid")
        balance_rows.append([
            ob.collection.name, ob.student.student_number,
            f"{ob.student.last_name}, {ob.student.first_name}",
            float(ob.amount_due), float(got), float(max(left, Decimal("0.00"))), status,
        ])
    add_sheet("Student balances", ["Collection", "Student no.", "Student", "Required", "Paid", "Left to pay", "Status"], balance_rows)

    tx_rows = []
    for r in reversed(transaction_rows(section)):
        tx_rows.append([
            timezone.localtime(r["when"]).strftime("%Y-%m-%d %H:%M"),
            "Money in" if r["kind"] == "in" else "Money out",
            r["description"], r["method_label"], r["reference"] or "",
            float(r["amount"]) if r["kind"] == "in" else -float(r["amount"]),
            "Voided" if r["is_void"] else "",
            "" if r["is_void"] else float(r["balance"]),
        ])
    add_sheet("Transactions", ["Date", "Type", "Description", "Method", "Reference", "Amount", "Status", "Balance"], tx_rows)

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="classfunds-report-{timezone.localdate():%Y-%m-%d}.xlsx"'
    return response