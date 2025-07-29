from django.urls import path
from . import views

urlpatterns = [
    path('keys/', views.key_list, name='key_list'),
    path('api/keys/', views.api_key_list, name="api_keys"),
    path('keys/save/', views.save_key, name='add_key'),  # Yeni kayıt için
    path('keys/save/<int:key_id>/', views.save_key, name='edit_key'),  # Güncelleme için
    path('keys/detail/<int:key_id>/', views.key_detail, name='key_detail'),
    path('api/parameters-for-key/', views.get_parameters_for_key, name="api_parameters_for_key"),
    path('parameters/', views.parameters_list, name='parameters_list'),
    path('parameters/add/', views.add_parameters, name='add_parameters'),
    path('parameters/edit/<int:param_id>/', views.edit_parameter, name='edit_parameter'),
    path('delete-key-parameter/<int:key_id>/<int:parameter_id>/', views.delete_key_parameter, name='delete_key_parameter'),
    path('search-keys/', views.search_keys, name='search_keys'),
    path('insurance-companies/', views.insurance_company_list, name='insurance_company_list'),
    path('insurance-companies/save/', views.save_insurance_company, name='save_insurance_company'),  # Ekle + güncelle
    path('insurance-companies/search/', views.search_insurance_companies, name='search_insurance_companies'),
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.add_product, name='add_product'),
    path('products/update/', views.update_product, name='update_product'),
    path('api/companies/', views.get_companies, name="api_companies"),
    path("api/policy-branches/", views.get_policy_branches, name="get_policy_branches"),

    path('services/', views.get_services, name="get_services"),
    path('services/<int:service_id>/', views.get_service_detail, name="service_detail"),
    path('services/<int:service_id>/template/', views.update_template, name="update_template"),
    path('services/new/', views.create_or_update_service, name="create_service"),
    path('services/<int:service_id>/update/', views.create_or_update_service, name="update_service"),
    path('service-configurations/', views.service_configurations_view, name="service_configurations_page"),

    path('get-customer/', views.get_customer, name='get_customer'),
    path("save-or-update-customer/", views.save_or_update_customer, name="save_or_update_customer"),
    path('save-customer-with-relationship/', views.save_customer_with_relationship, name='save_customer_with_relationship'),

    path('customer/', views.customer_detail, name='customer_detail'),
    path('search-customer/', views.customer_search_page, name='search_customer'),

    path("get-relationship-types/", views.get_relationship_types, name="get_relationship_types"),
    path("get-customer-relationships/", views.get_customer_relationships, name="get_customer_relationships"),
    path('delete-relationship/<int:relation_id>/', views.delete_customer_relationship, name='delete_relationship'),

    path("policies/", views.policy_list_page, name="policy_list_page"),
    path("get-policy-list/", views.get_policy_list_json, name="get_policy_list"),
    path("api/filter-options/", views.get_filter_options, name="get_filter_options"),

    path("customer/<int:customer_id>/policies/", views.customer_policy_list, name="customer_policy_list"),
    path("policy/<str:uuid>/", views.policy_detail_page, name="policy_detail_page"),

    path("offer-services/", views.get_offer_services, name="get_offer_services"),
    path("offer-services/<int:service_id>/", views.get_offer_service_detail, name="get_offer_service_detail"),
    path("offer-services/create/", views.create_or_update_offer_service, name="create_offer_service"),
    path("offer-services/<int:service_id>/update/", views.create_or_update_offer_service, name="update_offer_service"),
    path("offer-services/<int:service_id>/template/", views.update_offer_soap_template,name="update_offer_soap_template"),
    path('offer-service-configurations/', views.offer_service_configurations_view, name="offer_service_configurations_page"),

    path("transfer/services/api/", views.get_transfer_services, name="get_transfer_services"),
    path("transfer/services/new/", views.create_or_update_transfer_service, name="create_transfer_service"),
    path("transfer/services/<int:service_id>/update/", views.create_or_update_transfer_service,
         name="update_transfer_service"),
    path("transfer/services/<int:service_id>/", views.get_transfer_service_by_id, name="get_transfer_service"),
    path("transfer/services/<int:service_id>/template/", views.update_transfer_soap_template,
         name="update_transfer_soap_template"),
    path("transfer/services/", views.transfer_service_list_view, name="transfer_service_list"),


    path("service-logs/", views.service_log_list, name="service_log_list"),
    path('service-mapping/', views.service_mapping_page, name='service_mapping'),
    path('get-unmapped-product-codes/', views.get_unmapped_product_codes, name='get_unmapped_product_codes'),
    path('api/save-mappings/', views.save_mappings, name="api_save_mappings"),

    path("proposals/", views.proposal_list, name="proposal_list"),
    path('get-customer-proposals/', views.get_customer_proposals, name='get_customer_proposals'),
    path('get-customer-contacts/', views.get_customer_contacts, name='get_customer_contacts'),
    path('add-customer-contact/', views.add_customer_contact, name='add_customer_contact'),
    path('delete-customer-contact/', views.delete_customer_contact, name='delete_customer_contact'),

    path("get-customer-assets/", views.customer_assets_view, name="get_customer_assets"),
    path("customer/<int:customer_id>/assets/", views.customer_assets_view, name="customer_assets"),

    path("api/revision-options/", views.get_company_revision_options, name="get_company_revision_options"),
    path("cookie/", views.cookie_log_view, name="cookie_logs"),

]
