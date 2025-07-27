# offer/utils.py
from django.db.models import Case, When, IntegerField
from database.models import Key, Parameter, KeyParameters
import os
import redis


FORM_KEY_MAPPING = {
    "home": {
        "varlik": [104, 105, 106, 107, 108, 109, 112],
        "sigortali": [7, 1, 9, 10, 33],
        "sigorta_ettiren": [19, 4, 21, 22],
        "adres": [144, 100, 102, 195, 196, 197, 198, 199, 200, 201, 202],
        "teklif": [54, 55, 56, 118, 164]
    },
    "health": {
        "sigortali": [7, 1, 9, 10, 33],
        "sigorta_ettiren": [19, 4, 21, 22],
        "teklif": [54, 55, 56],
        "police": [144, 50, 52, 219]
    },
    "travel": {   # ← SEYAHAT SAĞLIK için yeni blok
        "sigortali": [7, 1, 9, 10, 33],  # Sigortalı kişisel bilgiler
        "sigorta_ettiren": [19, 4, 21, 22],  # Sigorta ettiren kişi (isteğe bağlı)
        "trip": [223,224],   # Gidiş/dönüş tarihi, seyahat süresi, ülke, şehir, vize tipi gibi key id'leri
        "teklif": [54, 55, 56]     # Teklif ve ürün detayları (ör: prim, teminat)
    },
    "assistant": {  # ← Yeni ürün adı
        "sigortali": [7, 1, 9, 10, 33],  # Sigortalı bilgileri (TC, ad, doğum, telefon vs.)
        "sigorta_ettiren": [19, 4, 21, 22],  # Sigorta ettiren
        "arac_bilgi":[156,77,79,85,81,88,82,80],
        "ek_bilgiler": [12,124],  # Buraya assistant’a özel ek bilgi alanları gelecek (örnek id'ler)
        "teklif": [54, 55, 56, ]  # Teklif ve ürün detayları (örnek id’ler)
    },
    "imm": {  # ← Ferdi Kaza veya istediğin IMM ürünü
        "sigortali": [7, 1, 9, 10, 33],  # Sigortalı kişisel bilgiler (TC, ad, doğum, tel, cinsiyet gibi)
        "sigorta_ettiren": [19, 4, 21, 22],  # Sigorta ettiren kişi (isteğe bağlı)
        "arac_bilgi": [156,77,79,85,81,88,82,80,89,90],  # Araç veya plaka, marka/model gibi özel key'ler (örnek)
        "ek_bilgiler": [225],  # Ürüne özel ekstra bilgiler (ör: ek teminatlar, iş kolu vs.)
        "teklif": [54, 55, 56]  # Teklif ve ürün detayları (ör: prim, teminat, ürün kodu)
    }
}


PRODUCT_BUNDLE_MAP = {
    "102": ["102", "103"],  # DASK → DASK ve KONUT
    # "105": ["105", "108"],  # Sağlık → Sağlık ve Tamamlayıcı gibi (ileride)
}


def get_keys_with_parameters(key_ids):
    keys_with_data = []

    preserved_order = Case(
        *[When(KeyID=pk, then=pos) for pos, pk in enumerate(key_ids)],
        output_field=IntegerField()
    )

    for key in Key.objects.filter(KeyID__in=key_ids).order_by(preserved_order):
        param_ids = KeyParameters.objects.filter(KeyID=key.KeyID).values_list('ParameterID', flat=True)
        parameters = Parameter.objects.filter(ParameterID__in=param_ids, IsActive=True) \
            .values("ParameterID", "ParameterName")

        keys_with_data.append({
            "id": key.KeyID,
            "name": key.KeyName,
            "description": key.Description or key.KeyName,
            "input_type": key.InputType or "text",
            "min_length": key.MinLength,
            "max_length": key.MaxLength,
            "regex": key.RegexPattern,
            "readonly": False,
            "visible_if_key": key.VisibleIfKey,
            "visible_if_value": key.VisibleIfValue,
            "parameters": list(parameters),  # 👈 artık [{'ParameterID': 1, 'ParameterName': 'Betonarme'}, ...]
        })

    return keys_with_data

REDIS_HOST = "redis" if os.environ.get("DOCKERIZED") == "true" else "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True  # string tipinde veri döndürür
)