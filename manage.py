#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

from django.core.management import execute_from_command_line
from django.core.management.commands.runserver import Command as Runserver

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'INSAI.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    # Varsayılan portu 8001 yap
    Runserver.default_port = "8001"
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()  # main() fonksiyonunu çağır
