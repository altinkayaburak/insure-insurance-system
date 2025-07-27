# agencyusers/models.py
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class Users(AbstractUser):
    # Temel Bilgiler
    username = models.CharField(max_length=150, unique=True)
    identity_no = models.CharField(max_length=150, unique=True)
    birth_date = models.DateField(null=True, blank=True)  # Doğum tarihi
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    email_confirmed = models.BooleanField(default=False)  # E-posta onay durumu
    phone_number = models.CharField(max_length=15, blank=True, null=True, unique=True)
    password = models.CharField(max_length=128)  # Şifre (Django'nun varsayılan şifre alanı)
    password_updated_at = models.DateTimeField(default=timezone.now)  # Şifre güncelleme tarihi
    first_login = models.BooleanField(default=True)  # İlk giriş yapılıp yapılmadığını takip eder

    # Adres Bilgileri
    city = models.CharField(max_length=100, blank=True, null=True)  # Şehir
    district = models.CharField(max_length=100, blank=True, null=True)  # İlçe

    # İş Bilgileri
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')  # Departman
    title = models.ForeignKey('Title', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')  # Ünvan
    role = models.ForeignKey('Role', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')  # Rol
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')

    # Acente ve Şube Bilgileri
    agency = models.ForeignKey('agency.Agency', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')  # Acente
    branch = models.ForeignKey('agency.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')  # Şube

    # Sistem Bilgileri
    date_joined = models.DateTimeField(auto_now_add=True)  # Kayıt tarihi
    last_login = models.DateTimeField(null=True, blank=True)  # Son giriş tarihi
    last_page_visited = models.CharField(max_length=255, blank=True, null=True)  # Son ziyaret edilen sayfa
    is_staff = models.BooleanField(default=False)  # Personel durumu
    is_active = models.BooleanField(default=True)  # Aktiflik durumu
    is_superuser = models.BooleanField(default=False)  # Süper kullanıcı durumu

    # Profil Resmi
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)  # Profil resmi

    # Güvenlik ve Kimlik Doğrulama
    key_guid = models.CharField(max_length=36, unique=True, default=uuid.uuid4, editable=False)

    # Meta Bilgileri
    class Meta:
        db_table = "users"
        verbose_name = "Kullanıcı"
        verbose_name_plural = "Kullanıcılar"
        ordering = ['-date_joined']

    def __str__(self):
        return self.username

    # Şifre güncelleme işlemi
    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_updated_at = timezone.now()
        self.save()

class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "departments"
        verbose_name = "Departman"
        verbose_name_plural = "Departmanlar"

    def __str__(self):
        return self.name


class Title(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "titles"
        verbose_name = "Ünvan"
        verbose_name_plural = "Ünvanlar"

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "roles"
        verbose_name = "Rol"
        verbose_name_plural = "Roller"

    def __str__(self):
        return self.name

