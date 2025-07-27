import json
import re,logging,requests
import ssl
from decimal import Decimal, InvalidOperation
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from requests.adapters import HTTPAdapter
from django.conf import settings
from datetime import timedelta
from datetime import datetime
from requests.auth import HTTPBasicAuth
from database.models import Customer, CustomerContact, AssetCars, ExternalTramerPolicy
import uuid

logger = logging.getLogger(__name__)

class SSLAdapter(HTTPAdapter):
    """Legacy SSL bağlantılarını kabul eden adapter."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers('DEFAULT:@SECLEVEL=1')  # Güvenlik seviyesi düşürülüyor
        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def send_email(subject, to_email, context=None, template_name=None):
    """
    E-posta göndermek için yardımcı fonksiyon.

    :param subject: E-posta konusu
    :param to_email: Alıcı e-posta adresi
    :param context: Şablon için context (opsiyonel)
    :param template_name: Şablon dosyası (opsiyonel)
    """
    try:
        # Şablonu kullanarak HTML içeriği oluştur
        if template_name and context:
            html_message = render_to_string(template_name, context)
        else:
            raise ValueError("Şablon ve context gereklidir.")

        # E-posta oluştur
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        email.content_subtype = 'html'  # HTML içerik olduğunu belirt

        # E-postayı gönder
        email.send()
        return True
    except Exception as e:
        print(f"E-posta gönderilirken hata oluştu: {e}")
        return False


def create_or_update_customer_generic(
    agency_id: int,
    customer_dict_list: list
) -> list:
    if not customer_dict_list:
        return []

    created_ids = []
    valid_fields = {f.name for f in Customer._meta.fields}

    for data in customer_dict_list:
        identity_number = str(
            data.get("SigortaEttirenKimlikNo") or
            data.get("SigortaliKimlikNo") or
            data.get("SigortaEttirenVergiKimlikNo") or
            data.get("SigortaliVergiKimlikNo") or
            data.get("identity_number")
        ).strip()

        full_name = data.get("full_name") or data.get("SigortaEttirenAdi") or data.get("SigortaliAdi")

        if not identity_number or identity_number == "0":
            print(f"❌ Geçersiz TC/VKN: {identity_number} → kayıt yapılmayacak")
            continue

        if not full_name:
            print(f"❌ Ad soyad eksik → {identity_number}")
            continue

        birth_date = data.get("birth_date") or data.get("SigortaEttirenDogumTarihi") or data.get("SigortaliDogumTarihi")

        model_fields = {}
        extra_fields = {}

        for k, v in data.items():
            if isinstance(v, str) and ("tarih" in k.lower() or "date" in k.lower()):
                parsed = parse_date(v)
                v = parsed if parsed else None

            if k in valid_fields:
                model_fields[k] = v or None
            else:
                extra_fields[k] = v or None  # 👈 Model dışı (telefon gibi) alanları ayrı tut

        if birth_date:
            parsed_birth = parse_date(birth_date)
            if parsed_birth:
                model_fields["birth_date"] = parsed_birth

        model_fields["agency_id"] = agency_id

        try:
            obj, created = Customer.objects.update_or_create(
                identity_number=identity_number,
                agency_id=agency_id,
                defaults=model_fields
            )
            print(f"{'➕' if created else '♻️'} Müşteri işlendi: {identity_number}")
            created_ids.append(identity_number)

            # ✅ Telefon veya ekstra alanlar buradan alınır
            save_transfer_phone_if_valid(obj, extra_fields)

        except Exception as ex:
            print(f"❌ HATA: Customer kaydı başarısız → {ex}")
            continue

    if not isinstance(created_ids, list):
        print("⚠️ create_or_update_customer_generic dönüş tipi list değil!")
        return []

    print(f"📦 Dönüş listesi: {created_ids}")
    return [i for i in created_ids if i]

def create_or_update_asset_car_generic(agency_id: int, customer_id: int, car_data: dict):
    """
    🚗 AssetCars modeline kayıt/güncelleme işlemi.
    - agency_id ve customer_id tenant separation sağlar.
    - AracSasiNo varsa ona göre, yoksa AracPlakaTam üzerinden kontrol yapılır.
    """

    if not car_data:
        print("⚠️ Araç verisi boş.")
        return None

    sasi_no = car_data.get("AracSasiNo")
    plaka = car_data.get("AracPlakaTam", "").replace(" ", "")
    if not sasi_no and not plaka:
        print("❌ Şase veya plaka bilgisi yok, araç atlanacak.")
        return None

    valid_fields = {f.name for f in AssetCars._meta.fields}
    model_fields = {
        k: (parse_date(v) if "tarih" in k.lower() else v)
        for k, v in car_data.items() if k in valid_fields
    }

    model_fields["agency_id"] = agency_id
    model_fields["customer_id"] = customer_id
    model_fields["AktifMi"] = True  # ✅ Her zaman aktif kayıt yazılır

    lookup = {
        "agency_id": agency_id,
        "customer_id": customer_id,
    }

    if sasi_no:
        lookup["AracSasiNo"] = sasi_no
    else:
        lookup["AracPlakaTam"] = plaka

    try:
        obj, created = AssetCars.objects.update_or_create(
            defaults=model_fields,
            **lookup
        )
        print(f"{'🆕' if created else '♻️'} Araç işlendi → ID={obj.id}")
        return obj.id
    except Exception as e:
        print(f"❌ Araç kaydı hatası: {e}")
        return None

def create_external_policy(agency_id, company_id, customer, car, data, branch_id):
    print("📝 [create_external_policy] Başlatıldı")
    records = []

    # Geçmiş ve yürür poliçeleri birleştir
    try:
        gecmis = data["value"]["TramerSonucObjesi_sn040102TrafikPoliceSorguSonucu"].get("gecmisPoliceler", [])
        yurur = data["value"]["TramerSonucObjesi_sn040102TrafikPoliceSorguSonucu"].get("yururPoliceler", [])
    except Exception as e:
        print("❌ Response parse hatası:", e)
        return []

    combined = gecmis + yurur
    print(f"📦 Toplam kayıt: {len(combined)}")

    for row in combined:
        try:
            policy_key = row.get("policeAnahtari", {})
            tarih = row.get("tarihBilgileri", {})
            belge = row.get("belgeBilgileri", {})
            alanlar = row.get("Alanlar", {})

            obj, created = ExternalTramerPolicy.objects.update_or_create(
                agency_id=agency_id,
                PoliceNo=policy_key.get("policeNo"),
                ZeyilNo=row.get("policeEkiNo"),
                YenilemeNo=policy_key.get("yenilemeNo"),
                customer=customer,
                asset_car=car,
                defaults={
                    "SigortaSirketiKodu": policy_key.get("sirketKodu"),
                    "AcentePartajNo": policy_key.get("acenteKod"),
                    "PoliceBaslangicTarihi": parse_date(tarih.get("baslangicTarihi")),
                    "PoliceBitisTarihi": parse_date(tarih.get("bitisTarihi")),
                    "ZeyilBaslangicTarihi": parse_date(tarih.get("ekBaslangicTarihi")),
                    "ZeyilBitisTarihi": parse_date(tarih.get("ekBitisTarihi")),
                    "PoliceTanzimTarihi": parse_date(tarih.get("tanzimTarihi")),
                    "ZeyilTanzimTarihi": parse_date(belge.get("belgeTarih")),
                    "ZeyilKodu": row.get("policeEkiTuru"),
                    "AracTrafikKademe": belge.get("uygulanmisTarifeBasamakKodu"),
                    "branch_id": branch_id,
                }
            )

            print(f"{'🆕' if created else '♻️'} ExternalPolicy işlendi: {obj.PoliceNo}")
            records.append(obj)

        except Exception as e:
            print(f"❌ Kayıt hatası (policy): {e}")
            continue

    return records


def apply_company_field_mapping(response_data, mapping_qs, company_id=None, policy_data=None):
    if isinstance(response_data, dict) and "Alanlar" in response_data and isinstance(response_data["Alanlar"], dict):
        data_source = response_data["Alanlar"]
    else:
        data_source = response_data

    mapped_fields = {}
    police_no = get_by_path(data_source, "CariPolNo") or policy_data.get("police_no") if policy_data else "?"

    for mapping in mapping_qs:
        key = mapping.key.KeyName
        company_key = mapping.company_key
        company_param_val = mapping.company_parameter
        parameter = mapping.parameter

        val = None

        try:
            if "ListOfInfo.BILGI_ADI=" in company_key:
                key_part = company_key.split("ListOfInfo.BILGI_ADI=")[-1].split(":")[0].strip()
                value_field = company_key.split(":")[-1].strip()
                list_info = get_by_path(data_source, "ListOfInfo.Info")
                if isinstance(list_info, dict):
                    list_info = [list_info]
                if isinstance(list_info, list):
                    for info in list_info:
                        if info.get("BILGI_ADI") == key_part:
                            val = info.get(value_field)
                            if isinstance(val, dict) and val.get("nil") == "true":
                                val = None
                            break

            elif "KeyName=" in company_key:
                key_part = company_key.split("KeyName=")[-1].split(":")[0].strip()
                value_field = company_key.split(":")[-1].strip()
                kv_list = get_by_path(data_source, "PolicyResultKeySet.KeyValueSet")
                if isinstance(kv_list, dict):
                    kv_list = [kv_list]
                if isinstance(kv_list, list):
                    for item in kv_list:
                        if item.get("KeyName") == key_part:
                            val = get_by_path(item, f"KeyValueList.{value_field}")
                            break

            elif "ListOfUavt." in company_key:
                val = normalize_empty(get_by_path(data_source, company_key))
                if isinstance(val, dict):
                    val = None

            elif "SİGORTALILAR.SİGORTALI." in company_key:
                base = get_by_path(data_source, "SİGORTALILAR.SİGORTALI")
                sub_path = company_key.split("SİGORTALILAR.SİGORTALI.")[1]
                if isinstance(base, list):
                    val = get_by_path(base[0], sub_path)
                else:
                    val = get_by_path(base, sub_path)

            else:
                val = get_by_path(data_source, company_key)

        except Exception as ex:
            print(f"❌ [Mapping HATASI] PoliceNo={police_no} | Key={key} | Path={company_key} | Hata: {ex}")
            continue  # Mapping'i atla

        val = normalize_empty(val)
        if isinstance(val, dict):
            val = None
        if val not in [None, "", [], {}]:
            print(f"✅ [Mapping EŞLEŞTİ] PoliceNo={police_no} | Key={key} | Path={company_key} → Value: {val}")

        # Parametre ve doğrudan key eşleşmesi
        if parameter is not None:
            if (val is None or str(val).strip() == "") and (
                company_param_val is None or str(company_param_val).strip() == ""):
                mapped_fields[key] = parameter.ParameterID
            elif company_param_val is not None and str(val).strip() == str(company_param_val).strip():
                mapped_fields[key] = parameter.ParameterID
            if key in ["KayitTipi"]:
                mapped_fields[key + "_raw"] = val
            continue

        if key in [
            "SigortaEttirenKimlikNo", "SigortaliKimlikNo",
            "SigortaEttirenVergiNo", "SigortaliVergiNo",
            "SigortaEttirenAdi", "SigortaliAdi",
            "SigortaEttirenCepTelefonu", "SigortaliCepTelefonu",
            "RizikoAcikAdres"
        ]:
            mapped_fields[key] = str(val).strip() if val else None
            continue

        if key in ["SigortaEttirenDogumTarihi", "SigortaliDogumTarihi"]:
            parsed = parse_date(val)
            mapped_fields[key] = parsed
            continue

        mapped_fields[key] = parse_date(val) if "tarih" in key.lower() else val

    return mapped_fields


def apply_company_service_field_mapping(response_data, mapping_qs, extra_fields=None):
    if isinstance(response_data, dict) and "value" in response_data and isinstance(response_data["value"], dict):
        data_source = response_data["value"]
    else:
        data_source = response_data

    mapped_fields = {}

    # 🔹 Alanlar (Özel Tramer yapısı) ön hazırlık
    alanlar_dict = {}
    try:
        alanlar_dict = data_source.get("Alanlar", {})
        if not isinstance(alanlar_dict, dict):
            alanlar_dict = {}
    except Exception:
        alanlar_dict = {}

    print("🔎 Alanlar içerik tipi:", type(data_source["Alanlar"]))
    print("📌 Alanlar örnek:", data_source["Alanlar"])

    for mapping in mapping_qs:
        key = mapping.key.KeyName if mapping.key else None
        company_key = mapping.company_key
        company_param_val = mapping.company_parameter
        parameter = mapping.parameter

        if not key or not company_key:
            continue

        val = None

        try:
            # 🧩 1. Alanlar.XXX için özel kontrol
            if company_key.startswith("Alanlar."):
                key_name = company_key.split(".")[1]
                val = alanlar_dict.get(key_name)

            # 🧩 2. BILGI_ADI içeren özel yapı
            elif "ListOfInfo.BILGI_ADI=" in company_key:
                key_part = company_key.split("ListOfInfo.BILGI_ADI=")[-1].split(":")[0].strip()
                value_field = company_key.split(":")[-1].strip()
                list_info = get_by_path(data_source, "ListOfInfo.Info")
                if isinstance(list_info, dict):
                    list_info = [list_info]
                if isinstance(list_info, list):
                    for info in list_info:
                        if info.get("BILGI_ADI") == key_part:
                            val = info.get(value_field)
                            break

            # 🧩 3. Normal nested path
            elif "." in company_key:
                val = get_by_path(data_source, company_key)

            # 🧩 4. Düz dict alan
            else:
                val = data_source.get(company_key)

        except Exception:
            val = None

        val = normalize_empty(val)
        if isinstance(val, dict):
            val = None

        # 🎯 Parametre eşleşmesi varsa
        if parameter is not None:
            if (val is None or str(val).strip() == "") and (
                company_param_val is None or str(company_param_val).strip() == ""):
                mapped_fields[key] = parameter.ParameterID
            elif company_param_val is not None and str(val).strip() == str(company_param_val).strip():
                mapped_fields[key] = parameter.ParameterID
            continue

        # 🎯 Tarih parse
        if "tarih" in key.lower():
            mapped_fields[key] = parse_date(val)
        else:
            mapped_fields[key] = val

    # ✅ Ekstra alanlar (örneğin TC formdan geliyorsa)
    if extra_fields:
        mapped_fields.update(extra_fields)

    return mapped_fields



def save_transfer_phone_if_valid(customer, data: dict):
    print(f"📞 [DEBUG] save_transfer_phone_if_valid → customer: {customer.identity_number}")

    phone_keys = ["SigortaEttirenCepTelefonu", "SigortaliCepTelefonu"]
    for tel_key in phone_keys:
        raw_phone = data.get(tel_key)
        print(f"🔍 [DEBUG] tel_key: {tel_key} → raw_phone: {raw_phone}")
        if raw_phone:
            phone = str(raw_phone).strip()
            print(f"📞 [DEBUG] Stripped phone → {phone}")

            if is_valid_phone(phone):
                print(f"✅ [VALID] is_valid_phone geçti → {phone}")
                exists = CustomerContact.objects.filter(customer=customer, value=phone).exists()
                print(f"🔎 [CHECK] DB'de var mı? → {exists}")
                if not exists:
                    try:
                        contact = CustomerContact.objects.create(
                            customer=customer,
                            contact_type='phone',
                            value=phone,
                            label='transfer',
                            is_primary=False,
                            is_verified=False,
                            is_active=True
                        )
                        print(f"✅ [KAYIT] Telefon kaydedildi → {contact}")
                    except Exception as ex:
                        print(f"❌ [HATA] CustomerContact kayıt hatası: {ex}")
                else:
                    print(f"ℹ️ [SKIP] Telefon zaten kayıtlı → {phone}")
            else:
                print(f"❌ [GEÇERSİZ] is_valid_phone başarısız → {phone}")
        else:
            print(f"ℹ️ [BOŞ] {tel_key} alanı yok.")


def get_universal_full_name(data: dict, ad_key: str, soyad_key: str) -> str:
    ad = (data.get(ad_key) or "").strip()
    soyad = (data.get(soyad_key) or "").strip()
    if ad and soyad:
        return f"{ad} {soyad}"
    elif ad:
        return ad
    elif soyad:
        return soyad
    return ""

def get_first_valid(response_data, *keys):
    for key in keys:
        val = response_data.get(key)
        if val not in [None, "", {}]:
            return val
    return None

def extract_value_from_raw_text(xml_text: str, key: str):
    pattern = fr"<{re.escape(key)}>(.*?)</{re.escape(key)}>"
    match = re.search(pattern, xml_text)
    if match:
        return match.group(1).strip()
    return None


def normalize_decimal(val):
    if not val or val in ["{}", [], "None"]:
        return None

    if isinstance(val, dict):
        print(f"⚠️ Decimal değer dict olarak geldi, atlanıyor → {val}")
        return None

    if isinstance(val, (float, int, Decimal)):
        return Decimal(str(val))

    try:
        str_val = str(val).strip()

        # Eğer içinde hem "," hem "." varsa → Amerikan formatı: "4,171.89"
        if "," in str_val and "." in str_val:
            str_val = str_val.replace(",", "")
        # Eğer sadece "," varsa → Avrupa formatı: "4171,89"
        elif "," in str_val:
            str_val = str_val.replace(",", ".")

        return Decimal(str_val)
    except (InvalidOperation, ValueError):
        print(f"❌ Geçersiz decimal formatı: {val}")
        return None

def normalize_empty(value):
    if value in ["", " ", None]:
        return None
    return value

def parse_date(val):
    if not val:
        return None

    val = str(val).strip().replace("\n", "").replace("\r", "")

    # ✅ .NET JSON tarih formatı: /Date(1753218000000)/
    if "Date(" in val:
        try:
            timestamp = int(re.search(r"\d+", val).group()) / 1000
            return datetime.utcfromtimestamp(timestamp).date()
        except Exception as e:
            print("❌ .NET tarih parse hatası:", e, "| Girdi:", val)

    # ✅ 13 haneli timestamp string (örnek: 1753218000000)
    if val.isdigit() and len(val) == 13:
        try:
            return datetime.utcfromtimestamp(int(val) / 1000).date()
        except Exception as e:
            print("❌ Timestamp tarih parse hatası:", e, "| Girdi:", val)

    try:
        # Türk tipi: 24.07.2025
        if re.match(r"\d{2}\.\d{2}\.\d{4}", val):
            return datetime.strptime(val, "%d.%m.%Y").date()

        # ISO tipi: 2025-07-24
        elif re.match(r"\d{4}-\d{2}-\d{2}", val):
            return datetime.strptime(val[:10], "%Y-%m-%d").date()

        # Slash tipi: 24/07/2025
        elif re.match(r"\d{2}/\d{2}/\d{4}", val):
            return datetime.strptime(val, "%d/%m/%Y").date()

        # ISO full datetime: 2025-07-24T15:30:00
        elif re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val):
            return datetime.strptime(val[:10], "%Y-%m-%d").date()

        # YYYMMDD tipi: 20250724
        elif re.match(r"\d{8}", val):
            return datetime.strptime(val, "%Y%m%d").date()

    except Exception as e:
        print("❌ parse_date hatası:", e, "| Girdi:", val)

    return None



def split_date_range(start_date, end_date, days=3):
    """
    İki tarih arasını 'days' gün arayla bloklara böler.
    """
    current = start_date
    result = []
    while current <= end_date:
        next_end = min(current + timedelta(days=days-1), end_date)
        result.append((current, next_end))
        current = next_end + timedelta(days=1)
    return result


def is_valid_phone(value):
    if not value:
        return False

    value = str(value).strip().replace(" ", "")

    # 🔄 Normalize: +90 veya 90 ile başlıyorsa 0 ile değiştir
    if value.startswith("+90"):
        value = "0" + value[3:]
    elif value.startswith("90") and len(value) == 12:
        value = "0" + value[2:]
    elif value.startswith("0") and len(value) == 11:
        value = value

    # 🔪 Sıfırı kaldır ve 10 haneli formatta kontrol et
    value = value.lstrip("0")

    if not (value.isdigit() and len(value) == 10):
        return False

    VALID_PREFIXES = {
        "501", "502", "503", "504", "505", "506", "507", "508", "509",
        "530", "531", "532", "533", "534", "535", "536", "537", "538", "539",
        "541", "542", "543", "544", "545", "546", "547", "548", "549",
        "550", "551", "552", "553", "554", "555", "556",
    }

    prefix = value[:3]
    if prefix not in VALID_PREFIXES:
        return False

    FAKE_NUMBERS = {
        "1111111111", "2222222222", "3333333333", "4444444444", "5555555555",
        "6666666666", "7777777777", "8888888888", "9999999999",
        "1234567890", "0123456789", "0000000000"
    }

    last_7 = value[-7:]
    if value in FAKE_NUMBERS or re.match(r'(\d)\1{6,}', last_7):
        return False
    if last_7 in {"1234567", "2345678", "3456789", "4567890", "0123456"}:
        return False

    return True

def clean_namespaces(obj):
    if isinstance(obj, dict):
        return {k.split(":")[-1] if ":" in k else k: clean_namespaces(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_namespaces(i) for i in obj]
    return obj

def get_by_path(data, path_str):
    parts = path_str.split('.')
    for i, part in enumerate(parts):
        if isinstance(data, list):
            # 🔄 Son path elemanıysa list olarak bırak
            if i == len(parts) - 1:
                return data
            data = data[0] if data else {}
            if not isinstance(data, dict):
                return None

        if not isinstance(data, dict):
            return None

        # Key normalize
        key_found = None
        for k in data.keys():
            if k.strip().lower() == part.strip().lower():
                key_found = k
                break

        if key_found:
            data = data.get(key_found, {})
        else:
            return None

    # dict ise boş ya da nil kontrolü
    if isinstance(data, dict):
        if data.get("@i:nil") == "true" or data.get("nil") == "true":
            return None
        if "#text" in data:
            return data["#text"]
        if not data:
            return None

    return data


def parse_date_from_string(val):
    if not val:
        return None

    val = val.strip()

    try:
        # 1998-05-16T00:00:00 gibi ISO formatı
        if "T" in val:
            val = val.split("T")[0]

        # GG.AA.YYYY
        if re.match(r"\d{2}\.\d{2}\.\d{4}$", val):
            return datetime.strptime(val, "%d.%m.%Y").date()
        # YYYY-MM-DD
        elif re.match(r"\d{4}-\d{2}-\d{2}$", val):
            return datetime.strptime(val, "%Y-%m-%d").date()
        # YYYY/MM/DD
        elif re.match(r"\d{4}/\d{2}/\d{2}$", val):
            return datetime.strptime(val, "%Y/%m/%d").date()
        # GG/AA/YYYY
        elif re.match(r"\d{2}/\d{2}/\d{4}$", val):
            return datetime.strptime(val, "%d/%m/%Y").date()
        # Düz 8 hane: 31012025
        elif re.match(r"\d{8}$", val):
            return datetime.strptime(val, "%d%m%Y").date()
    except Exception:
        pass

    return None

def get_api_token_from_passwords(password_info):
    """
    AgencyPasswords üzerinden token alır.
    """
    if not password_info or not password_info.token_url:
        logger.warning("⚠️ Token URL tanımlı değil → token alınamadı.")
        return None

    try:
        logger.info(f"🎯 Token alınmaya çalışılıyor → URL: {password_info.token_url}")
        response = requests.post(
            password_info.token_url,
            auth=HTTPBasicAuth(password_info.token_username, password_info.token_password),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
            verify=False
        )
        response.raise_for_status()
        response_data = response.json()
        token = response_data.get("access_token") or response_data.get("token") or response_data.get("result", {}).get("token")
        logger.info(f"✅ Token alındı: {token if token else '❌ Boş geldi'}")
        return token
    except Exception as e:
        logger.error(f"❌ Token alma hatası: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"📥 Token response: {e.response.text}")
        return None

def generate_referans_no(gw_agent_id: int, gw_service_operation_id: int, platform_proposal_id="0") -> str:
    """
    Örnek çıktı: 15_20250725112543983_ab123_0_19
    """
    now_str = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]  # yyyyMMddHHmmssfff
    guid_part = uuid.uuid4().hex[:5]  # ilk 5 karakter
    return f"{gw_agent_id}_{now_str}{guid_part}_{platform_proposal_id}_{gw_service_operation_id}"
