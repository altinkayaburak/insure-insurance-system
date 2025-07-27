import json
import re,requests,xmltodict
from decimal import Decimal
from django.utils import timezone
from jinja2 import Template

from INSAI.utils import apply_company_field_mapping, create_or_update_customer_generic
from agency.models import AgencyPasswords
from database.models import CompanyFieldMapping, Customer, Policy, Collection, PaymentPlan, AssetCars, AssetHome, \
    PolicyAssetRelation
from transfer.models import TransferLogDetail, CurrencyMapping
from transfer.views import SSLAdapter, clean_namespaces, get_by_path,\
  parse_date


def extract_uavt_from_riziko_adres(adres_str):
    if not adres_str:
        return None
    match = re.search(r"AK:\s*(\d+)", adres_str)
    return match.group(1) if match else None


def transfer_ankara(
    agency_id,
    company_id,
    service_config,
    start_date,
    end_date,
    batch_id,
    log=None,
    password=None,
    mapping_qs=None
):
    print("🚚 [Ankara] Transfer servisi başlatıldı")

    success_count = 0
    updated_count = 0
    total_customers = 0
    total_cars = 0
    total_homes = 0

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=company_id
    ).first()

    context = {
        "web_username": (password_info.web_username or "").strip(),
        "web_password": (password_info.web_password or "").strip(),
        "baslangicTarihi": start_date.strftime(service_config.date_format).strip('"'),
        "bitisTarihi": end_date.strftime(service_config.date_format).strip('"'),
    }

    try:
        soap_body = Template(service_config.soap_template).render(**context)
        print("📤 Giden SOAP Body:\n", soap_body)
    except Exception as ex:
        raise Exception(f"❌ SOAP şablon hatası: {ex}")

    headers = {"Content-Type": "text/xml; charset=utf-8"}
    if service_config.soap_action:
        headers["SOAPAction"] = service_config.soap_action

    try:
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        response = session.post(service_config.url, data=soap_body.encode("utf-8"), headers=headers, timeout=30)
        response.raise_for_status()
        print("📥 Gelen SOAP Yanıt:\n", response.text[:5000])
    except Exception as ex:
        raise Exception(f"❌ SOAP istek hatası: {ex}")

    try:
        data_dict = clean_namespaces(xmltodict.parse(response.text))
    except Exception as ex:
        raise Exception(f"❌ XML parse hatası: {ex}")

    police_list = None
    for path in (service_config.policy_list_path or "").split("|"):
        try:
            police_list = get_by_path(data_dict, path.strip())
            print("🧾 DEBUG RESPONSE:", json.dumps(data_dict, indent=2)[:2000])
            print(f"🧪 Denenen path: {path.strip()} → {type(police_list)}")
        except Exception as ex:
            print(f"⚠️ Path kontrol hatası: {ex}")
            police_list = None

        if police_list:
            print(f"✅ Poliçe path bulundu: {path.strip()}")
            break

    if not police_list:
        raise Exception("❌ Poliçe listesi bulunamadı")

    if isinstance(police_list, dict):
        police_list = [police_list]

    police_list.sort(key=lambda x: int(get_by_path(x, "ZeyilNo") or 0))

    if mapping_qs is None:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_config.id,
            is_active=True
        ).select_related("key", "parameter")

    for police_data in police_list:
        print("🧾 --- Yeni poliçe işleniyor ---")
        mapped = apply_company_field_mapping(police_data, mapping_qs)

        insured_tc = mapped.get("SigortaliKimlikNo") or mapped.get("SigortaliVergiKimlikNo")
        ettiren_tc = mapped.get("SigortaEttirenKimlikNo") or mapped.get("SigortaEttirenVergiKimlikNo")

        customer_list = []

        if insured_tc and insured_tc != "0":
            customer_list.append({
                "identity_number": insured_tc,
                "full_name": f"{mapped.get('SigortaliAdi', '')} {mapped.get('SigortaliSoyadi', '')}".strip(),
                "birth_date": mapped.get("birth_date"),
                "SigortaliCepTelefonu": mapped.get("SigortaliCepTelefonu"),
            })

        if ettiren_tc and ettiren_tc != insured_tc and ettiren_tc != "0":
            customer_list.append({
                "identity_number": ettiren_tc,
                "full_name": f"{mapped.get('SigortaEttirenAdi', '')} {mapped.get('SigortaEttirenSoyadi', '')}".strip(),
                "SigortaEttirenCepTelefonu": mapped.get("SigortaEttirenCepTelefonu"),
            })

        if not customer_list:
            print("⚠️ Geçerli müşteri yok, atlandı.")
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no="UNKNOWN",
                    status="skipped",
                    message="Geçerli müşteri bilgisi bulunamadı"
                )
            continue

        created_ids = create_or_update_customer_generic(agency_id, customer_list)
        total_customers += len(set(created_ids))

        mapped.update({
            "SigortaEttirenKimlikNo": ettiren_tc,
            "SigortaliKimlikNo": insured_tc,
            "identity_number": ettiren_tc,
            "insured_identity_number": insured_tc
        })

        customer = Customer.objects.filter(identity_number=ettiren_tc, agency_id=agency_id).first()
        insured = Customer.objects.filter(identity_number=insured_tc, agency_id=agency_id).first()

        try:
            result = create_policy_ankara(
                mapped, agency_id, company_id, customer, insured,
                police_data, log=log, service_id=service_config.id
            )

            policy_obj = result.get("policy") if result else None
            if not policy_obj or not result.get("collection_created"):
                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=f"{mapped.get('PoliceNo')}-{mapped.get('ZeyilNo') or 0}-{mapped.get('YenilemeNo') or 0}",
                        status="failed",
                        message="Poliçe veya tahsilat oluşturulamadı",
                        record_type="policy",
                        customer_identity_number=ettiren_tc,
                        data_source="ankara"
                    )
                continue

            is_created = result.get("created", False)
            if is_created:
                success_count += 1
            else:
                updated_count += 1

            if result.get("car_created"):
                total_cars += 1
            if result.get("home_created"):
                total_homes += 1

            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=policy_obj.PoliceNoKombine,
                    status="created" if is_created else "updated",
                    message="Poliçe kaydedildi",
                    record_type="policy",
                    policy=policy_obj,
                    customer_identity_number=ettiren_tc,
                    data_source="ankara"
                )

        except Exception as ex:
            print(f"❌ Poliçe kayıt hatası: {ex}")
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=mapped.get("PoliceNo") or "UNKNOWN",
                    status="failed",
                    message=f"Poliçe kayıt hatası: {str(ex)[:500]}"
                )

    if log:
        log.created_count = success_count
        log.updated_count = updated_count
        log.customers_created = total_customers
        log.cars_created = total_cars
        log.homes_created = total_homes
        log.save(update_fields=[
            "created_count", "updated_count",
            "customers_created", "cars_created", "homes_created"
        ])

    print("✅ [Ankara] Transfer tamamlandı.")
    return {
        "success": True,
        "message": f"{len(police_list)} poliçe işlendi",
        "total": len(police_list),
        "created": success_count,
        "updated": updated_count,
        "skipped": len(police_list) - (success_count + updated_count),
        "customers_created": total_customers,
        "cars_created": total_cars,
        "homes_created": total_homes
    }




def create_policy_ankara(mapped, agency_id, company_id, customer, insured, police_data, log=None, service_id=None):
    valid_fields = {f.name for f in Policy._meta.get_fields()}
    cleaned = {}

    for k, v in mapped.items():
        if k in valid_fields:
            if isinstance(v, str) and ("tarih" in k.lower() or "date" in k.lower()):
                cleaned[k] = parse_date(v)
            else:
                cleaned[k] = v

    cleaned["agency_id"] = agency_id
    cleaned["company_id"] = company_id

    if not customer:
        print("❌ Customer nesnesi yok, poliçe kaydı atlandı.")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=mapped.get("PoliceNo") or "UNKNOWN",
                status="skipped",
                message="Customer kaydı olmadığından poliçe işlenmedi.",
                record_type="policy",
                data_source="ankara"
            )
        return {"policy": None, "collection_created": False, "created": False}

    cleaned["customer_id"] = customer.id
    cleaned["insured_id"] = insured.id if insured else customer.id

    police_no = cleaned.get("PoliceNo")
    zeyil_no = str(int(cleaned.get("ZeyilNo") or 0))
    yenileme_no = str(int(cleaned.get("YenilemeNo") or 0))
    cleaned["ZeyilNo"] = zeyil_no
    cleaned["YenilemeNo"] = yenileme_no
    cleaned["PoliceAnaKey"] = f"{police_no}-{yenileme_no}"

    if not police_no:
        print("❌ PoliceNo boş, kayıt yapılmadı.")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no="UNKNOWN",
                status="failed",
                message="PoliceNo boş olduğu için kayıt yapılmadı.",
                record_type="policy",
                data_source="ankara"
            )
        return {"policy": None, "collection_created": False, "created": False}

    iptal_durumu = mapped.get("PoliceIptalDurumu")
    if str(iptal_durumu) == "222":
        cleaned["PolicyStatus_id"] = 222
        cleaned["AktifMi"] = "0"
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
                message="İptal poliçe tespit edildi. Önceki kayıtlar pasife alındı.",
                record_type="policy",
                data_source="ankara"
            )
    else:
        cleaned["PolicyStatus_id"] = 221
        cleaned["AktifMi"] = "1"

    policy, created = Policy.objects.update_or_create(
        PoliceNo=police_no,
        ZeyilNo=zeyil_no,
        YenilemeNo=yenileme_no,
        agency_id=agency_id,
        defaults=cleaned
    )

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy.PoliceNoKombine,
            status="created" if created else "updated",
            message="Poliçe başarıyla işlendi",
            record_type="policy",
            policy=policy,
            customer_identity_number=customer.identity_number if customer else None,
            data_source="ankara"
        )

    create_collection_ankara_from_table(police_data, agency_id, policy, customer, insured, company_id)
    create_payment_plan_ankara_from_response(police_data, policy, agency_id)

    is_car_created = create_asset_car_ankara(police_data, policy, agency_id, company_id, service_id, log=log)
    is_home_created = create_asset_home_ankara(police_data, policy, agency_id, company_id, service_id, log=log)

    return {
        "policy": policy,
        "collection_created": True,
        "created": created,
        "car_created": is_car_created,
        "home_created": is_home_created
    }


def create_collection_ankara_from_table(table_row, agency_id, policy_obj, customer, insured, company_id):
    try:
        doviz_raw = table_row.get("DovizTipi", "").strip()
        currency = CurrencyMapping.objects.filter(
            company_id=company_id,
            raw_value__iexact=doviz_raw,
            is_active=True
        ).first()

        valid_fields = {f.name for f in Collection._meta.get_fields()}
        print(f"🧾 Collection model alanları: {valid_fields}")
        print(f"🧾 Gelen tablo key'leri: {list(table_row.keys())}")

        # ✅ Sayısal alanları Decimal'a dönüştür (string olarak gelenleri)
        values = {}
        decimal_fields = [
            "KomisyonTL", "BrutPrimTL", "NetPrimTL", "Komisyon", "BrutPrim", "NetPrim",
            "GiderVergisi", "YSV", "Kur"
        ]

        for field, value in table_row.items():
            if field in decimal_fields:
                try:
                    key_name = (
                        "KomisyonPrimTL" if field == "KomisyonTL"
                        else "DovizKuru" if field == "Kur"
                        else field
                    )
                    values[key_name] = Decimal(str(value).replace(",", "."))
                except Exception:
                    print(f"⚠️ {field} değeri dönüştürülemedi: {value}")
            elif field in valid_fields:
                values[field] = value  # raw değer (string, tarih vb.) olarak yaz

        # ➕ Ek zorunlu alanlar
        values.update({
            "policy": policy_obj,
            "agency_id": agency_id,
            "customer": customer,
            "insured": insured,
            "DovizCinsi": currency.currency_code if currency else None,
            "KKBlokeli": bool(int(table_row.get("SanalPos", 0))),
        })

        print(f"📦 Collection oluşturulacak değerler: {values}")

        collection, created = Collection.objects.update_or_create(
            PoliceNoKombine=policy_obj.PoliceNoKombine,
            agency_id=agency_id,
            defaults=values
        )
        collection.save()

        print(f"{'➕' if created else '♻️'} Tahsilat kaydedildi → {collection.PoliceNoKombine}")
        return collection

    except Exception as ex:
        print(f"❌ Tahsilat kayıt hatası: {ex}")
        return None


def create_payment_plan_ankara_from_response(police_data, policy_obj, agency_id):
    try:
        print("📥 [Ödeme Planı] Ankara - İşleniyor...")

        payment_list = get_by_path(police_data, "Taksitler.Taksit") or []
        if isinstance(payment_list, dict):
            payment_list = [payment_list]

        print(f"📊 [Ödeme Planı] Bulunan taksit sayısı: {len(payment_list)}")

        # 🔁 Mevcut kayıtları temizle
        PaymentPlan.objects.filter(policy=policy_obj).delete()
        print("🧹 [Ödeme Planı] Eski kayıtlar silindi.")

        payment_objs = []

        for idx, item in enumerate(payment_list, start=1):
            tutar_raw = item.get("Tutar")
            vade_raw = item.get("Tarih")

            try:
                tutar = Decimal(str(tutar_raw).replace(",", "."))
            except:
                print(f"⚠️ Tutar dönüştürülemedi: {tutar_raw}")
                continue

            vade = parse_date(vade_raw)
            if not vade:
                print(f"⚠️ Geçersiz vade tarihi: {vade_raw}")
                continue

            payment_objs.append(PaymentPlan(
                policy=policy_obj,
                agency=policy_obj.agency,
                PoliceNoKombine=policy_obj.PoliceNoKombine,
                TaksitSirasi=str(idx),
                TaksitVadeTarihi=vade,
                TaksitTutar=tutar
            ))

        PaymentPlan.objects.bulk_create(payment_objs)
        print(f"✅ [Ödeme Planı] {len(payment_objs)} kayıt eklendi.")

        # ♻️ Collection güncellemesi
        collection = Collection.objects.filter(policy=policy_obj).first()
        if collection:
            collection.TaksitSayisi = len(payment_objs)
            collection.save()  # update_fields verme → modelin save() fonksiyonu tam çalışsın
            print("♻️ [Collection] TaksitSayisi ve oranlar güncellendi.")


    except Exception as e:
        print(f"❌ [HATA] Ödeme planı yazım hatası: {e}")

def create_asset_car_ankara(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚗 [Araç Varlık] Kayıt başlatıldı...")

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

        if not insured or (not sasi_no and not plaka):
            print("⚠️ Eksik veri: sigortalı ve plaka/şase yok, kayıt atlandı")
            return False  # 🔁 Sayım için önemli

        lookup = {
            "insured": insured,
            "agency": policy_obj.agency
        }
        if sasi_no:
            lookup["AracSasiNo"] = sasi_no
        else:
            lookup["AracPlakaTam"] = plaka

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

        if plaka and (not asset_data.get("AracPlakailKodu") or not asset_data.get("AracPlakaNo")):
            asset_data["AracPlakailKodu"] = plaka[:3]
            asset_data["AracPlakaNo"] = plaka[3:]

        obj, created = AssetCars.objects.update_or_create(
            **lookup,
            defaults=asset_data
        )

        PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_car=obj)

        if created:
            obj.is_verified = False
            obj.save(update_fields=["is_verified"])

        print(f"{'➕' if created else '♻️'} Araç kaydedildi → {obj.AracPlakaTam or sasi_no}")

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_car",
                data_source="ankara",
                message="Araç varlık kaydedildi"
            )

        return created  # 🔁 Sayımda true/false döner

    except Exception as e:
        print(f"❌ create_asset_car_ankara exception → {e}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine if policy_obj else "UNKNOWN",
                status="failed",
                record_type="asset_car",
                data_source="ankara",
                message=str(e)[:1000]
            )
        return False
    return created


def create_asset_home_ankara(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🏠 [Konut Varlık] Kayıt başlatıldı...")

    try:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_id,
            is_active=True
        ).select_related("key", "parameter")

        mapped_data = apply_company_field_mapping(police_data, mapping_qs)
        insured = policy_obj.insured
        riziko_adres = get_by_path(police_data, "RizikoAdres")
        uavt_code = extract_uavt_from_riziko_adres(riziko_adres)

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

        PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_home=obj)

        if created:
            obj.is_verified = False
            obj.save(update_fields=["is_verified"])

        print(f"{'➕' if created else '♻️'} Konut varlığı kaydedildi → {obj.PoliceNoKombine}")

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_home",
                data_source="ankara",
                message="Konut varlık kaydedildi"
            )

        return created  # ✅ Eklenen satır (sayım için önemli)

    except Exception as e:
        print(f"❌ create_asset_home_ankara exception → {e}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine if policy_obj else "UNKNOWN",
                status="failed",
                record_type="asset_home",
                data_source="ankara",
                message=str(e)[:1000]
            )
        return False  # ✅ Hata durumunda False dön
    return created





