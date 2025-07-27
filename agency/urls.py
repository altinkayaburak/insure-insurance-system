from django.urls import path
from . import views

urlpatterns = [
    # Acente Listeleme ve Detay
    path('', views.agency_list, name='agency_list'),  # /agency/
    path('<int:agency_id>/', views.agency_detail, name='agency_detail'),  # /agency/3/
    path('add/', views.add_agency, name='add_agency'),  # << Burası önemli!

    path('<int:agency_id>/get-agency-tab/', views.get_agency_tab, name='get_agency_tab'),
    path('<int:agency_id>/get-users-tab/', views.get_users_tab, name='get_users_tab'),
    path('<int:agency_id>/get-companies-tab/', views.get_companies_tab, name='get_companies_tab'),
    path('<int:agency_id>/get-branches-tab/', views.get_branches_tab, name="get_branches_tab"),
    path('<int:agency_id>/get-services-tab/', views.get_services_tab, name="get_services_tab"),
    path('<int:agency_id>/get-offer-services-tab/', views.get_offer_services_tab, name='get_offer_services_tab'),
    path('<int:agency_id>/get-transfer-services-tab/', views.get_transfer_services_tab,name='get_transfer_services_tab'),

    # Şirket ve Şifre Yönetimi
    path('<int:agency_id>/company/<int:company_id>/save-password/', views.save_agency_password, name='save_agency_password'),

    # Şube İşlemleri
    path('<int:agency_id>/branches/', views.branch_list, name='branch_list'),
    path('<int:agency_id>/branch/<int:branch_id>/save/', views.save_branch, name='save_branch'),
    path('<int:agency_id>/branch/add/', views.add_branch, name='add_branch'),

    # Logo Güncelleme
    path('<int:agency_id>/update-logo/', views.update_agency_logo, name='update_agency_logo'),

    # ✅ Servis Yetkilendirme
    path('<int:agency_id>/authorize-service/', views.authorize_service, name='authorize_service'),
    path('<int:agency_id>/remove-service/<int:service_id>/', views.remove_service_authorization, name='remove_service_authorization'),
    path('<int:agency_id>/get-unassigned-services/', views.get_unassigned_services, name='get_unassigned_services'),

    # ✅ Teklif Yetkilendirme
    path('<int:agency_id>/remove-offer-service/<int:offer_service_id>/',views.remove_offer_service_authorization,name='remove_offer_service_authorization'),
    path("<int:agency_id>/authorize-offer-service/",views.authorize_offer_service,name="authorize_offer_service"),
    path('<int:agency_id>/get-unassigned-offer-services/', views.get_unassigned_offer_services,name='get_unassigned_offer_services'),

    # ✅ Transfer Servis Yetkilendirme
    path('<int:agency_id>/authorize-transfer-service/', views.authorize_transfer_service,name='authorize_transfer_service'),
    path('<int:agency_id>/remove-transfer-service/<int:transfer_service_id>/',views.remove_transfer_service_authorization, name='remove_transfer_service_authorization'),
    path('<int:agency_id>/get-unassigned-transfer-services/', views.get_unassigned_transfer_services,name='get_unassigned_transfer_services'),
    path('<int:agency_id>/toggle-transfer-service-status/<int:service_auth_id>/', views.toggle_transfer_service_status, name="toggle_transfer_service_status"),


]