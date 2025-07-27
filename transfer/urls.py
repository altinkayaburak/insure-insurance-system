from django.urls import path
from . import views

urlpatterns = [
    path("", views.transfer_page_view, name="transfer_page"),
    path("run/", views.run_single_company_transfer, name="run_single_company_transfer"),
    path("run-all/", views.run_all_transfer_sliced, name="run_all_transfer_sliced"),
    path("status/<int:company_id>/", views.get_latest_transfer_status, name="get_latest_transfer_status"),
    path("trigger-card-task/", views.trigger_card_task, name="trigger_card_task"),

]
