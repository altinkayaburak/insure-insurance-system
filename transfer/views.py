import importlib,ssl,requests,xmltodict,time,json,os,re
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models.functions import Length
from django.shortcuts import render
from django.http import JsonResponse
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from requests import Session
from django.template import Template
from INSAI.utils import parse_date, split_date_range, clean_namespaces, get_by_path, SSLAdapter, \
    apply_company_service_field_mapping
from agency.models import AgencyPasswords, AgencyTransferServiceAuthorization
from database.models import ServiceConfiguration, Customer, \
    TransferServiceConfiguration, AssetCars, AssetHome, CompanyServiceFieldMapping, InsuranceCompany
from gateway.views import get_first_available_birth_date, verify_customer_backend, get_tescil_detay
from transfer.models import TransferLog, TransferPostProcessLog
from jinja2 import Template
from datetime import timedelta
from django.utils import timezone
from datetime import datetime
from transfer.tasks import run_transfer_service_task, run_bereket_card_info_task


def run_transfer_service_controller(
    agency_id,
    service_config,
    company_id,
    start_date,
    end_date,
    log=None,
    user=None,
    source="manual"
):
    handler_func_path = service_config.handler_function
    if not handler_func_path:
        raise Exception(f"Handler fonksiyonu tanımlı değil: Service ID {service_config.id}")

    try:
        module_path, func_name = handler_func_path.rsplit(".", 1)
        import_path = f"transfer.{module_path}"
        handler_module = importlib.import_module(import_path)
        handler_func = getattr(handler_module, func_name)
    except (ImportError, AttributeError) as ex:
        raise Exception(f"❌ Handler fonksiyonu yüklenemedi: {handler_func_path} → {ex}")

    batch_id = f"TRF{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        if log is None:
            log = TransferLog.objects.create(
                agency_id=agency_id,
                company_id=company_id,
                start_date=start_date,
                end_date=end_date,
                block_start=start_date,
                block_end=end_date,
                request_sent=False,
                response_received=False,
                success=False,
                batch_id=batch_id,
                user=user,
                source=source,
                started_at=timezone.now()
            )
        elif log.started_at is None:
            log.started_at = timezone.now()

        print("📘 Log ID:", log.id)

        # 🔐 TOKEN bilgisi için password objesi alınır
        password = AgencyPasswords.objects.get(
            agency_id=agency_id,
            insurance_company=service_config.insurance_company
        )

        total_result = {
            "total": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "customers_created": 0,
            "cars_created": 0,
            "homes_created": 0,
        }

        date_blocks = split_date_range(start_date, end_date, days=3)

        at_least_one_success = False

        for block_start, block_end in date_blocks:
            print(f"📅 Tarih bloğu → {block_start} → {block_end}")
            try:
                result = handler_func(
                    agency_id=agency_id,
                    company_id=company_id,
                    service_config=service_config,
                    password=password,
                    start_date=block_start,
                    end_date=block_end,
                    batch_id=batch_id,
                    log=log
                )

                if result in [None, {}, "NO_DATA"]:
                    print("ℹ️ Veri yok, blok atlandı.")
                    continue

                if isinstance(result, dict):
                    at_least_one_success = True
                    for key in total_result:
                        total_result[key] += result.get(key, 0)

            except Exception as ex:
                print(f"⚠️ Blok hatası: {block_start} → {block_end} → {ex}")
                continue

        log.request_sent = True
        log.response_received = True
        log.success = at_least_one_success  # ✅ DÜZENLENDİ
        log.finished_at = timezone.now()

        if log.started_at and log.finished_at:
            log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())

        log.total_count = total_result["total"]
        log.created_count = total_result["created"]
        log.updated_count = total_result["updated"]
        log.skipped_count = total_result["skipped"]
        log.customers_created = total_result["customers_created"]
        log.cars_created = total_result["cars_created"]
        log.homes_created = total_result["homes_created"]
        log.save()

        return {
            "success": True,
            **total_result
        }

    except Exception as ex:
        print(f"❌ Ana servis hatası: {ex}")
        log.success = False
        log.error_message = str(ex)
        log.finished_at = timezone.now()
        if log.started_at and log.duration_seconds is None:
            log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())
        log.save()
        return None


def run_post_transfer_services(agency_id: int, company_id: int, transfer_log: TransferLog):
    """
    Manuel tetiklenen post-transfer doğrulama ve potansiyel işlem servisleri.
    Her biri kendi içinde loglanır, sonunda toplam sonuç TransferPostProcessLog'a yazılır.
    """
    print("🚀 [Post Transfer Servisleri] Başlatılıyor...")

    customer_verified = 0
    cars_verified = 0
    homes_verified = 0
    certificate_found = 0

    try:
        # 1️⃣ Müşteri doğrulama
        identity_numbers = Customer.objects.filter(
            agency_id=agency_id,
            is_verified=False
        ).values_list("identity_number", flat=True)
        verify_transferred_customers(identity_numbers, agency_id)
        customer_verified = Customer.objects.filter(
            agency_id=agency_id,
            is_verified=True,
            updated_at__gte=timezone.now() - timedelta(minutes=10)
        ).count()

        # 2️⃣ Konut doğrulama
        verify_unverified_asset_homes_with_uavt(agency_id, company_id)
        homes_verified = AssetHome.objects.filter(
            agency_id=agency_id,
            is_verified=True,
            updated_at__gte=timezone.now() - timedelta(minutes=10)
        ).count()

        # 3️⃣ Araç tescil no bulma → önce bu!
        verify_unverified_asset_cars_with_tescil(agency_id, company_id, service_id=80)
        certificate_found = AssetCars.objects.filter(
            agency_id=agency_id,
            AracTescilSeriNo__isnull=False,
            updated_at__gte=timezone.now() - timedelta(minutes=10)
        ).count()

        # 4️⃣ Araç doğrulama
        verify_unverified_asset_cars_with_api(agency_id, company_id, service_id=79)
        cars_verified = AssetCars.objects.filter(
            agency_id=agency_id,
            is_verified=True,
            updated_at__gte=timezone.now() - timedelta(minutes=10)
        ).count()

        # 🔄 Toplu log kaydı
        TransferPostProcessLog.objects.create(
            log=transfer_log,
            customer_verified_count=customer_verified,
            cars_verified_count=cars_verified,
            homes_verified_count=homes_verified,
            certificate_found_count=certificate_found,
            notes="Manuel tetiklenen post-transfer servisleri başarıyla çalıştı"
        )

        print("✅ Tüm post-transfer işlemler tamamlandı ve log kaydedildi.")

    except Exception as e:
        print(f"❌ Post-process işlemlerinde genel hata: {e}")

def verify_transferred_customers(identity_number_list, agency_id):
    """
    Yeni transfer edilen müşterileri sırayla doğrular.
    - Sadece son 72 saatte oluşturulan ve doğrulanmamış olanlar işlenir.
    - Doğum tarihi yoksa servislerden alınır.
    - Her müşteri yalnızca bir kez sorgulanır.
    """
    time_threshold = timezone.now() - timedelta(hours=72)

    customers = Customer.objects.filter(
        agency_id=agency_id,
        identity_number__in=identity_number_list,
        is_verified=False,
        created_at__gte=time_threshold
    )

    verified = set()

    for customer in customers:
        kimlik_no = str(customer.identity_number).strip()
        if not kimlik_no or kimlik_no in verified:
            continue

        if not kimlik_no.isdigit() or len(kimlik_no) not in [10, 11]:
            print(f"⚠️ Kimlik formatı hatalı, doğrulama atlandı → {kimlik_no}")
            continue

        print(f"⏳ Müşteri doğrulama başlıyor → {kimlik_no}")

        if not customer.birth_date and len(kimlik_no) == 11:
            try:
                result = get_first_available_birth_date(kimlik_no, agency_id, update_customer=True)
                print(f"🗓️ Doğum tarihi sorgu sonucu → {result}")
                if result["success"]:
                    customer.refresh_from_db()
                else:
                    print(f"⚠️ Doğum tarihi alınamadı → {kimlik_no}")
                    verified.add(kimlik_no)
                    continue
            except Exception as e:
                print(f"❌ Doğum tarihi servisi hatası: {kimlik_no} → {e}")
                verified.add(kimlik_no)
                continue

        try:
            bdate = customer.birth_date.strftime("%d.%m.%Y") if customer.birth_date else ""
            result = verify_customer_backend(kimlik_no, bdate, agency_id)

            if not isinstance(result, dict):
                result = {"success": False, "error": str(result)}

            if result.get("success"):
                customer.is_verified = True
                customer.save(update_fields=["is_verified"])
                print(f"✅ Doğrulama başarılı → {kimlik_no}")
            else:
                print(f"❌ Doğrulama başarısız → {kimlik_no} | Cevap: {result}")
        except Exception as e:
            print(f"❌ Doğrulama servisi hatası: {kimlik_no} → {e}")

        verified.add(kimlik_no)
        time.sleep(3)

def verify_unverified_asset_homes_with_uavt(agency_id: int, company_id: int):
    print("📍 [UAVT Adres Doğrulama] Başlatıldı")

    try:
        service = ServiceConfiguration.objects.get(id=9)
    except ServiceConfiguration.DoesNotExist:
        print("❌ ServiceConfiguration ID=9 bulunamadı.")
        return

    time_threshold = timezone.now() - timedelta(hours=72)

    asset_qs = AssetHome.objects.filter(
        agency_id=agency_id,
        is_verified=False,
        created_at__gte=time_threshold,
        RizikoUavtKod__isnull=False
    ).exclude(RizikoUavtKod="")

    if not asset_qs.exists():
        print("ℹ️ Doğrulanacak konut kaydı bulunamadı.")
        return

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company=service.insurance_company
    ).first()

    web_username = password_info.web_username if password_info else ""
    web_password = password_info.web_password if password_info else ""

    for asset in asset_qs:
        uavt_code = asset.RizikoUavtKod
        print(f"\n🔎 UAVT Doğrulama başlatıldı → {uavt_code}")
        try:
            soap_body = Template(service.soap_template).render(
                web_username=web_username,
                web_password=web_password,
                uavtAdresKodu=uavt_code
            )

            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": service.soap_action
            }

            response = requests.post(service.url, data=soap_body, headers=headers, timeout=15)
            print(f"📩 HTTP Status: {response.status_code}")
            if response.status_code != 200:
                continue

            parsed = clean_namespaces(xmltodict.parse(response.text))
            content = get_by_path(parsed, "Envelope.Body.UavtAdresDetayAlResponse.UavtAdresDetayAlResult")
            if not content:
                print(f"⚠️ Response içeriği boş veya path hatalı → {uavt_code}")
                continue

            mapped_fields = {
                "RizikoUavtKod": get_by_path(content, "Daireler.UavtDaire.AdresKodu"),
                "Riziko_il_kod": get_by_path(content, "Ilceler.UavtIlce.IlKodu"),
                "Riziko_ilce_kodu": get_by_path(content, "Ilceler.UavtIlce.IlceKodu"),
                "Riziko_Koy_kodu": get_by_path(content, "Koyler.UavtKoy.KoyKodu"),
                "Riziko_mahalle_kodu": get_by_path(content, "Mahalleler.UavtMahalle.MahalleKodu"),
                "Riziko_csbm_kodu": get_by_path(content, "CSBMler.UavtCSBM.CSBMKodu"),
                "Riziko_bina_kodu": get_by_path(content, "Binalar.UavtBina.BinaKodu"),
                "Riziko_bina_adi": get_by_path(content, "Binalar.UavtBina.BinaAdi"),
                "Riziko_daire_kodu": get_by_path(content, "Daireler.UavtDaire.DaireKodu"),
                "Riziko_daire_no": get_by_path(content, "Daireler.UavtDaire.DaireNumarasi"),
                "Riziko_il_ad": get_by_path(content, "Iller.UavtIl.IlAdi"),
                "Riziko_ilce_adi": get_by_path(content, "Ilceler.UavtIlce.IlceAdi"),
                "Riziko_koy_adi": get_by_path(content, "Koyler.UavtKoy.KoyAdi"),
                "Riziko_mahalle_adi": get_by_path(content, "Mahalleler.UavtMahalle.MahalleAdi"),
                "Riziko_sokak_adi": get_by_path(content, "CSBMler.UavtCSBM.CSBMAdi"),
            }

            if not mapped_fields["RizikoUavtKod"]:
                print(f"⚠️ AdresKodu bulunamadı → {uavt_code}")
                continue

            valid_fields = {f.name for f in AssetHome._meta.get_fields()}
            update_fields = {k: v for k, v in mapped_fields.items() if k in valid_fields}

            for k, v in update_fields.items():
                setattr(asset, k, v)

            asset.is_verified = True
            asset.save(update_fields=list(update_fields.keys()) + ["is_verified"])

            print(f"✅ Doğrulandı: id={asset.id} | UAVT={uavt_code}")

        except Exception as e:
            print(f"❌ Exception: {uavt_code} → {e}")
            continue

def verify_unverified_asset_cars_with_tescil(agency_id: int, company_id: int, service_id: int = 80):
    print("🚘 [Araç Tescil No Doğrulama] Başlatıldı")

    time_threshold = timezone.now() - timedelta(hours=72)

    cars = AssetCars.objects.filter(
        agency_id=agency_id,
        created_at__gte=time_threshold,
        AracTescilSeriNo__isnull=True
    ).exclude(AracPlakaTam__isnull=True).exclude(AracPlakaTam="").annotate(
        plaka_len=Length("AracPlakaTam")
    ).filter(plaka_len__gt=4)

    print(f"🔍 İşlenecek araç sayısı: {cars.count()}")
    if not cars.exists():
        print("ℹ️ İşlenecek araç bulunamadı.")
        return

    for car in cars:
        try:
            kimlik_no = car.insured.identity_number if car.insured else None
            if not kimlik_no:
                print(f"⚠️ Kimlik no eksik → Araç ID: {car.id}")
                continue

            plaka_tam = car.AracPlakaTam
            plaka_il_kodu_raw = plaka_tam[:3].lstrip("0")
            plaka_il_kodu = plaka_il_kodu_raw.zfill(2)
            plaka_no = plaka_tam[3:]

            result = get_tescil_detay(
                agency_id=agency_id,
                plaka_il_kodu=plaka_il_kodu,
                plaka=plaka_no,
                kimlik_no=kimlik_no,
                service_id=service_id
            )

            if result.get("success") and result.get("result"):
                seri_no = result["result"]
                car.AracTescilSeriKod = "AA"
                car.AracTescilSeriNo = seri_no
                car.AracTescilTam = f"AA{seri_no}"
                car.save(update_fields=["AracTescilSeriKod", "AracTescilSeriNo", "AracTescilTam"])
                print(f"✅ Tescil kaydı yapıldı → Araç ID: {car.id} | AA{seri_no}")
            else:
                print(f"⚠️ Servis başarısız → Araç ID: {car.id} | Hata: {result.get('error')}")

        except Exception as e:
            print(f"❌ Genel hata → Araç ID: {car.id} | Hata: {e}")
            continue

def verify_unverified_asset_cars_with_api(agency_id: int, company_id: int, service_id: int = 79):
    print("🚗 [Araç Varlık Doğrulama] Başlatıldı")

    try:
        service = ServiceConfiguration.objects.get(id=service_id)
    except ServiceConfiguration.DoesNotExist:
        print("❌ Servis bulunamadı.")
        return

    ap = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company=service.insurance_company
    ).first()
    if not ap or not ap.cookie:
        print("❌ Cookie bulunamadı.")
        return

    time_threshold = timezone.now() - timedelta(hours=72)

    car_qs = AssetCars.objects.filter(
        agency_id=agency_id,
        is_verified=False,
        created_at__gte=time_threshold
    ).exclude(AracTescilSeriNo__isnull=True).exclude(AracTescilSeriNo="")

    print(f"🔍 Doğrulanacak araç sayısı: {car_qs.count()}")
    if not car_qs.exists():
        print("ℹ️ Doğrulanacak araç varlığı bulunamadı.")
        return

    session = Session()
    adapter = SSLAdapter()
    session.mount("https://", adapter)

    mapping_qs = CompanyServiceFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key", "parameter")

    if not mapping_qs.exists():
        print("🚨 Mapping tablosu boş dönüyor! company_id veya service_id hatalı olabilir.")
    else:
        print("📌 [Mapping Tablosu] Eşleşme satırları:")
        for m in mapping_qs:
            print(f"🧩 Mapping satırı → key_id={m.key_id} | key={m.key.KeyName if m.key else '-'} | company_key={m.company_key}")

    for car in car_qs:
        print(f"🔍 Doğrulama adayı → ID: {car.id} | Plaka: {car.AracPlakaTam}")

        try:
            # 👤 Kimlik kontrolü
            kimlik_no = car.insured.identity_number if car.insured else None
            if not kimlik_no:
                print(f"⚠️ Kimlik no eksik → Araç ID: {car.id}")
                continue

            # 🔧 Tescil seri kod/no ayrıştırma
            tescil_seri_kod = (car.AracTescilSeriKod or "").strip()
            tescil_seri_no = (car.AracTescilSeriNo or "").strip()

            if (not tescil_seri_kod or not tescil_seri_no) and car.AracTescilTam:
                tescil = car.AracTescilTam.strip()
                if len(tescil) >= 3:
                    tescil_seri_kod = tescil[:2]
                    tescil_seri_no = tescil[2:]

            if not tescil_seri_kod and tescil_seri_no:
                tescil_seri_kod = "AA"

            tescil_seri_raw = tescil_seri_kod + tescil_seri_no
            tescil_seri = ''.join(filter(str.isdigit, tescil_seri_raw))[-6:] if tescil_seri_raw else ""

            # 🚘 Plaka ayrıştırma
            plaka_il = (car.AracPlakailKodu or "").strip()
            plaka_no = (car.AracPlakaNo or "").strip()

            if (not plaka_il or not plaka_no) and car.AracPlakaTam:
                tam = car.AracPlakaTam.strip()
                if len(tam) >= 4:
                    plaka_il = tam[:2] if tam[:2].isdigit() else ""
                    plaka_no = tam[2:]

            if not plaka_il or not plaka_no:
                print(f"⚠️ Plaka bilgisi eksik → Araç ID: {car.id} | PlakaTam: {car.AracPlakaTam}")
                continue

            # 👤 Kimlik tipine göre alan belirle
            tc_kimlik = kimlik_no if len(kimlik_no) == 11 else ""
            vergi_no = kimlik_no if len(kimlik_no) == 10 else ""

            # 📦 Gövde verisi
            body_data = {
                "TescilBelgeSeriNo": tescil_seri,
                "PlakaIlKodu": plaka_il.zfill(3),
                "Plaka": plaka_no,
                "TcKimlikNo": tc_kimlik,
                "VergiNo": vergi_no or " "
            }

            headers = {
                "Content-Type": service.content_type,
                "Cookie": ap.cookie.strip()
            }
            if service.custom_headers:
                headers.update(service.custom_headers)

            resp = session.post(service.url, json={"input": body_data}, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"❌ HTTP hatası: {resp.status_code}")
                continue

            try:
                response_data = resp.json()
            except Exception as e:
                print(f"❌ JSON parse hatası → Araç ID: {car.id} | {e}")
                continue

            response_data = response_data.get("value") or {}
            if not isinstance(response_data, dict):
                print(f"⚠️ Geçersiz yanıt yapısı → Araç ID: {car.id}")
                continue

            print("📜 Mapping’e gidecek temizlenmiş veri:")
            for k, v in response_data.items():
                print(f"→ {k} : {v}")

            mapped_fields = apply_company_service_field_mapping(response_data, mapping_qs)

            if not mapped_fields:
                print(f"⚠️ Mapping sonucu boş → Araç ID: {car.id}")
                continue

            valid_fields = {f.name for f in AssetCars._meta.fields}
            for key, val in mapped_fields.items():
                if val in [None, '', {}, [], 0, "0001-01-01"]:
                    continue
                if key in valid_fields:
                    setattr(car, key, val)
                    print(f"📝 Set → {key} = {val}")

            car.is_verified = True
            car.save()
            print(f"✅ Doğrulandı ve kaydedildi → Araç ID: {car.id}")

        except Exception as e:
            print(f"❌ Genel hata → Araç ID: {car.id} | {e}")
            continue


@login_required
def transfer_page_view(request):
    agency = request.user.agency

    auth_qs = AgencyTransferServiceAuthorization.objects.filter(
        agency=agency,
        is_active=True,
        transfer_service__is_active=True
    ).select_related("transfer_service", "transfer_service__insurance_company")

    seen_companies = set()
    company_cards = []
    latest_logs = {}

    for auth in auth_qs:
        company = auth.transfer_service.insurance_company
        if company.id in seen_companies:
            continue

        seen_companies.add(company.id)

        # 🔄 Son logu al
        last_log = TransferLog.objects.filter(
            agency_id=agency.id,
            company_id=company.id
        ).order_by("-finished_at").first()

        latest_logs[company.id] = last_log

        logo_filename = f"{company.company_code}.png"
        logo_path = f"logos/{logo_filename}"
        absolute_logo_path = os.path.join(settings.BASE_DIR, "static", logo_path)
        if not os.path.exists(absolute_logo_path):
            logo_path = "logos/default.png"

        company_cards.append({
            "company_id": company.id,
            "name": company.name,
            "logo": logo_path,
            "slug": company.company_code.lower(),
            "has_credit_card_task": company.has_credit_card_task,  # ✅ EKLENDİ
            "credit_card_handler_function": company.credit_card_handler_function  # ✅ EKLENDİ
        })

    # ✅ Global log toplamları (son 24 saat)
    time_threshold = now() - timedelta(hours=24)
    global_logs = TransferLog.objects.filter(
        agency=agency,
        finished_at__gte=time_threshold
    )

    global_totals = {
        "total": sum(log.total_count or 0 for log in global_logs),
        "created": sum(log.created_count or 0 for log in global_logs),
        "updated": sum(getattr(log, "updated_count", 0) or 0 for log in global_logs),
        "skipped": sum(
            (log.total_count or 0) - ((log.created_count or 0) + (getattr(log, "updated_count", 0) or 0))
            for log in global_logs
        ),
        "last_transfer": global_logs.order_by("-finished_at").first().finished_at if global_logs.exists() else None
    }

    return render(request, "transfer/transferpage.html", {
        "company_cards": company_cards,
        "latest_logs": latest_logs,
        "global_totals": global_totals,
    })


@login_required
def run_all_transfer_sliced(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek."})

    try:
        data = json.loads(request.body)
        agency_id = request.user.agency_id
        start_date = datetime.strptime(data.get("start_date"), "%d/%m/%Y").date()
        end_date = datetime.strptime(data.get("end_date"), "%d/%m/%Y").date()

        # Tarih validasyon
        if (end_date - start_date).days > 30:
            return JsonResponse({"success": False, "error": "Tarih aralığı 30 günden fazla olamaz."})

        date_blocks = split_date_range(start_date, end_date, days=3)

        # Yetkili ana servisler
        auths = AgencyTransferServiceAuthorization.objects.filter(
            agency_id=agency_id,
            is_active=True,
            transfer_service__is_active=True,
            transfer_service__detail_service__isnull=True
        ).select_related("transfer_service", "transfer_service__insurance_company")

        if not auths.exists():
            return JsonResponse({"success": False, "error": "Yetkili servis bulunamadı."})

        for auth in auths:
            service = auth.transfer_service
            company_id = service.insurance_company_id

            for start, end in date_blocks:
                run_transfer_service_task.delay(
                    agency_id=agency_id,
                    company_id=company_id,
                    service_config_id=service.id,
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    source="manual",
                    user_id=request.user.id
                )

        return JsonResponse({"success": True, "message": f"Tüm servisler {len(date_blocks)} blokta başlatıldı."})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@require_POST
@login_required
def run_single_company_transfer(request):
    try:
        print("📥 AJAX istek alındı (run_single_company_transfer)")

        data = json.loads(request.body)
        company_id = data.get("company_id")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        agency_id = request.user.agency_id
        user_id = request.user.id

        print("📅 Alınan Tarihler → Start:", start_date_str, "| End:", end_date_str)
        print("🏢 Şirket ID:", company_id, "| Acenta ID:", agency_id)

        start_date = datetime.strptime(start_date_str, "%d/%m/%Y").date()
        end_date = datetime.strptime(end_date_str, "%d/%m/%Y").date()

        service = TransferServiceConfiguration.objects.filter(
            insurance_company_id=company_id,
            is_active=True
        ).first()

        if not service:
            print("❌ Aktif ana servis bulunamadı.")
            return JsonResponse({"success": False, "error": "Servis bulunamadı."})

        print("✅ Ana servis bulundu:", service.handler_function)
        print("🚀 Transfer Celery kuyruğuna alınıyor...")

        run_transfer_service_task.delay(
            agency_id=agency_id,
            company_id=company_id,
            service_config_id=service.id,
            start_date=str(start_date),
            end_date=str(end_date),
            source="manual",
            user_id=user_id
        )

        return JsonResponse({
            "success": True,
            "message": f"{service.insurance_company.name} için transfer kuyruğa alındı. Sonuçlar logdan takip edilebilir."
        })

    except Exception as e:
        print("❌ Hata:", str(e))
        return JsonResponse({"success": False, "error": str(e)})


def get_latest_transfer_status(request, company_id):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"status": "unauthorized"}, status=401)

    agency_id = user.agency_id
    latest_log = TransferLog.objects.filter(
        agency_id=agency_id,
        company_id=company_id
    ).order_by("-created_at").first()

    if not latest_log or not latest_log.finished_at:
        return JsonResponse({"status": "pending"})

    # ✅ Son 24 saatlik global toplamlar
    time_threshold = now() - timedelta(hours=24)
    global_logs = TransferLog.objects.filter(
        agency_id=agency_id,
        finished_at__gte=time_threshold
    )

    global_totals = {
        "total": sum(log.total_count or 0 for log in global_logs),
        "created": sum(log.created_count or 0 for log in global_logs),
        "updated": sum(getattr(log, "updated_count", 0) or 0 for log in global_logs),
        "skipped": sum(
            (log.total_count or 0) - ((log.created_count or 0) + (getattr(log, "updated_count", 0) or 0))
            for log in global_logs
        ),
        "last_transfer": global_logs.order_by("-finished_at").first().finished_at.strftime("%d.%m.%Y %H:%M") if global_logs.exists() else None
    }

    return JsonResponse({
        "status": "done" if latest_log.success else "failed",
        "success": latest_log.success,
        "total_count": latest_log.total_count,
        "created_count": latest_log.created_count,
        "updated_count": latest_log.updated_count,
        "skipped_count": latest_log.skipped_count,
        "global_totals": global_totals  # 🆕 Eklendi!
    })

@login_required
def trigger_card_task(request):
    company_id = request.GET.get("company_id")
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return JsonResponse({"status": "invalid_company_id"})

    company = InsuranceCompany.objects.filter(id=company_id).first()
    if not company:
        return JsonResponse({"status": "not_found"})

    handler_name = company.credit_card_handler_function
    if not handler_name:
        return JsonResponse({"status": "not_found"})

    service = TransferServiceConfiguration.objects.filter(
        insurance_company_id=company.id,
        handler_function=handler_name,
        is_active=True
    ).first()

    if not service:
        return JsonResponse({"status": "service_not_found"})

    # ⏱ Tarih aralığı
    start_date = (now() - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = now().strftime("%Y-%m-%d")
    agency_id = request.user.agency_id

    try:
        # 🔁 Dinamik import
        module = importlib.import_module("transfer.tasks")
        handler_func = getattr(module, handler_name)
        handler_func.delay(agency_id, service.id, start_date, end_date)
        print(f"🚀 Kart handler başlatıldı: {handler_name}")
        return JsonResponse({"status": "started"})
    except Exception as e:
        print(f"❌ Handler çağrısı hatası: {e}")
        return JsonResponse({"status": "handler_error"})