import re

from django.db.models import Sum
from jinja2 import Template
import requests,xmltodict
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from INSAI.utils import apply_company_field_mapping, normalize_decimal, get_by_path, SSLAdapter, clean_namespaces, \
    create_or_update_customer_generic, parse_date
from agency.models import AgencyTransferServiceAuthorization, AgencyPasswords
from transfer.models import TransferLogDetail
from database.models import CompanyFieldMapping, Customer, Policy, PaymentPlan, AssetCars, AssetHome, Collection, \
    PolicyAssetRelation, TransferServiceConfiguration
from decimal import Decimal, InvalidOperation
from io import BytesIO
import pandas as pd


def print_tax_values(police_data):
    tax_list = get_by_path(police_data, "ListOfTax.Tax") or []
    if isinstance(tax_list, dict):
        tax_list = [tax_list]

    def to_decimal(val):
        try:
            return Decimal(str(val).replace(",", "."))
        except (InvalidOperation, TypeError):
            return Decimal("0.0")

    total_vergi = Decimal("0.0")
    total_dvergi = Decimal("0.0")

    for t in tax_list:
        dvergi = to_decimal(t.get("DVERGI"))
        vergi = to_decimal(t.get("VERGI"))
        total_dvergi += dvergi
        total_vergi += vergi



def transfer_bereket(
    agency_id,
    company_id,
    service_config,
    start_date,
    end_date,
    batch_id,
    log=None,
    mapping_qs=None,
    password=None,

):
    print("🚚 [Bereket] Tek servis başlatıldı")

    # ⛔ Yetki kontrolü
    is_authorized = AgencyTransferServiceAuthorization.objects.filter(
        agency_id=agency_id,
        transfer_service_id=service_config.id,  # ✅ Doğru alan adı
        is_active=True
    ).exists()

    if not is_authorized:
        raise Exception("⛔ Bu acente için servis yetkisi tanımlı değil!")

    # 🔑 Giriş bilgileri
    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=company_id
    ).first()

    if not password_info or not password_info.authenticationKey:
        raise Exception("⛔ Acente için authenticationKey tanımlı değil!")


    # 🧩 SOAP template context
    context = {
        "baslangicTarihi": start_date.strftime("%d.%m.%Y"),
        "bitisTarihi": end_date.strftime("%d.%m.%Y"),
        "authenticationKey": password_info.authenticationKey.strip(),
    }

    try:
        soap_body = Template(service_config.soap_template).render(**context)
        print("📤 SOAP Body render tamam")
        print("📨 Giden SOAP Body:\n", soap_body)  # 👈 BURADA
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
        print("📥 SOAP yanıt alındı")
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
        print("ℹ️ Bereket → Son 3 günde poliçe bulunamadı")
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

            print("🧪 DEBUG → mapped:", mapped)
            print("🧪 DEBUG → SigortaliCepTelefonu:", mapped.get("SigortaliCepTelefonu"))

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
                        data_source="bereket"
                    )
                skipped_count += 1
                continue

            created_ids = create_or_update_customer_generic(agency_id, musteri_listesi) or []
            total_customers += len(created_ids)

            customer = Customer.objects.filter(identity_number=ettiren_tc, agency_id=agency_id).first()
            insured = Customer.objects.filter(identity_number=sigortali_tc, agency_id=agency_id).first()

            result = create_policy_bereket(
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
                        data_source="bereket"
                    )
                continue

            is_created = result.get("created", False)
            if is_created:
                created_count += 1
            else:
                updated_count += 1

            car_created, home_created = handle_asset_creation(
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
                    data_source="bereket"
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
                    data_source="bereket"
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

    print("✅ [Bereket] Transfer tamamlandı")

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


def create_policy_bereket(mapped, agency_id, company_id, customer, insured, police_data, log=None, service_id=None):
    try:
        police_no = mapped.get("PoliceNo")
        zeyil_no = str(int(mapped.get("ZeyilNo") or 0))
        yenileme_no = str(int(mapped.get("YenilemeNo") or 0))
        ana_key = f"{police_no}-{yenileme_no}"

        mapped["ZeyilNo"] = zeyil_no
        mapped["YenilemeNo"] = yenileme_no
        mapped["PoliceAnaKey"] = ana_key

        if zeyil_no != "0":
            try:
                zeyil_int = int(zeyil_no)
                eksik_zeyiller = []
                for i in range(zeyil_int):
                    if not Policy.objects.filter(
                            PoliceAnaKey=ana_key,
                            ZeyilNo=str(i),
                            agency_id=agency_id
                    ).exists():
                        eksik_zeyiller.append(i)

                if eksik_zeyiller:
                    if log:
                        try:
                            TransferLogDetail.objects.create(
                                log=log,
                                police_no=f"{police_no}-{zeyil_no}-{yenileme_no}",
                                status="skipped",
                                record_type="policy",
                                customer_identity_number=str(customer.identity_number) if customer else None,
                                policy=None,
                                data_source="detail",
                                message=f"Eksik zeyil kayıtları: {eksik_zeyiller} → zeyil alınmadı: {ana_key}"
                            )
                            print(f"⛔ Eksik zeyiller bulundu: {eksik_zeyiller} → kayıt atlandı")
                        except Exception as log_ex:
                            print(f"⚠️ Log yazılamadı → {log_ex}")

                    return {"policy": None, "collection_created": False, "created": False}

            except Exception as e:
                print(f"⚠️ Zeyil kontrol hatası: {e}")

                return {"policy": None, "collection_created": False, "created": False}

        mapped["PolicyStatus"] = mapped.get("PoliceIptalDurumu") or 221
        mapped["AktifMi"] = "0" if mapped["PolicyStatus"] == 222 else "1"

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
                data_source="bereket",
                message="Poliçe kaydedildi" if created else "Poliçe güncellendi"
            )

        totals = extract_collection_totals_from_coverages(
            police_data,
            policy_obj=policy_obj,
            log=log,
            service_id=service_id,
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
                    data_source="bereket"
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
            NetPrim=totals.get("NetPrim") or 0,
            NetPrimTL=totals.get("NetPrimTL") or 0,
            Komisyon=totals.get("Komisyon") or 0,
            KomisyonPrimTL=totals.get("KomisyonPrimTL") or 0,
            BrutPrim=totals.get("BrutPrim") or 0,
            BrutPrimTL=totals.get("BrutPrimTL") or 0,
            EkKomisyon=totals.get("EkKomisyon") or 0,
            ZeyilKomisyonu=totals.get("ZeyilKomisyonu") or 0,
            DovizKuru=totals.get("DovizKuru"),
            DovizCinsi=totals.get("DovizCinsi"),
            KKBlokeli=totals.get("KKBlokeli"),
        )

        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=policy_obj.PoliceNoKombine,
                status="created",
                record_type="collection",
                customer_identity_number=(customer.identity_number if customer else None),
                policy=policy_obj,
                data_source="bereket",
                message="Tahsilat kaydedildi"
            )

        create_payment_plans_from_response(police_data, policy_obj, agency_id)
        car_created, home_created = handle_asset_creation(
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
                data_source="bereket",
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
                data_source="bereket",
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
                data_source="bereket"
            )
        return {"policy": None, "collection_created": False, "created": False}

def extract_collection_totals_from_coverages(police_data, policy_obj=None, log=None, service_id=None, company_id=None):

    # Mapping tablosundan döviz ve blokeli bilgisi çekilir
    mapped = {}
    if service_id:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_id,
            is_active=True
        ).select_related("key", "parameter")
        mapped = apply_company_field_mapping(police_data, mapping_qs)

    raw_kod = mapped.get("KKBlokeli")
    kk_blokeli = None
    if raw_kod is not None:
        val = str(raw_kod).strip().upper()
        if val in ["1", "E", "EVET", "YES"]:
            kk_blokeli = True
        elif val in ["0", "H", "HAYIR", "NO"]:
            kk_blokeli = False

    doviz_kur = normalize_decimal(mapped.get("DovizKuru"))
    doviz_cins = mapped.get("DovizCinsi")

    def to_tl(val):
        return round(val * doviz_kur, 2) if doviz_kur else None

    # Poliçe detayları
    coverages = get_by_path(police_data, "ListOfCoverage.Coverage") or []
    if isinstance(coverages, dict):
        coverages = [coverages]

    def to_decimal(val):
        try:
            return Decimal(str(val).replace(",", ".")) if val else Decimal("0.0")
        except (InvalidOperation, TypeError):
            return Decimal("0.0")

    is_iptal = any(str(cov.get("T_I", "")).strip().upper() == "I" for cov in coverages)
    is_teklif = all(str(cov.get("T_I", "")).strip().upper() == "T" for cov in coverages)
    zeyil_no = str(policy_obj.ZeyilNo) if policy_obj else "0"

    net_prim = sum(to_decimal(cov.get("NET_PRIM")) for cov in coverages)
    komisyon = sum(to_decimal(cov.get("DKOM_TUTARI")) for cov in coverages)
    zeyil_komisyon = sum(to_decimal(cov.get("KOM_TUTARI")) for cov in coverages if str(cov.get("ZeyilSiraNo", "0")) != "0")

    tax_list = get_by_path(police_data, "ListOfTax.Tax") or []
    if isinstance(tax_list, dict):
        tax_list = [tax_list]

    total_dvergi = sum(to_decimal(t.get("DVERGI")) for t in tax_list)

    # 🔁 Zeyil karşılaştırması
    if policy_obj and zeyil_no != "0":
        ana_key = policy_obj.PoliceAnaKey
        agency_id = policy_obj.agency_id
        kombine = policy_obj.PoliceNoKombine

        ana_var = Policy.objects.filter(PoliceAnaKey=ana_key, ZeyilNo="0", agency_id=agency_id).exists()
        if not ana_var:
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=kombine,
                    status="skipped",
                    message=f"Ana poliçe bulunamadı: {ana_key} (Zeyil: {zeyil_no})"
                )
            return None

        previous = Collection.objects.filter(
            policy__PoliceAnaKey=ana_key,
            policy__agency_id=agency_id
        ).exclude(policy=policy_obj)

        totals_db = previous.aggregate(
            netprim=Sum("NetPrim"), komisyon=Sum("Komisyon")
        )

        prev_net = totals_db["netprim"] or Decimal("0.0")
        prev_kom = totals_db["komisyon"] or Decimal("0.0")

        if is_iptal:
            net = -(prev_net - net_prim)
            kom = -(prev_kom - komisyon)
            brut = -(prev_net - net_prim + total_dvergi)
            return {
                "NetPrim": round(net, 2),
                "NetPrimTL": to_tl(net),
                "Komisyon": round(kom, 2),
                "KomisyonPrimTL": to_tl(kom),
                "BrutPrim": round(brut, 2),
                "BrutPrimTL": to_tl(brut),
                "ZeyilKomisyonu": round(-zeyil_komisyon, 2),
                "DovizKuru": doviz_kur,
                "DovizCinsi": doviz_cins,
                "KKBlokeli": kk_blokeli,
            }

        elif is_teklif:
            net = net_prim - prev_net
            kom = komisyon - prev_kom
            brut = (net_prim + total_dvergi) - prev_net
            return {
                "NetPrim": round(net, 2),
                "NetPrimTL": to_tl(net),
                "Komisyon": round(kom, 2),
                "KomisyonPrimTL": to_tl(kom),
                "BrutPrim": round(brut, 2),
                "BrutPrimTL": to_tl(brut),
                "ZeyilKomisyonu": round(zeyil_komisyon, 2),
                "DovizKuru": doviz_kur,
                "DovizCinsi": doviz_cins,
                "KKBlokeli": kk_blokeli,
            }

    # 🟢 Normal poliçeler (zeyil = 0)
    brut = net_prim + total_dvergi
    return {
        "NetPrim": round(net_prim, 2),
        "NetPrimTL": to_tl(net_prim),
        "Komisyon": round(komisyon, 2),
        "KomisyonPrimTL": to_tl(komisyon),
        "BrutPrim": round(brut, 2),
        "BrutPrimTL": to_tl(brut),
        "ZeyilKomisyonu": round(zeyil_komisyon, 2),
        "DovizKuru": doviz_kur,
        "DovizCinsi": doviz_cins,
        "KKBlokeli": kk_blokeli,
    }

def create_payment_plans_from_response(police_data, policy_obj, agency_id):
    try:
        print("📥 [Ödeme Planı] Veri işleniyor...")

        payment_list = get_by_path(police_data, "ListOfPayment.Payment") or []
        if isinstance(payment_list, dict):
            payment_list = [payment_list]

        print(f"📊 [Ödeme Planı] Bulunan taksit sayısı: {len(payment_list)}")

        # 🔁 Eski kayıtları temizle
        PaymentPlan.objects.filter(policy=policy_obj).delete()
        print("🧹 [Ödeme Planı] Eski kayıtlar silindi.")

        payment_objs = []
        payment_type_set = set()

        for idx, item in enumerate(payment_list, start=1):
            tutar_raw = item.get("DTUTAR")
            vade_raw = item.get("VADE")
            hesap_tip = item.get("HESAP_TIP")
            t_i = str(item.get("T_I", "")).strip().upper()

            try:
                tutar = Decimal(str(tutar_raw).replace(",", "."))
            except:
                print(f"⚠️ Taksit tutarı dönüştürülemedi: {tutar_raw}")
                continue

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
                    TaksitTutar=tutar if t_i == "T" else -tutar,
                )
            )

            if hesap_tip:
                payment_type_set.add(hesap_tip)

        PaymentPlan.objects.bulk_create(payment_objs)
        print(f"✅ [Ödeme Planı] {len(payment_objs)} kayıt yazıldı.")

        # ♻️ Collection tablosunu güncelle
        collection = Collection.objects.filter(policy=policy_obj).first()
        if collection:
            collection.TaksitSayisi = len(payment_objs)
            if payment_type_set:
                collection.OdemeSekli = ",".join(sorted(payment_type_set))
            collection.save()  # update_fields VERME → save() override çalışsın
            print("♻️ [Collection] Taksit, ödeme tipi ve oranlar güncellendi.")


    except Exception as e:
        print(f"❌ [HATA] Ödeme planı yazım hatası: {e}")

def handle_asset_creation(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚦 [Varlık Kontrol] Başlatıldı...")

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key", "parameter")

    mapped_data = apply_company_field_mapping(police_data, mapping_qs)
    urun_kodu = mapped_data.get("SirketUrunNo")

    allowed_vehicle_products = ["ASP", "BDK", "BEK", "BFK", "BSP", "HSP", "KSP", "KTP", "T01", "FE6"]
    if urun_kodu in allowed_vehicle_products:
        print("🚘 [Araç Varlık] için uygun ürün kodu bulundu →", urun_kodu)
        created = create_asset_car_from_mapping(
            police_data, policy_obj, agency_id, company_id, service_id, log=log
        )
        return int(bool(created)), 0  # (araç, konut)

    allowed_home_products = ["Y01", "DSK"]
    if urun_kodu in allowed_home_products:
        print("🏠 [Konut Varlık] için uygun ürün kodu bulundu →", urun_kodu)
        created = create_asset_home_from_mapping(
            police_data, policy_obj, agency_id, company_id, service_id, log=log
        )
        return 0, int(bool(created))  # (araç, konut)

    print(f"⚠️ Ürün kodu ({urun_kodu}) araç veya konut için tanımlı değil.")
    return 0, 0

def create_asset_car_from_mapping(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🚗 [Araç Varlık] Mapping ile kayıt başlıyor...")

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

    lookup = {"insured": insured, "agency_id": agency_id}
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

    obj, created = AssetCars.objects.update_or_create(
        **lookup,
        defaults=defaults
    )

    PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_car=obj)

    tarife_kod = mapped_data.get("TarifeKod")
    if policy_obj.PolicyStatus_id == 222 and tarife_kod == "T01":
        obj.AktifMi = False
        obj.save(update_fields=["AktifMi"])
        print("🚫 [Araç Varlık] İptal & TarifeKod=T01 → Pasife çekildi.")

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy_obj.PoliceNoKombine,
            status="created",
            record_type="asset_car",
            customer_identity_number=insured.identity_number if insured else None,
            policy=policy_obj,
            data_source="bereket",
            message="Araç varlık kaydedildi (mapping)"
        )

    print(f"{'➕' if created else '♻️'} Araç varlığı kaydedildi → {obj.AracPlakaTam or sasi_no}")
    return created

def create_asset_home_from_mapping(police_data, policy_obj, agency_id, company_id, service_id, log=None):
    print("🏠 [Konut Varlık] Mapping ile kayıt başlıyor...")

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
        "RizikoUavtKod": uavt_kod,
        "agency_id": agency_id
    }

    defaults = {
        "policy": policy_obj,
        "agency": policy_obj.agency,
        "PoliceNoKombine": policy_obj.PoliceNoKombine,
        "AktifMi": True,
        **{k: v for k, v in mapped_data.items() if hasattr(AssetHome, k)},
    }

    obj, created = AssetHome.objects.update_or_create(
        **lookup,
        defaults=defaults
    )

    PolicyAssetRelation.objects.get_or_create(policy=policy_obj, asset_home=obj)

    if log:
        TransferLogDetail.objects.create(
            log=log,
            police_no=policy_obj.PoliceNoKombine,
            status="created",
            record_type="asset_home",
            customer_identity_number=insured.identity_number if insured else None,
            policy=policy_obj,
            data_source="bereket",
            message="Konut varlık kaydedildi (mapping)"
        )

    print(f"{'➕' if created else '♻️'} Konut varlık kaydedildi → {uavt_kod}")
    return created


def run_transfer_bereket_custom_api(agency_id, service_id, start_date, end_date):
    print("🚀 [Bereket API] Veri çekme işlemi başlatıldı")

    config = TransferServiceConfiguration.objects.get(id=service_id)
    password = AgencyPasswords.objects.get(
        agency_id=agency_id,
        insurance_company=config.insurance_company
    )

    # ✅ Cookie string doğrudan headers'a aktarılıyor
    cookie_string = password.cookie.strip() if password.cookie else ""

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie_string
    }

    # 🧠 submitAjaxEventConfig template render
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

    full_url = config.url
    session = requests.Session()
    session.mount("https://", SSLAdapter())

    try:
        response = session.post(
            full_url,
            headers=headers,
            data=payload,
            timeout=60
        )

        print(f"📦 [Bereket API] Status: {response.status_code}")
        print(f"📄 Yanıt: {response.text[:500]}...")

        # 🎯 Yanıt içinden XLSX yolu çıkar
        match = re.search(r'Output/[\w\-]+\.xlsx', response.text)
        if not match:
            print("❌ XLSX dosya yolu bulunamadı.")
            return response.text

        xlsx_path = match.group(0)

        # 📥 Playwright ile XLSX indir
        xlsx_data = fetch_bereket_excel_with_playwright(xlsx_path, password)

        if xlsx_data:
            print("✅ XLSX veri başarıyla alındı")
            update_bereket_card_info_from_excel(xlsx_data, agency_id)
        else:
            print("⚠️ XLSX veri alınamadı")

        return response.text

    except Exception as e:
        print(f"❌ [Bereket API] Hata: {e}")
        return None

def fetch_bereket_excel_with_playwright(xlsx_path, password_obj):
    full_url = urljoin("https://nareks.bereket.com.tr/report/", xlsx_path)
    print(f"🔗 [Bereket - SSLAdapter] İndirme URL: {full_url}")

    cookies_raw = password_obj.cookie.strip()
    cookie_dict = dict(
        item.strip().split("=", 1) for item in cookies_raw.split(";") if "=" in item
    )

    session = requests.Session()
    session.mount("https://", SSLAdapter())  # 🛡 Legacy TLS destekli adapter

    try:
        response = session.get(full_url, cookies=cookie_dict, timeout=60)
        if response.status_code == 200:
            print("✅ [Bereket] XLSX dosyası başarıyla alındı (SSLAdapter).")
            return response.content
        else:
            print(f"❌ [Bereket] Yanıt kodu: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ [Bereket] XLSX indirme hatası (SSLAdapter): {e}")
        return None



def update_bereket_card_info_from_excel(excel_binary_data, agency_id):


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
            zeyil_raw = row[3] if pd.notna(row[3]) else "0"  # 🧩 Zeyil varsa al, yoksa '0'
            borclu = row[7] if pd.notna(row[7]) else ""
            kartno = row[9] if pd.notna(row[9]) else ""

            poliseno_raw = str(poliseno_raw).strip()
            zeyil_raw = str(zeyil_raw).strip()
            borclu = str(borclu).strip()
            kartno = str(kartno).strip()

            poliseno_clean = ''.join(filter(str.isdigit, poliseno_raw))
            zeyil_clean = ''.join(filter(str.isdigit, zeyil_raw)) or "0"

            print(f"\n🔍 Satır {i}: Poliçe='{poliseno_clean}' | Zeyil='{zeyil_clean}' | Sahip='{borclu}' | Kart='{kartno}'")

            if not poliseno_clean or not kartno:
                print("⚠️ Veri eksik → atlandı")
                continue

            read_count += 1

            policies = Policy.objects.filter(
                PoliceNo=poliseno_clean,
                ZeyilNo=zeyil_clean,
                agency_id=agency_id
            )

            if not policies.exists():
                print(f"❌ Poliçe bulunamadı: {poliseno_clean} / Zeyil={zeyil_clean} | Acente={agency_id}")
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
                        print(f"✅ Güncellendi → {poliseno_clean}-{zeyil_clean} → {borclu} / {kartno}")
                    else:
                        print("ℹ️ Zaten dolu veya veri yok → atlandı")

        except Exception as e:
            print(f"❌ Satır {i} hatası: {e}")

    print(f"\n🎯 Toplam güncellenen kayıt: {updated_count}, okunan geçerli satır: {read_count}")
    return updated_count, read_count


























