from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from account.converters import CaseInsensitiveUUIDConverter
from django.urls import register_converter

# UUID converter kaydı
register_converter(CaseInsensitiveUUIDConverter, 'caseuuid')

# Özel 404 sayfası tanımı
handler404 = "account.views.custom_404_view"

urlpatterns = [
    path('', lambda request: redirect('login'), name='home'),  # Girişe yönlendirme
    path('admin/', admin.site.urls),
    path('login/', include('account.urls')),     # Giriş işlemleri
    path('account/', include('account.urls')),   # Hesap işlemleri
    path('dashboard/', include('dashboard.urls')),
    path('database/', include('database.urls')),
    path('agency/', include('agency.urls')),
    path('agencyusers/', include('agencyusers.urls')),
    path('proposal/', include('offer.urls')),
    path('gateway/', include('gateway.urls')),
    path('docservice/', include('docservice.urls')),
    path('transfer/', include('transfer.urls')),

]

# 🔥 Her ortamda media & static dosyalarını servis et
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
