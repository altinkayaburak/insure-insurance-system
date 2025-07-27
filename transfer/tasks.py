import json
import re
from datetime import timedelta
import pandas as pd
from jinja2 import Template
import requests
from celery import shared_task
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from INSAI.utils import SSLAdapter, get_api_token_from_passwords
from agency.models import AgencyTransferServiceAuthorization, AgencyPasswords
from agencyusers.models import Users
from cookie.tasks import update_neova_cookies
from database.models import TransferServiceConfiguration
import datetime
from transfer.bereket import update_bereket_card_info_from_excel, fetch_bereket_excel_with_playwright
from transfer.hdi_katilim import fetch_card_info_hdi_katilim
from transfer.models import TransferLog
from transfer.neova import fetch_neova_excel_with_playwright, update_neova_card_info_from_excel


def split_date_range(start_date, end_date, days=3):
    ranges = []
    current = start_date
    while current <= end_date:
        next_date = min(current + timedelta(days=days - 1), end_date)
        ranges.append((current, next_date))
        current = next_date + timedelta(days=1)
    return ranges

@shared_task
def run_transfer_service_task(agency_id, company_id, service_config_id, start_date, end_date, source="celery", user_id=None):
    from transfer.views import run_transfer_service_controller  # 👈 circular import fix burada

    try:
        service_config = TransferServiceConfiguration.objects.get(id=service_config_id)
        user = Users.objects.get(id=user_id) if user_id else None

        # 🛑 DEBUG: Kullanıcı ve acente kontrolü
        print(f"🧪 [DEBUG] TASK BAŞLADI — agency_id={agency_id}, user_id={user_id}, user.agency_id={getattr(user, 'agency_id', 'N/A')}, company_id={company_id}, service_id={service_config_id}")

        print(f"🧪 [DEBUG] TASK BAŞLADI — agency_id={agency_id}, user_id={user_id}")
        # 🔒 Tenant isolation kontrolü
        if user and user.agency_id != agency_id:
            print(f"👤 user.agency_id={user.agency_id}, user.username={user.username}")
            raise Exception(f"⛔ Kullanıcı ile acente eşleşmiyor! user.agency_id={user.agency_id}, agency_id={agency_id}")

        return run_transfer_service_controller(
            agency_id=agency_id,
            company_id=company_id,
            service_config=service_config,
            start_date=datetime.datetime.strptime(start_date, "%Y-%m-%d").date(),
            end_date=datetime.datetime.strptime(end_date, "%Y-%m-%d").date(),
            source=source,
            user=user
        )
    except Exception as e:
        print(f"❌ [ERROR] run_transfer_service_task: {e}")
        return {"success": False, "error": str(e)}

@login_required
def run_all_transfer_sliced(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Geçersiz istek."})

    try:
        data = json.loads(request.body)
        agency_id = request.user.agency_id
        user_id = request.user.id

        start_date = datetime.datetime.strptime(data.get("start_date"), "%d/%m/%Y").date()
        end_date = datetime.datetime.strptime(data.get("end_date"), "%d/%m/%Y").date()

        if (end_date - start_date).days > 30:
            return JsonResponse({"success": False, "error": "Tarih aralığı 30 günden fazla olamaz."})

        date_blocks = split_date_range(start_date, end_date, days=3)

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
                    start_date=str(start),
                    end_date=str(end),
                    source="manual",
                    user_id=user_id
                )

        return JsonResponse({"success": True, "message": f"Tüm servisler sıraya alındı ({len(date_blocks)} blok × {auths.count()} şirket)."})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@shared_task
def run_hourly_transfers():
    from transfer.tasks import run_transfer_service_task, run_post_transfer_services_task
    from transfer.models import TransferLog
    from agency.models import AgencyTransferServiceAuthorization
    import datetime

    print("⏰ [TASK] run_hourly_transfers tetiklendi...")

    today = datetime.date.today()

    auths = AgencyTransferServiceAuthorization.objects.filter(
        is_active=True,
        transfer_service__is_active=True,
        transfer_service__detail_service__isnull=True
    ).select_related("transfer_service", "transfer_service__insurance_company")

    for auth in auths:
        agency_id = auth.agency_id
        service = auth.transfer_service
        company_id = service.insurance_company_id

        # ✅ Önce transfer task'ini sıraya al
        result = run_transfer_service_task.apply_async(
            kwargs={
                "agency_id": agency_id,
                "company_id": company_id,
                "service_config_id": service.id,
                "start_date": str(today),
                "end_date": str(today),
                "source": "auto",
                "user_id": None
            }
        )

        # ✅ TransferLog henüz oluşmadığı için post-process task’i 5 dakika sonra tetikle
        # log filtrelemesi zaman alacağından gecikmeli yapılır (ETA veya countdown ile)
        run_post_transfer_services_task.apply_async(
            args=[agency_id, company_id],
            countdown=300  # 5 dakika sonra çalıştır
        )


@shared_task
def run_post_transfer_services_task(agency_id, company_id):
    from transfer.models import TransferLog
    from transfer.views import run_post_transfer_services  # senin yukarıda verdiğin fonksiyon

    try:
        last_log = TransferLog.objects.filter(
            agency_id=agency_id,
            company_id=company_id,
            source="auto",
            success=True
        ).order_by("-finished_at").first()

        if last_log:
            print(f"📌 Post-process başlatılıyor → Agency: {agency_id}, Company: {company_id}, LogID: {last_log.id}")
            run_post_transfer_services(agency_id, company_id, last_log)
        else:
            print(f"⚠️ Uygun log kaydı bulunamadı → Agency: {agency_id}, Company: {company_id}")

    except Exception as e:
        print(f"❌ run_post_transfer_services_task hata: {e}")

@shared_task(bind=True, name="run_bereket_card_info_task")
def run_bereket_card_info_task(self, agency_id, service_id, start_date_str, end_date_str, is_retry=False):
    from cookie.tasks import update_bereket_cookies
    import datetime
    import re
    from io import BytesIO

    print("🚀 [Celery] Bereket kart task başladı...")

    try:
        update_bereket_cookies(agency_id)
        print("🔑 [Bereket] Cookie güncellendi.")
    except Exception as e:
        print(f"❌ [Bereket] Cookie güncellenemedi: {e}")
        if not is_retry:
            return run_bereket_card_info_task.apply_async(
                args=[agency_id, service_id, start_date_str, end_date_str],
                kwargs={"is_retry": True},
                countdown=10
            )
        return

    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

    try:
        config = TransferServiceConfiguration.objects.get(id=service_id)
        password = AgencyPasswords.objects.get(
            agency_id=agency_id,
            insurance_company=config.insurance_company
        )

        cookie_string = password.cookie.strip() if password.cookie else ""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_string
        }

        submit_template = Template(config.submit_ajax_template or "")
        submit_ajax_value = submit_template.render(
            baslangicTarihi=start_date.strftime("%d.%m.%Y"),
            bitisTarihi=end_date.strftime("%d.%m.%Y")
        )

        payload = {
            "cboDynParam389_Value": "1",
            "cboDynParam389": "Giriş Tarihi",
            "cboDynParam389_SelIndex": "0",
            "cboDynParam390_Value": "5",
            "cboDynParam390": "Tümü",
            "cboDynParam390_SelIndex": "5",
            "cboDynParam701_Value": "G",
            "cboDynParam701": "Güncel",
            "cboDynParam701_SelIndex": "0",
            "dtDynParam5": start_date.strftime("%d.%m.%Y"),
            "dtDynParam6": end_date.strftime("%d.%m.%Y"),
            "cboDynParam490_SelIndex": "0",
            "cboDynParam491_SelIndex": "0",
            "cboDynParam492_Value": "34001722",
            "cboDynParam492": "34001722 ARMOR KATILIM SİGORTA VE REASÜRANS BROKERLİĞİ ANON",
            "cboDynParam492_SelIndex": "0",
            "radDynParam255_Group": "ctl44",
            "radDynParam30_Group": "ctl46",
            "__EVENTTARGET": "ctl00$smCoolite",
            "__EVENTARGUMENT": "-|public|GetReport",
            "__VIEWSTATE": config.viewstate,
            "__EVENTVALIDATION": config.eventvalidation,
            "__CooliteAjaxEventMarker": "delta=true",
            "submitAjaxEventConfig": submit_ajax_value,
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(config.url, headers=headers, data=payload, timeout=60)

        print(f"📦 [Bereket API] Status: {response.status_code}")
        print(f"📄 Yanıt: {response.text[:500]}...")

        match = re.search(r'Output/[\w\-]+\.xlsx', response.text)
        if not match:
            print("❌ XLSX yolu bulunamadı")
            return

        xlsx_path = match.group(0)
        xlsx_data = fetch_bereket_excel_with_playwright(xlsx_path, password)

        if not xlsx_data:
            print("⚠️ XLSX indirilemedi")
            return

        print("✅ XLSX başarıyla alındı, işleniyor...")

        # Kayıtları güncelle ve logla
        updated_count, read_count = update_bereket_card_info_from_excel(xlsx_data, agency_id)

        print("\n📋 Güncellenen Poliçeler:")
        df = pd.read_excel(BytesIO(xlsx_data), header=None)
        for i, row in df.iterrows():
            if i == 0:
                continue
            poliseno = str(row[2]).strip()
            zeyil = str(row[3]).strip() if pd.notna(row[3]) else "0"
            borclu = str(row[7]).strip() if pd.notna(row[7]) else ""
            kartno = str(row[9]).strip() if pd.notna(row[9]) else ""
            if poliseno and kartno:
                print(f"🧾 {poliseno} - Zeyil {zeyil} - {borclu} - {kartno}")

        print(f"\n🎯 Tamamlandı → Toplam okunan: {read_count} / Güncellenen: {updated_count}")

    except Exception as e:
        print(f"❌ [Bereket Card Task] Hata: {e}")
        raise self.retry(exc=e, countdown=30, max_retries=3)


@shared_task(bind=True, name="run_neova_card_info_task")
def run_neova_card_info_task(self, agency_id, service_id, start_date_str, end_date_str):
    print("🚀 [Celery] Neova kart task başladı...")

    try:
        update_neova_cookies(agency_id)
        print("🔑 [Neova] Cookie başarıyla güncellendi.")
    except Exception as e:
        print(f"❌ [Neova] Cookie güncellenemedi: {e}")
        return

    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")

    def fetch_and_process(config, password, is_retry=False):
        cookie_string = password.cookie.strip() if password.cookie else ""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie_string
        }

        submit_template = Template(config.submit_ajax_template or "")
        submit_ajax_value = submit_template.render(
            baslangicTarihi=start_date.strftime("%d.%m.%Y"),
            bitisTarihi=end_date.strftime("%d.%m.%Y")
        )

        payload = {
            "cboDynParam389_Value": "1",
            "cboDynParam389": "Giriş Tarihi",
            "cboDynParam389_SelIndex": "0",
            "dtDynParam5": start_date.strftime("%d.%m.%Y"),
            "dtDynParam6": end_date.strftime("%d.%m.%Y"),
            "cboDynParam490_Value": "14",
            "cboDynParam490": "14 İSTANBUL ANADOLU BÖLGE",
            "cboDynParam490_SelIndex": "0",
            "cboDynParam491_Value": "5",
            "cboDynParam491": "5 BROKER",
            "cboDynParam491_SelIndex": "0",
            "cboDynParam492_Value": "0534073",
            "cboDynParam492": "0534073 ARMOR KATILIM SİGORTA VE REASÜRANS BROKERLİĞİ A.Ş.-",
            "cboDynParam492_SelIndex": "0",
            "cboDynParam390_Value": "5",
            "cboDynParam390": "Tümü",
            "cboDynParam390_SelIndex": "4",
            "radDynParam255_Group": "ctl28",
            "radDynParam30_Group": "ctl30",
            "__EVENTTARGET": "ctl00$smCoolite",
            "__EVENTARGUMENT": "-|public|GetReport",
            "__VIEWSTATE": config.viewstate,
            "__EVENTVALIDATION": config.eventvalidation,
            "__CooliteAjaxEventMarker": "delta=true",
            "submitAjaxEventConfig": submit_ajax_value
        }

        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(config.url, headers=headers, data=payload, timeout=240)

        print(f"📦 [Neova API] Status: {response.status_code}")
        print(f"📄 Yanıt Önizleme:\n{response.text[:500]}")

        match = re.search(r'Output/[\w\-]+\.xlsx', response.text)
        if not match:
            print("❌ XLSX dosya yolu bulunamadı.")
            return False

        xlsx_path = match.group(0)
        xlsx_data = fetch_neova_excel_with_playwright(xlsx_path, password)

        if xlsx_data:
            print("✅ XLSX veri başarıyla alındı")
            updated_count, read_count = update_neova_card_info_from_excel(xlsx_data, agency_id)
            if updated_count == 0 and read_count == 0 and not is_retry:
                print("🔁 Hiç geçerli veri yok → tekrar deneniyor...")
                fetch_and_process(config, password, is_retry=True)
        else:
            print("⚠️ XLSX veri alınamadı")

        return True

    try:
        config = TransferServiceConfiguration.objects.get(id=service_id)
        password = AgencyPasswords.objects.get(
            agency_id=agency_id,
            insurance_company=config.insurance_company
        )

        fetch_and_process(config, password)
        return "OK"

    except Exception as e:
        print(f"❌ [Neova Card Task] Hata: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


@shared_task
def fetch_card_info_hdi_katilim_task(agency_id, company_id, start_date_str, end_date_str, password_id=None, token=None, log_id=None):

    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

    # Şifre bilgisi
    password = AgencyPasswords.objects.filter(id=password_id).first() if password_id else \
               AgencyPasswords.objects.filter(agency_id=agency_id, insurance_company_id=company_id).first()

    if not password:
        print("❌ Şifre bilgisi bulunamadı")
        return

    # Token yoksa yeniden al
    if not token:
        token = get_api_token_from_passwords(password)
        if not token:
            print("❌ Token alınamadı")
            return

    # Log nesnesi
    log = TransferLog.objects.filter(id=log_id).first() if log_id else None

    fetch_card_info_hdi_katilim(
        agency_id=agency_id,
        company_id=company_id,
        password=password,
        start_date=start_date,
        end_date=end_date,
        token=token,
        log=log
    )

