from django.urls import path
from . import views


app_name = 'agencyusers'  # App name tanımlayın

urlpatterns = [
    path('<int:agency_id>/users/', views.get_users, name='get_users'),
    path('<int:agency_id>/user/add/', views.add_user, name='add_user'),
    path('<int:agency_id>/user/<int:user_id>/get/', views.get_user_details, name='get_user_details'),
    path('<int:agency_id>/user/<int:user_id>/update/', views.update_user, name='update_user'),
    path('<int:agency_id>/user/<int:user_id>/toggle-status/', views.toggle_user_active, name='toggle_user_active'),

    path('<int:agency_id>/company/save/', views.save_company, name='save_company'),
    path('<int:agency_id>/get-available-companies/', views.get_available_companies, name='get_available_companies'),
    path('<int:agency_id>/company/<int:company_id>/delete/', views.delete_agency_company, name='delete_agency_company'),
    path('<int:agency_id>/company/<int:company_id>/get/', views.get_company_details, name='get_company_details'),
    path('<int:agency_id>/company/update/', views.update_company, name='update_company'),
    path('<int:agency_id>/branch/add/', views.add_branch, name='add_branch'),
    path('<int:agency_id>/branch/<int:branch_id>/get/', views.get_branch_details, name="get_branch_details"),
    path('<int:agency_id>/branch/update/', views.update_branch, name="update_branch"),
    path('<int:agency_id>/branch/<int:branch_id>/delete/', views.delete_branch, name="delete_branch"),
    path('<int:agency_id>/toggle-service-status/<int:service_auth_id>/', views.toggle_service_status, name='toggle_service_status'),
    path("<int:agency_id>/get-unassigned-services/", views.get_unassigned_services, name="get_unassigned_services"),
    path('<int:agency_id>/toggle-offer-service-status/<int:offer_service_auth_id>/', views.toggle_offer_service_status, name='toggle_offer_service_status'),

]