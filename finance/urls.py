from django.urls import path
from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("collections/", views.CollectionListView.as_view(), name="collections"),
    path("collections/add/", views.CollectionCreateView.as_view(), name="collection_add"),
    path("collections/<int:pk>/", views.CollectionDetailView.as_view(), name="collection_detail"),
    path("collections/<int:pk>/toggle/", views.toggle_collection, name="collection_toggle"),
    path("transactions/", views.TransactionListView.as_view(), name="transactions"),
    path("transactions/record/", views.RecordPaymentView.as_view(), name="record_payment"),
    path("transactions/<int:pk>/void/", views.void_payment, name="payment_void"),
    path("transactions/expense/", views.RecordExpenseView.as_view(), name="record_expense"),
    path("transactions/expenses/<int:pk>/void/", views.void_expense, name="expense_void"),
    path("cashouts/", views.CashOutListView.as_view(), name="cashouts"),
    path("cashouts/record/", views.RecordCashOutView.as_view(), name="record_cashout"),
    path("cashouts/<int:pk>/void/", views.void_cashout, name="cashout_void"),
    path("remittances/record/", views.RecordRemittanceView.as_view(), name="record_remittance"),
    path("remittances/<int:pk>/void/", views.void_remittance, name="remittance_void"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports/excel/", views.reports_excel, name="reports_excel"),
]