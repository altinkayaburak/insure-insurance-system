from django.shortcuts import redirect
from django.conf import settings
from django.urls import resolve

EXEMPT_URLS = [
    '/login/',
    '/logout/',
    '/password_change/',
    '/static/',  # statik dosyalar
    '/account/',  # özel sayfaların dışı
]

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if not request.user.is_authenticated and not any(path.startswith(url) for url in EXEMPT_URLS):
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        return self.get_response(request)
