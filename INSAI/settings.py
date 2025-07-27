import os
from pathlib import Path
import socket

from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-b5f#th&($t4k1i-t21$0d@^yo4jsa&z=phs%*x_*9mimfr^08k'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['10.10.5.74', 'localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'home',
    'database',
    'dashboard',
    'agency',
    'agencyusers',
    'account',
    'offer',
    'gateway',
    'docservice',
    'cookie',
    'transfer',
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'INSAI.middleware.LoginRequiredMiddleware',

]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',  # Geliştirme için yeterli
    }
}

ROOT_URLCONF = 'INSAI.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],  # BASE_DIR/templates dizinine işaret etmelidir
        'APP_DIRS': True,  # Uygulama içindeki templates klasörlerini de bulsun
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
1

WSGI_APPLICATION = 'INSAI.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

import socket

hostname = socket.gethostname()

# 🔍 IP tabanlı ayrım: Docker veya ortamdan bağımsız çalışsın
if os.environ.get("DOCKERIZED") == "true":
    db_host = "192.168.1.101"  # Şirkette konteynerden bağlanırken bu IP
else:
    db_host = "localhost\\SQLEXPRESS01"  # Lokal ortamda SQL Server instance adı

DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'INSAI3',
        'USER': 'insai_worker',
        'PASSWORD': 'Insai2025secure',
        'HOST': db_host,
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    }
}




# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = "Europe/Istanbul"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

import os

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]  # geliştirici dizinin
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")    # canlıda servis edilecek dizin

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # profil resimleri buradan okunur



DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'





AUTH_USER_MODEL = 'agencyusers.Users'  # Doğru uygulama ve model adı

# settings.py

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.office365.com'  # Outlook SMTP sunucusu
EMAIL_PORT = 587  # Outlook için port
EMAIL_USE_TLS = True  # TLS kullan
EMAIL_HOST_USER = 'helpio@sigortambir.com'  # E-posta adresiniz
EMAIL_HOST_PASSWORD = '1r+Tep@2024*'  # E-posta şifreniz
DEFAULT_FROM_EMAIL = 'helpio@sigortambir.com'  # Varsayılan gönderen e-posta


SESSION_COOKIE_AGE = 16000  # 10 dakika (saniye cinsinden)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Tarayıcı kapanınca oturum sonlanır
SESSION_SAVE_EVERY_REQUEST = True  # Kullanıcı her istek yaptığında oturum süresi yenilenir

LOGIN_URL = "/login/"



if os.environ.get("DOCKERIZED") == "true":
    CELERY_BROKER_URL = "redis://redis:6379/0"
else:
    CELERY_BROKER_URL = "redis://localhost:6379/0"

CELERY_RESULT_BACKEND = "django-db"
INSTALLED_APPS += ["django_celery_results"]



CELERY_BEAT_SCHEDULE = {
    # ✅ Katılım: 30 dakikada bir
    'update_katilim_cookies_periodic': {
        'task': 'cookie.tasks.update_katilim_cookies',
        'schedule': 60 * 10,
        'args': (5,),
    },

    # ✅ Bereket: 1 dakikada bir (test için)
    'update_bereket_cookies_periodic': {
        'task': 'cookie.tasks.update_bereket_cookies',
        'schedule': 60 * 10,
        'args': (5,),   # test için agency_id=3
    },
    'update_neova_cookies_periodic': {
        'task': 'cookie.tasks.update_neova_cookies',
        'schedule': 60 * 10,
        'args': (5,),    # 📌 agency_id = 5 (test için)
    },

    # ✅ Haftalık transfer
    'run_weekly_transfers': {
        'task': 'transfer.tasks.run_hourly_transfers',
        'schedule': crontab(minute=0, hour=6, day_of_week='sun'),
    },
}


# Local ayar dosyası eklensin (şifre, bağlantı vs.)
try:
    from .settings_local import *
except ImportError:
    pass