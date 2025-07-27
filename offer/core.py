import ssl,json,xmltodict,logging,requests
from datetime import datetime
from importlib import import_module
import xml.etree.ElementTree as ET
from jinja2 import Template
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from INSAI.utils import get_api_token_from_passwords
from gateway.models import ProposalServiceLog
from offer.models import ProposalDetails
from django.utils.timezone import now
from agency.models import AgencyPasswords
from database.models import OfferServiceConfiguration, InsuranceCompany

logger = logging.getLogger(__name__)

class SSLAdapter(HTTPAdapter):
    """Legacy SSL bağlantılarını ve sertifika doğrulamasını devre dışı bırakır."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


class LegacySSLAdapter(HTTPAdapter):
    """Legacy SSL bağlantılarını ve sertifika doğrulamasını devre dışı bırakır."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class UniversalUnsafeSSLAdapter(HTTPAdapter):
    """Tüm sertifikaları kabul eder ve legacy renegotiation'ı da aktif eder."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl._create_unverified_context()
        try:
            context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        except Exception:
            pass
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def match_company_parameters(form_data: dict, product_code: str, insurance_company_id: int) -> dict:
    """
    Form verisini CompanyParameterMapping tablosu ile eşleştirir.

    Giriş:
        form_data = {"105": 17, "100": "68504428", ...}
        product_code = "102"
        insurance_company_id = 7

    Çıkış:
        {
            "Informations:BinaInsaYili": "2013",
            "Informations:DaskPoliceNo": "68504428"
        }
    """
    from database.models import CompanyParameterMapping

    matched = {}

    for key_id_str, value in form_data.items():
        if not key_id_str.isdigit():
            continue  # "proposal_id", "user_id" gibi alanları geç

        key_id = int(key_id_str)
        parameter_id = int(value) if str(value).isdigit() else None


        # 🎯 Kural 1: Parametre ID ile tam eşleşme
        mapping_qs = CompanyParameterMapping.objects.filter(
            insurance_company_id=insurance_company_id,
            product_code=str(product_code),
            key_id=key_id,
            parameter_id=parameter_id
        )

        if mapping_qs.exists():
            mapping = mapping_qs.first()
            matched[mapping.target_company_key] = mapping.company_parameter or str(value)
            continue

        # 🎯 Kural 2: Parametre'siz eşleşme (parameter_id IS NULL)
        mapping_qs = CompanyParameterMapping.objects.filter(
            insurance_company_id=insurance_company_id,
            product_code=str(product_code),
            key_id=key_id,
            parameter__isnull=True
        )

        if mapping_qs.exists():
            mapping = mapping_qs.first()
            matched[mapping.target_company_key] = str(value)

    return matched


def run_offer_service(detail, form_data):
    proposal = detail.proposal
    company = detail.insurance_company
    agency = detail.agency


    offer_service = None
    request_body = ""
    response_text = ""
    success = False

    LEGACY_COMPANIES = [7, 12]
    UNSAFE_SSL_COMPANIES = [23, 27]

    try:
        logger.info(f"🚀 Servis başlatılıyor | Şirket: {company.name}, Ürün: {detail.product_code}, Sub: {detail.sub_product_code}")

        offer_service = OfferServiceConfiguration.objects.get(
            insurance_company=company,
            product_code=str(detail.product_code),
            sub_product_code=detail.sub_product_code
        )
        print(f"✅ offer_service bulundu: {offer_service.url}")

        matched_data = match_company_parameters(form_data, detail.product_code, company.id)
        if company.id == 20 and str(detail.product_code) == "103":
            tarih_val = matched_data.get("Tarih")
            if tarih_val:
                try:
                    custom_tarih = datetime.strptime(tarih_val, "%Y-%m-%d").strftime("%d%m%Y")
                    matched_data["Tarih"] = custom_tarih
                    logger.info(f"✅ [HDI] matched_data.Tarih dönüştürüldü: {custom_tarih}")
                except Exception as e:
                    logger.warning(f"❌ [HDI] Tarih dönüşüm hatası: {e}")

        logger.info(f"🧩 FINAL matched_data: {matched_data}")
        try:
            passwords = AgencyPasswords.objects.get(agency=agency, insurance_company=company)
            web_username = passwords.web_username
            web_password = passwords.web_password
            authentication_key = passwords.authenticationKey
            app_security_key = passwords.appSecurityKey
            partaj_code = passwords.partaj_code
            sube_kod = passwords.sube_kod  # ✅ yeni eklendi
            kaynak_kod = passwords.kaynak_kod  # ✅ yeni eklendi
        except AgencyPasswords.DoesNotExist:
            web_username = None
            web_password = None
            authentication_key = None
            app_security_key = None
            partaj_code = None
            sube_kod = None
            kaynak_kod = None

        print(f"🔐 web_username: {web_username} | web_password: {web_password}")

        context = {
            "matched_data": matched_data,
            "web_username": web_username,
            "web_password": web_password,
            "authenticationKey": authentication_key,
            "appSecurityKey": app_security_key,
            "uuid": proposal.proposal_id,
            "tanzim_date": now().strftime("%Y-%m-%d"),
            "partaj_code": partaj_code,
            "sube_kod": sube_kod,
            "kaynak_kod": kaynak_kod
        }

        if offer_service.is_api:
            template = Template(offer_service.request_template or "")
            request_body = template.render(**context)

            logger.info(f"🔗 [API] Servis çağrılıyor: {offer_service.url}")

            token = None
            try:
                password_info = AgencyPasswords.objects.get(
                    agency=agency,
                    insurance_company=offer_service.insurance_company
                )
                token = get_api_token_from_passwords(password_info)
            except AgencyPasswords.DoesNotExist:
                logger.warning("⚠️ AgencyPasswords kaydı bulunamadı → token alınamadı.")

            headers = {
                "Content-Type": offer_service.content_type or "application/json"
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            if offer_service.custom_headers:
                try:
                    headers.update(json.loads(offer_service.custom_headers))
                except Exception as e:
                    logger.warning(f"⚠️ Custom header parse hatası: {e}")

            if offer_service.http_method == "GET":
                separator = "&" if "?" in offer_service.url else "?"
                full_url = f"{offer_service.url}{separator}{request_body}"
                response = requests.get(full_url, headers=headers, timeout=30)
            else:
                content_type = headers.get("Content-Type", "application/json")
                is_json = content_type.startswith("application/json")
                is_form_encoded = content_type == "application/x-www-form-urlencoded"

                if is_form_encoded:
                    body_data = {"xmlData": request_body}
                else:
                    body_data = json.loads(request_body) if is_json else request_body

                response = requests.post(
                    offer_service.url,
                    headers=headers,
                    data=None if is_json else body_data,
                    json=body_data if is_json else None,
                    timeout=30,
                    verify=False
                )

            response.raise_for_status()
            response_text = response.text
            success = True


        else:
            template = Template(offer_service.soap_template or "")
            request_body = template.render(**context)

            print(f"🔗 [SOAP] Servis çağrılıyor: {offer_service.url}")

            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": offer_service.soap_action
            }
            if offer_service.custom_headers:
                try:
                    headers.update(json.loads(offer_service.custom_headers))
                except:
                    pass

            auth = None
            if offer_service.requires_auth and offer_service.auth_username and offer_service.auth_password:
                auth = HTTPBasicAuth(offer_service.auth_username, offer_service.auth_password)

            # Burada şirket ID'ye göre doğru SSL adapter'ı seçiyoruz:
            session = requests.Session()
            if company.id in LEGACY_COMPANIES:
                session.mount("https://", LegacySSLAdapter())
                print("🔑 LegacySSLAdapter kullanıldı (7/12)!")
            elif company.id in UNSAFE_SSL_COMPANIES:
                session.mount("https://", UniversalUnsafeSSLAdapter())
                print("🔑 UniversalUnsafeSSLAdapter kullanıldı (23/27)!")
            else:
                print("🔑 Default SSL ayarları kullanıldı.")

            response = session.post(
                offer_service.url,
                data=request_body,
                headers=headers,
                auth=auth,
                timeout=30,
                verify=False  # Tüm adapter'larda verify kapalı
            )

            response.raise_for_status()
            response_text = response.text
            success = True

        if success and response_text:
            print("✅ Parse başlatılıyor...")
            parse_insurer_response(
                response_data=response_text,
                proposal_id=proposal.proposal_id,
                insurance_company_id=company.id,
                product_code=detail.product_code,
                sub_product_code=detail.sub_product_code
            )
            print("📦 Parse tamamlandı.")

    except Exception as e:
        print(f"❌ Servis hatası: {e}")
        response_text = f"[ERROR] Servis hatası: {str(e)}"

    finally:
        if offer_service:
            print("📝 Log kaydı oluşturuluyor.")
            ProposalServiceLog.objects.create(
                proposal_id=proposal.proposal_id,
                product_code=detail.product_code,
                sub_product_code=detail.sub_product_code,
                agency=agency,
                user=proposal.created_by,
                offer_service=offer_service,
                request_data=request_body,
                response_data=response_text,
                success=success,
                created_at=now()
            )



def parse_insurer_response(response_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    """
    Gelen XML/JSON yanıtını ürün bazlı uygun parser fonksiyonunu çağırarak işler.
    Her OfferServiceConfiguration için ayrı parser_function atanabilir.
    """
    try:
        print(f"🔍 Parse başlatıldı | Şirket ID: {insurance_company_id} | Product: {product_code} | Sub: {sub_product_code}")

        if not response_data:
            print("⚠️ Boş yanıt verisi")
            return {"insurance_company_id": insurance_company_id, "error": "Boş yanıt alındı."}

        # 1. Doğru OfferServiceConfiguration kaydını bul
        offer_service = OfferServiceConfiguration.objects.filter(
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code
        ).first()

        # 2. Doğru parser_function'u belirle
        parser_function = None
        if offer_service and offer_service.parser_function:
            parser_function = offer_service.parser_function
        else:
            company = InsuranceCompany.objects.filter(id=insurance_company_id).first()
            if company and company.parser_function:
                parser_function = company.parser_function
            else:
                print("❌ Parser fonksiyonu tanımlı değil (Ürün ve Şirket)")
                return {"insurance_company_id": insurance_company_id, "error": "Parser fonksiyonu tanımlı değil."}

        print(f"🔧 Kullanılacak parser fonksiyonu: {parser_function}")

        # 3. Veri tipi tespit: JSON mu XML mi?
        is_json = False
        data_obj = response_data

        if isinstance(response_data, dict):
            is_json = True
        elif isinstance(response_data, bytes):
            response_data = response_data.decode("utf-8")
        if isinstance(response_data, str):
            stripped = response_data.lstrip()
            # JSON ise direkt işaretle
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    data_obj = json.loads(response_data)
                    is_json = True
                except Exception:
                    is_json = False

        # 4. Parser fonksiyonunu import et
        module = import_module("offer.parsers")
        parser_func = getattr(module, parser_function, None)

        if not parser_func:
            print(f"❌ Parser fonksiyonu '{parser_function}' bulunamadı.")
            return {"insurance_company_id": insurance_company_id, "error": f"'{parser_function}' fonksiyonu bulunamadı."}

        print("📦 Parser fonksiyonu çağrılıyor...")

        # 5. Fonksiyonu doğru veri tipi ile çağır
        if is_json:
            result = parser_func(data_obj, proposal_id, insurance_company_id, product_code, sub_product_code)
        else:
            # XML ise ön kontrol (parse hatası vs.)
            try:
                ET.fromstring(response_data.strip())
                print("✅ XML parse edildi")
            except Exception as ex:
                print(f"❌ XML parse edilemedi: {ex}")
                return {"insurance_company_id": insurance_company_id, "error": "XML parse edilemedi: " + str(ex)}
            result = parser_func(response_data, proposal_id, insurance_company_id, product_code, sub_product_code)

        print(f"✅ Parser çalıştı. Sonuç: {result}")

        # 6. ProposalDetails status güncelle
        updated = ProposalDetails.objects.filter(
            proposal_id=proposal_id,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code
        ).update(status="Completed", received_at=now())
        print(f"📝 ProposalDetails güncellendi: {updated} kayıt")

        return result

    except Exception as e:
        print(f"❌ Parse exception: {str(e)}")
        return {"insurance_company_id": insurance_company_id, "error": str(e)}

def parse_service_response(xml_data, mappings):
    fields = {}

    # 1. XML'den dict'e çevir
    parsed = xmltodict.parse(xml_data)
    stats = {}
    informations = {}

    # Tüm stats ve informations'ı bul:
    try:
        stats_list = parsed['s:Envelope']['s:Body']['QueryOnlinePolicyResponse']['stats']['a:KeyValuePairOfstringstring']
        if not isinstance(stats_list, list):
            stats_list = [stats_list]
        for item in stats_list:
            k = item['a:key']
            v = item['a:value']
            stats[k] = v
    except Exception:
        pass

    try:
        informations_list = parsed['s:Envelope']['s:Body']['QueryOnlinePolicyResponse']['informations']['a:KeyValuePairOfstringstring']
        if not isinstance(informations_list, list):
            informations_list = [informations_list]
        for item in informations_list:
            k = item['a:key']
            v = item['a:value']
            informations[k] = v
    except Exception:
        pass

    # Düz field'lar (örn: renewFirmCode)
    try:
        response = parsed['s:Envelope']['s:Body']['QueryOnlinePolicyResponse']
    except Exception:
        response = {}

    # 1) Key_85 için mapping'i devre dışı bırak, direkt TKL value’sunu kullan
    # Öncelikli olarak stats içindeki "TKL" yi kontrol et ve "85" olarak ata
    tkl_code = stats.get("TKL")
    if tkl_code:
        fields["85"] = tkl_code

    # 2) Diğer keyler için mapping'i uygula (ama 85 hariç)
    for mapping in mappings:
        if mapping.key and str(mapping.key.KeyID) == "85":
            continue  # 85 için yukarıda özel işledik

        val = None
        # Düz field için:
        if mapping.parse_type == "field":
            val = response.get(mapping.response_field)
            if val is not None:
                fields[str(mapping.key.KeyID)] = val
        # Dict field (ör: stats.YKT, informations.15)
        elif mapping.parse_type == "dict":
            if mapping.response_field.startswith("stats."):
                dict_key = mapping.response_field.split(".")[1]
                dict_val = stats.get(dict_key)
            elif mapping.response_field.startswith("informations."):
                dict_key = mapping.response_field.split(".")[1]
                dict_val = informations.get(dict_key)
            else:
                continue

            # expected_value varsa parametreli, yoksa direkt eşle
            if hasattr(mapping, "expected_value") and mapping.expected_value:
                if dict_val is not None and mapping.expected_value == dict_val:
                    fields[str(mapping.key.KeyID)] = mapping.parameter.ParameterID
            else:
                if dict_val is not None:
                    fields[str(mapping.key.KeyID)] = dict_val

    return fields


