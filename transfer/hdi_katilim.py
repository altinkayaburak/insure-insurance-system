import json
from decimal import Decimal
from django.utils import timezone
import requests
import xmltodict
from jinja2 import Template

from INSAI.utils import apply_company_field_mapping, normalize_decimal, get_by_path, create_or_update_customer_generic, \
    parse_date, get_api_token_from_passwords
from database.models import CompanyFieldMapping, Policy, Customer, Collection, PaymentPlan, AssetHome, AssetCars, \
    PolicyAssetRelation, TransferServiceConfiguration

from transfer.models import TransferLogDetail, CurrencyMapping



def transfer_hdi_katilim(
    agency_id,
    company_id,
    service_config,
    password,
    start_date,
    end_date,
    batch_id=None,
    log=None
):
    from transfer.tasks import fetch_card_info_hdi_katilim_task

    print(f"📅 [HDI] Servise gönderilen tarih aralığı → {start_date} → {end_date}")
    created_count = 0
    updated_count = 0
    skipped_count = 0
    total_cars = 0
    total_homes = 0

    print("🚢 [HDI Katılım] Transfer işlemi başlatıldı")

    try:
        context = {
            "baslangicTarihi": start_date.strftime("%Y%m%d"),
            "bitisTarihi": end_date.strftime("%Y%m%d"),
        }

        token = get_api_token_from_passwords(password)
        print(f"🔐 Token sonucu: {token[:20]}..." if token else "❌ Token alınamadı.")
        if not token:
            if log:
                log.success = False
                log.error_message = "Token alınamadı"
                log.save()
            return

        template = Template(service_config.request_template or "")
        request_body = template.render(matched_data=context)
        full_url = f"{service_config.url}?{request_body}"

        print("📤 [HDI] 1. servis isteği atılıyor...")
        print("🔗 İstek URL:", full_url)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": service_config.content_type or "application/x-www-form-urlencoded"
        }

        response = requests.post(full_url, headers=headers, timeout=30)
        print(f"📥 HTTP Durum: {response.status_code}")
        print(f"📥 Yanıt ilk 500 karakter:\n{response.text[:500]}")

        if response.status_code != 200:
            print("❌ Servis yanıtı başarısız.")
            if log:
                log.success = False
                log.error_message = f"HTTP {response.status_code}"
                log.response_received = True
                log.request_sent = True
                log.save()
            return

        decoded_text = response.content.decode("iso-8859-9")
        with open("transfer/hdi_response.xml", "wb") as f:
            f.write(response.content)

        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_config.id,
            is_active=True
        ).select_related("key", "parameter")

        customer_summary = process_customers_from_policy_list(
            decoded_text,
            mapping_qs,
            agency_id,
            company_id,
            service_config,
            log=log
        )
        customer_total = customer_summary.get("total", 0)
        print(f"📦 Toplam POLİÇE sayısı: {customer_total}")

        parsed_dict = xmltodict.parse(decoded_text)
        policy_list = get_by_path(parsed_dict, "POLİÇELER.POLİÇE") or []

        if isinstance(policy_list, dict):
            policy_list = [policy_list]

        print(f"🔎 Toplam {len(policy_list)} poliçe bulundu")

        for police_data in policy_list:
            mapped = apply_company_field_mapping(police_data, mapping_qs)

            ettiren_tc = mapped.get("SigortaEttirenKimlikNo") or mapped.get("SigortaEttirenVergiKimlikNo")
            sigortali_tc = mapped.get("SigortaliKimlikNo") or mapped.get("SigortaliVergiKimlikNo")

            customer = Customer.objects.filter(identity_number=ettiren_tc, agency_id=agency_id).first()
            insured = Customer.objects.filter(identity_number=sigortali_tc, agency_id=agency_id).first()

            print(f"🧾 Müşteri eşleşmesi: Ettiren: {ettiren_tc} → {bool(customer)} | Sigortalı: {sigortali_tc} → {bool(insured)}")

            if not customer and not insured:
                print(f"⚠️ Müşteri bulunamadı → Ettiren: {ettiren_tc} | Sigortalı: {sigortali_tc}")
                skipped_count += 1
                continue

            result = create_policy_hdi_katilim(
                mapped,
                agency_id,
                company_id,
                customer or insured,
                insured or customer,
                police_data,
                log=log,
                service_id=service_config.id
            )

            policy_obj = result.get("policy") if result else None
            is_created = result.get("created", False)
            car_created = result.get("car_created", False)
            home_created = result.get("home_created", False)

            if not policy_obj:
                print("⚠️ Poliçe oluşturulamadı.")
                skipped_count += 1
                continue

            create_collection_hdi_katilim(
                policy=policy_obj,
                response_data=police_data,
                company_id=company_id,
                service_id=service_config.id
            )

            create_payment_plan_hdi_katilim(police_data, policy_obj, agency_id)

            if is_created:
                created_count += 1
            else:
                updated_count += 1

            if car_created:
                total_cars += 1
            if home_created:
                total_homes += 1

        # 📤 Tahsilat servisini asenkron başlat
        fetch_card_info_hdi_katilim_task.delay(
            agency_id=agency_id,
            company_id=company_id,
            start_date_str=start_date.strftime("%Y-%m-%d"),
            end_date_str=end_date.strftime("%Y-%m-%d"),
            password_id=password.id,
            token=token,
            log_id=log.id if log else None
        )

        if log:
            log.success = True
            log.request_sent = True
            log.response_received = True
            log.finished_at = timezone.now()
            if log.started_at:
                log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())

            log.customers_created += customer_total
            log.created_count = created_count
            log.updated_count = updated_count
            log.skipped_count = skipped_count
            log.cars_created = total_cars
            log.homes_created = total_homes

            log.save(update_fields=[
                "success", "request_sent", "response_received", "finished_at",
                "duration_seconds", "customers_created", "created_count", "updated_count",
                "skipped_count", "cars_created", "homes_created"
            ])

        return {
            "success": True,
            "message": f"{created_count + updated_count} kayıt işlendi",
            "total": created_count + updated_count + skipped_count,
            "customers_created": customer_total,
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "cars_created": total_cars,
            "homes_created": total_homes,
        }

    except Exception as e:
        print(f"❌ Genel hata: {e}")
        if log:
            log.success = False
            log.error_message = str(e)
            log.finished_at = timezone.now()
            if log.started_at:
                log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())
            log.save()
        return None





def process_customers_from_policy_list(response_text, mapping_qs, agency_id, company_id, service_config, log=None):
    parsed = xmltodict.parse(response_text)
    policy_list = get_by_path(parsed, "POLİÇELER.POLİÇE") or []

    if isinstance(policy_list, dict):
        policy_list = [policy_list]

    print(f"📦 Toplam POLİÇE sayısı: {len(policy_list)}")

    created_count = 0
    updated_count = 0

    for p_data in policy_list:
        mapped = apply_company_field_mapping(p_data, mapping_qs)

        ettiren_tc = mapped.get("SigortaEttirenKimlikNo")
        if not ettiren_tc or ettiren_tc == "0":
            ettiren_tc = mapped.get("SigortaEttirenVergiKimlikNo")

        sigortali_tc = mapped.get("SigortaliKimlikNo")
        if not sigortali_tc or sigortali_tc == "0":
            sigortali_tc = mapped.get("SigortaliVergiKimlikNo")
        print(f"🧾 Ettiren TC: {ettiren_tc} | Sigortalı TC: {sigortali_tc}")

        musteri_listesi = []

        if ettiren_tc and ettiren_tc != "0":
            musteri_listesi.append({
                "identity_number": ettiren_tc,
                "birth_date": mapped.get("SigortaEttirenDogumTarihi"),
                "full_name": mapped.get("SigortaEttirenAdi"),
                "SigortaEttirenCepTelefonu": mapped.get("SigortaEttirenCepTelefonu"),
            })

        if sigortali_tc and sigortali_tc != ettiren_tc and sigortali_tc != "0":
            musteri_listesi.append({
                "identity_number": sigortali_tc,
                "birth_date": mapped.get("SigortaliDogumTarihi"),
                "full_name": mapped.get("SigortaliAdi"),
                "SigortaliCepTelefonu": mapped.get("SigortaliCepTelefonu"),
            })

        print(f"📥 Kayıt edilecek müşteri sayısı: {len(musteri_listesi)}")

        if musteri_listesi:
            created_ids = create_or_update_customer_generic(agency_id, musteri_listesi) or []

            for tc in created_ids:
                exists = Customer.objects.filter(identity_number=tc, agency_id=agency_id).exists()
                if exists:
                    updated_count += 1
                else:
                    created_count += 1

                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=p_data.get("PoliceNumarası") or "UNKNOWN",
                        status="created",
                        record_type="customer",
                        customer_identity_number=tc,
                        data_source="main",
                        message="Müşteri kaydedildi"
                    )

    print(f"✅ Toplam müşteri → Yeni: {created_count}, Güncellenen: {updated_count}")
    return {
        "created": created_count,
        "updated": updated_count,
        "total": created_count + updated_count
    }



def create_policy_hdi_katilim(mapped, agency_id, company_id, customer, insured, police_data, log=None, service_id=None):
    print("📥 [HDI] Poliçe kaydı başlatıldı")

    valid_fields = {f.name for f in Policy._meta.get_fields()}
    cleaned = {}

    for k, v in mapped.items():
        if k in valid_fields:
            if k == "SirketUrunNo" and isinstance(v, str):
                v = v.split("_")[0]
            if isinstance(v, str) and ("tarih" in k.lower() or "date" in k.lower()):
                cleaned[k] = parse_date(v)
            else:
                cleaned[k] = v

    cleaned["agency_id"] = agency_id
    cleaned["company_id"] = company_id

    if not customer:
        print("❌ [HDI] Customer bilgisi yok, kayıt atlandı.")
        return {"policy": None, "created": False, "car_created": False, "home_created": False}

    cleaned["customer_id"] = customer.id
    cleaned["insured_id"] = insured.id if insured else customer.id

    police_no = cleaned.get("PoliceNo")
    zeyil_no = cleaned.get("ZeyilNo") or "0"
    yenileme_no = cleaned.get("YenilemeNo") or "0"

    if not police_no:
        print("❌ [HDI] PoliceNo yok, kayıt yapılamaz.")
        return {"policy": None, "created": False, "car_created": False, "home_created": False}

    cleaned["ZeyilNo"] = str(zeyil_no)
    cleaned["YenilemeNo"] = str(yenileme_no)
    cleaned["PoliceAnaKey"] = f"{police_no}-{yenileme_no}"

    print(f"📌 [HDI] AnaKey: {cleaned['PoliceAnaKey']}")

    iptal_durumu = str(mapped.get("iptal")).strip().upper()
    print(f"🔎 [HDI] İptal durumu: {iptal_durumu}")

    if iptal_durumu == "E":
        cleaned["PolicyStatus_id"] = 222
        cleaned["AktifMi"] = "0"
        print(f"🚫 [HDI] İptal poliçe → {cleaned['PoliceAnaKey']}")

        Policy.objects.filter(
            PoliceAnaKey=cleaned["PoliceAnaKey"],
            agency_id=agency_id,
            AktifMi="1"
        ).exclude(
            PoliceNo=police_no,
            ZeyilNo=zeyil_no
        ).update(
            AktifMi="0",
            updated_at=timezone.now()
        )

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=cleaned["PoliceAnaKey"],
                status="cancelled",
                message="İptal poliçe. Önceki kayıtlar pasife çekildi.",
                record_type="policy",
                data_source="hdi"
            )
    else:
        cleaned["PolicyStatus_id"] = 221
        cleaned["AktifMi"] = "1"
        print(f"✅ [HDI] Aktif poliçe → {cleaned['PoliceAnaKey']}")

    policy, created = Policy.objects.update_or_create(
        PoliceNo=police_no,
        ZeyilNo=zeyil_no,
        YenilemeNo=yenileme_no,
        agency_id=agency_id,
        defaults=cleaned
    )

    print(f"{'🆕' if created else '♻️'} [HDI] Poliçe işlendi: {policy.PoliceNoKombine}")

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy.PoliceNoKombine,
            status="created" if created else "updated",
            message="HDI poliçe kaydı başarılı",
            record_type="policy",
            policy=policy,
            customer_identity_number=customer.identity_number,
            data_source="hdi"
        )

    # ✅ Varlık sayımı
    car_created = create_asset_car_hdi_katilim(police_data, policy, agency_id, company_id, service_id, log=log)
    home_created = create_asset_home_hdi(police_data, policy, agency_id, company_id, service_id, log=log)

    return {
        "policy": policy,
        "created": created,
        "car_created": car_created,
        "home_created": home_created
    }


def create_collection_hdi_katilim(*, policy, response_data, company_id, service_id):
    if not policy:
        print("❌ [HDI] Policy nesnesi yok, collection atlandı.")
        return None

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key")

    mapped = apply_company_field_mapping(response_data, mapping_qs)

    if "DovizKuru" not in mapped or mapped.get("DovizKuru") in [None, ""]:
        raw_kur = get_by_path(response_data, "DÖVİZ.DövizKuru")
        if raw_kur:
            mapped["DovizKuru"] = normalize_decimal(raw_kur)
            print(f"💱 [PATCH] Döviz kuru doğrudan alındı: {raw_kur}")
        else:
            print("⚠️ [PATCH] Döviz kuru doğrudan da alınamadı")

    # 💱 Döviz tipi mapping
    doviz = None
    raw_doviz = mapped.get("DovizCinsi")
    if raw_doviz:
        doviz = CurrencyMapping.objects.filter(
            company_id=company_id,
            raw_value=str(raw_doviz).strip()
        ).values_list("currency_code", flat=True).first()
        if doviz:
            print(f"💱 Döviz eşleşti: {raw_doviz} → {doviz}")
            mapped["DovizCinsi"] = doviz
        else:
            print(f"⚠️ Döviz eşleşmedi: {raw_doviz}")

    # 🧾 İptal kontrolü (H = iptal değil → aktif, E = iptal)
    iptal_durumu = (mapped.get("SonDurum") or "").strip().upper()
    is_iptal = iptal_durumu == "E"

    # 🔢 Alanlar
    decimal_fields = [
        "BrutPrim", "NetPrim", "Komisyon",
        "BrutPrimTL", "NetPrimTL", "KomisyonPrimTL",
        "ZeyilKomisyonu", "EkKomisyon", "GHP",
        "GiderVergisi", "THGF", "YSV", "SGKPayi"
    ]
    data = {}

    for field in decimal_fields:
        val = mapped.get(field)
        norm = normalize_decimal(val)

        if is_iptal and norm is not None:
            print(f"➖ [İptal] {field} negatifleniyor → {norm} → {-norm}")
            norm *= -1

        data[field] = norm

    data["DovizKuru"] = normalize_decimal(mapped.get("DovizKuru"))

    # 💱 TL değerlerini kur ile hesapla
    try:
        kur = data.get("DovizKuru") or Decimal("1.00")
        for ana, tl in [("BrutPrim", "BrutPrimTL"), ("NetPrim", "NetPrimTL"), ("Komisyon", "KomisyonPrimTL")]:
            if data.get(ana) is not None:
                data[tl] = round(data[ana] * kur, 2)
                print(f"💱 {tl} = {ana} * {kur} → {data[tl]}")
    except Exception as e:
        print(f"⚠️ TL hesaplama hatası: {e}")

    # 📌 Diğer alanlar
    data.update({
        "DovizCinsi": doviz,
        "TaksitSayisi": mapped.get("TaksitSayisi"),
        "PoliceNoKombine": policy.PoliceNoKombine,
        "agency_id": policy.agency_id,
        "customer_id": policy.customer_id,
        "insured_id": policy.insured_id or policy.customer_id,
        "policy_id": policy.id
    })

    obj, created = Collection.objects.update_or_create(
        PoliceNoKombine=policy.PoliceNoKombine,
        policy=policy,
        defaults=data
    )
    obj.save()
    print(f"{'🆕' if created else '♻️'} [HDI] Collection kaydı → {obj}")
    return obj


def create_payment_plan_hdi_katilim(police_data, policy_obj, agency_id):
    try:
        print("📥 [HDI] Ödeme Planı - İşleniyor...")

        payment_list = get_by_path(police_data, "TAKSİTLER.TAKSİT") or []
        if isinstance(payment_list, dict):
            payment_list = [payment_list]

        print(f"📊 [HDI] Bulunan taksit sayısı: {len(payment_list)}")

        # 🔁 Eski kayıtları sil
        PaymentPlan.objects.filter(policy=policy_obj).delete()
        print("🧹 [HDI] Eski taksit kayıtları silindi.")

        taksit_objs = []
        for idx, item in enumerate(payment_list, start=1):
            tutar_raw = item.get("Tutar")
            vade_raw = item.get("VadeTarihi")

            try:
                tutar = Decimal(str(tutar_raw).replace(",", "."))
            except:
                print(f"⚠️ Tutar hatalı: {tutar_raw}")
                continue

            vade = parse_date(vade_raw)
            if not vade:
                print(f"⚠️ Geçersiz vade tarihi: {vade_raw}")
                continue

            taksit_objs.append(PaymentPlan(
                policy=policy_obj,
                agency=policy_obj.agency,
                PoliceNoKombine=policy_obj.PoliceNoKombine,
                TaksitSirasi=str(idx),
                TaksitVadeTarihi=vade,
                TaksitTutar=tutar
            ))

        PaymentPlan.objects.bulk_create(taksit_objs)
        print(f"✅ [HDI] {len(taksit_objs)} ödeme planı kaydı eklendi.")

        # ♻️ Collection güncellemesi: taksit sayısı ve KKBlokeli
        collection = Collection.objects.filter(policy=policy_obj).first()
        if collection:
            collection.TaksitSayisi = len(taksit_objs)

            odeme_turu = get_by_path(police_data, "TAKSİTLER.OdemeTuru")
            collection.KKBlokeli = str(odeme_turu).strip() == "1"

            collection.save()
            print(f"♻️ [HDI] Collection güncellendi: TaksitSayisi={len(taksit_objs)}, KKBlokeli={collection.KKBlokeli}")

    except Exception as e:
        print(f"❌ [HDI] Ödeme planı işlenirken hata: {e}")

def create_asset_home_hdi(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🏠 [HDI] Konut Varlık → Kayıt başlatıldı")

    try:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_id,
            is_active=True
        ).select_related("key", "parameter")

        mapped_data = apply_company_field_mapping(police_data, mapping_qs)
        insured = policy_obj.insured
        uavt_code = mapped_data.get("RizikoUavtKod")

        if not insured or not uavt_code:
            print("⚠️ Sigortalı veya UAVT kodu eksik, kayıt atlandı.")
            return

        lookup = {
            "insured": insured,
            "agency": policy_obj.agency,
            "RizikoUavtKod": uavt_code
        }

        valid_fields = {f.name for f in AssetHome._meta.get_fields()}
        home_data = {
            k: v for k, v in mapped_data.items() if k in valid_fields
        }

        home_data.update({
            "policy": policy_obj,
            "agency": policy_obj.agency,
            "PoliceNoKombine": policy_obj.PoliceNoKombine,
            "AktifMi": True,
            "RizikoUavtKod": uavt_code
        })

        obj, created = AssetHome.objects.update_or_create(
            **lookup,
            defaults=home_data
        )

        if created:
            obj.is_verified = False
            obj.save(update_fields=["is_verified"])

            PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_home=obj)

        print(f"{'➕' if created else '♻️'} [HDI] Konut varlığı kaydedildi → {obj.PoliceNoKombine}")

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_home",
                data_source="hdi",
                message="Konut varlık kaydedildi"
            )

        return created

    except Exception as e:
        print(f"❌ [HDI] create_asset_home_hdi exception → {e}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine if policy_obj else "UNKNOWN",
                status="failed",
                record_type="asset_home",
                data_source="hdi",
                message=str(e)[:1000]
            )
        return False
    return False

def create_asset_car_hdi_katilim(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚗 [HDI Araç] Varlık kaydı başlatıldı...")

    try:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_id,
            is_active=True
        ).select_related("key", "parameter")

        mapped_data = apply_company_field_mapping(police_data, mapping_qs)
        insured = policy_obj.insured
        sasi_no = mapped_data.get("AracSasiNo")
        plaka_raw = mapped_data.get("AracPlakaTam", "")
        plaka = plaka_raw.replace(" ", "").upper() if plaka_raw else None

        if not insured or not sasi_no:
            print("⚠️ Sigortalı veya şasi numarası eksik, kayıt atlandı.")
            return False

        lookup = {
            "insured": insured,
            "agency": policy_obj.agency,
            "AracSasiNo": sasi_no
        }

        valid_fields = {f.name for f in AssetCars._meta.get_fields()}
        asset_data = {
            k: v for k, v in mapped_data.items() if k in valid_fields
        }

        asset_data.update({
            "policy": policy_obj,
            "agency": policy_obj.agency,
            "PoliceNoKombine": policy_obj.PoliceNoKombine,
            "AktifMi": True,
            "AracPlakaTam": plaka,
        })

        # Plaka alt detayları
        if plaka and (not asset_data.get("AracPlakailKodu") or not asset_data.get("AracPlakaNo")):
            plaka_digits = ''.join(filter(str.isdigit, plaka[:3])) or "00"
            asset_data["AracPlakailKodu"] = plaka_digits.zfill(2)
            asset_data["AracPlakaNo"] = plaka[3:]

        obj, created = AssetCars.objects.update_or_create(
            **lookup,
            defaults=asset_data
        )

        if created:
            obj.is_verified = False
            obj.save(update_fields=["is_verified"])

            PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_car=obj)

        print(f"{'➕' if created else '♻️'} [HDI Araç] Kayıt → {obj.AracPlakaTam or sasi_no}")

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_car",
                data_source="hdi",
                message="Araç varlık kaydedildi"
            )

        return created

    except Exception as e:
        print(f"❌ create_asset_car_hdi_katilim exception → {e}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine if policy_obj else "UNKNOWN",
                status="failed",
                record_type="asset_car",
                data_source="hdi",
                message=str(e)[:1000]
            )
        return False
    return False


def fetch_card_info_hdi_katilim(
    agency_id,
    company_id,
    password,
    start_date,
    end_date,
    token,
    log=None
):

    print("💳 [HDI Kart] Tahsilat bilgileri alınıyor...")

    try:
        service_config = TransferServiceConfiguration.objects.get(id=57)

        query_string = Template(service_config.request_template or "").render(
            web_username=password.web_username,
            web_password=password.web_password,
            baslangicTarihi=start_date.strftime("%Y%m%d"),
            bitisTarihi=end_date.strftime("%Y%m%d")
        )

        url = service_config.url.strip()
        if not url.startswith("http"):
            url = f"https://{url}"

        full_url = f"{url}?{query_string}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": service_config.content_type or "application/json"
        }

        print("🔗 İstek atılıyor →", full_url)
        response = requests.post(full_url, headers=headers, timeout=30)
        print(f"📥 HTTP Durum: {response.status_code}")

        if response.status_code != 200:
            print("❌ Yanıt başarısız.")
            return

        decoded_text = response.content.decode("iso-8859-9")
        parsed = xmltodict.parse(decoded_text)
        tahsil_list = get_by_path(parsed, "TAHSILATLAR.TAHSIL") or []

        if isinstance(tahsil_list, dict):
            tahsil_list = [tahsil_list]

        print(f"🔍 {len(tahsil_list)} tahsilat kaydı bulundu.")

        updated_count = 0

        for tahsil in tahsil_list:
            police_no = tahsil.get("PoliceNo")
            zeyil_no = tahsil.get("ZeylNo") or "0"
            yenileme_no = tahsil.get("YenilemeNo") or "0"
            kart_no = tahsil.get("KartNo")
            k_sahibi_ad = str(tahsil.get("KSahibiAd") or "").strip()
            k_sahibi_soy = str(tahsil.get("KSahibiSoy") or "").strip()

            policy = Policy.objects.filter(
                PoliceNo=police_no,
                ZeyilNo=zeyil_no,
                YenilemeNo=yenileme_no,
                agency_id=agency_id
            ).first()

            if not policy:
                print(f"⚠️ Policy bulunamadı: {police_no}-{zeyil_no}-{yenileme_no}")
                continue

            collection = Collection.objects.filter(policy=policy).first()
            if not collection:
                print(f"⚠️ Collection bulunamadı: policy_id={policy.id}")
                continue

            collection.KartSahibi = f"{k_sahibi_ad} {k_sahibi_soy}".strip()
            collection.KrediKartNo = kart_no
            collection.save()
            updated_count += 1

            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=policy.PoliceNoKombine,
                    record_type="collection",
                    status="updated",
                    data_source="hdi_card",
                    message="Kart bilgileri güncellendi"
                )

        print(f"✅ Güncellenen collection sayısı: {updated_count}")

    except Exception as e:
        print(f"❌ Hata: {e}")





