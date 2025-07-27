from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# 📌 Geliştirme Modu
DEBUG = True

# 📌 Local Allowed Hosts
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# 📌 Local Email Ayarları (Outlook SMTP)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.office365.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "mail@sigorta.com"  # kendi mailin
EMAIL_HOST_PASSWORD = "********"      # mail şifresi (app password önerilir)

# 📌 Local Database Ayarı (MSSQL - Windows Authentication)
DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": "INSAI3",
        "HOST": "localhost",
        "PORT": "",  # boş bırak
        "OPTIONS": {
            "driver": "ODBC Driver 17 for SQL Server",
            "trusted_connection": "yes",
        },
    }
}

# 📌 Static ve Media dizinleri
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
