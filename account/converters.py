# yourapp/converters.py
from django.urls.converters import UUIDConverter, register_converter

class CaseInsensitiveUUIDConverter(UUIDConverter):
    def to_python(self, value):
        return str(super().to_python(value)).lower()

    def to_url(self, value):
        return str(super().to_url(value)).lower()