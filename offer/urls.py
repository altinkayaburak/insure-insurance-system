from django.urls import path
from . import views

urlpatterns = [
    path("form/open/", views.open_proposal_form, name="open_proposal_form"),

    path("get-fixed-values/", views.get_offer_fixed_values, name="get_fixed_values"),
    path("set-ettiren/", views.set_ettiren, name="set_ettiren"),

    path("create-proposal-entry/", views.create_proposal_entry, name="create_proposal_entry"),
    path("get_customer_companies_by_identity/", views.get_customer_companies_by_identity,name="get_customer_companies_by_identity"),
    path("<uuid:uuid>/", views.proposal_detail_page, name="proposal_detail_page"),  # ✅ DOĞRU

    path("check-proposal-status/<int:proposal_id>/", views.check_proposal_status, name="check_proposal_status"),
    path("get-proposal-details/<int:proposal_id>/", views.get_proposal_details, name="get_proposal_details"),


]

