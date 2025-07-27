from decimal import Decimal

from django.utils.timezone import now
import xml.etree.ElementTree as ET
from offer.models import ProposalDetails
import re
from offer.models import Proposal, ProposalDetails



def parse_ankara_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)

        namespaces = {
            'a': "http://schemas.datacontract.org/2004/07/AnkaraSigorta.ExtApps.WS.Models"
        }

        def get_xml_value(tag):
            elem = xml_root.find(f".//a:{tag}", namespaces)
            return elem.text.strip() if elem is not None and elem.text else None

        policy_no = get_xml_value("PolicyNumber")
        gross_premium = float(get_xml_value("Premium") or 0)
        premium = float(get_xml_value("PremiumInCurrency") or 0)
        commission = float(get_xml_value("Commission") or 0)
        currency = get_xml_value("Currency") or "TL"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        # Başarılıysa, statü kararını da güncelle!
        status = "approved" if premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": policy_no,
                "currency": currency,
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": policy_no,
            "status": status
        }

    except Exception as e:
        # Hata olursa da, ProposalDetails'a 'rejected' statüsü ile güncelleme/kayıt yap!
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "TL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }


def parse_nippon_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    from django.utils.timezone import now
    from offer.models import Proposal, ProposalDetails
    import xml.etree.ElementTree as ET

    xml_root = ET.fromstring(xml_data)

    # Namespace otomatik bulma: İlk child elementin namespace'i
    def get_namespace(element):
        m = element.tag
        if m[0] == "{":
            return m[1:].split("}")[0]
        return ""

    # root altındaki ProposalResponse namespace'i
    body = xml_root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    if body is None:
        print("❌ SOAP Body bulunamadı!")
        return

    # ProposalResponse elementini bulalım
    proposal_response = None
    for child in body:
        proposal_response = child
        break

    if proposal_response is None:
        print("❌ ProposalResponse bulunamadı!")
        return

    ns_uri = get_namespace(proposal_response)

    ns = {'ns': ns_uri} if ns_uri else {}

    premium = None
    auth_detail = None
    policy_no = None

    # Premium ve StatusDescription al (namespace olmadan)
    for elem in xml_root.iter():
        tag_name = elem.tag.split('}')[-1]
        if tag_name == 'Premium':
            premium = elem.text
            print(f"==> Premium bulundu: {premium}")
        elif tag_name == 'StatusDescription':
            auth_detail = elem.text
            print(f"==> StatusDescription bulundu: {auth_detail}")

    # ProposalResult içindeki PolicyNo'yu namespace ile bul
    proposal_result = proposal_response.find('ns:ProposalResult', ns)
    if proposal_result is not None:
        policy_no_elem = proposal_result.find('ns:PolicyNo', ns)
        if policy_no_elem is not None and policy_no_elem.text and policy_no_elem.text != "0":
            policy_no = policy_no_elem.text

    if premium is None:
        print("❌ Premium bulunamadı!")
    if auth_detail is None:
        print("❌ StatusDescription bulunamadı!")
    if policy_no is None:
        print("❌ PolicyNo bulunamadı!")

    try:
        premium_val = float(str(premium).replace(",", ".").replace(" ", "")) if premium else 0.0
    except Exception as e:
        print(f"Premium float çevrilemedi: {premium} | Hata: {e}")
        premium_val = 0.0

    print(f"Kayıt edilecek premium_val: {premium_val}, auth_detail: {auth_detail}, policy_no: {policy_no}")

    try:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "premium": premium_val,
                "authorization_detail": auth_detail,
                "offer_number": policy_no or "",
                "received_at": now(),
                "status": "approved" if premium_val > 0 else "rejected"
            }
        )
        print("✅ DB'ye yazıldı.")
    except Exception as db_err:
        print("❌ DB'ye yazılamadı:", db_err)

    return {
        "company_id": insurance_company_id,
        "product_code": product_code,
        "sub_product_code": sub_product_code,
        "premium": premium_val,
        "auth_detail": auth_detail,
        "offer_number": policy_no,
        "status": "approved" if premium_val > 0 else "rejected"
    }


def parse_sompo_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)
        ns = {"ns": "http://tempuri.org/"}

        def get_xml_value(tag, parent=None):
            elem = parent.find(f".//ns:{tag}", ns) if parent else xml_root.find(f".//ns:{tag}", ns)
            return elem.text.strip() if elem is not None and elem.text else None

        response_element = xml_root.find(".//ns:CreateProposalResponse/ns:PROPOSAL_RESPONSE", ns)
        payment_element = response_element.find(".//ns:PAYMENT", ns) if response_element is not None else None
        taxes_element = payment_element.find(".//ns:TAXES/ns:TAX", ns) if payment_element is not None else None
        error_element = response_element.find(".//ns:RESULT/ns:ERROR", ns) if response_element is not None else None

        offer_number = get_xml_value("PROPOSAL_NO", response_element)
        gross_premium = get_xml_value("GROSS_PREMIUM", payment_element)
        premium = get_xml_value("NET_PREMIUM", payment_element)
        commission = get_xml_value("DEDUCTION_AMOUNT", taxes_element)
        currency = get_xml_value("POL_CURRENCY_TYPE", payment_element)

        auth_code = get_xml_value("ERROR_CODE", error_element)
        auth_detail = get_xml_value("ERROR_DESCRIPTION", error_element)

        gross_premium = float(gross_premium.replace(',', '.')) if gross_premium else 0.0
        premium = float(premium.replace(',', '.')) if premium else 0.0
        commission = float(commission.replace(',', '.')) if commission else 0.0
        currency = currency or "YTL"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        status = "approved" if premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "authorization_code": auth_code,
                "authorization_detail": auth_detail,
                "currency": currency,
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status,
            "auth_code": auth_code,
            "auth_detail": auth_detail
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "authorization_code": None,
                "authorization_detail": str(e),
                "currency": "YTL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }



def parse_ray_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)

        def get_xml_value(tag):
            elem = xml_root.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else None

        def parse_float(value):
            if value:
                value = value.replace(".", "").replace(",", ".")
                return float(value)
            return 0.0

        gross_premium = parse_float(get_xml_value("TLBrutPrim"))
        premium = parse_float(get_xml_value("TLNetPrim"))
        commission = parse_float(get_xml_value("TLAcenteKomisyon"))
        offer_number = get_xml_value("PoliceNo")
        currency = get_xml_value("DovizTip") or "YTL"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        status = "approved" if premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "currency": currency,
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "YTL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }


def parse_ray_api(json_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        # Eğer json_data str ise parse et
        if isinstance(json_data, str):
            import json
            data = json.loads(json_data)
        else:
            data = json_data

        def parse_float(value):
            # Hem nokta hem virgül varyasyonlarını düzeltir
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            value = re.sub(r'[^\d,.-]', '', str(value))  # Nokta, virgül ve sayı hariç hepsini sil
            value = value.replace(".", "").replace(",", ".")
            try:
                return float(value)
            except Exception:
                return 0.0

        gross_premium = parse_float(data.get("TLBrutPrim"))
        premium = parse_float(data.get("TLNetPrim"))
        commission = parse_float(data.get("TLAcenteKomisyon"))
        offer_number = str(data.get("PoliceNo") or "")
        currency = data.get("DovizTip") or "YTL"
        hata_kodu = data.get("HataKodu")
        hata_mesaji = data.get("HataMesaji")
        status = "approved" if premium > 0 and not hata_kodu else "rejected"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "currency": currency,
                "received_at": now(),
                "status": status,
                "error_code": hata_kodu,         # Ekstra alanlar için modelde yer varsa!
                "error_message": hata_mesaji
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status,
            "error_code": hata_kodu,
            "error_message": hata_mesaji
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "YTL",
                "received_at": now(),
                "status": "rejected",
                "error_code": None,
                "error_message": str(e)
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }


def parse_turkiye_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)

        def get_xml_value(tag):
            elem = xml_root.find(f".//TeklifResponse/{tag}")
            return elem.text.strip() if elem is not None and elem.text else None

        def parse_float(value):
            if value:
                value = value.replace(",", ".")
                try:
                    return float(value)
                except ValueError:
                    return 0.0
            return 0.0

        gross_premium = parse_float(get_xml_value("brutPrim"))
        premium = parse_float(get_xml_value("netPrim"))
        commission = parse_float(get_xml_value("komisyon"))
        offer_number = get_xml_value("teklifNo")
        currency = "YTL"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        status = "approved" if premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "currency": currency,
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "YTL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }



def parse_ak_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)

        def get_xml_value(tag):
            elem = xml_root.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else None

        authorization_code = get_xml_value("errorCode")
        authorization_detail = get_xml_value("errorType")
        gross_premium = get_xml_value("brutPrim")
        premium = get_xml_value("netPrim")
        commission = get_xml_value("komisyonTutari")
        offer_number = get_xml_value("policeNo")
        currency = "TL"

        gross_premium = float(gross_premium.replace(",", ".")) if gross_premium else 0.0
        premium = float(premium.replace(",", ".")) if premium else 0.0
        commission = float(commission.replace(",", ".")) if commission else 0.0

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        status = "approved" if premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "authorization_code": authorization_code,
                "authorization_detail": authorization_detail,
                "currency": currency,
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "authorization_code": None,
                "authorization_detail": str(e),
                "currency": "TL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }



def parse_hdi_sigorta(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data.strip())

        def get(tag):
            elem = xml_root.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else None

        def parse_decimal(val):
            try:
                return Decimal(val.replace(",", "."))
            except:
                return Decimal("0.00")

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        offer_number = get("PoliceNo")  # 🆔 HDI → teklif numarası
        gross_premium = parse_decimal(get("WSBRUT")) if product_code == "103" else parse_decimal(get("OdenecekPrim"))
        premium = parse_decimal(get("WSNPRM")) if product_code == "103" else gross_premium
        commission = parse_decimal(get("XDACKM")) if product_code == "103" else parse_decimal(get("Komisyon"))

        status = "approved" if gross_premium > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": gross_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "status": status,
                "received_at": now()
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "gross_premium": gross_premium,
            "premium": premium,
            "commission": commission,
            "offer_number": offer_number,
            "status": status
        }

    except Exception as e:
        ProposalDetails.objects.update_or_create(
            proposal_id=proposal_id,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "status": "rejected",
                "received_at": now()
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }






def parse_ada_yazilim(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        xml_root = ET.fromstring(xml_data)

        brut_prim, net_prim, komisyon, police_no = 0.0, 0.0, 0.0, None

        for dsoru in xml_root.findall(".//{http://tempuri.org/}DSoru"):
            soru = dsoru.find("{http://tempuri.org/}Soru")
            cevap = dsoru.find("{http://tempuri.org/}Cevap")
            if soru is not None and cevap is not None:
                if soru.text and soru.text.strip() == "PoliceNo":
                    police_no = cevap.text.strip() if cevap.text else None
                    break

        hesaplama_sonucu = xml_root.find(".//{http://tempuri.org/}HesaplamaSonuclari/{http://tempuri.org/}DHesaplamaSonucu")
        if hesaplama_sonucu is not None:
            brut_prim = hesaplama_sonucu.findtext("{http://tempuri.org/}BrutPrim", "0").replace(",", ".")
            net_prim = hesaplama_sonucu.findtext("{http://tempuri.org/}NetPrim", "0").replace(",", ".")
            komisyon = hesaplama_sonucu.findtext("{http://tempuri.org/}Komisyon", "0").replace(",", ".")

            brut_prim = float(brut_prim) if brut_prim else 0.0
            net_prim = float(net_prim) if net_prim else 0.0
            komisyon = float(komisyon) if komisyon else 0.0

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        status = "approved" if net_prim > 0 else "rejected"

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": brut_prim,
                "premium": net_prim,
                "commission": komisyon,
                "offer_number": police_no,
                "currency": "TL",
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": police_no,
            "status": status
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "TL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }



def parse_vizyoneks(xml_data, proposal_id, insurance_company_id, product_code, sub_product_code=None):
    try:
        try:
            xml_root = ET.fromstring(xml_data.strip())
        except ET.ParseError:
            proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
            ProposalDetails.objects.update_or_create(
                proposal=proposal_obj,
                insurance_company_id=insurance_company_id,
                product_code=product_code,
                sub_product_code=sub_product_code,
                defaults={
                    "gross_premium": 0,
                    "premium": 0,
                    "commission": 0,
                    "offer_number": None,
                    "currency": "TL",
                    "received_at": now(),
                    "status": "rejected"
                }
            )
            return {
                "company_id": insurance_company_id,
                "product_code": product_code,
                "sub_product_code": sub_product_code,
                "error": "Geçersiz XML formatı",
                "status": "rejected"
            }

        namespaces = {
            'a': "http://schemas.datacontract.org/2004/07/EntitySpaces.NonLife.Policy",
            'b': "http://schemas.datacontract.org/2004/07/EntitySpaces.NonLife.TypeMapping"
        }

        offer_number = None
        offer_elem = xml_root.find(".//b:CARI_POL_NO", namespaces)
        if offer_elem is not None and offer_elem.text:
            offer_number = offer_elem.text.strip()

        if not offer_number:
            alert_elem = xml_root.find(".//{http://schemas.datacontract.org/2004/07/ApplicationBlocks.Common}AlertText")
            if alert_elem is not None and alert_elem.text:
                match = re.search(r"\b\d+\b", alert_elem.text)
                if match:
                    offer_number = match.group()

        def get_float(tag, ns="a"):
            el = xml_root.find(f".//{ns}:{tag}", namespaces)
            return float(el.text.replace(',', '.')) if el is not None and el.text else 0.0

        total_premium = get_float("TotalPremium")
        premium = get_float("TotalPremiumCash")
        commission = get_float("TotalCommissionCash")

        # Karar: Premium veya teklif no varsa approved, yoksa rejected
        status = "approved" if offer_number or premium > 0 else "rejected"

        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)

        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": total_premium,
                "premium": premium,
                "commission": commission,
                "offer_number": offer_number,
                "currency": "TL",
                "received_at": now(),
                "status": status
            }
        )

        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "offer_number": offer_number,
            "status": status
        }

    except Exception as e:
        proposal_obj = Proposal.objects.get(proposal_id=proposal_id)
        ProposalDetails.objects.update_or_create(
            proposal=proposal_obj,
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            sub_product_code=sub_product_code,
            defaults={
                "gross_premium": 0,
                "premium": 0,
                "commission": 0,
                "offer_number": None,
                "currency": "TL",
                "received_at": now(),
                "status": "rejected"
            }
        )
        return {
            "company_id": insurance_company_id,
            "product_code": product_code,
            "sub_product_code": sub_product_code,
            "error": str(e),
            "status": "rejected"
        }


