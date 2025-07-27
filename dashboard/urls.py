from django.urls import path
from . import views,customer

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path("sales/", views.dashboard_sales, name="dashboard_sales"),
    path("branch-monthly-table-data/", views.branch_monthly_table_data, name="branch-monthly-table-data"),
    path("company-monthly-table-data/", views.company_monthly_table_data, name="company_monthly_table_data"),
    path("combined-data/", views.dashboard_combined_data, name="dashboard_combined_data"),
    path("company-branch-monthly-summary/", views.get_company_branch_monthly_summary, name="company_branch_monthly_summary"),

    # 🔽 Müşteri Dashboard
    path("customer/", customer.customer_dashboard_page, name="customer_dashboard_page"),
    path("customer/summary/", customer.get_customer_summary, name="customer_summary"),
    path("customer/monthly/", customer.get_monthly_customer_policy_data, name="monthly_customer_policy_data"),  # ← bunu ekle
    path("customer/age-distribution/",  customer.get_customer_age_data, name="customer_age_data"),
    path("customer/city-distribution/", customer.get_customer_city_data, name="customer_city_data"),  # ✅ Yeni satır

]
