import re
from datetime import datetime, timedelta
from requests import Session
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.contrib.auth.decorators import login_required
import xml.etree.ElementTree as ET
from django.db import models
from urllib3 import Retry
from typing import Any

from INSAI.utils import SSLAdapter, clean_namespaces, get_by_path, \
    apply_company_service_field_mapping, create_or_update_customer_generic, create_or_update_asset_car_generic, \
    parse_date, create_external_policy
from database.models import City, ServiceConfiguration, Customer, CompanyServiceFieldMapping, \
    InsuranceCompany, AssetCars, ExternalTramerPolicy, PolicyBranch
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from gateway.models import ProposalServiceLog, UavtDetails
from agency.models import AgencyPasswords, AgencyServiceAuthorization,Agency
import json, requests, xmltodict,ssl
from jinja2 import Template
from requests.adapters import HTTPAdapter
from offer.core import parse_service_response
from offer.models import DaskMapping, CustomerCompany
import logging
logger = logging.getLogger(__name__)




def get_cities(request):
    cities = City.objects.all().order_by('CityCode')
    data = [
        {"code": city.CityCode, "name": city.CityName}
        for city in cities
    ]
    return JsonResponse({"success": True, "cities": data})


def get_ilceler(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        city_code = data.get("city_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=3)

        # ✅ YETKİ KONTROLÜ – sadece bu servis öncesinde yapılır
        yetki_var = AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists()
        if not yetki_var:
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        # ✅ GİRİŞ BİLGİSİ – insurance_company_id üzerinden kullanıcı adı/şifre çek
        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Acente için kullanıcı bilgisi tanımlanmamış'}, status=404)

        # ✅ SOAP Template işleme
        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            ilKodu=city_code
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text


        # ✅ Cevabı parse et (örnek response yapısına göre uyarlayabilirsin)
        parsed = xmltodict.parse(response_text)
        ilceler = parsed.get('soap:Envelope', {}).get('soap:Body', {}) \
            .get('UavtIlceleriAlResponse', {}).get('UavtIlceleriAlResult', {}) \
            .get('Ilceler', {}).get('UavtIlce', [])

        # Listeyi sadeleştir
        data_list = []
        for item in ilceler:
            data_list.append({
                'IlceKodu': item.get('IlceKodu'),
                'IlceAdi': item.get('IlceAdi')
            })

        return JsonResponse({'success': True, 'ilceler': data_list})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_koyler(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        ilce_kodu = data.get("ilce_kodu")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=4)

        # ✅ Yetki kontrolü
        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        # ✅ Kullanıcı bilgileri
        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        # ✅ SOAP şablonu işleniyor
        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            ilceKodu=ilce_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text


        # ✅ SOAP Cevabını güvenli şekilde parse et
        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        response_key = next((k for k in body.keys() if "UavtIlceyeBagliKoyleriAlResponse" in k), None)
        result_key = None
        koyler = []

        if response_key:
            response_data = body[response_key]
            result_key = next((k for k in response_data.keys() if "UavtIlceyeBagliKoyleriAlResult" in k), None)

            if result_key:
                result_data = response_data[result_key]
                koy_list = result_data.get("Koyler", {}).get("UavtKoy", [])

                if isinstance(koy_list, dict):
                    koy_list = [koy_list]

                koyler = [
                    {"KoyKodu": item.get("KoyKodu"), "KoyAdi": item.get("KoyAdi")}
                    for item in koy_list
                ]

        return JsonResponse({'success': True, 'koyler': koyler})

    except Exception as e:
        return JsonResponse({'error': f"Hata oluştu: {str(e)}"}, status=500)


def get_mahalleler(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        koy_kodu = data.get("koy_kodu")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=5)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            koyKodu=koy_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text


        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        response_key = next((k for k in body if "UavtKoyeBagliMahalleleriAlResponse" in k), None)
        mahalleler = []

        if response_key:
            result_key = next((k for k in body[response_key] if "UavtKoyeBagliMahalleleriAlResult" in k), None)

            if result_key:
                mahalle_data = body[response_key][result_key].get("Mahalleler", {}).get("UavtMahalle", [])
                if isinstance(mahalle_data, dict):
                    mahalle_data = [mahalle_data]

                mahalleler = [
                    {
                        "MahalleKodu": item.get("MahalleKodu"),
                        "MahalleAdi": item.get("MahalleAdi")
                    }
                    for item in mahalle_data
                ]

        return JsonResponse({'success': True, 'mahalleler': mahalleler})

    except Exception as e:
        return JsonResponse({'error': f"Hata oluştu: {str(e)}"}, status=500)


def get_csbm(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        mahalle_kodu = data.get("mahalle_kodu")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=6)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            mahalleKodu=mahalle_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        response_key = next((k for k in body if "UavtMahalleyeBagliSokaklariAlResponse" in k), None)
        csbm_liste = []

        if response_key:
            result_key = next((k for k in body[response_key] if "UavtMahalleyeBagliSokaklariAlResult" in k), None)

            if result_key:
                csbm_data = body[response_key][result_key].get("CSBMler", {}).get("UavtCSBM", [])

                if isinstance(csbm_data, dict):
                    csbm_data = [csbm_data]

                csbm_liste = [
                    {
                        "CSBMKodu": csbm.get("CSBMKodu"),
                        "CSBMAdi": csbm.get("CSBMAdi")
                    }
                    for csbm in csbm_data
                ]

        return JsonResponse({'success': True, 'csbm': csbm_liste})

    except Exception as e:
        return JsonResponse({'error': f"Hata oluştu: {str(e)}"}, status=500)


def get_binalar(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        csbm_kodu = data.get("csbm_kodu")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=7)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            csbmKodu=csbm_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        response_key = next((k for k in body if "UavtSokagaBagliBinalariAlResponse" in k), None)
        bina_listesi = []

        if response_key:
            result_key = next((k for k in body[response_key] if "UavtSokagaBagliBinalariAlResult" in k), None)
            if result_key:
                binalar = body[response_key][result_key].get("Binalar", {}).get("UavtBina", [])

                if isinstance(binalar, dict):
                    binalar = [binalar]

                for bina in binalar:
                    bina_kodu = bina.get("BinaKodu")
                    bina_numarasi = bina.get("BinaNumarasi")
                    bina_adi = bina.get("BinaAdi", "")

                    bina_listesi.append({
                        "bina_kodu": bina_kodu,
                        "bina_numarasi": bina_numarasi,
                        "bina_adi": bina_adi or ""
                    })

        return JsonResponse({'success': True, 'binalar': bina_listesi})

    except Exception as e:
        return JsonResponse({'error': f"Hata oluştu: {str(e)}"}, status=500)


def get_daireler(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        bina_kodu = data.get("bina_kodu")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=8)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            binaKodu=bina_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        # 🔍 Dinamik olarak doğru response/result tag'larını bul
        response_key = next((k for k in body if "DaireleriAlResponse" in k), None)
        if not response_key:
            return JsonResponse({'success': False, 'daireler': []})

        result = body.get(response_key, {})
        result_key = next((k for k in result if "DaireleriAlResult" in k), None)
        if not result_key:
            return JsonResponse({'success': False, 'daireler': []})

        daireler_raw = result.get(result_key, {}).get("Daireler", {}).get("UavtDaire", [])
        if not daireler_raw:
            return JsonResponse({'success': False, 'daireler': []})

        # 🔄 Tek obje olarak geldiyse listeye çevir
        if isinstance(daireler_raw, dict):
            daireler_raw = [daireler_raw]

        daire_listesi = []
        for daire in daireler_raw:
            daire_listesi.append({
                "DaireKodu": daire.get("DaireKodu"),
                "DaireNumarasi": daire.get("DaireNumarasi"),
                "AdresKodu": daire.get("AdresKodu")
            })

        return JsonResponse({'success': True, 'daireler': daire_listesi})

    except Exception as e:
        return JsonResponse({'error': f"Hata: {str(e)}"}, status=500)

@ratelimit(key='user', rate='5/m', method='POST', block=False)
def get_adres_detay(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'İstek sınırı aşıldı. Lütfen 1 dakika sonra tekrar deneyiniz.'}, status=429)

    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        uavt_kodu = data.get("uavt_kodu")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        agency = user.agency
        service = ServiceConfiguration.objects.get(id=9)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            uavtAdresKodu=uavt_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        print("📤 GİDEN SOAP BODY:\n", soap_body)
        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        # LOG
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=response.status_code == 200
        )

        parsed = xmltodict.parse(response_text)
        body = parsed.get("soap:Envelope", {}).get("soap:Body", {})

        response_key = next((k for k in body if "AdresDetayAlResponse" in k), None)
        result = body.get(response_key, {})
        result_key = next((k for k in result if "AdresDetayAlResult" in k), None)
        content = result.get(result_key, {})

        # Gelen değerleri topla
        result_data = {
            "success": True,
            "IlKodu": content.get("Iller", {}).get("UavtIl", {}).get("IlKodu"),
            "IlceKodu": content.get("Ilceler", {}).get("UavtIlce", {}).get("IlceKodu"),
            "KoyKodu": content.get("Koyler", {}).get("UavtKoy", {}).get("KoyKodu"),
            "MahalleKodu": content.get("Mahalleler", {}).get("UavtMahalle", {}).get("MahalleKodu"),
            "CSBMKodu": content.get("CSBMler", {}).get("UavtCSBM", {}).get("CSBMKodu"),
            "BinaKodu": content.get("Binalar", {}).get("UavtBina", {}).get("BinaKodu"),
            "BinaAdi": content.get("Binalar", {}).get("UavtBina", {}).get("BinaAdi"),
            "BinaNumarasi": content.get("Binalar", {}).get("UavtBina", {}).get("BinaNumarasi"),
            "DaireNumarasi": content.get("Daireler", {}).get("UavtDaire", {}).get("DaireNumarasi"),
            "AdresKodu": content.get("Daireler", {}).get("UavtDaire", {}).get("AdresKodu"),
            "IlAdi": content.get("Iller", {}).get("UavtIl", {}).get("IlAdi"),
            "IlceAdi": content.get("Ilceler", {}).get("UavtIlce", {}).get("IlceAdi"),
            "KoyAdi": content.get("Koyler", {}).get("UavtKoy", {}).get("KoyAdi"),
            "MahalleAdi": content.get("Mahalleler", {}).get("UavtMahalle", {}).get("MahalleAdi"),
            "CSBMAdi": content.get("CSBMler", {}).get("UavtCSBM", {}).get("CSBMAdi"),
            "BinaAdiDetay": content.get("Binalar", {}).get("UavtBina", {}).get("BinaAdi"),
        }

        # ✅ Veritabanına kaydet/güncelle
        adres_kodu = result_data["AdresKodu"]

        if adres_kodu:
            UavtDetails.objects.update_or_create(
                uavt_code=adres_kodu,
                defaults={
                    'proposal_id': proposal_id,
                    'product_code': product_code,
                    'service_id': service.id,
                    'agency_id': agency.id,
                    'user_id': user.id,

                    'il_kodu': result_data["IlKodu"],
                    'ilce_kodu': result_data["IlceKodu"],
                    'koy_kodu': result_data["KoyKodu"],
                    'mahalle_kodu': result_data["MahalleKodu"],
                    'csbm_kodu': result_data["CSBMKodu"],
                    'bina_kodu': result_data["BinaKodu"],
                    'bina_adi': result_data["BinaAdi"],
                    'daire_kodu': adres_kodu,
                    'daire_numarasi': result_data["DaireNumarasi"]
                }
            )

        return JsonResponse(result_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@ratelimit(key='user', rate='5/m', method='POST', block=False)
@login_required(login_url='/login/')
def get_ray_adres_detay(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'İstek sınırı aşıldı. Lütfen 1 dakika sonra tekrar deneyiniz.'}, status=429)

    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        uavt_kodu = data.get("uavt_kodu")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        agency = user.agency
        service = ServiceConfiguration.objects.get(id=45)  # Ray Sigorta servisi

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            uavtAdresKodu=uavt_kodu
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=response.status_code == 200
        )

        # Sadece Ray Sigorta'nın dönüşünü eski projedeki gibi net yakala:
        parsed_response = xmltodict.parse(response_text)
        detaylar = (
            parsed_response.get('s:Envelope', {})
            .get('s:Body', {})
            .get('AdresSorguResponse', {})
            .get('AdresSorguResult', {})
        )

        acik_adres = detaylar.get('a:AcikAdres') if detaylar else None
        il_adi = detaylar.get('a:ilAd') if detaylar else None
        ilce_adi = detaylar.get('a:ilceAd') if detaylar else None

        result_data = {
            "success": True,
            "acik_adres": acik_adres,
            "il_adi": il_adi,
            "ilce_adi": ilce_adi
        }

        if acik_adres or il_adi or ilce_adi:
            UavtDetails.objects.update_or_create(
                uavt_code=uavt_kodu,
                defaults={
                    'proposal_id': proposal_id,
                    'product_code': product_code,
                    'service_id': service.id,
                    'agency_id': agency.id,
                    'user_id': user.id,
                    'acik_adres': acik_adres,
                    'il_adi': il_adi,
                    'ilce_adi': ilce_adi,
                }
            )

        return JsonResponse(result_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
@login_required
def get_uavt_from_db(request):
    try:
        data = json.loads(request.body)
        proposal_id = data.get("proposal_id")
        user = request.user

        uavt = UavtDetails.objects.filter(
            proposal_id=proposal_id,
            user_id=user.id
        ).first()

        if not uavt:
            return JsonResponse({"success": False, "error": "UAVT verisi bulunamadı."})

        return JsonResponse({
            "success": True,
            "data": {
                "102": uavt.daire_kodu,
                "195": uavt.il_kodu,
                "196": uavt.ilce_kodu,
                "197": uavt.koy_kodu,
                "198": uavt.mahalle_kodu,
                "199": uavt.csbm_kodu,
                "200": uavt.bina_kodu,
                "201": uavt.bina_adi,
                "202": uavt.daire_numarasi
            }
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

@login_required(login_url='/login/')
def update_uavt_details_extra_fields(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            uavt_code = data.get("uavt_code")
            proposal_id = data.get("proposal_id")
            product_code = data.get("product_code")

            # ✅ Extra inputlardan gelen veriler
            extra_fields = {
                'daire_metrekare': data.get("key_104"),
                'dask_insa_yili': data.get("key_105"),
                'dask_kullanim_sekli': data.get("key_106"),
                'dask_kat_araligi': data.get("key_107"),
                'dask_yapi_tarzi': data.get("key_108"),
                'dask_hasar_durumu': data.get("key_109"),
                'sigorta_ettiren_sifati': data.get("key_112"),
                'riziko_konum': data.get("key_118"),
                'riziko_tipi': data.get("key_164"),
                'riziko_ada': data.get("key_115"),
                'riziko_pafta': data.get("key_114"),
                'riziko_parsel': data.get("key_116"),
            }

            updated = UavtDetails.objects.filter(
                uavt_code=uavt_code,
                proposal_id=proposal_id,
                product_code=product_code
            ).update(**extra_fields)

            if updated:
                return JsonResponse({"success": True, "updated": True})
            else:
                return JsonResponse({"success": False, "error": "Kayıt bulunamadı"}, status=404)

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"error": "Sadece POST desteklenir"}, status=405)


def get_first_available_birth_date(identity_number, agency_id, update_customer=True):
    """
    Tüm doğum tarihi servislerini sırayla dener.
    İlk bulunan doğum tarihini döndürür ve varsa Customer kaydını günceller.
    Customer yoksa sadece doğum tarihini geri döner.
    """
    from database.models import Customer

    birthdate_services = [
        get_customer_birthdate_backend,
        get_customer_birthdate_v2_backend,
        get_customer_birthdate_v3_backend,
        get_katilim_birthdate_backend,
        get_customer_from_ray_v2_backend,
        get_customer_birthdate_backend_v4,
    ]

    dogum_tarihi = None
    result_success = False

    logger.warning(f"📡 Doğum tarihi sorgusu başlatıldı → TC: {identity_number}, agency: {agency_id}")

    for service_func in birthdate_services:
        try:
            logger.info(f"🔍 Servis deneniyor: {service_func.__name__}")
            result = service_func(identity_number, agency_id)

            if result and result.get("success") and result.get("birth_date"):
                dogum_tarihi = parse_date(result["birth_date"])

                if dogum_tarihi:
                    result_success = True
                    logger.warning(f"✅ Doğum tarihi bulundu → {dogum_tarihi} (Servis: {service_func.__name__})")
                    break
                else:
                    logger.warning(f"⚠️ Doğum tarihi parse edilemedi (Servis: {service_func.__name__})")
            else:
                logger.warning(f"❌ Servis başarısız döndü: {service_func.__name__} → Yanıt: {result}")

        except Exception as e:
            logger.exception(f"🚨 Servis hatası → {service_func.__name__}: {e}")

    if dogum_tarihi and update_customer:
        customer = Customer.objects.filter(identity_number=identity_number, agency_id=agency_id).first()
        if customer:
            customer.birth_date = dogum_tarihi
            customer.save(update_fields=["birth_date"])
            logger.info(f"📌 Müşteri güncellendi → ID: {customer.id}, doğum tarihi: {dogum_tarihi}")

    return {
        "success": result_success,
        "birth_date": dogum_tarihi
    }

def verify_customer_backend(identity_number: str, birth_date: str, agency_id: int) -> dict:
    """
    Tüm müşteri doğrulama servislerini sırayla dener.
    İlk başarılı doğrulamada müşteri kaydı yapılır ve doğrulama tamamlanır.
    """
    verification_services = [
        call_katilim_customer_info_service,
        call_katilim_corporate_service,
    ]

    for service_func in verification_services:
        try:
            if len(identity_number) == 11 and "customer_info" in service_func.__name__:
                return service_func(
                    agency_id=agency_id,
                    kimlik_no=identity_number,
                    dogum_tarihi=birth_date
                )
            elif len(identity_number) == 10 and "corporate" in service_func.__name__:
                return service_func(
                    vergi_no=identity_number,
                    agency_id=agency_id
                )
        except Exception as e:
            print(f"❌ Servis çağrısı hatası: {service_func.__name__} → {e}")
            continue

    return {"success": False, "response": None}


@ratelimit(key='user', rate='5/m', method='POST', block=False)
@login_required(login_url='/login/')
def api_get_universal_birthdate(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Sadece POST isteği kabul edilir"}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        agency_id = data.get("agency_id")

        # Kimlik numarası kontrolü
        if not identity_number or not agency_id:
            return JsonResponse({"success": False, "error": "Eksik parametre"}, status=400)

        # Universal backend fonksiyonunu çağır
        result = get_first_available_birth_date(identity_number, agency_id, update_customer=True)

        if result["success"]:
            return JsonResponse({"success": True, "birth_date": result["birth_date"]})
        else:
            return JsonResponse({"success": False, "error": "Doğum tarihi bulunamadı"})


    except Exception as ex:
        logger.exception("🚨 Doğum tarihi alma sırasında beklenmeyen bir hata oluştu")
        return JsonResponse({"success": False, "error": str(ex)}, status=500)


@login_required(login_url='/login/')
def get_customer_birthdate(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=10)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        query_type = "0" if len(identity_number) == 11 else "1"

        agency_password = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company  # ✅
        ).first()

        if not agency_password:
            return JsonResponse({'error': 'Şirket için şifre bilgisi tanımlı değil'}, status=400)

        authentication_key = agency_password.authenticationKey
        app_security_key = agency_password.appSecurityKey

        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type,
            authenticationKey=authentication_key,
            appSecurityKey=app_security_key
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        # --- BURADA TİP KONTROLÜ ve BOŞLUK DÜZELTMESİ ---
        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        customer_no = clean_field(entity.get("a:CustomerNo", ""))

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful_raw = entity.get("a:IsSuccessful") or entity.get("IsSuccessful")
        is_successful = extract_bool(is_successful_raw)

        # Loglama
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        # CustomerCompany kaydı
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany
            company = InsuranceCompany.objects.get(company_code="057")
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={
                    "customer_no": customer_no
                }
            )

        return JsonResponse({
            "success": is_successful,
            "birth_date": birth_date,
            "customer_no": customer_no
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_customer_birthdate_backend(identity_number, agency_id):
    try:
        agency = Agency.objects.get(id=agency_id)
        service = ServiceConfiguration.objects.get(id=10)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            print("❌ Yetkisiz servis erişimi")
            return {"success": False, "birth_date": None}

        agency_password = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company  # ✅
        ).first()

        if not agency_password:
            print("❌ Şirket için şifre bilgisi bulunamadı")
            return {"success": False, "birth_date": None}

        authentication_key = agency_password.authenticationKey
        app_security_key = agency_password.appSecurityKey

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type,
            authenticationKey=authentication_key,
            appSecurityKey=app_security_key
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text
        print("📩 SOAP RESPONSE:\n", response_text)

        parsed = xmltodict.parse(response_text)
        parsed_clean = clean_namespaces(parsed)

        # 👀 Burayı test etmek için yaz
        from pprint import pprint
        pprint(parsed_clean)

        birth_date_raw = get_by_path(parsed_clean, "Envelope.Body.GetCustomerNoResponse.entity.BirthDate")

        def clean(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val).strip() if val else ""

        birth_date = clean(birth_date_raw)

        print(f"🎯 Çekilen Doğum Tarihi → {birth_date}")
        is_successful = True if birth_date else False

        return {
            "success": is_successful,
            "birth_date": birth_date or None
        }

    except Exception as e:
        print(f"❌ HATA: {e}")
        return {"success": False, "birth_date": None}


@login_required(login_url='/login/')
def get_customer_birthdate_v2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=11)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        query_type = "0" if len(identity_number) == 11 else "1"

        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        # --- Burada alanları standartlaştırıyoruz ---
        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        customer_no = clean_field(entity.get("a:CustomerNo", ""))

        # Başarı kontrolü (sadece birth_date'in varlığına göre)
        is_successful = bool(birth_date)

        # Log kaydı
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        # CustomerCompany tablosuna ekle
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            company = InsuranceCompany.objects.get(company_code="017")
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={
                    "customer_no": customer_no
                }
            )

        return JsonResponse({
            "success": is_successful,
            "birth_date": birth_date,
            "customer_no": customer_no
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_customer_birthdate_v2_backend(identity_number, agency_id, **kwargs):

    try:
        agency = Agency.objects.get(id=agency_id)
        service = ServiceConfiguration.objects.get(id=11)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return {"success": False, "birth_date": None}

        password_info = AgencyPasswords.objects.filter(
            agency=agency, insurance_company=service.insurance_company
        ).first()
        if not password_info:
            return {"success": False, "birth_date": None}

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        is_successful = bool(birth_date)

        return {
            "success": is_successful,
            "birth_date": birth_date if birth_date else None
        }
    except Exception:
        return {"success": False, "birth_date": None}


@login_required(login_url='/login/')
def get_customer_birthdate_v3(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=44)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        query_type = "0" if len(identity_number) == 11 else "1"

        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        # --- BOŞ/NIL KONTROLÜ EKLENDİ ---
        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        customer_no = clean_field(entity.get("a:CustomerNo", ""))

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful_raw = entity.get("a:IsSuccessful") or entity.get("IsSuccessful")
        is_successful = extract_bool(is_successful_raw)

        # 📋 Log
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        # ✅ CustomerCompany tablosuna ekle
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            company = InsuranceCompany.objects.get(company_code="106")

            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={
                    "customer_no": customer_no
                }
            )

        return JsonResponse({
            "success": is_successful,
            "birth_date": birth_date,
            "customer_no": customer_no
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_customer_birthdate_v3_backend(identity_number, agency_id, **kwargs):

    try:
        agency = Agency.objects.get(id=agency_id)
        service = ServiceConfiguration.objects.get(id=44)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return {"success": False, "birth_date": None}

        password_info = AgencyPasswords.objects.filter(
            agency=agency, insurance_company=service.insurance_company
        ).first()
        if not password_info:
            return {"success": False, "birth_date": None}

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        is_successful_raw = entity.get("a:IsSuccessful") or entity.get("IsSuccessful")
        is_successful = (str(is_successful_raw).strip().lower() == "true")

        return {
            "success": is_successful and bool(birth_date),
            "birth_date": birth_date if birth_date else None
        }
    except Exception:
        return {"success": False, "birth_date": None}

@login_required(login_url='/login/')
def get_customer_birthdate_v4(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=86)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        agency_password = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company  # ✔️ Modeldeki doğru alan
        ).first()

        if not agency_password or not agency_password.appSecurityKey:
            return JsonResponse({'error': 'AppSecurityKey tanımlı değil'}, status=400)

        query_type = "0" if len(identity_number) == 11 else "1"

        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type,
            appSecurityKey=agency_password.appSecurityKey
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        entity = parsed.get("s:Envelope", {}).get("s:Body", {}) \
            .get("GetCustomerNoResponse", {}) \
            .get("entity", {})

        def clean_field(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val) if val else ""

        birth_date = clean_field(entity.get("a:BirthDate", ""))
        customer_no = clean_field(entity.get("a:CustomerNo", ""))

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful_raw = entity.get("a:IsSuccessful") or entity.get("IsSuccessful")
        is_successful = extract_bool(is_successful_raw)

        # Loglama
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        # CustomerCompany kaydı
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany
            company = InsuranceCompany.objects.get(company_code=service.insurance_company.company_code)
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={"customer_no": customer_no}
            )

        return JsonResponse({
            "success": is_successful,
            "birth_date": birth_date,
            "customer_no": customer_no
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_customer_birthdate_backend_v4(identity_number, agency_id):
    try:
        agency = Agency.objects.get(id=agency_id)
        service = ServiceConfiguration.objects.get(id=86)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            print("❌ Yetkisiz servis erişimi")
            return {"success": False, "birth_date": None, "customer_no": None}

        agency_password = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company  # ✅
        ).first()

        if not agency_password or not agency_password.appSecurityKey:
            print("❌ AppSecurityKey tanımlı değil")
            return {"success": False, "birth_date": None, "customer_no": None}

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            query_type=query_type,
            appSecurityKey=agency_password.appSecurityKey
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text
        print("📩 SOAP RESPONSE:\n", response_text)

        parsed = xmltodict.parse(response_text)
        parsed_clean = clean_namespaces(parsed)

        birth_date_raw = get_by_path(parsed_clean, "Envelope.Body.GetCustomerNoResponse.entity.BirthDate")
        customer_no_raw = get_by_path(parsed_clean, "Envelope.Body.GetCustomerNoResponse.entity.CustomerNo")

        def clean(val):
            if isinstance(val, dict) and val.get("@i:nil") == "true":
                return ""
            return str(val).strip() if val else ""

        birth_date = clean(birth_date_raw)
        customer_no = clean(customer_no_raw)

        print(f"🎯 Doğum Tarihi: {birth_date} | Müşteri No: {customer_no}")
        is_successful = bool(birth_date or customer_no)

        return {
            "success": is_successful,
            "birth_date": birth_date or None,
            "customer_no": customer_no or None
        }

    except Exception as e:
        print(f"❌ HATA: {e}")
        return {"success": False, "birth_date": None, "customer_no": None}

@csrf_exempt
def get_katilim_birthdate(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            kimlik_no = data.get("identity_number")
            agency_id = request.user.agency_id

            # Katılım servisiyle sorgula
            result = call_katilim_birthdate_service(agency_id, kimlik_no)
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    else:
        return JsonResponse({"success": False, "error": "Yalnızca POST desteklenir."})

def get_katilim_birthdate_backend(identity_number, agency_id, **kwargs):

    try:
        service_id = 60
        if not AgencyServiceAuthorization.objects.filter(agency_id=agency_id, service_id=service_id, is_active=True).exists():
            return {"success": False, "birth_date": None}

        service = ServiceConfiguration.objects.get(id=service_id)
        ap = AgencyPasswords.objects.filter(agency_id=agency_id, insurance_company_id=service.insurance_company_id).first()
        if not ap or not ap.cookie:
            return {"success": False, "birth_date": None}

        body = Template(service.request_template).render(kimlik_no=identity_number)
        headers = {
            "Content-Type": service.content_type,
            "Cookie": ap.cookie,
        }
        if service.custom_headers:
            headers.update(service.custom_headers)

        resp = requests.post(service.url, headers=headers, data=body.encode("utf-8"), timeout=5)

        try:
            json_response = resp.json()
        except Exception:
            return {"success": False, "birth_date": None}

        if isinstance(json_response, dict):
            value = json_response.get("value")
            if value and value.get("Basarili"):
                return {"success": True, "birth_date": value.get("Mesaj")}
            else:
                return {"success": False, "birth_date": None}
        else:
            return {"success": False, "birth_date": None}
    except Exception:
        return {"success": False, "birth_date": None}

def call_katilim_birthdate_service(agency_id, kimlik_no, service_id=60):
    # 1. Yetki kontrolü
    if not AgencyServiceAuthorization.objects.filter(agency_id=agency_id, service_id=service_id, is_active=True).exists():
        return {"success": False, "error": "Yetkiniz yok"}

    service = ServiceConfiguration.objects.get(id=service_id)
    ap = AgencyPasswords.objects.filter(agency_id=agency_id, insurance_company_id=service.insurance_company_id).first()
    if not ap or not ap.cookie:
        return {"success": False, "error": "Cookie bulunamadı"}

    # Body render
    body = Template(service.request_template).render(kimlik_no=kimlik_no)

    # Headerları hazırla (tablodan JSON çek)
    headers = {
        "Content-Type": service.content_type,
        "Cookie": ap.cookie,
    }
    if service.custom_headers:
        headers.update(service.custom_headers)

    try:
        resp = requests.post(service.url, headers=headers, data=body.encode("utf-8"), timeout=5)

        # --- Güvenli JSON parse ---
        try:
            print("🟢 [Katilim Request Body]:", body)
            json_response = resp.json()
            print("🔵 [Katilim Response Status]:", resp.status_code)
            print("🔵 [Katilim Response Text]:", resp.text)
        except Exception as e:
            return {
                "success": False,
                "error": f"JSON parse hatası: {e} - Gelen veri: {resp.text}"
            }

        if isinstance(json_response, dict):
            value = json_response.get("value")
            if value and value.get("Basarili"):
                return {"success": True, "birth_date": value.get("Mesaj")}
            else:
                mesaj = ""
                if value and "Mesaj" in value:
                    mesaj = value.get("Mesaj")
                elif isinstance(value, str):
                    mesaj = value
                return {"success": False, "error": mesaj or "Doğum tarihi bulunamadı"}
        else:
            # JSON olmayan cevap
            return {"success": False, "error": f"Servis düz string döndürdü: {json_response}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@login_required(login_url='/login/')
def get_customer_from_ray_v2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=12)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        musteri_tipi = "TcNo" if len(identity_number) == 11 else "VkNo"

        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            musteri_tipi=musteri_tipi,
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        result = parsed.get("s:Envelope", {}).get("s:Body", {}) \
                       .get("MusteriAraResponse", {}) \
                       .get("MusteriAraResult", {})

        def extract_text(val):
            if isinstance(val, dict):
                return val.get("#text", "")
            return val or ""

        # 🔍 Başarı kontrolü (Basarilimi)
        is_successful = str(extract_text(result.get("Basarilimi"))).lower() == "true"

        customer_no = extract_text(result.get("MusteriNo"))
        birth_date = extract_text(result.get("DogumTarihi"))
        firma_adi = extract_text(result.get("FirmaAdi"))
        ad = extract_text(result.get("Adi"))
        soyad = extract_text(result.get("Soyadi"))

        # --- Doğum tarihi otomatik olarak "0001-01-01..." dönerse temizle ---
        def clean_birth_date(val):
            if not val:
                return ""
            if val in ["0001-01-01", "0001-01-01T00:00:00"]:
                return ""
            return str(val)
        birth_date = clean_birth_date(birth_date)

        if musteri_tipi == "VkNo":
            full_name = firma_adi
        else:
            full_name = f"{ad} {soyad}".strip()

        # ✅ Yeni tabloya kayıt (CustomerCompany)
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            try:
                company = InsuranceCompany.objects.get(company_code="042")
                CustomerCompany.objects.update_or_create(
                    identity_number=identity_number,
                    company=company,
                    defaults={"customer_no": customer_no}
                )
            except InsuranceCompany.DoesNotExist:
                print("❌ HATA: InsuranceCompany bulunamadı - company_code=042")

        # 📋 Gerçek log
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        return JsonResponse({
            "success": is_successful,
            "customer_no": customer_no,
            "birth_date": birth_date,
            "full_name": full_name
        })

    except Exception as e:
        print("❌ Hata:", str(e))
        return JsonResponse({'error': str(e)}, status=500)

def get_customer_from_ray_v2_backend(identity_number, agency_id, **kwargs):

    try:
        agency = Agency.objects.get(id=agency_id)
        service = ServiceConfiguration.objects.get(id=12)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return {"success": False, "birth_date": None}

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()
        if not password_info:
            return {"success": False, "birth_date": None}

        musteri_tipi = "TcNo" if len(identity_number) == 11 else "VkNo"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            web_username=password_info.web_username,
            web_password=password_info.web_password,
            musteri_tipi=musteri_tipi,
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        result = parsed.get("s:Envelope", {}).get("s:Body", {}) \
                       .get("MusteriAraResponse", {}) \
                       .get("MusteriAraResult", {})

        def extract_text(val):
            if isinstance(val, dict):
                return val.get("#text", "")
            return val or ""

        is_successful = str(extract_text(result.get("Basarilimi"))).lower() == "true"
        birth_date = extract_text(result.get("DogumTarihi"))

        # Temizle
        if birth_date in ["0001-01-01", "0001-01-01T00:00:00"]:
            birth_date = ""

        return {
            "success": is_successful and bool(birth_date),
            "birth_date": birth_date if birth_date else None
        }
    except Exception:
        return {"success": False, "birth_date": None}


@ratelimit(key='user_or_ip', rate='3/m', method='POST', block=False)
@login_required(login_url='/login/')
def save_customer_to_ray(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'success': False, 'error': 'Çok fazla istek gönderildi. Lütfen daha sonra tekrar deneyiniz.'}, status=429)

    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        phone_number = data.get("phone_number", "5324711010")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=13)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()
        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi tanımlı değil'}, status=404)

        # 🟣 Jinja2 template rendering
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            dogum_tarihi=birth_date,
            web_username=password_info.web_username,
            web_password=password_info.web_password,
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        result = parsed.get("s:Envelope", {}).get("s:Body", {}) \
                       .get("MusteriKaydetResponse", {}) \
                       .get("MusteriKaydetResult", {})

        def extract(val):
            if isinstance(val, dict):
                return val.get("#text", "")
            if val is None:
                return ""
            return str(val).strip()

        is_successful = extract(result.get("Basarilimi")).lower() == "true"
        musteri_no = extract(result.get("MusteriNo"))
        firma_adi = extract(result.get("FirmaAdi"))
        ad = extract(result.get("Adi"))
        soyad = extract(result.get("Soyadi"))

        full_name = firma_adi if len(identity_number) == 10 else f"{ad} {soyad}".strip()

        # ✅ SOAP loglama
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id if proposal_id else 9999,
            product_code=product_code if product_code else 102,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        if is_successful and musteri_no:
            from offer.models import CustomerCompany
            from database.models import Customer, InsuranceCompany

            company = InsuranceCompany.objects.get(company_code="042")  # Ray Sigorta

            # ✅ CustomerCompany bağlantısı
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={"customer_no": musteri_no}
            )

            # ✅ Customer tablosuna ekle (veya varsa alma)
            customer, _ = Customer.objects.get_or_create(
                identity_number=identity_number,
                defaults={
                    "birth_date": birth_date,
                    "full_name": full_name,
                    "phone_number": phone_number,
                    "agency_id": agency.id,
                    "user_id": user.id,
                    "is_verified": True
                }
            )

            return JsonResponse({
                "success": True,
                "customer_no": musteri_no,
                "full_name": full_name,
                "customer_key": customer.customer_key  # 💥 frontend bunu bekliyor
            })

        return JsonResponse({
            "success": False,
            "error": "Ray servisi başarısız döndü"
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def call_katilim_customer_info_service(agency_id, kimlik_no, dogum_tarihi, service_id=61, user=None):
    try:
        from database.models import CompanyFieldMapping, Customer

        service = ServiceConfiguration.objects.get(id=service_id)
        if not agency_id:
            return {"success": False, "error": "agency_id boş gönderildi!"}
        if not AgencyServiceAuthorization.objects.filter(agency_id=agency_id, service=service, is_active=True).exists():
            return {"success": False, "error": "Yetkiniz yok"}

        ap = AgencyPasswords.objects.filter(agency_id=agency_id, insurance_company=service.insurance_company).first()
        if not ap or not ap.cookie or not ap.partaj_code:
            return {"success": False, "error": "Cookie veya PartajCode bulunamadı"}

        # 🔧 SOAP Body render
        body = Template(service.request_template).render(
            acenteNo=ap.partaj_code,
            aKimlikNo=kimlik_no,
            dogumTarihi=dogum_tarihi
        )

        headers = {
            "Content-Type": service.content_type,
            "Cookie": ap.cookie,
        }
        if service.custom_headers:
            headers.update(service.custom_headers)

        print("\n📤 İSTEK BODY:\n", body)
        print("📩 HEADERS:", headers)

        resp = requests.post(service.url, headers=headers, data=body.encode("utf-8"), timeout=7)
        print("📥 RESPONSE:\n", resp.text)

        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code}", "response": resp.text}

        json_response = resp.json()
        value = json_response.get("value")

        if not value:
            return {"success": False, "error": "Yanıt içeriği boş", "response": json_response}

        # 🧩 Mapping işlemi
        mapping_qs = CompanyServiceFieldMapping.objects.filter(
            company=service.insurance_company,
            service=service,
            is_active=True
        ).select_related("key")

        customer_data = {}
        identity_number = kimlik_no
        full_name = ""

        for m in mapping_qs:
            key = m.key.KeyName
            val = value.get(m.company_key)

            # 🎯 Tüm tarih alanlarını otomatik parse et
            if isinstance(val, str) and "tarih" in key.lower():
                parsed = parse_date(val)
                if parsed:
                    val = parsed

            # 👤 İsim birleştirme
            if key == "full_name":
                ad = value.get("Ad") or value.get("AdUnvan") or ""
                soyad = value.get("Soyad", "")
                val = f"{ad.strip()} {soyad.strip()}".strip()
                full_name = val

            if val is not None:
                customer_data[key] = val

        if len(str(identity_number)) == 11:
            customer_data["type"] = "1"
        elif len(str(identity_number)) == 10:
            customer_data["type"] = "2"

        # ✅ Müşteri kaydı
        customer, _ = Customer.objects.get_or_create(
            identity_number=identity_number,
            defaults={"agency_id": agency_id}
        )

        # 🎯 DateField alanları belirle
        date_fields = {f.name for f in Customer._meta.fields if isinstance(f, models.DateField)}

        for key, val in customer_data.items():
            if val in [None, ""]:
                val = None
            elif key in date_fields and isinstance(val, str):
                val = parse_date(val)
            setattr(customer, key, val)

        customer.agency_id = agency_id
        customer.is_verified = True
        customer.save()

        return {
            "success": True,
            "response": value,
            "customer_id": customer.id,
            "full_name": full_name,
            "birth_date": customer.birth_date.strftime("%d.%m.%Y") if customer.birth_date else ""
        }

    except Exception as e:
        print(f"❌ SERVİS HATASI → {e}")
        return {"success": False, "error": str(e)}

def call_katilim_corporate_service(vergi_no, agency_id, user=None, service_id=62):
    try:
        service = ServiceConfiguration.objects.get(id=service_id)
        if not agency_id:
            return {"success": False, "error": "agency_id boş gönderildi!"}
        if not AgencyServiceAuthorization.objects.filter(agency_id=agency_id, service=service, is_active=True).exists():
            return {"success": False, "error": "Yetkiniz yok."}

        ap = AgencyPasswords.objects.filter(
            agency_id=agency_id,
            insurance_company=service.insurance_company
        ).first()
        if not ap or not ap.cookie:
            return {"success": False, "error": "Kurumsal sorgu için cookie bulunamadı."}

        log_obj = ProposalServiceLog.objects.create(
            proposal_id=9999,
            product_code="199",
            info_service=service,
            agency_id=agency_id,
            user=user,
            request_data="",
            response_data="",
            success=False
        )

        headers = {
            "Content-Type": service.content_type,
            "Cookie": ap.cookie,
        }
        if service.custom_headers:
            headers.update(service.custom_headers)

        body = Template(service.request_template).render({"vergiNo": str(vergi_no).zfill(10)})
        log_obj.request_data = body

        resp = requests.post(
            service.url,
            headers=headers,
            data=body.encode("utf-8"),
        )
        log_obj.response_data = resp.text
        is_successful = False
        customer = None
        full_name = ""

        if resp.status_code == 200:
            try:
                json_response = resp.json()
                value = json_response.get("value", {})
                if value:
                    from database.models import CompanyFieldMapping
                    mapping_qs = CompanyServiceFieldMapping.objects.filter(
                        company=service.insurance_company,
                        service=service,
                        is_active=True
                    ).select_related("key")

                    customer_data = {}
                    identity_number = str(vergi_no)
                    full_name = ""

                    for m in mapping_qs:
                        key = m.key.KeyName
                        val = value.get(m.company_key)
                        if key in ["birth_date", "VefatTarihi"]:
                            val = parse_date(val) if val else None
                        if val == "":
                            val = None
                        if key == "full_name":
                            adunvan = value.get("AdUnvan", "").strip()
                            ad = value.get("Ad", "").strip()
                            soyad = value.get("Soyad", "").strip()
                            unvan = value.get("Unvan", "").strip()
                            if adunvan and soyad and not adunvan.endswith(soyad):
                                val = f"{adunvan} {soyad}"
                            elif ad and soyad:
                                val = f"{ad} {soyad}"
                            elif adunvan:
                                val = adunvan
                            elif ad:
                                val = ad
                            elif soyad:
                                val = soyad
                            elif unvan:
                                val = unvan
                            else:
                                val = ""
                            full_name = val
                        if val is not None:
                            customer_data[key] = val
                        if key == "identity_number":
                            identity_number = val or str(vergi_no)

                    if len(str(identity_number)) == 11:
                        customer_data["type"] = "1"
                    elif len(str(identity_number)) == 10:
                        customer_data["type"] = "2"

                    if not full_name.strip() or "BULUNAMADI" in full_name.upper():
                        log_obj.success = False
                        is_successful = False
                        full_name = ""
                    else:
                        customer, _ = Customer.objects.get_or_create(
                            identity_number=identity_number,
                            defaults={"agency_id": agency_id}
                        )
                        for key, val in customer_data.items():
                            setattr(customer, key, val if val not in [None, ""] else None)
                        customer.agency_id = agency_id
                        customer.is_verified = True  # ✔️ düzeltildi
                        customer.save()
                        is_successful = True
                        log_obj.success = True
                else:
                    log_obj.success = False
                    log_obj.response_data = resp.text or "Veri alınamadı"
            except Exception as e:
                log_obj.success = False
                log_obj.response_data = str(e)
        else:
            log_obj.success = False
            log_obj.response_data = resp.text or "Servis erişilemedi"

        log_obj.save()

        return {
            "success": is_successful,
            "response": log_obj.response_data,
            "customer_id": customer.id if is_successful and customer else None,
            "full_name": full_name if is_successful else None,
            "birth_date": customer.birth_date.strftime("%d.%m.%Y") if is_successful and customer and customer.birth_date else ""
        }

    except Exception as e:
        try:
            ProposalServiceLog.objects.create(
                proposal_id=9999,
                product_code="199",
                info_service=service,
                agency_id=agency_id,
                user=user,
                request_data=str({"vergiNo": vergi_no}),
                response_data=str(e),
                success=False,
            )
        except Exception:
            pass
        return {"success": False, "error": str(e)}


def call_katilim_customer_info(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'success': False, 'error': 'Çok fazla istek gönderdiniz. Lütfen biraz sonra tekrar deneyiniz.'}, status=429)

    if request.method == "POST":
        data = json.loads(request.body)
        agency_id = data.get("agency_id")
        kimlik_no = data.get("kimlik_no")
        dogum_tarihi = data.get("dogum_tarihi")

        kimlik_no_str = str(kimlik_no)
        # 11 haneli ise bireysel (TC)
        if len(kimlik_no_str) == 11:
            result = call_katilim_customer_info_service(
                agency_id=agency_id,
                kimlik_no=kimlik_no,
                dogum_tarihi=dogum_tarihi,
                user=request.user if request.user.is_authenticated else None
            )
        # 10 haneli ise kurumsal (Vergi No)
        elif len(kimlik_no_str) == 10:
            result = call_katilim_corporate_service(
                vergi_no=kimlik_no,
                agency_id=agency_id,
                user=request.user if request.user.is_authenticated else None
            )
        else:
            return JsonResponse({"success": False, "error": "Kimlik numarası 10 veya 11 haneli olmalı"}, status=400)

        print("🔍 Katılım servisi response:", result)
        return JsonResponse({
            "success": result.get("success", False),
            "full_name": result.get("full_name", "") if result else "",
            "birth_date": result.get("birth_date", "") if result else ""

        })

    return JsonResponse({"success": False, "error": "Sadece POST"}, status=405)

def get_arac_detay(agency_id, kimlik_no, plaka, tescil_belge_seri_no="", service_id=79):
    print(f"\n🚀 [get_arac_detay Başlatıldı] agency_id={agency_id}, plaka={plaka}, kimlik_no={kimlik_no}, tescil={tescil_belge_seri_no}, service_id={service_id}")

    # 🛡️ Yetki kontrolü
    if not AgencyServiceAuthorization.objects.filter(
        agency_id=agency_id,
        service_id=service_id,
        is_active=True
    ).exists():
        print("⛔ Yetki bulunamadı.")
        return {"success": False, "error": "Yetkiniz yok"}

    # 🔧 Servis yapılandırması
    try:
        service = ServiceConfiguration.objects.get(id=service_id)
        print("✅ Servis bulundu:", service.name)
    except ServiceConfiguration.DoesNotExist:
        print("❌ ServiceConfiguration bulunamadı.")
        return {"success": False, "error": "Servis bulunamadı"}

    # 🔑 Cookie al
    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company=service.insurance_company_id
    ).first()

    if not password_info or not password_info.cookie:
        print("❌ Cookie eksik.")
        return {"success": False, "error": "Cookie bulunamadı"}

    # 📄 Plaka parçala
    plaka_il_kodu_raw = plaka[:3].lstrip("0")  # "027" → "27"
    plaka_il_kodu = plaka_il_kodu_raw.zfill(2)  # "7" → "07"
    plaka_no = plaka[3:]
    print(f"🔢 Plaka ayrıştırıldı: il_kodu={plaka_il_kodu}, plaka_no={plaka_no}")

    # 👤 Kimlik türü belirle
    tc_kimlik_no = kimlik_no if len(kimlik_no) == 11 else ""
    vergi_no = kimlik_no if len(kimlik_no) == 10 else ""
    print(f"👤 Kimlik ayrımı: TC={tc_kimlik_no}, VKN={vergi_no}")

    # 🧩 Body hazırla
    try:
        body_json = Template(service.request_template).render(
            tescil_belge_seri_no=tescil_belge_seri_no,
            plaka_il_kodu=plaka_il_kodu,
            plaka=plaka_no,
            tc_kimlik_no=tc_kimlik_no,
            vergi_no=vergi_no
        )
        print("📤 Request Body:\n", body_json)
    except Exception as e:
        print("❌ Template render hatası:", e)
        return {"success": False, "error": f"Template render hatası: {e}"}

    headers = {
        "Content-Type": service.content_type,
        "Cookie": password_info.cookie.strip()
    }
    if service.custom_headers:
        headers.update(service.custom_headers)

    print("📤 Request Headers:\n", headers)
    print("🌍 URL:", service.url)

    # 🔐 SSL adapter
    session = Session()
    adapter = SSLAdapter()
    adapter.max_retries = Retry(total=3, backoff_factor=1)
    session.mount("https://", adapter)

    try:
        print("🚀 İstek gönderiliyor...")
        response = session.post(
            url=service.url,
            headers=headers,
            data=body_json,
            timeout=20
        )
        print(f"📩 HTTP Status: {response.status_code}")
        print(f"📥 Response Body:\n{response.text}")

        response.raise_for_status()
        try:
            json_data = response.json()
            print(f"🧾 Parsed JSON:\n{json.dumps(json_data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print("❌ JSON parse hatası:", e)
            return {"success": False, "error": f"JSON parse hatası: {e} | Cevap: {response.text[:500]}"}

        return {
            "success": True,
            "status": response.status_code,
            "data": json_data
        }

    except Exception as e:
        print("❌ HTTP Exception:", str(e))
        return {"success": False, "error": str(e)}


def get_tescil_detay(agency_id, plaka_il_kodu, plaka, kimlik_no, service_id=80):
    # 🔐 Yetki kontrolü
    if not AgencyServiceAuthorization.objects.filter(
        agency_id=agency_id, service_id=service_id, is_active=True
    ).exists():
        return {"success": False, "error": "Yetkiniz yok"}

    try:
        service = ServiceConfiguration.objects.get(id=service_id)
    except ServiceConfiguration.DoesNotExist:
        return {"success": False, "error": "Servis bulunamadı"}

    ap = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=service.insurance_company_id
    ).first()
    if not ap or not ap.cookie:
        return {"success": False, "error": "Cookie bulunamadı"}

    # 👤 Kimlik ayrımı
    tc_kimlik = kimlik_no if len(kimlik_no) == 11 else ""
    vergi_no = kimlik_no if len(kimlik_no) == 10 else ""

    # 📤 Body oluştur
    body = Template(service.request_template).render(
        plakaIlKodu=plaka_il_kodu,
        plaka=plaka,
        tcKimlikNo=tc_kimlik,
        vergiNo=vergi_no,
        basTar="24.06.2025",
        oncekiPoliceKey="1",
        policeIslemId="1"
    )

    print("📤 Gönderilen SOAP Body:\n", body)  # 👈 burayı ekle

    headers = {
        "Content-Type": service.content_type,
        "Cookie": ap.cookie.strip()
    }
    if service.custom_headers:
        headers.update(service.custom_headers)

    try:
        resp = requests.post(service.url, data=body.encode("utf-8"), headers=headers, timeout=10)
        print("📥 Response Body:\n", resp.text)

        if not resp.text.strip():
            return {"success": False, "error": "Servis boş döndü"}

        # 🧪 "Mesaj":"646711" değerini manuel parse et
        match = re.search(r'"Mesaj"\s*:\s*"([^"]+)"', resp.text)
        if match:
            return {"success": True, "result": match.group(1)}
        else:
            return {"success": False, "error": "Mesaj alanı bulunamadı"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def run_and_process_tramer_policies(request, form_data: dict, agency_id: int, service_id: int, save_fn: callable):
    print(f"\n🚦 Tramer servisi başlatıldı | agency_id={agency_id} | service_id={service_id}")

    # 👤 Kimlik kontrolü ve ayrıştırma
    kimlik_no = form_data.get("SigortaliKimlikNo") or form_data.get("SigortaliVergiKimlikNo", "")
    tc_kimlik_no = kimlik_no if len(kimlik_no) == 11 else ""
    vergi_no = kimlik_no if len(kimlik_no) == 10 else ""

    if not tc_kimlik_no and not vergi_no:
        return {"success": False, "error": "TC Kimlik No veya Vergi No geçerli değil."}

    # 🚗 Plaka kontrolü
    plaka_raw = form_data.get("AracPlakaTam", "").replace(" ", "")
    if len(plaka_raw) < 4:
        return {"success": False, "error": "Geçersiz plaka formatı."}

    # 📄 Template context (ortak yapı)
    context = {
        "AracPlakaTam": plaka_raw,
        "SigortaliKimlikNo": tc_kimlik_no,
        "SigortaliVergiKimlikNo": vergi_no,
        "TescilBelgeSeriNo": form_data.get("TescilBelgeSeriNo", ""),
    }

    # 🛡️ Yetki kontrolü
    if not AgencyServiceAuthorization.objects.filter(
        agency_id=agency_id,
        service_id=service_id,
        is_active=True
    ).exists():
        print("⛔ Yetki yok")
        return {"success": False, "error": "Bu servisi kullanma yetkiniz yok."}

    try:
        service = ServiceConfiguration.objects.get(id=service_id)
    except ServiceConfiguration.DoesNotExist:
        return {"success": False, "error": "Servis yapılandırması bulunamadı."}

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company=service.insurance_company
    ).first()

    if not password_info or not password_info.cookie:
        return {"success": False, "error": "Cookie veya kullanıcı bilgisi eksik."}

    # 🧩 Template render
    try:
        rendered_body = Template(service.request_template).render(**context)
        print("📤 Request Body:\n", rendered_body)
    except Exception as e:
        return {"success": False, "error": f"Şablon oluşturulamadı: {e}"}

    # 📤 İstek gönder
    headers = {
        "Content-Type": service.content_type,
        "Cookie": password_info.cookie.strip()
    }
    if service.custom_headers:
        headers.update(service.custom_headers)

    session = Session()
    adapter = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1))
    session.mount("https://", adapter)

    try:
        response = session.post(
            url=service.url,
            headers=headers,
            data=rendered_body,
            timeout=20
        )
        print("📥 Yanıt:", response.status_code)
        if response.status_code != 200:
            return {"success": False, "error": f"Yanıt kodu: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"İstek hatası: {e}"}

    # 🧾 Kayıt işlemi
    try:
        raw_text = response.text
        print("📦 İlk 500 karakter:\n", raw_text[:500])

        # İsteğe bağlı: tüm cevabı dosyaya yaz
        with open("last_tramer_response.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)

        if getattr(save_fn, "expects_json", False):
            try:
                parsed = json.loads(raw_text)
            except Exception as e:
                print("❌ JSON parse hatası:", e)
                return {"success": False, "error": "Servis yanıtı geçersiz JSON formatında."}
            return save_fn(agency_id, parsed)
        else:
            return save_fn(agency_id, raw_text)

    except Exception as e:
        return {"success": False, "error": f"Kayıt hatası: {e}"}



def create_and_save_kasko_tramer_data(agency_id: int, response_data: dict):
    print("🚦 [KASKO TRAMER] create_and_save_kasko_tramer_data başladı")

    if "error" in response_data:
        print("❌ Servis error yanıtı:", response_data["error"].get("Message", "Bilinmeyen hata"))
        return

    branch_obj = PolicyBranch.objects.filter(code=101).first()
    if not branch_obj:
        print("❌ PolicyBranch bulunamadı (code=101)")
        return

    try:
        main_block = response_data["value"]
        all_policies = main_block.get("DigerPoliceler", [])
    except Exception as e:
        print(f"❌ JSON parse hatası: {e}")
        return

    if not all_policies:
        print("⚠️ DigerPoliceler boş, kayıt yapılmadı.")
        return

    # ✅ Her bir poliçeyi sırayla işle
    for i, item in enumerate(all_policies, start=1):
        hesaplama_list = item.get("HesaplamaLoglari", [])
        if not hesaplama_list:
            print(f"⚠️ DigerPoliceler[{i}] → HesaplamaLoglari boş, atlanıyor.")
            continue

        row = hesaplama_list[0]
        customer_dict = {
            "SigortaliKimlikNo": row.get("SigortaliTCKimlikNo"),
            "SigortaliVergiKimlikNo": row.get("SigortaliVergiNo"),
            "SigortaliAdi": row.get("SigortaliAdi"),
            "SigortaliSoyadi": row.get("SigortaliSoyadi"),
        }
        customer_ids = create_or_update_customer_generic(agency_id, [customer_dict])
        if not customer_ids:
            print("❌ Müşteri oluşturulamadı")
            continue

        identity_number = customer_ids[0]
        customer = Customer.objects.filter(agency_id=agency_id, identity_number=identity_number).first()
        if not customer:
            print("❌ Customer nesnesi bulunamadı")
            continue

        car_dict = {
            "AracPlakailKodu": row.get("PlakaIlKodu"),
            "AracPlakaNo": row.get("PlakaKodu"),
            "AracPlakaTam": f"{row.get('PlakaIlKodu', '')}{row.get('PlakaKodu', '')}",
            "AracKullanimTarzi": row.get("AracTarifeGrupKodu"),
            "AracMarkaKodu": row.get("AracMarkaKodu"),
            "AracBirlikKodu": row.get("AracKodu"),
            "AracTipKodu": row.get("AracTipKodu"),
            "AracMarkaAdi": row.get("Marka"),
            "AracTipAdi": row.get("Tipi"),
            "AracModelYili": row.get("ModelYili"),
            "AracMotorNo": row.get("MotorNo"),
            "AracSasiNo": row.get("SasiNo"),
        }
        create_or_update_asset_car_generic(agency_id, customer.id, car_dict)

        create_external_policy(
            agency_id=agency_id,
            company_id=None,
            customer=customer,
            data={"value": row},
            branch_id=branch_obj.id,
        )

        print(f"✅ [{i}] poliçe kaydedildi")

    print("✅ Kasko Tramer kayıt işlemi tamamlandı")

create_and_save_kasko_tramer_data.expects_json = True

def create_and_save_tramer_data(agency_id: int, raw_text: str) -> dict[str, Any]:
    print("\n🚧 Tramer response verisi işleniyor (JSON fix ile)")

    result = {
        "customers_created": 0,
        "cars_created": 0,
        "policies_created": 0,
        "errors": [],
        "latest_policy": None
    }

    try:
        cleaned = raw_text.replace('new Ajax.Web.Dictionary("AdaGenel.Cesitli.NesneAlanlari",', '')
        cleaned = cleaned.replace(')', '')
        try:
            parsed = json.loads(cleaned)
        except Exception as e:
            print(f"❌ JSON parse hatası: {e}")
            result["errors"].append("JSON parse edilemedi")
            return result

        tramer_obj = parsed.get("value", {}).get("TramerSonucObjesi_sn040102TrafikPoliceSorguSonucu") or \
                     parsed.get("value", {}).get("TramerSonucObjesi_sn040101TrafikPoliceSorguSonucu")

        if not tramer_obj:
            result["errors"].append("TramerSonucObjesi eksik")
            return result

        gecmis_blocks = tramer_obj.get("gecmisPoliceler", [])
        yurur_blocks = tramer_obj.get("yururPoliceler", [])
        all_blocks = gecmis_blocks + yurur_blocks
        print(f"📆 Toplam poliçe sayısı (geçmiş+yürür): {len(all_blocks)}")

        branch_obj = PolicyBranch.objects.filter(code=100).first()

        for block in all_blocks:
            try:
                sigortali = block.get("sigortali", {})
                identity_number = sigortali.get("tckimlikNo")
                full_name = f"{sigortali.get('adUnvan', '')} {sigortali.get('soyad', '')}".strip()

                if not identity_number or not full_name:
                    print("❌ Kimlik veya isim eksik, atlandı")
                    continue

                customer_list = [{"SigortaliKimlikNo": identity_number, "full_name": full_name}]
                created_ids = create_or_update_customer_generic(agency_id, customer_list)
                if not created_ids:
                    print("❌ Müşteri oluşturulamadı")
                    continue

                customer = Customer.objects.filter(identity_number=identity_number, agency_id=agency_id).first()
                if not customer:
                    continue
                result["customers_created"] += 1

                arac = block.get("aracTemelBilgileri", {})
                marka = arac.get("marka", {})
                tip = arac.get("tip", {})
                plaka = arac.get("plaka", {})

                car_data = {
                    "AracMarkaAdi": marka.get("aciklama"),
                    "AracMarkaKodu": marka.get("kod"),
                    "AracTipAdi": tip.get("aciklama"),
                    "AracTipKodu": tip.get("kod"),
                    "AracModelYili": arac.get("modelYili"),
                    "AracMotorNo": arac.get("motorNo"),
                    "AracSasiNo": arac.get("sasiNo"),
                    "AracPlakailKodu": plaka.get("ilKodu"),
                    "AracPlakaNo": plaka.get("no"),
                    "AracTrafikKademe": block.get("belgeBilgileri", {}).get("uygulanmisTarifeBasamakKodu"),
                    "AracTescilTarihi": parse_date(arac.get("tescilTarihi")),
                }

                if plaka.get("no"):
                    car_data["AracPlakaTam"] = f"{plaka.get('ilKodu', '')} {plaka.get('no')}"

                car_id = create_or_update_asset_car_generic(agency_id, customer.id, car_data)
                if not car_id:
                    print("❌ Araç kaydedilemedi")
                    continue

                car = AssetCars.objects.get(id=car_id)
                result["cars_created"] += 1

                police = block.get("policeAnahtari", {})
                tarih = block.get("tarihBilgileri", {})

                lookup = {
                    "agency_id": agency_id,
                    "PoliceNo": police.get("policeNo"),
                    "ZeyilNo": str(block.get("policeEkiNo") or "0"),
                    "YenilemeNo": str(police.get("yenilemeNo") or "0"),
                }

                defaults = {
                    "customer": customer,
                    "asset_car": car,
                    "branch": branch_obj,
                    "SigortaSirketiKodu": police.get("sirketKodu"),
                    "AcentePartajNo": police.get("acenteKod"),
                    "PoliceTanzimTarihi": parse_date(tarih.get("tanzimTarihi")),
                    "PoliceBaslangicTarihi": parse_date(tarih.get("baslangicTarihi")),
                    "PoliceBitisTarihi": parse_date(tarih.get("bitisTarihi")),
                    "ZeyilBaslangicTarihi": parse_date(tarih.get("ekBaslangicTarihi")),
                    "ZeyilBitisTarihi": parse_date(tarih.get("ekBitisTarihi")),
                    "ZeyilTanzimTarihi": parse_date(block.get("belgeTarih")),
                }

                obj, created = ExternalTramerPolicy.objects.get_or_create(**lookup, defaults=defaults)
                if not created:
                    for key, val in defaults.items():
                        setattr(obj, key, val)
                    obj.save()

                print(f"{'🆕' if created else '♻️'} Poliçe işlendi → {lookup['PoliceNo']}")
                print(f"✅ Poliçe kaydedildi → {lookup['PoliceNo']}")
                result["policies_created"] += 1

            except Exception as ex:
                print(f"❌ Blok işleme hatası: {ex}")
                result["errors"].append(str(ex))

        alanlar_raw = parsed.get("value", {}).get("Alanlar", [])
        alan_dict = {item[0]: item[1].get("Cevap") for item in alanlar_raw} if alanlar_raw else {}

        if alan_dict and alan_dict.get("OncekiPoliceNo"):
            try:
                # Poliçeyi bul ve bazı alanlarını güncelle (DB'ye yazılacak olanlar)
                update_lookup = {
                    "agency_id": agency_id,
                    "PoliceNo": alan_dict.get("OncekiPoliceNo"),
                    "ZeyilNo": str(alan_dict.get("OncekiZeyilNo") or "0"),
                    "YenilemeNo": str(alan_dict.get("OncekiYenilemeNo") or "0"),
                }
                last_policy = ExternalTramerPolicy.objects.filter(**update_lookup).first()

                if last_policy:
                    last_policy.AcentePartajNo = alan_dict.get("OncekiAcenteNo") or last_policy.AcentePartajNo
                    last_policy.SigortaSirketiKodu = alan_dict.get("OncekiSirketKodu") or last_policy.SigortaSirketiKodu
                    last_policy.ZeyilNo = "0"
                    if last_policy.PoliceBitisTarihi:
                        last_policy.PoliceBaslangicTarihi = last_policy.PoliceBitisTarihi - timedelta(days=365)
                    last_policy.save()

                # 🧾 Kullanıcıya gösterilecek ekstra alanlar (sadece UI için)
                result["latest_policy"] = {
                    # Araç bilgileri (car_data’dan)
                    "AracMarkaAdi": car_data.get("AracMarkaAdi"),
                    "AracMarkaKodu": car_data.get("AracMarkaKodu"),
                    "AracTipAdi": car_data.get("AracTipAdi"),
                    "AracTipKodu": car_data.get("AracTipKodu"),
                    "AracModelYili": car_data.get("AracModelYili"),
                    "AracMotorNo": car_data.get("AracMotorNo"),
                    "AracSasiNo": car_data.get("AracSasiNo"),
                    "AracPlakailKodu": car_data.get("AracPlakailKodu"),
                    "AracPlakaNo": car_data.get("AracPlakaNo"),
                    "AracTrafikKademe": car_data.get("AracTrafikKademe"),
                    "AracTescilTarihi": car_data.get("AracTescilTarihi"),
                    "AracPlakaTam": car_data.get("AracPlakaTam"),

                    # Alanlar'dan gelen bilgiler
                    "OncekiPoliceNo": alan_dict.get("OncekiPoliceNo"),
                    "OncekiZeyilNo": alan_dict.get("OncekiZeyilNo"),
                    "OncekiYenilemeNo": alan_dict.get("OncekiYenilemeNo"),
                    "OncekiAcenteNo": alan_dict.get("OncekiAcenteNo"),
                    "OncekiSirketKodu": alan_dict.get("OncekiSirketKodu"),
                    "PoliceBitisTarihi": last_policy.PoliceBitisTarihi.strftime(
                        "%Y-%m-%d") if last_policy and last_policy.PoliceBitisTarihi else None,
                    "PoliceBaslangicTarihi": last_policy.PoliceBaslangicTarihi.strftime(
                        "%Y-%m-%d") if last_policy and last_policy.PoliceBaslangicTarihi else None,
                    "AracTarz": alan_dict.get("AracTarz"),
                }

                print("📦 Kullanıcıya gösterilecek latest_policy içeriği:")
                for k, v in result["latest_policy"].items():
                    print(f"  {k}: {v}")

            except Exception as ex:
                print(f"❌ Alanlar güncelleme hatası: {ex}")
                result["errors"].append(str(ex))

    except Exception as ex:
        print(f"❌ Genel parse hatası: {ex}")
        result["errors"].append(str(ex))

    return result




@ratelimit(key='user', rate='5/m', method='POST', block=False)
@login_required(login_url='/login/')
def dask_police_sorgula(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'İstek sınırı aşıldı. Lütfen biraz sonra tekrar deneyiniz.'}, status=429)

    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        police_no = data.get("police_no")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=1)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi tanımlı değil'}, status=404)

        # SOAP body oluştur
        template = Template(service.soap_template)
        soap_body = template.render(
            police_no=police_no,
            web_username=password_info.web_username,
            web_password=password_info.web_password,
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        # İstek gönder
        response = requests.post(service.url, data=soap_body, headers=headers, verify=False, timeout=15)
        response_text = response.text

        if response.status_code != 200:
            return JsonResponse({'success': False, 'error': 'Servis yanıt vermedi'}, status=502)

        # XML parse
        parsed = xmltodict.parse(response_text)
        soru_cevap = parsed.get('soap:Envelope', {}).get('soap:Body', {}).get(
            'DaskPoliceSorgulaResponse', {}).get('DaskPoliceSorgulaResult', {}).get('SoruCevap', [])

        if isinstance(soru_cevap, dict):
            soru_cevap = [soru_cevap]

        # Log
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=True
        )

        # Hata varsa
        hata = next((item for item in soru_cevap if item.get("Soru") == "Hata" and item.get("Cevap")), None)
        if hata:
            return JsonResponse({'success': False, 'error': hata.get("Cevap")}, status=400)

        # Değerleri çek
        def get_val(key):
            return next((item.get("Cevap") for item in soru_cevap if item.get("Soru") == key), "")

        result_data = {
            "UavtAdresKodu": get_val("UavtAdresKodu"),
            "BinaMetreKare": get_val("BinaMetreKare"),
            "YapiTarzi": get_val("YapiTarzi"),
            "BinaKullanimSekli": get_val("BinaKullanimSekli"),
            "BinaKatSayisi": get_val("BinaKatSayisi"),
            "BinaInsaYili": get_val("BinaInsaYili"),
            "BinaHasarDurumu": get_val("BinaHasarDurumu"),
            "SigortaEttirenSifati": get_val("SigortaEttirenSifati"),
            "DaskOncekiTecditNo": get_val("DaskOncekiTecditNo"),
            "SigortaliTcKimlikNo": get_val("SigortaliTcKimlikNo"),
            "SigortaliVergiNo": get_val("SigortaliVergiNo"),
            "SigortaliCepTelefonNo": get_val("SigortaliCepTelefonNo"),
            "VadeBaslangic": get_val("VadeBaslangic"),
            "VadeBitis": get_val("VadeBitis"),
            "RizikoAda": get_val("RizikoAda"),
            "RizikoPafta": get_val("RizikoPafta"),
            "RizikoParsel": get_val("RizikoParsel"),
            "SigortaliAdi": get_val("SigortaliAdi"),
            "SigortaliSoyadi": get_val("SigortaliSoyadi"),
        }

        # Mapping fonksiyonu çağrılır
        mapped_inputs = apply_dask_mapping(service, result_data)

        return JsonResponse({
            "success": True,
            "data": result_data,
            "mapped": mapped_inputs
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def apply_dask_mapping(service, result_data):
    mapped_result = {}

    for key, value in result_data.items():
        if not value:
            continue

        mappings = DaskMapping.objects.filter(
            service=service,
            service_key=key,
            company_value=value
        ).values("key_id", "parameter_id")

        if mappings.exists():
            first = mappings.first()
            mapped_result[first["key_id"]] = first["parameter_id"]

    return mapped_result

@login_required(login_url='/login/')
def get_customer_bereket(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=18)  # Bereket servis ID

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        if not identity_number or not birth_date:
            return JsonResponse({'error': 'Kimlik numarası ve doğum tarihi zorunludur.'}, status=400)

        # 🔐 AgencyPasswords'dan token bilgilerini al
        agency_password = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company  # ✅
        ).first()

        if not agency_password:
            return JsonResponse({'error': 'Şirket için şifre bilgisi tanımlı değil'}, status=400)

        authentication_key = agency_password.authenticationKey
        app_security_key = agency_password.appSecurityKey

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            birth_date=birth_date,
            query_type=query_type,
            authenticationKey=authentication_key,
            appSecurityKey=app_security_key
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        body = parsed.get("s:Envelope", {}).get("s:Body", {})
        result = body.get("GetCustomerNoResponse", {})
        entity = result.get("entity", {})

        customer_no = entity.get("a:CustomerNo", "")

        is_successful_raw = result.get("IsSuccessful") or entity.get("IsSuccessful")

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful = extract_bool(is_successful_raw)

        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        if is_successful and customer_no:
            company = InsuranceCompany.objects.get(company_code="057")  # ✅ Bereket company_code
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={"customer_no": customer_no}
            )
            return JsonResponse({
                "success": True,
                "customer_no": customer_no
            })

        return JsonResponse({'success': False, 'message': 'CustomerNo bilgisi alınamadı'}, status=404)

    except Exception as e:
        print("❌ HATA:", str(e))
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def get_customer_unico(request):
    print("🔍 UNICO müşteri servisi çağrıldı")

    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=19)  # ✅ UNICO servis ID

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            birth_date=birth_date,
            query_type=query_type
        )



        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        body = parsed.get("s:Envelope", {}).get("s:Body", {})
        result = body.get("GetCustomerNoResponse", {})
        entity = result.get("entity", {})

        customer_no = entity.get("a:CustomerNo", "")

        is_successful_raw = result.get("IsSuccessful") or entity.get("IsSuccessful")

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful = extract_bool(is_successful_raw)

        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            company = InsuranceCompany.objects.get(company_code="017")  # ✅ UNICO company_code

            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={
                    "customer_no": customer_no
                }
            )

            return JsonResponse({
                "success": True,
                "customer_no": customer_no
            })
        else:
            return JsonResponse({'success': False, 'message': 'CustomerNo bilgisi alınamadı'}, status=404)

    except Exception as e:
        print("❌ HATA:", str(e))
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def get_customer_orient(request):


    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=20)  # ✅ SERVIS ID = 20

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        query_type = "0" if len(identity_number) == 11 else "1"
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            birth_date=birth_date,
            query_type=query_type
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text


        parsed = xmltodict.parse(response_text)
        body = parsed.get("s:Envelope", {}).get("s:Body", {})
        result = body.get("GetCustomerNoResponse", {})
        entity = result.get("entity", {})

        customer_no = entity.get("a:CustomerNo", "")

        is_successful_raw = result.get("IsSuccessful") or entity.get("IsSuccessful")

        def extract_bool(val):
            if isinstance(val, dict):
                val = val.get("#text", "")
            return str(val).strip().lower() == "true"

        is_successful = extract_bool(is_successful_raw)

        # ✅ Log kaydı
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        if is_successful and customer_no and "@i:nil" not in str(customer_no):
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            company = InsuranceCompany.objects.get(company_code="106")  # ✅ COMPANY CODE = 106

            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={
                    "customer_no": customer_no
                }
            )

            return JsonResponse({
                "success": True,
                "customer_no": customer_no
            })
        else:
            return JsonResponse({'success': False, 'message': 'CustomerNo bilgisi alınamadı'}, status=404)

    except Exception as e:
        print("❌ HATA:", str(e))
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def get_customer_ankara_v2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        phone = data.get("phone_number")
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")

        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'error': 'Giriş yapılmamış'}, status=403)

        agency = user.agency
        service = ServiceConfiguration.objects.get(id=17)  # Ankara Sigorta servisi

        # Yetki kontrolü
        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        # Giriş bilgilerini çek
        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company_id=7  # Ankara Sigorta
        ).first()

        if not password_info:
            return JsonResponse({'error': 'Kullanıcı adı/şifre bulunamadı'}, status=404)

        if not identity_number or not birth_date or not phone:
            return JsonResponse({'error': 'TC, doğum tarihi ve telefon zorunludur'}, status=400)

        # SOAP oluştur
        template = Template(service.soap_template)
        soap_body = template.render(
            identity_number=identity_number,
            birth_date=birth_date,
            phone=phone,
            web_username=password_info.web_username,
            web_password=password_info.web_password,
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())

        response = session.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        root = ET.fromstring(response_text)
        ns = {'ns': 'http://ws.ankarasigorta.com.tr'}
        result = root.find('.//ns:CreateCustomerResult', ns)
        customer_no = result.text if result is not None else ""

        is_successful = bool(customer_no and customer_no.strip())

        # ✅ CustomerCompany kaydı
        if is_successful and customer_no:
            from offer.models import CustomerCompany
            from database.models import InsuranceCompany

            company = InsuranceCompany.objects.get(id=7)
            CustomerCompany.objects.update_or_create(
                identity_number=identity_number,
                company=company,
                defaults={"customer_no": customer_no}
            )

        # ✅ Servis log kaydı
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=is_successful
        )

        return JsonResponse({
            "success": is_successful,
            "customer_no": customer_no
        })

    except Exception as e:
        print("❌ HATA:", str(e))
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def egm_query_online_policy(request):
    if request.method != "POST":
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")
        key_1 = data.get("key_1")  # Kimlik/Vergi No
        key_77 = data.get("key_77")  # Plaka
        key_79 = data.get("key_79")  # Tescil
        agency = request.user.agency
        user = request.user

        # Servis yapılandırmasını çek
        service = ServiceConfiguration.objects.get(id=54)

        # Acente yetki kontrolü
        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        # Jinja template ile SOAP body hazırla
        form_data = {
            "key_1": key_1,
            "key_77": key_77,
            "key_79": key_79
        }
        context = {
            "form_data": form_data
        }
        template = Template(service.soap_template)
        soap_body = template.render(**context)

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        # İstek gönder (SSLAdapter ile)
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=15)
        response_text = response.text

        # LOG kaydı
        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=response.status_code == 200
        )

        # Mapping ile parse et (GENERIC!)
        mappings = ServiceFieldMapping.objects.filter(service=service).select_related("key", "parameter")
        fields = parse_service_response(response_text, mappings)

        # Sonuçları dön (tuple key dönmeyeceği için direkt)
        return JsonResponse({"success": True, "fields": fields})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def egm_ray(request):
    if request.method != "POST":
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)

    try:
        data = json.loads(request.body)
        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")
        key_77 = data.get("key_77")    # Plaka
        key_79 = data.get("key_79")    # Tescil Belge Seri

        user = request.user
        agency = user.agency
        service = ServiceConfiguration.objects.get(id=59)  # Ray EGM Servis

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=service.insurance_company
        ).first()
        if not password_info:
            return JsonResponse({'error': 'Kullanıcı bilgisi bulunamadı'}, status=404)

        template = Template(service.soap_template)
        soap_body = template.render(
            web_username=password_info.web_username or "",
            web_password=password_info.web_password or "",
            plaka=key_77 or "",
            belge_seri=key_79 or ""
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        response = requests.post(service.url, data=soap_body, headers=headers, timeout=10)
        response_text = response.text

        # --- MotorNo ve SasiNo PARSE ---
        motor_no = None
        sasi_no = None
        try:
            # XML parse işlemi
            ns = {
                "s": "http://schemas.xmlsoap.org/soap/envelope/",
                "a": "http://schemas.datacontract.org/2004/07/Ray.Net.Entity.SorgulamaIslemleri.EgmSorgu"
            }
            root = ET.fromstring(response_text)
            # <a:MotorNo>
            motor_no_el = root.find(".//a:MotorNo", namespaces=ns)
            sasi_no_el = root.find(".//a:SasiNo", namespaces=ns)
            motor_no = motor_no_el.text if motor_no_el is not None else ""
            sasi_no = sasi_no_el.text if sasi_no_el is not None else ""
        except Exception as ex:
            motor_no = ""
            sasi_no = ""

        ProposalServiceLog.objects.create(
            proposal_id=proposal_id,
            product_code=product_code,
            info_service=service,
            agency=agency,
            user=user,
            request_data=soap_body,
            response_data=response_text,
            success=response.status_code == 200
        )

        return JsonResponse({
            "success": True,
            "motor_no": motor_no,
            "sasi_no": sasi_no
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def get_arac_markalari(request):
    if request.method != "GET":
        return JsonResponse({'error': 'Sadece GET isteği kabul edilir'}, status=405)

    try:
        agency = request.user.agency
        service = ServiceConfiguration.objects.get(id=55)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        template = Template(service.soap_template)
        soap_body = template.render()
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=15)
        response_text = response.text

        parsed = xmltodict.parse(response_text)

        # LOG İÇİN:
        # print(json.dumps(parsed, indent=2, ensure_ascii=False))

        # Her yerde bulmak için:
        marka_list = []
        def find_keyvalue_pairs(node):
            if isinstance(node, list):
                for n in node:
                    find_keyvalue_pairs(n)
            elif isinstance(node, dict):
                for k, v in node.items():
                    if k.endswith('KeyValuePairOfstringstring'):
                        if isinstance(v, list):
                            marka_list.extend(v)
                        else:
                            marka_list.append(v)
                    else:
                        find_keyvalue_pairs(v)
        find_keyvalue_pairs(parsed)

        # Markaları toparla
        result = []
        for item in marka_list:
            code = item.get('b:key') or item.get('key') or ""
            name = item.get('b:value') or item.get('value') or ""
            if code and name:
                result.append({"code": code, "name": name})

        return JsonResponse({"success": True, "brands": result})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def get_arac_tarzlari(request):
    if request.method != "GET":
        return JsonResponse({'error': 'Sadece GET isteği kabul edilir'}, status=405)

    try:
        agency = request.user.agency
        service = ServiceConfiguration.objects.get(id=57)

        if not AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({'error': 'Bu servise erişim yetkiniz yok!'}, status=403)

        template = Template(service.soap_template)
        soap_body = template.render()
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=15)
        response_text = response.text

        parsed = xmltodict.parse(response_text)
        tarz_list = []

        # Esnek: Data altında KeyValuePair'leri bul
        def find_keyvalue_pairs(node):
            if isinstance(node, list):
                for n in node:
                    find_keyvalue_pairs(n)
            elif isinstance(node, dict):
                for k, v in node.items():
                    if k.endswith('KeyValuePairOfstringstring'):
                        if isinstance(v, list):
                            tarz_list.extend(v)
                        else:
                            tarz_list.append(v)
                    else:
                        find_keyvalue_pairs(v)
        find_keyvalue_pairs(parsed)

        result = []
        for item in tarz_list:
            code = item.get('b:key') or item.get('key') or ""
            name = item.get('b:value') or item.get('value') or ""
            if code and name:
                result.append({"code": code, "name": name})

        return JsonResponse({"success": True, "tarzlar": result})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def get_model_years(request):
    if request.method != "POST":
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)
    try:
        data = json.loads(request.body)
        tarz_kodu = data.get("tarz_kodu")   # key_85'teki kod
        marka_kodu = data.get("marka_kodu") # key_81'deki kod

        service = ServiceConfiguration.objects.get(id=56)  # id=58 model year servisi olsun

        context = {
            "authentication_key": "",  # veya gerekliyse şifreni yaz
            "first_param": tarz_kodu,
            "second_param": marka_kodu
        }
        template = Template(service.soap_template)
        soap_body = template.render(**context)

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=15)
        response_text = response.text

        # Model yılı listesini XML’den çıkar
        parsed = xmltodict.parse(response_text)
        model_years = []
        try:
            items = parsed["s:Envelope"]["s:Body"]["GetListSourceResponse"]["GetListSourceResult"]["a:Data"]["b:KeyValuePairOfstringstring"]
            if not isinstance(items, list):
                items = [items]
            for item in items:
                code = item.get("b:key")
                name = item.get("b:value")
                model_years.append({"code": code, "name": name})
        except Exception:
            pass

        return JsonResponse({"success": True, "years": model_years})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='/login/')
def get_arac_modelleri(request):
    if request.method != "POST":
        return JsonResponse({'error': 'Sadece POST isteği kabul edilir'}, status=405)
    try:
        data = json.loads(request.body)
        tarz_kodu = data.get("tarz_kodu")   # key_85
        marka_kodu = data.get("marka_kodu") # key_81
        yil_kodu = data.get("yil_kodu")     # key_88
        urun_kodu = data.get("urun_kodu", "HSP")  # product_code veya sabit

        # Servis config (ör: id=59)
        service = ServiceConfiguration.objects.get(id=58)

        context = {
            "authentication_key": "",  # Gerekirse ekle
            "first_param": tarz_kodu,
            "second_param": marka_kodu,
            "third_param": yil_kodu,
            "fourth_param": urun_kodu,
        }
        template = Template(service.soap_template)
        soap_body = template.render(**context)

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": service.soap_action
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service.url, data=soap_body, headers=headers, timeout=15)
        response_text = response.text

        # Model listesini XML’den çıkar
        parsed = xmltodict.parse(response_text)
        model_list = []
        try:
            items = parsed["s:Envelope"]["s:Body"]["GetListSourceResponse"]["GetListSourceResult"]["a:Data"]["b:KeyValuePairOfstringstring"]
            if not isinstance(items, list):
                items = [items]
            for item in items:
                code = item.get("b:key")
                name = item.get("b:value")
                model_list.append({"code": code, "name": name})
        except Exception as ex:
            print("Model parsing hatası:", ex)

        return JsonResponse({"success": True, "models": model_list})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)














