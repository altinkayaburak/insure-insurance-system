from django.urls import path
from . import views


urlpatterns = [

    path('request-pdf/', views.request_pdf, name='request_pdf'),
    path("poll-pdf-result/",views.poll_pdf_result, name="poll_pdf_result"),

]
