import io
import json
import logging
import os
import ssl
import uuid
from requests.adapters import HTTPAdapter
from celery import shared_task
import requests
import xml.etree.ElementTree as ET
import base64
from jinja2 import Template
from INSAI.utils import get_by_path, get_api_token_from_passwords
from agency.models import AgencyPasswords, AgencyServiceAuthorization
from gateway.models import ServiceConfiguration
from offer.utils import redis_client
from jinja2 import Template as JinjaTemplate



class SSLAdapter(HTTPAdapter):
    """Legacy SSL bağlantılarını ve sertifika doğrulamasını devre dışı bırakır."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        # Python'da varsa ssl.OP_LEGACY_SERVER_CONNECT kullan, yoksa 0x4 kullan
        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            context.options |= ssl.OP_LEGACY_SERVER_CONNECT
        else:
            context.options |= 0x4
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

logger = logging.getLogger("transfer")


@shared_task(bind=True)
def fetch_pdf_from_service(self, service_id=None, agency_id=None, params=None):
    try:
        logger.debug(f"🟡 [GELEN PARAMS] (ilk hali): {json.dumps(params or {}, indent=2, ensure_ascii=False)}")

        yetkili = AgencyServiceAuthorization.objects.filter(
            agency_id=agency_id,
            service_id=service_id,
            is_active=True
        ).exists()
        if not yetkili:
            result = {"success": False, "error": "Bu servisi kullanma yetkiniz yok!"}
            redis_client.set(self.request.id, json.dumps(result), ex=300)
            return result

        service = ServiceConfiguration.objects.get(id=service_id)
        password_info = AgencyPasswords.objects.filter(
            agency_id=agency_id,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            logger.warning(f"🚨 password_info bulunamadı! Agency ID: {agency_id}, Company: {service.insurance_company_id}")
        elif not password_info.partaj_code:
            logger.warning(f"❗ partaj_code boş geldi! Agency ID: {agency_id}, Company: {service.insurance_company_id}")

        full_params = dict(params or {})
        if password_info:
            full_params.update({
                "web_username": password_info.web_username or "",
                "web_password": password_info.web_password or "",
                "authenticationKey": password_info.authenticationKey or "",
                "appSecurityKey": password_info.appSecurityKey or "",
                "partaj_code": password_info.partaj_code or "",
            })

        if not full_params.get("appSecurityKey"):
            logger.warning(f"🛑 appSecurityKey boş! Agency ID: {agency_id}, service_id: {service_id}")

        logger.debug(f"🟢 [KULLANILAN PARAMS]: {json.dumps(full_params, indent=2, ensure_ascii=False)}")

        # 🔁 API özel servisler
        if service.is_api is True:
            token = get_api_token_from_passwords(password_info)

            try:
                req_template = JinjaTemplate(service.request_template or "")
                rendered_body = req_template.render(**full_params)
            except Exception as ex:
                error_result = {"success": False, "error": f"Request template render hatası: {str(ex)}"}
                logger.error(f"❌ Request template render hatası: {str(ex)}")
                logger.error(f"🔍 Render parametreleri:\n{json.dumps(full_params, indent=2, ensure_ascii=False)}")

                redis_client.set(self.request.id, json.dumps(error_result), ex=300)
                return error_result

            headers = {
                "Content-Type": service.content_type or "application/json"
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            try:
                is_json = headers["Content-Type"].startswith("application/json")
                body_data = json.loads(rendered_body) if is_json else rendered_body

                resp = requests.post(
                    service.url,
                    headers=headers,
                    data=None if is_json else body_data,
                    json=body_data if is_json else None,
                    timeout=20
                )
                resp.raise_for_status()
                response_text = resp.text
            except Exception as e:
                error_result = {"success": False, "error": str(e)}
                redis_client.set(self.request.id, json.dumps(error_result), ex=300)
                return error_result

            response_type = (service.response_type or "base64").lower()
            if response_type == "base64":
                if not resp.content:
                    result = {"success": False, "error": "Boş yanıt alındı, PDF verisi yok."}
                else:
                    try:
                        encoded_pdf = base64.b64encode(resp.content).decode("utf-8")
                        result = {"success": True, "pdf_base64": encoded_pdf}
                    except Exception as ex:
                        logger.error(f"❌ Base64 encode hatası: {ex}")
                        result = {"success": False, "error": f"Base64 encode hatası: {ex}"}
            elif response_type == "url":
                try:
                    resp_json = json.loads(response_text)
                    pdf_url = get_by_path(resp_json, service.pdf_field_path)
                    if pdf_url:
                        result = {"success": True, "pdf_url": pdf_url}
                    else:
                        err = get_by_path(resp_json, service.error_field_path) or "PDF içeriği bulunamadı"
                        result = {"success": False, "error": err}
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON parse hatası: {e}")
                    logger.error(f"📥 Yanıt ilk 500 karakter (decode hatası):\n{response_text[:500]}")
                    result = {"success": False, "error": f"JSON parse hatası: {e}"}
            else:
                result = {"success": False, "error": f"Desteklenmeyen response_type: {response_type}"}

            redis_client.set(self.request.id, json.dumps(result), ex=300)
            return result

        # 🔁 SOAP servisler (default)
        template = Template(service.soap_template)
        body = template.render(**full_params)
        logger.debug(f"📦 SOAP Body:\n{body}")

        headers = {
            "Content-Type": "text/xml; charset=utf-8"
        }
        if service.custom_headers:
            headers.update(service.custom_headers)
        elif service.soap_action:
            headers["SOAPAction"] = service.soap_action

        auth = None
        if getattr(service, "requires_auth", False) and service.auth_username and service.auth_password:
            auth = (service.auth_username, service.auth_password)

        tmp_path = os.path.join(os.getcwd(), "soap_request.xml")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(body)

        session = requests.Session()
        session.mount('https://', SSLAdapter())
        response = session.post(service.url, data=body, headers=headers, timeout=20, auth=auth, verify=False)
        response.raise_for_status()

        with open("/tmp/soap_response.xml", "w", encoding="utf-8") as f:
            f.write(response.text)

        root = ET.fromstring(response.text)
        namespaces = {}
        for event, elem in ET.iterparse(io.StringIO(response.text), events=('start-ns',)):
            prefix, uri = elem
            namespaces[prefix if prefix else 'ns'] = uri

        response_type = getattr(service, 'response_type', 'base64').lower()
        result = {"success": False, "error": "Beklenmedik durum"}

        def extract_field(path, tag_name):
            try:
                found = root.find(path, namespaces)
                if found is not None and found.text:
                    return found.text.strip()
            except Exception:
                pass
            for elem in root.iter():
                if elem.tag.endswith(tag_name) and elem.text:
                    return elem.text.strip()
            return None

        if response_type == 'base64':
            pdf_tag = (service.pdf_field_path or ".//ns:return").split(":")[-1].replace(".//", "").strip()
            error_tag = (service.error_field_path or ".//ns:Message").split(":")[-1].replace(".//", "").strip()

            pdf_base64 = extract_field(service.pdf_field_path or ".//ns:return", pdf_tag)
            error_message = extract_field(service.error_field_path or ".//ns:Message", error_tag)

            if not error_message:
                error_message = extract_field(".//ns:faultstring", "faultstring")

            if pdf_base64:
                result = {"success": True, "pdf_base64": pdf_base64}
            elif error_message:
                result = {"success": False, "error": error_message}
            else:
                result = {"success": False, "error": f"PDF alanı ({pdf_tag}) veya hata mesajı bulunamadı!"}

        elif response_type == 'url':
            pdf_tag = (service.pdf_field_path or ".//ns:return").split(":")[-1].replace(".//", "").strip()
            error_tag = (service.error_field_path or ".//ns:Message").split(":")[-1].replace(".//", "").strip()

            pdf_url = extract_field(service.pdf_field_path or ".//ns:return", pdf_tag)
            error_message = extract_field(service.error_field_path or ".//ns:Message", error_tag)

            if not error_message:
                error_message = extract_field(".//ns:faultstring", "faultstring")

            if pdf_url:
                result = {"success": True, "pdf_url": pdf_url}
            elif error_message:
                result = {"success": False, "error": error_message}
            else:
                result = {"success": False, "error": f"PDF alanı ({pdf_tag}) veya hata mesajı bulunamadı!"}
        else:
            result = {"success": False, "error": f"Desteklenmeyen response_type: {response_type}"}

        redis_client.set(self.request.id, json.dumps(result), ex=300)
        return result

    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        request_id = getattr(self.request, "id", str(uuid.uuid4()))
        redis_client.set(request_id, json.dumps(error_result), ex=300)
        return error_result






