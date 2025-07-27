from django.shortcuts import redirect
from django.urls import path
from .views import user_login, home_redirect,password_change,user_profile,upload_profile_picture,forgot_password
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("login/", user_login, name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("password_change/", password_change, name="password_change"),
    path("", home_redirect, name="home"),
    path('profile/<uuid:key_guid>/', user_profile, name='profile'),
    path('profile/<uuid:key_guid>/upload/', upload_profile_picture, name='upload_profile_picture'),
    path("forgot-password/", forgot_password, name="forgot_password"),

]