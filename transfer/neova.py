import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import pandas as pd
import requests
import xmltodict
from django.utils import timezone
from jinja2 import Template
from INSAI.utils import apply_company_field_mapping, normalize_decimal, SSLAdapter, clean_namespaces, get_by_path, \
    create_or_update_customer_generic, parse_date
from agency.models import AgencyPasswords
from database.models import CompanyFieldMapping, Customer, Policy, Collection, PaymentPlan, PolicyAssetRelation, \
    AssetCars, AssetHome, TransferServiceConfiguration
from transfer.bereket import print_tax_values
from transfer.models import TransferLogDetail, CurrencyMapping





def transfer_neova(
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
    print("🚚 [Neova] Tek servis başlatıldı")

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company=service_config.insurance_company
    ).first()
    app_security_key = password_info.appSecurityKey if password_info else ""

    context = {
        "baslangicTarihi": start_date.strftime("%d.%m.%Y"),
        "bitisTarihi": end_date.strftime("%d.%m.%Y"),
        "appSecurityKey": app_security_key,
    }

    try:
        soap_body = Template(service_config.soap_template).render(**context)
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
    except Exception as ex:
        raise Exception(f"❌ SOAP istek hatası: {ex}")

    try:
        data_dict = clean_namespaces(xmltodict.parse(response.text))
    except Exception as ex:
        raise Exception(f"❌ XML parse hatası: {ex}")

    police_list = None
    for path in (service_config.policy_list_path or "").split("|"):
        police_list = get_by_path(data_dict, path.strip())
        if police_list:
            print(f"✅ Poliçe path bulundu: {path.strip()}")
            break

    if not police_list:
        print("ℹ️ Neova → Son 3 günde poliçe bulunamadı")
        if log:
            log.success = True
            log.total_count = 0
            log.created_count = 0
            log.updated_count = 0
            log.skipped_count = 0
            log.customers_created = 0
            log.cars_created = 0
            log.homes_created = 0
            log.save(update_fields=[
                "success", "total_count", "created_count", "updated_count", "skipped_count",
                "customers_created", "cars_created", "homes_created"
            ])
        return {
            "success": True,
            "message": "Son 3 günde veri yok",
            "total": 0
        }

    if isinstance(police_list, dict):
        police_list = [police_list]

    print(f"📦 Toplam {len(police_list)} poliçe bulundu")

    if mapping_qs is None:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_config.id,
            is_active=True
        ).select_related("key", "parameter")

    total_customers, total_cars, total_homes = 0, 0, 0
    created_count, updated_count, skipped_count = 0, 0, 0

    for police_data in police_list:
        try:
            print("📄 Yeni poliçe işleniyor")
            print_tax_values(police_data)

            mapped = apply_company_field_mapping(police_data, mapping_qs)

            ettiren_tc = mapped.get("SigortaEttirenKimlikNo") or mapped.get("SigortaEttirenVergiKimlikNo")
            sigortali_tc = mapped.get("SigortaliKimlikNo") or mapped.get("SigortaliVergiKimlikNo")

            musteri_listesi = []

            if sigortali_tc and sigortali_tc != "0":
                musteri_listesi.append({
                    "identity_number": sigortali_tc,
                    "birth_date": mapped.get("SigortaliDogumTarihi"),
                    "full_name": f"{mapped.get('SigortaliAdi', '')} {mapped.get('SigortaliSoyadi', '')}".strip(),
                    "SigortaliCepTelefonu": mapped.get("SigortaliCepTelefonu")
                })

            if ettiren_tc and ettiren_tc != sigortali_tc and ettiren_tc != "0":
                musteri_listesi.append({
                    "identity_number": ettiren_tc,
                    "birth_date": mapped.get("SigortaEttirenDogumTarihi"),
                    "full_name": f"{mapped.get('SigortaEttirenAdi', '')} {mapped.get('SigortaEttirenSoyadi', '')}".strip(),
                    "SigortaEttirenCepTelefonu": mapped.get("SigortaEttirenCepTelefonu")
                })

            if not musteri_listesi:
                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=mapped.get("PoliceNo") or "UNKNOWN",
                        status="skipped",
                        message="Geçerli müşteri bilgisi yok",
                        record_type="policy",
                        data_source="neova"
                    )
                continue

            created_ids = create_or_update_customer_generic(agency_id, musteri_listesi) or []
            total_customers += len(created_ids)

            customer = Customer.objects.filter(identity_number=ettiren_tc, agency_id=agency_id).first()
            insured = Customer.objects.filter(identity_number=sigortali_tc, agency_id=agency_id).first()

            result = create_policy_neova(
                mapped, agency_id, company_id, customer, insured, police_data,
                log=log, service_id=service_config.id
            )

            policy_obj = result.get("policy") if result else None
            collection_success = result.get("collection_created") if result else False

            if not policy_obj or not collection_success:
                skipped_count += 1
                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=f"{mapped.get('PoliceNo')}-{mapped.get('ZeyilNo') or 0}-{mapped.get('YenilemeNo') or 0}",
                        status="failed",
                        message="Poliçe veya tahsilat oluşturulamadı",
                        record_type="policy",
                        customer_identity_number=ettiren_tc,
                        data_source="neova"
                    )
                continue

            is_created = bool(result.get("created"))  # ❗️ Garantili boolean dönüşüm

            if result.get("policy"):
                if result.get("created"):
                    created_count += 1
                else:
                    updated_count += 1
            else:
                skipped_count += 1

            # 🔄 Varlık (araç/konut) kontrolü ve yazımı
            car_created, home_created = handle_asset_creation_neova(
                police_data, policy_obj, agency_id, company_id, service_config.id, log=log
            )

            total_cars += car_created
            total_homes += home_created

            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=policy_obj.PoliceNoKombine,
                    status="created" if is_created else "updated",
                    message="Poliçe ve tahsilat kaydedildi",
                    record_type="policy",
                    policy=policy_obj,
                    customer_identity_number=ettiren_tc,
                    data_source="neova"
                )

        except Exception as ex:
            print(f"❌ HATA: {ex}")
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no="UNKNOWN",
                    status="failed",
                    message=str(ex)[:1000],
                    record_type="policy",
                    data_source="neova"
                )

    if log:
        log.customers_created = total_customers
        log.cars_created = total_cars
        log.homes_created = total_homes
        log.total_count = len(police_list)
        log.created_count = created_count
        log.updated_count = updated_count
        log.skipped_count = skipped_count
        log.save(update_fields=[
            "customers_created", "cars_created", "homes_created",
            "total_count", "created_count", "updated_count", "skipped_count"
        ])

    print("✅ [Neova] Transfer tamamlandı")

    return {
        "success": True,
        "total": len(police_list),
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "customers_created": total_customers,
        "cars_created": total_cars,
        "homes_created": total_homes,
    }



def create_policy_neova(mapped, agency_id, company_id, customer, insured, police_data, log=None, service_id=None):
    try:
        police_no = mapped.get("PoliceNo")
        zeyil_no = str(int(mapped.get("ZeyilNo") or 0))
        yenileme_no = str(int(mapped.get("YenilemeNo") or 0))
        ana_key = f"{police_no}-{yenileme_no}"

        mapped["ZeyilNo"] = zeyil_no
        mapped["YenilemeNo"] = yenileme_no
        mapped["PoliceAnaKey"] = ana_key

        # ⛔ Eksik zeyil kontrolü
        if zeyil_no != "0":
            try:
                eksik_zeyiller = []
                for i in range(int(zeyil_no)):
                    if not Policy.objects.filter(
                        PoliceAnaKey=ana_key,
                        ZeyilNo=str(i),
                        agency_id=agency_id
                    ).exists():
                        eksik_zeyiller.append(i)

                if eksik_zeyiller:
                    if log:
                        TransferLogDetail.objects.create(
                            log=log,
                            police_no=f"{police_no}-{zeyil_no}-{yenileme_no}",
                            status="skipped",
                            record_type="policy",
                            customer_identity_number=str(customer.identity_number) if customer else None,
                            policy=None,
                            data_source="neova",
                            message=f"Eksik zeyil kayıtları: {eksik_zeyiller} → zeyil alınmadı: {ana_key}"
                        )
                    return {"policy": None, "collection_created": False, "created": False}
            except Exception as e:
                print(f"⚠️ Zeyil kontrol hatası: {e}")
                return {"policy": None, "collection_created": False, "created": False}

        mapped["PolicyStatus"] = mapped.get("PoliceIptalDurumu") or 221
        mapped["AktifMi"] = "0" if mapped["PolicyStatus"] == 222 else "1"

        # 🧾 Poliçe kaydı
        policy_obj, created = Policy.objects.update_or_create(
            PoliceNo=police_no,
            ZeyilNo=zeyil_no,
            YenilemeNo=yenileme_no,
            agency_id=agency_id,
            company_id=company_id,
            defaults={
                "customer": customer,
                "insured": insured,
                "PoliceTanzimTarihi": mapped.get("PoliceTanzimTarihi"),
                "PoliceBaslangicTarihi": mapped.get("PoliceBaslangicTarihi"),
                "PoliceBitisTarihi": mapped.get("PoliceBitisTarihi"),
                "SirketUrunNo": mapped.get("SirketUrunNo"),
                "ZeyilKodu": mapped.get("ZeyilKodu"),
                "ZeyilAdi": mapped.get("ZeyilAdi"),
                "PoliceKesenKullanici": mapped.get("PoliceKesenKullanici"),
                "AktifMi": mapped.get("AktifMi"),
                "PolicyStatus_id": mapped.get("PolicyStatus"),
                "PoliceAnaKey": ana_key,
            }
        )

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created" if created else "updated",
                record_type="policy",
                customer_identity_number=(customer.identity_number if customer else None),
                policy=policy_obj,
                data_source="neova",
                message="Poliçe kaydedildi" if created else "Poliçe güncellendi"
            )

        if mapped["PolicyStatus"] == 222:
            Policy.objects.filter(
                PoliceAnaKey=ana_key,
                agency_id=agency_id,
                AktifMi="1"
            ).exclude(
                PoliceNo=police_no,
                ZeyilNo=zeyil_no
            ).update(
                AktifMi="0",
                updated_at=timezone.now()
            )

        # 💰 Tahsilat hesapla
        totals = extract_collection_totals_from_response_neova(
            mapped=mapped,
            policy_obj=policy_obj,
            company_id=company_id
        )

        if not totals:
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=policy_obj.PoliceNoKombine,
                    status="skipped",
                    record_type="collection",
                    message="Tahsilat hesaplanamadı",
                    data_source="neova"
                )
            policy_obj.delete()
            return {"policy": None, "collection_created": False, "created": False}

        Collection.objects.filter(policy=policy_obj).delete()
        Collection.objects.create(
            policy=policy_obj,
            agency=policy_obj.agency,
            customer=policy_obj.customer,
            insured=policy_obj.insured,
            PoliceNoKombine=policy_obj.PoliceNoKombine,
            NetPrim=totals["NetPrim"],
            NetPrimTL=totals["NetPrimTL"],
            Komisyon=totals["Komisyon"],
            KomisyonPrimTL=totals["KomisyonPrimTL"],
            BrutPrim=totals["BrutPrim"],
            BrutPrimTL=totals["BrutPrimTL"],
            ZeyilKomisyonu=totals["ZeyilKomisyonu"],
            EkKomisyon=totals["EkKomisyon"],
            DovizKuru=totals["DovizKuru"],
            DovizCinsi=totals["DovizCinsi"],
            KKBlokeli=totals["KKBlokeli"]
        )

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="collection",
                policy=policy_obj,
                customer_identity_number=(customer.identity_number if customer else None),
                data_source="neova",
                message="Tahsilat kaydedildi"
            )

        create_payment_plans_from_response_neova(police_data, policy_obj, agency_id)
        car_created, home_created = handle_asset_creation_neova(
            police_data, policy_obj, agency_id, company_id, service_id, log=log
        )

        if log and (mapped.get("AracSasiNo") or mapped.get("AracPlakaTam")):
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_car",
                customer_identity_number=(insured.identity_number if insured else None),
                policy=policy_obj,
                data_source="neova",
                message="Araç varlık kaydedildi"
            )

        if log and mapped.get("RizikoUavtKod"):
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="asset_home",
                customer_identity_number=(insured.identity_number if insured else None),
                policy=policy_obj,
                data_source="neova",
                message="Konut varlık kaydedildi"
            )

        return {
            "policy": policy_obj,
            "collection_created": True,
            "created": created,
            "car_created": car_created,
            "home_created": home_created
        }

    except Exception as e:
        print(f"❌ Poliçe kaydı hatası → {e}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=police_no or "UNKNOWN",
                status="failed",
                record_type="policy",
                message=str(e)[:1000],
                data_source="neova"
            )
        return {"policy": None, "collection_created": False, "created": False}


def extract_collection_totals_from_response_neova(mapped, policy_obj=None, company_id=None):
    try:
        net_prim = normalize_decimal(mapped.get("NetPrim"))
        brut_prim = normalize_decimal(mapped.get("BrutPrim"))
        komisyon = normalize_decimal(mapped.get("Komisyon"))
        doviz_kur = normalize_decimal(mapped.get("DovizKuru"))
        raw_doviz = mapped.get("DovizCinsi")
        raw_kk = str(mapped.get("KKBlokeli")).strip().upper() if mapped.get("KKBlokeli") else ""

        if doviz_kur in [None, Decimal("0.0")]:
            print(f"❌ Döviz kuru geçersiz → {doviz_kur}")
            return None

        # 🚨 Eksik alan kontrolü
        if net_prim is None:
            print(f"⚠️ [{policy_obj.PoliceNoKombine}] NetPrim alanı boş geldi!")
        if brut_prim is None:
            print(f"⚠️ [{policy_obj.PoliceNoKombine}] BrutPrim alanı boş geldi!")
        if komisyon is None:
            print(f"⚠️ [{policy_obj.PoliceNoKombine}] Komisyon alanı boş geldi!")


        doviz_cinsi = None
        if raw_doviz:
            doviz_obj = CurrencyMapping.objects.filter(
                company_id=company_id,
                raw_value=raw_doviz,
                is_active=True
            ).first()
            if doviz_obj:
                doviz_cinsi = doviz_obj.currency_code
            else:
                print(f"⚠️ Döviz cinsi eşleşmedi → {raw_doviz}")

        kk_blokeli = None
        if raw_kk in ["1", "E", "EVET", "YES"]:
            kk_blokeli = True
        elif raw_kk in ["0", "H", "HAYIR", "NO"]:
            kk_blokeli = False

        is_iptal = str(mapped.get("PoliceIptalDurumu")) == "222"
        multiplier = -1 if is_iptal else 1

        return {
            "NetPrim": round((net_prim or Decimal("0.00")) * multiplier, 2),
            "NetPrimTL": round((net_prim or Decimal("0.00")) * doviz_kur * multiplier, 2),
            "Komisyon": round((komisyon or Decimal("0.00")) * multiplier, 2),
            "KomisyonPrimTL": round((komisyon or Decimal("0.00")) * doviz_kur * multiplier, 2),
            "BrutPrim": round((brut_prim or Decimal("0.00")) * multiplier, 2),
            "BrutPrimTL": round((brut_prim or Decimal("0.00")) * doviz_kur * multiplier, 2),
            "ZeyilKomisyonu": Decimal("0.00"),
            "EkKomisyon": Decimal("0.00"),
            "DovizKuru": doviz_kur,
            "DovizCinsi": doviz_cinsi,
            "KKBlokeli": kk_blokeli
        }

    except Exception as e:
        print(f"❌ Tahsilat hesaplama hatası (Neova): {e}")
        return None



def parse_neova_money(raw):
    try:
        return round(Decimal(str(raw)) / Decimal("10000"), 2)
    except (TypeError, InvalidOperation):
        return Decimal("0.00")

def convert_neova_payment_amount(raw_val):
    try:
        return Decimal(str(raw_val)) / Decimal("1000000")
    except (InvalidOperation, TypeError):
        return Decimal("0.00")

def create_payment_plans_from_response_neova(police_data, policy_obj, agency_id):
    try:
        print("📥 [Neova] Ödeme planı verisi işleniyor...")

        payment_list = get_by_path(police_data, "ListOfPayment.Payment") or []
        if isinstance(payment_list, dict):
            payment_list = [payment_list]

        print(f"📊 [Neova] Bulunan taksit sayısı: {len(payment_list)}")

        PaymentPlan.objects.filter(policy=policy_obj).delete()
        print("🧹 [Neova] Eski ödeme planı kayıtları silindi.")

        payment_objs = []
        payment_type_set = set()

        for idx, item in enumerate(payment_list, start=1):
            tutar_raw = item.get("TUTAR")
            vade_raw = item.get("VADE")
            hesap_tip = item.get("HESAP_TIP")
            t_i = str(item.get("T_I", "")).strip().upper()

            tutar = convert_neova_payment_amount(tutar_raw)
            if t_i == "I":
                tutar = -tutar

            vade = parse_date(vade_raw)
            if not vade:
                print(f"⚠️ Geçersiz vade tarihi: {vade_raw}")
                continue

            payment_objs.append(
                PaymentPlan(
                    policy=policy_obj,
                    agency_id=agency_id,
                    PoliceNoKombine=policy_obj.PoliceNoKombine,
                    TaksitSirasi=str(idx),
                    TaksitVadeTarihi=vade,
                    TaksitTutar=tutar
                )
            )

            if hesap_tip:
                payment_type_set.add(hesap_tip)

        PaymentPlan.objects.bulk_create(payment_objs)
        print(f"✅ [Neova] {len(payment_objs)} ödeme planı kaydı yapıldı.")

        # ♻️ Collection güncelle
        collection = Collection.objects.filter(policy=policy_obj).first()
        if collection:
            collection.TaksitSayisi = len(payment_objs)
            if payment_type_set:
                collection.OdemeSekli = ",".join(sorted(payment_type_set))
            collection.save()
            print("♻️ [Neova] Collection tablosu güncellendi.")

    except Exception as e:
        print(f"❌ [HATA] Neova ödeme planı yazım hatası: {e}")

def handle_asset_creation_neova(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚦 [Neova Varlık Kontrol] Başlatıldı...")

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key", "parameter")

    mapped_data = apply_company_field_mapping(police_data, mapping_qs)
    urun_kodu = mapped_data.get("SirketUrunNo")

    if not urun_kodu:
        print("⚠️ Ürün kodu boş, varlık tipi belirlenemedi.")
        return 0, 0

    # 🚘 Neova Araç ürün kodları
    allowed_vehicle_products = ["FK-1", "F18", "K11", "K18", "K23", "TR4", "TR3", "TR6", "T08", "K26", "K10"]
    if urun_kodu in allowed_vehicle_products:
        print(f"🚘 [Araç Varlık] için uygun ürün kodu bulundu → {urun_kodu}")
        created = create_asset_car_neova(
            police_data, policy_obj, agency_id, company_id, service_id, log=log
        )
        return int(bool(created)), 0

    # 🏠 Neova Konut ürün kodları
    allowed_home_products = ["DSK", "Y06", "YI1", "YK2"]
    if urun_kodu in allowed_home_products:
        print(f"🏠 [Konut Varlık] için uygun ürün kodu bulundu → {urun_kodu}")
        created = create_asset_home_neova(
            police_data, policy_obj, agency_id, company_id, service_id, log=log
        )
        return 0, int(bool(created))

    print(f"⚠️ Ürün kodu ({urun_kodu}) araç veya konut için tanımlı değil.")
    return 0, 0



def create_asset_car_neova(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚗 [Neova - Araç Varlık] Mapping ile kayıt başlıyor...")

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key", "parameter")

    mapped_data = apply_company_field_mapping(police_data, mapping_qs)
    insured = policy_obj.insured
    sasi_no = mapped_data.get("AracSasiNo")
    plaka = mapped_data.get("AracPlakaTam")

    if not insured or (not sasi_no and not plaka):
        print("⚠️ Eksik veri → sigortalı ve plaka/şase yok, kayıt atlandı.")
        return

    lookup = {
        "insured": insured,
        "agency": policy_obj.agency
    }
    if sasi_no:
        lookup["AracSasiNo"] = sasi_no
    else:
        lookup["AracPlakaTam"] = plaka.strip()

    defaults = {
        "policy": policy_obj,
        "agency": policy_obj.agency,
        "PoliceNoKombine": policy_obj.PoliceNoKombine,
        "AktifMi": True,
        **{k: v for k, v in mapped_data.items() if hasattr(AssetCars, k)},
    }

    obj, created = AssetCars.objects.update_or_create(**lookup, defaults=defaults)

    if obj and isinstance(obj, AssetCars):
        relation, _ = PolicyAssetRelation.objects.get_or_create(policy=policy_obj)
        relation.asset_car = obj
        relation.asset_home = None  # diğer alanı sıfırla
        relation.save(update_fields=["asset_car", "asset_home"])

    tarife_kod = mapped_data.get("TarifeKod")
    if policy_obj.PolicyStatus_id == 222 and tarife_kod in ["TR4", "TR6"]:
        obj.AktifMi = False
        obj.save(update_fields=["AktifMi"])
        print(f"🚫 [Neova - Araç Varlık] İptal & TarifeKod={tarife_kod} → Pasife çekildi.")

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy_obj.PoliceNoKombine,
            status="created",
            record_type="asset_car",
            customer_identity_number=insured.identity_number if insured else None,
            policy=policy_obj,
            data_source="neova",
            message="Araç varlık kaydedildi (mapping)"
        )

    print(f"{'➕' if created else '♻️'} Araç varlığı kaydedildi → {obj.AracPlakaTam or sasi_no}")
    return created

def create_asset_home_neova(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🏠 [Konut Varlık - Neova] Mapping ile kayıt başlıyor...")

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key", "parameter")

    mapped_data = apply_company_field_mapping(police_data, mapping_qs)
    insured = policy_obj.insured
    uavt_kod = mapped_data.get("RizikoUavtKod")

    if not insured or not uavt_kod:
        print("⚠️ Eksik veri → sigortalı veya UAVT kodu yok, konut kaydı atlandı.")
        return

    lookup = {
        "insured": insured,
        "agency": policy_obj.agency,
        "RizikoUavtKod": uavt_kod
    }

    defaults = {
        "policy": policy_obj,
        "agency": policy_obj.agency,
        "PoliceNoKombine": policy_obj.PoliceNoKombine,
        "AktifMi": True,
        **{k: v for k, v in mapped_data.items() if hasattr(AssetHome, k)},
    }

    obj, created = AssetHome.objects.update_or_create(**lookup, defaults=defaults)

    if obj and isinstance(obj, AssetHome):
        relation, _ = PolicyAssetRelation.objects.get_or_create(policy=policy_obj)
        relation.asset_home = obj
        relation.asset_car = None  # diğer alanı sıfırla
        relation.save(update_fields=["asset_home", "asset_car"])

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy_obj.PoliceNoKombine,
            status="created",
            record_type="asset_home",
            customer_identity_number=insured.identity_number if insured else None,
            policy=policy_obj,
            data_source="neova",
            message="Konut varlık kaydedildi (mapping)"
        )

    print(f"{'➕' if created else '♻️'} Konut varlık kaydedildi → {uavt_kod}")
    return created


def run_transfer_neova_custom_api(agency_id, service_id, start_date, end_date):
    print("🚀 [Neova API] Veri çekme işlemi başlatıldı")

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

    # 🔎 XLSX yolunu al
    match = re.search(r'Output/[\w\-]+\.xlsx', response.text)
    if not match:
        print("❌ XLSX dosya yolu bulunamadı.")
        return response.text

    xlsx_path = match.group(0)

    # 📥 Playwright ile indir
    xlsx_data = fetch_neova_excel_with_playwright(xlsx_path, password)

    if xlsx_data:
        print("✅ XLSX veri başarıyla alındı")
        # 🔄 Collection tablolarını güncelle
        update_neova_card_info_from_excel(xlsx_data, agency_id)
    else:
        print("⚠️ XLSX veri alınamadı")

    return response.text


# 📥 Playwright ile XLSX dosyasını indir
def fetch_neova_excel_with_playwright(xlsx_path, password_obj):


    print("📥 [XLSX Alım - Neova - Playwright] Başlatıldı")

    full_url = urljoin("https://sigorta.neova.com.tr:4443/report/", xlsx_path)
    print(f"🔗 [Neova] İndirme URL: {full_url}")

    cookies_raw = password_obj.cookie.strip()
    cookie_pairs = [c.strip().split("=", 1) for c in cookies_raw.split(";") if "=" in c]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        context.add_cookies([
            {
                "name": name,
                "value": value,
                "domain": "sigorta.neova.com.tr",
                "path": "/",
                "secure": True,
                "httpOnly": False
            } for name, value in cookie_pairs
        ])

        page = context.new_page()

        try:
            response = page.request.get(full_url, timeout=240 * 1000)
            if response.status == 200:
                print("✅ [Neova] XLSX dosyası başarıyla alındı.")
                return response.body()  # Binary olarak dön
            else:
                print(f"❌ [Neova] Yanıt kodu: {response.status}")
                return None
        except Exception as e:
            print(f"❌ [Neova] XLSX çekme hatası: {e}")
            return None
        finally:
            context.close()
            browser.close()



def update_neova_card_info_from_excel(excel_binary_data, agency_id):
    df = pd.read_excel(BytesIO(excel_binary_data), header=None)

    print(f"📄 Toplam satır: {len(df)}")
    updated_count = 0
    read_count = 0

    for i, row in df.iterrows():
        if i == 0:
            print("🔸 İlk satır atlandı (muhtemelen başlık)")
            continue

        try:
            poliseno_raw = row[2] if pd.notna(row[2]) else ""
            borclu = row[6] if pd.notna(row[6]) else ""
            kartno = row[7] if pd.notna(row[7]) else ""

            poliseno_raw = str(poliseno_raw).strip()
            borclu = str(borclu).strip()
            kartno = str(kartno).strip()

            poliseno_clean = ''.join(filter(str.isdigit, poliseno_raw))

            print(f"\n🔍 Satır {i}: Orijinal='{poliseno_raw}' → Temiz='{poliseno_clean}' | Sahip='{borclu}' | Kart='{kartno}'")

            if not poliseno_clean or not kartno:
                print("⚠️ Veri eksik → atlandı")
                continue

            read_count += 1  # 🔢 Geçerli veri satırı

            policies = Policy.objects.filter(
                PoliceNo=poliseno_clean,
                agency_id=agency_id
            ).order_by("ZeyilNo")

            if not policies.exists():
                print(f"❌ Poliçe bulunamadı: {poliseno_clean} | Acente={agency_id}")
                continue
            else:
                print(f"✅ {policies.count()} poliçe bulundu")

            for policy in policies:
                print(f"🧾 Policy ID: {policy.id} | Zeyil: {policy.ZeyilNo}")
                collections = Collection.objects.filter(policy=policy)
                for c in collections:
                    print(f"📌 Collection ID: {c.id} | Kart Sahibi: {c.KartSahibi} | Kart No: {c.KrediKartNo}")

                    guncellendi = False
                    if not c.KartSahibi and borclu:
                        c.KartSahibi = borclu
                        guncellendi = True
                    if not c.KrediKartNo and kartno:
                        c.KrediKartNo = kartno
                        guncellendi = True

                    if guncellendi:
                        c.save()
                        updated_count += 1
                        print(f"✅ Güncellendi → {poliseno_clean} → {borclu} / {kartno}")
                    else:
                        print("ℹ️ Zaten dolu veya veri yok → atlandı")

        except Exception as e:
            print(f"❌ Satır {i} hatası: {e}")

    print(f"\n🎯 Toplam güncellenen kayıt: {updated_count}, okunan geçerli satır: {read_count}")
    return updated_count, read_count












