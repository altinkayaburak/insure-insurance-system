from django.urls import path
from . import views, tests

urlpatterns = [
    path('get-cities/', views.get_cities, name='get_cities'),
    path('get-ilceler/', views.get_ilceler, name='get_ilceler'),
    path('get-koyler/', views.get_koyler, name='get_koyler'),
    path('get-mahalleler/', views.get_mahalleler, name='get_mahalleler'),
    path('get-csbm/', views.get_csbm, name='get_csbm'),
    path('get-binalar/', views.get_binalar, name='get_binalar'),
    path('get-daireler/', views.get_daireler, name='get_daireler'),
    path('get-adres-detay/', views.get_adres_detay, name='get_adres_detay'),
    path('get-adres-detay/', views.get_adres_detay, name='get_adres_detay'),

    path('ray-adres-detay/', views.get_ray_adres_detay, name='get_ray_adres_detay'),
    path('get-uavt-from-db/', views.get_uavt_from_db, name='get_uavt_from_db'),

    path("api/get-universal-birthdate/", views.api_get_universal_birthdate, name="api_get_universal_birthdate"),
    path('get-customer-birthdate/', views.get_customer_birthdate, name='get_customer_birthdate'),
    path("get-customer-birthdate-v2/", views.get_customer_birthdate_v2, name="get_customer_birthdate_v2"),
    path("get-customer-birthdate-v3/", views.get_customer_birthdate_v3, name="get_customer_birthdate_v3"),
    path("get-customer-birthdate-v4/", views.get_customer_birthdate_v4, name="get_customer_birthdate_v4"),
    path("get-customer-from-ray/", views.get_customer_from_ray_v2, name="get_customer_from_ray"),
    path('get-katilim-birthdate/', views.get_katilim_birthdate, name='get_katilim_birthdate'),
    path('save-customer-to-ray/', views.save_customer_to_ray, name='save_customer_to_ray'),
    path('get-dask-police/', views.dask_police_sorgula, name='get_dask_police'),
    path("uavt/update-extra/", views.update_uavt_details_extra_fields, name="update_uavt_extra"),
    path("customer/bereket/", views.get_customer_bereket, name="get_customer_bereket"),
    path("customer/unico/", views.get_customer_unico, name="get_customer_unico"),
    path("customer/orient/", views.get_customer_orient, name="get_customer_orient"),
    path("get_customer_ankara_v2/", views.get_customer_ankara_v2, name="get_customer_ankara_v2"),
    path("call-katilim-customer-info/", views.call_katilim_customer_info, name="call_katilim_customer_info"),

    path('query-online-policy/', views.egm_query_online_policy, name='egm_query_online_policy'),
    path('get-arac-markalari/', views.get_arac_markalari, name='get_arac_markalari'),
    path('get-arac-tarzlari/', views.get_arac_tarzlari, name='get_arac_tarzlari'),
    path('get-model-years/', views.get_model_years, name='get_model_years'),
    path("get-arac-modelleri/", views.get_arac_modelleri, name="get_arac_modelleri"),
    path("egm-ray/", views.egm_ray, name="egm_ray"),




]