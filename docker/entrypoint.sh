#!/bin/bash

echo "🚀 Django Celery Worker başlatılıyor..."

# Gerekirse migrate burada aktif edebilirsin
# python manage.py migrate

# Komutu çalıştır
exec "$@"