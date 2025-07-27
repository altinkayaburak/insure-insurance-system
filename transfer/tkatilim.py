import requests,xmltodict,time,json
from decimal import Decimal
from django.template import Template

from INSAI.utils import apply_company_field_mapping, normalize_decimal, create_or_update_customer_generic, SSLAdapter, \
    clean_namespaces, get_by_path, parse_date
from agency.models import AgencyPasswords, AgencyTransferServiceAuthorization
from database.models import CompanyFieldMapping, Policy, Customer, Collection, PaymentPlan, AssetCars, AssetHome, \
    PolicyAssetRelation
from transfer.models import CurrencyMapping
from jinja2 import Template
from django.db.models.functions import Cast
from django.db.models import IntegerField
from django.utils import timezone
from transfer.models import PolicyTransferTemp, TransferLogDetail



def transfer_turkiye_katilim(
    agency_id,
    company_id,
    service_config,
    start_date,
    end_date,
    batch_id,
    password=None,
    log=None
):
    created_count = 0
    updated_count = 0

    print("🚚 [Türkiye Katılım] İlk servis başlatıldı")

    # ⛔ Yetki kontrolü
    is_authorized = AgencyTransferServiceAuthorization.objects.filter(
        agency_id=agency_id,
        transfer_service=service_config,
        is_active=True
    ).exists()

    if not is_authorized:
        raise Exception("⛔ Bu acente için servis yetkisi tanımlı değil!")

    # 🔐 Giriş bilgileri
    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=company_id
    ).first()

    if not password_info or not password_info.web_username:
        raise Exception("⛔ Acente için giriş bilgileri eksik!")

    # 🧩 SOAP template context
    context = {
        "web_username": (password_info.web_username or "").strip(),
        "web_password": (password_info.web_password or "").strip(),
        "partaj_code": (password_info.partaj_code or "").strip(),
        "baslangicTarihi": start_date.strftime(service_config.date_format),
        "bitisTarihi": end_date.strftime(service_config.date_format),
    }

    try:
        soap_body = Template(service_config.soap_template).render(**context)
        print("📤 SOAP Body render tamam")
        print("📨 Giden SOAP Body:\n", soap_body)  # 🔍 Giden istek log
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
        raise Exception("❌ Poliçe listesi bulunamadı")
    if isinstance(police_list, dict):
        police_list = [police_list]

    print(f"📦 Toplam {len(police_list)} kayıt bulundu")

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_config.id,
        is_active=True
    ).select_related("key", "parameter")

    success_count = 0
    for police_data in police_list:
        try:
            mapped = apply_company_field_mapping(police_data, mapping_qs)

            police_no = mapped.get("PoliceNo") or police_data.get("PoliceNo")
            zeyil_no = str(int(mapped.get("ZeyilNo") or 0))
            yenileme_no = str(int(mapped.get("YenilemeNo") or 0))

            if not police_no:
                print("⚠️ PoliceNo boş → atlandı.")
                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no="UNKNOWN",
                        status="skipped",
                        record_type="policy",
                        customer_identity_number=None,
                        data_source="list",
                        message="PoliceNo boş geldi"
                    )
                continue

            if not mapped.get("PoliceTanzimTarihi"):
                raw = mapped.get("TanzimTarihi") or police_data.get("TanzimTarihi")
                mapped["PoliceTanzimTarihi"] = parse_date(raw)
            mapped.pop("TanzimTarihi", None)

            allowed_fields = {f.name for f in PolicyTransferTemp._meta.fields}
            cleaned = {k: v for k, v in mapped.items() if k in allowed_fields}

            cleaned.update({
                "agency_id": agency_id,
                "company_id": company_id,
                "service_id": service_config.id,
                "batch_id": batch_id,
                "status": "pending",
                "source": "turkiye_katilim",
                "raw_data": police_data,
                "ZeyilNo": zeyil_no,
                "YenilemeNo": yenileme_no,
            })

            obj, created = PolicyTransferTemp.objects.update_or_create(
                PoliceNo=police_no,
                ZeyilNo=zeyil_no,
                YenilemeNo=yenileme_no,
                agency_id=agency_id,
                defaults=cleaned
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=obj.PoliceNo,
                    status="created" if created else "updated",
                    record_type="policy",
                    customer_identity_number=mapped.get("SigortaEttirenKimlikNo"),
                    data_source="list",
                    message="Temp tabloya kayıt alındı" if created else "Temp tablo kaydı güncellendi"
                )

            print(f"{'➕' if created else '♻️'} {police_no}-{zeyil_no}-{yenileme_no}")

        except Exception as ex:
            print(f"❌ Kayıt hatası: {ex}")
            if log:
                try:
                    mapped = apply_company_field_mapping(police_data, mapping_qs)
                except:
                    mapped = {}

                TransferLogDetail.objects.create(
                    log=log,
                    police_no=police_data.get("PoliceNo") or mapped.get("PoliceNo") or "UNKNOWN",
                    status="failed",
                    record_type="policy",
                    customer_identity_number=mapped.get("SigortaEttirenKimlikNo") or None,
                    data_source="list",
                    message=f"Hata: {str(ex)[:500]}"
                )

    print(f"✅ [Türkiye Katılım] Tamamlandı → {success_count}/{len(police_list)}")
    return {
    "created": created_count,
    "updated": updated_count,
    "total": len(police_list)
    }



def transfer_turkiye_katilim_detail(
    agency_id,
    company_id,
    service_config,
    batch_id,
    log=None
):
    created_policies = 0
    updated_policies = 0  # ✅ yeni alan
    created_customers = 0
    created_cars = 0
    created_homes = 0

    print(f"📦 [Katılım Detay] Batch: {batch_id} — Detay servis başlıyor...")

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=company_id
    ).first()

    if not password_info:
        print("❌ Şifre bilgisi bulunamadı, işlem iptal.")
        return

    temp_qs = PolicyTransferTemp.objects.filter(
        agency_id=agency_id,
        batch_id=batch_id,
        status="pending"
    ).annotate(
        zeyil_int=Cast("ZeyilNo", IntegerField())
    ).order_by("zeyil_int")

    if not temp_qs.exists():
        print("⚠️ Pending transfer kaydı bulunamadı.")
        return

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_config.id,
        is_active=True
    ).select_related("key", "parameter")

    verified_tc_list = set()
    created_policies = 0
    created_customers = 0
    created_cars = 0
    created_homes = 0

    for temp in temp_qs:
        try:
            print(f"\n🔍 [Detay İstek] {temp.PoliceNo}-{temp.ZeyilNo}-{temp.YenilemeNo}")

            context = {
                "web_username": (password_info.web_username or "").strip(),
                "web_password": (password_info.web_password or "").strip(),
                "partaj_code": (password_info.partaj_code or "").strip(),
                "police_no": temp.PoliceNo,
                "zeyil_no": temp.ZeyilNo or "0",
                "yenileme_no": temp.YenilemeNo or "0",
                "brans": temp.SirketUrunNo or "",
            }

            soap_body = Template(service_config.soap_template).render(**context)
            print("📬 SOAP isteği hazırlanıyor...")

            headers = {"Content-Type": "text/xml; charset=utf-8"}
            if service_config.soap_action:
                headers["SOAPAction"] = service_config.soap_action

            session = requests.Session()
            session.mount("https://", SSLAdapter())
            response = session.post(service_config.url, data=soap_body.encode("utf-8"), headers=headers, timeout=30)
            response.raise_for_status()

            data_dict = clean_namespaces(xmltodict.parse(response.text))

            police_list = None
            for path in (service_config.policy_list_path or "").split("|"):
                police_list = get_by_path(data_dict, path.strip())
                if police_list:
                    break

            if police_list and isinstance(police_list, dict):
                police_list = [police_list]
            elif not police_list:
                print("⚠️ Police listesi doğrudan alınamadı, ana dict ile devam.")
                police_list = [data_dict]

            for item in police_list:
                raw_data = item
                mapped_data = apply_company_field_mapping(item, mapping_qs)

                for tc_key in ["identity_number", "insured_identity_number"]:
                    tc = mapped_data.get(tc_key)
                    if tc and str(tc).isdigit() and len(str(tc)) in [10, 11]:
                        verified_tc_list.add(tc)

                policy_obj, created = process_customer_and_policy(
                    data=raw_data,
                    mapping_qs=mapping_qs,
                    agency_id=agency_id,
                    company_id=company_id,
                    service_config=service_config,
                    log=log
                )

                if policy_obj:
                    if created:
                        created_policies += 1
                    else:
                        updated_policies += 1

                    if policy_obj.customer and not policy_obj.customer.is_verified:
                        created_customers += 1

                    if policy_obj.car_assets.exists():
                        created_cars += 1
                    if policy_obj.home_assets.exists():
                        created_homes += 1

                    if log:
                        TransferLogDetail.objects.create(
                            log=log,
                            police_no=policy_obj.PoliceNoKombine,
                            status="created",
                            record_type="policy",
                            customer_identity_number=policy_obj.customer.identity_number if policy_obj.customer else None,
                            policy=policy_obj,
                            data_source="detail",
                            message="Poliçe ve müşteri başarıyla yazıldı"
                        )

            temp.status = "done"
            temp.last_synced_at = timezone.now()
            temp.save(update_fields=["status", "last_synced_at"])

        except Exception as ex:
            print(f"❌ HATA: {ex}")
            temp.status = "failed"
            temp.error_message = str(ex)[:1000]
            temp.save(update_fields=["status", "error_message"])

            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=temp.PoliceNo or "UNKNOWN",
                    status="failed",
                    record_type="policy",
                    message=str(ex)[:1000],
                    data_source="detail"
                )

    return {
        "total": created_policies + updated_policies,  # ✅ eklendi
        "created": created_policies,
        "customers_created": created_customers,
        "cars_created": created_cars,
        "homes_created": created_homes
    }


def process_customer_and_policy(data, mapping_qs, agency_id, company_id, service_config, log=None):
    customer_data = apply_company_field_mapping(data, mapping_qs)

    ettiren_tc = customer_data.get("SigortaEttirenKimlikNo")
    sigortali_tc = customer_data.get("SigortaliKimlikNo")
    print(f"🧾 Ettiren TC: {ettiren_tc} | Sigortalı TC: {sigortali_tc}")

    musteri_listesi = []

    if ettiren_tc and ettiren_tc != "0":
        musteri_listesi.append({
            "identity_number": ettiren_tc,
            "birth_date": customer_data.get("SigortaEttirenDogumTarihi"),
            "full_name": customer_data.get("SigortaEttirenAdi"),
            "RizikoAcikAdres": customer_data.get("RizikoAcikAdres"),
            "SigortaEttirenCepTelefonu": customer_data.get("SigortaEttirenCepTelefonu"),
        })

    if sigortali_tc and sigortali_tc != "0" and sigortali_tc != ettiren_tc:
        musteri_listesi.append({
            "identity_number": sigortali_tc,
            "birth_date": customer_data.get("SigortaliDogumTarihi"),
            "full_name": customer_data.get("SigortaliAdi"),
            "RizikoAcikAdres": customer_data.get("RizikoAcikAdres"),
            "SigortaliCepTelefonu": customer_data.get("SigortaliCepTelefonu"),
        })

    print(f"📥 Kayıt edilecek müşteri sayısı: {len(musteri_listesi)}")
    created_ids = create_or_update_customer_generic(agency_id, musteri_listesi) or []
    print(f"📦 Dönüş listesi: {created_ids}")

    if log:
        for tc in created_ids:
            TransferLogDetail.objects.create(
                log=log,
                police_no=customer_data.get("PoliceNo") or "UNKNOWN",
                status="created",
                record_type="customer",
                customer_identity_number=tc,
                data_source="detail",
                message="Müşteri kaydedildi"
            )

    ettiren = Customer.objects.filter(identity_number=ettiren_tc, agency_id=agency_id).first()
    sigortali = Customer.objects.filter(identity_number=sigortali_tc, agency_id=agency_id).first() if sigortali_tc and sigortali_tc != ettiren_tc else ettiren

    policy = None
    created = False  # ✅ Buraya ekle
    try:
        if ettiren and sigortali:
            print(f"📝 Poliçe kaydı başlatılıyor → Ettiren: {ettiren.identity_number}, Sigortalı: {sigortali.identity_number}")
            policy, created = create_policy_katilim(
                company_id=company_id,
                service_id=service_config.id,
                policy_data=customer_data,
                agency_id=agency_id,
                customer=ettiren,
                insured=sigortali,
                raw_response_data=data,
                log=log  # ✅ buraya sadece bunu ekliyorsun
            )

            if policy:
                create_or_update_collection_generic(
                    policy=policy,
                    response_data=data,
                    company_id=company_id,
                    service_id=service_config.id
                )

                plaka = customer_data.get("VtPlaka") or customer_data.get("AracPlakaTam")
                sasi = customer_data.get("AracSasiNo")
                if (plaka or sasi):
                    create_asset_car_katilim(policy=policy, insured=sigortali, response_data=customer_data, log=log)

                uavt = customer_data.get("RizikoUavtKod")
                if uavt:
                    create_asset_home_katilim(policy=policy, insured=sigortali, response_data=customer_data, log=log)

                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=policy.PoliceNoKombine,
                        status="created",
                        record_type="policy",
                        customer_identity_number=ettiren_tc,
                        policy=policy,
                        data_source="detail",
                        message="Poliçe ve müşteri başarıyla yazıldı"
                    )

    except Exception as ex:
        print(f"❌ Poliçe veya varlık kaydı hatası → {ex}")
        if log:
            TransferLogDetail.objects.create(
                log=log,
                police_no=customer_data.get("PoliceNo") or "UNKNOWN",
                status="failed",
                record_type="policy",
                customer_identity_number=ettiren_tc,
                data_source="detail",
                message=f"Hata: {str(ex)[:500]}"
            )

    return policy, created





def create_policy_katilim(
    company_id,
    service_id,
    policy_data: dict,
    agency_id,
    customer,
    insured=None,
    raw_response_data=None,
    log=None  # ✅ Log parametresi eklendi
):
    valid_fields = {f.name for f in Policy._meta.get_fields()}

    # 🔧 Alanları parse et
    cleaned = {}
    for k, v in policy_data.items():
        if k in valid_fields:
            if isinstance(v, str) and ("tarih" in k.lower() or "date" in k.lower()):
                parsed = parse_date(v)
                cleaned[k] = parsed if parsed else None
            else:
                cleaned[k] = v

    cleaned["agency_id"] = agency_id
    cleaned["company_id"] = company_id

    zeyil_raw = cleaned.get("ZeyilNo") or "0"
    yenileme_raw = cleaned.get("YenilemeNo") or "0"
    zeyil_no = str(int(zeyil_raw)) if str(zeyil_raw).isdigit() else "0"
    yenileme_no = str(int(yenileme_raw)) if str(yenileme_raw).isdigit() else "0"
    police_no = cleaned.get("PoliceNo")

    if not police_no:
        print("❌ PoliceNo boş, kayıt yapılmadı.")
        return None, False

    cleaned["ZeyilNo"] = zeyil_no
    cleaned["YenilemeNo"] = yenileme_no
    cleaned["PoliceAnaKey"] = f"{police_no}-{yenileme_no}"
    cleaned["customer_id"] = customer.id
    cleaned["insured_id"] = insured.id if insured else customer.id

    iptal_durumu = policy_data.get("PoliceIptalDurumu")
    print(f"🔎 PoliceIptalDurumu ham değer → {iptal_durumu}")

    try:
        iptal_durumu_float = float(str(iptal_durumu).replace(",", "."))
        print(f"🔢 PoliceIptalDurumu float → {iptal_durumu_float}")
    except Exception as parse_err:
        print(f"⚠️ PoliceIptalDurumu parse edilemedi → {iptal_durumu} | Hata: {parse_err}")
        iptal_durumu_float = 0.0

    if iptal_durumu_float == 1.0:
        cleaned["PolicyStatus_id"] = 222  # İptal
        cleaned["AktifMi"] = "0"
        print(f"🚫 İptal kayıt tespit edildi: {cleaned['PoliceAnaKey']}")

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
    else:
        cleaned["PolicyStatus_id"] = 221  # Aktif
        cleaned["AktifMi"] = "1"
        print(f"✅ Aktif poliçe → {cleaned['PoliceAnaKey']}")

    # ✅ Poliçe kaydı
    policy, created = Policy.objects.update_or_create(
        PoliceNo=police_no,
        ZeyilNo=zeyil_no,
        YenilemeNo=yenileme_no,
        agency_id=agency_id,
        defaults=cleaned
    )
    print(f"{'🆕' if created else '♻️'} Poliçe işlendi → {policy.PoliceNoKombine}")

    create_asset_car_katilim(policy, insured, raw_response_data, log=log)
    create_asset_home_katilim(policy, insured, raw_response_data, log=log)

    # ✅ Prim bilgileri
    create_or_update_collection_generic(
        policy=policy,
        response_data=raw_response_data or policy_data,
        company_id=company_id,
        service_id=service_id
    )

    # ✅ Taksit planı bilgileri
    create_or_update_payment_plans_katilim(
        policy=policy,
        response_data=raw_response_data or policy_data,
        agency_id=agency_id
    )

    # ✅ Varlık pasife çekme (iptal + SirketUrunNo = 310)
    try:
        if iptal_durumu_float == 1.0 and str(policy_data.get("SirketUrunNo")) == "310":
            from database.models import AssetCars
            updated_count = AssetCars.objects.filter(policy=policy).update(AktifMi=False)
            print(f"🚗 [PASİF] Araç varlıkları kapatıldı → {updated_count} kayıt.")
    except Exception as ex:
        print(f"⚠️ Varlık pasife çekme hatası → {ex}")

    return policy, created


def create_or_update_policy_generic(
    company_id,
    first_service_id=None,
    detail_service_id=None,
    first_response_data: dict = None,
    detail_response_data: dict = None,
    agency_id=None,
    customer=None,
    insured=None
):

    DATE_FIELDS = {
        "PoliceTanzimTarihi", "PoliceBaslangicTarihi", "PoliceBitisTarihi", "PoliceİptalTarihi",
        "created_at", "updated_at", "delete_date"
    }

    def get_field_with_fallback(detail_fields, first_fields, key, default="0"):
        if detail_fields and key in detail_fields and detail_fields[key] not in [None, ""]:
            return detail_fields[key]
        if first_fields and key in first_fields and first_fields[key] not in [None, ""]:
            return first_fields[key]
        return default

    policy_data = {}
    valid_fields = {f.name for f in Policy._meta.get_fields()}
    first_fields, detail_fields = {}, {}

    if first_service_id and first_response_data:
        mapping_qs_first = CompanyFieldMapping.objects.filter(
            company_id=company_id, service_id=first_service_id, is_active=True
        ).select_related("key", "parameter")
        first_fields = apply_company_field_mapping(first_response_data, mapping_qs_first)
        policy_data.update({k: v for k, v in first_fields.items() if k in valid_fields})

    if detail_service_id and detail_response_data:
        mapping_qs_detail = CompanyFieldMapping.objects.filter(
            company_id=company_id, service_id=detail_service_id, is_active=True
        ).select_related("key", "parameter")
        detail_fields = apply_company_field_mapping(detail_response_data, mapping_qs_detail)
        for k, v in detail_fields.items():
            if k in valid_fields and v not in [None, ""]:
                policy_data[k] = v

    policy_data["ZeyilNo"] = str(int(get_field_with_fallback(detail_fields, first_fields, "ZeyilNo", "0")))
    policy_data["YenilemeNo"] = str(int(get_field_with_fallback(detail_fields, first_fields, "YenilemeNo", "0")))

    for field in DATE_FIELDS:
        if field in policy_data and isinstance(policy_data[field], str):
            parsed = parse_date(policy_data[field])
            if parsed:
                policy_data[field] = parsed

    if not customer:
        identity_number = (
            policy_data.get("identity_number")
            or policy_data.get("SigortaliTcKimlikNo")
            or policy_data.get("MusteriTcKimlikNo")
        )
        if identity_number and agency_id:
            customer = Customer.objects.filter(identity_number=identity_number, agency_id=agency_id).first()
    if not customer:
        print("❌ Kimlik numarası bulunamadı, poliçe kaydında müşteri atanamadı.")
        return None, False
    policy_data["customer_id"] = customer.id

    if insured and insured != customer:
        policy_data["insured_id"] = insured.id

    if not policy_data.get("PoliceNo"):
        print("❌ PoliceNo zorunlu, kayıt yapılmadı!")
        return None, False

    policy_data["company_id"] = company_id  # ✅ BURASI EKLENDİ

    zeyil_no = policy_data["ZeyilNo"]
    policy_data["PoliceTipi"] = 215 if zeyil_no == "0" else 216

    policy, created = Policy.objects.update_or_create(
        PoliceNo=policy_data.get("PoliceNo"),
        ZeyilNo=zeyil_no,
        YenilemeNo=str(policy_data["YenilemeNo"]),
        agency_id=agency_id,
        defaults=policy_data
    )

    print(f"{'✅ [NEW]' if created else '🔄 [UPDATE]'} Poliçe kayıt edildi: {policy.PoliceNoKombine}")

    if not getattr(policy, "user", None) or not getattr(policy, "customer", None):
        print("⚠️ Eksik/Sahipsiz poliçe kaydı: Kullanıcı/şube doldurmalı!")

    return policy, created

def create_or_update_collection_generic(
    policy,
    response_data: dict,
    company_id,
    service_id
):
    if not policy or not policy.PoliceNoKombine:
        print("❌ Geçersiz policy objesi. Collection oluşturulamadı.")
        return None, False

    mapping_qs = CompanyFieldMapping.objects.filter(
        company_id=company_id,
        service_id=service_id,
        is_active=True
    ).select_related("key")

    valid_fields = {f.name for f in Collection._meta.get_fields()}
    collection_data = {}
    mapped_fields = apply_company_field_mapping(response_data, mapping_qs)

    # 💱 DovizCinsi normalize et
    doviz = None
    raw_mapped_doviz = mapped_fields.get("DovizCinsi")
    if raw_mapped_doviz:
        doviz = CurrencyMapping.objects.filter(
            company_id=company_id,
            raw_value=str(raw_mapped_doviz).strip()
        ).values_list("currency_code", flat=True).first()
        if doviz:
            print(f"💱 Normalized mapped DovizCinsi → {raw_mapped_doviz} → {doviz}")
            mapped_fields["DovizCinsi"] = doviz
        else:
            print(f"⚠️ CurrencyMapping eşleşmesi bulunamadı: {raw_mapped_doviz}")

    kayit_tipi = (mapped_fields.get("KayitTipi") or "").strip().upper()
    print(f"🧾 [KayitTipi] → {kayit_tipi}")

    decimal_fields = [
        "BrutPrim", "BrutPrimTL", "NetPrim", "NetPrimTL",
        "Komisyon", "KomisyonPrimTL", "ZeyilKomisyonu",
        "EkKomisyon", "GHP", "GiderVergisi",
        "THGF", "YSV", "SGKPayi"
    ]
    negate_fields = decimal_fields.copy()

    for field in decimal_fields:
        val = mapped_fields.get(field)
        norm = normalize_decimal(val)

        if norm is not None:
            print(f"🧾 [{field}] ← [{field}] → {val} → Norm: {norm}")

        if kayit_tipi == "I" and field in negate_fields and norm is not None:
            print(f"⚠️ Negatife çevriliyor → {field}: {norm} → {-1 * norm}")
            norm *= -1

        collection_data[field] = norm

    # 🧮 TL değerleri her durumda doviz_kuru ile çarpılarak yazılmalı
    doviz_kuru = collection_data.get("DovizKuru") or Decimal("1.00")
    try:
        for ana, tl in [("BrutPrim", "BrutPrimTL"), ("NetPrim", "NetPrimTL"), ("Komisyon", "KomisyonPrimTL")]:
            ana_val = collection_data.get(ana)
            if ana_val is not None:
                tl_val = round(ana_val * doviz_kuru, 2)
                collection_data[tl] = tl_val
                print(f"💱 {tl} = {ana} * {doviz_kuru} → {tl_val}")
    except Exception as e:
        print(f"⚠️ TL hesaplama hatası: {e}")

    # 🧩 Diğer alanlar
    for key, val in mapped_fields.items():
        if key not in decimal_fields and key in valid_fields:
            collection_data[key] = val

    # 💱 DovizCinsi mapping sonrası override edilir
    if doviz:
        collection_data["DovizCinsi"] = doviz

    # 📌 Ana alanlar
    collection_data["PoliceNoKombine"] = policy.PoliceNoKombine
    collection_data["agency_id"] = policy.agency_id
    collection_data["customer_id"] = policy.customer_id
    collection_data["insured_id"] = policy.insured_id if policy.insured_id else policy.customer_id
    collection_data["policy_id"] = policy.id

    obj, created = Collection.objects.update_or_create(
        PoliceNoKombine=policy.PoliceNoKombine,
        policy=policy,
        defaults=collection_data
    )
    obj.save()  # 🔐 Mutlaka ekle — override edilmiş save() metodunu tetikler

    print(f"{'✅ [NEW]' if created else '🔄 [UPDATE]'} Collection kaydı: {obj}")
    return obj, created





def create_or_update_payment_plans_katilim(policy, response_data, agency_id):
    print("📌 TAKSİT PLAN BAŞLIYOR...")

    opl_data = response_data.get("Opl")
    print("🔎 Opl içeriği:", opl_data)

    if not opl_data or "TaksitArr" not in opl_data or not opl_data["TaksitArr"]:
        print("⚠️ TaksitArr bulunamadı → Opl.TaksitArr.Taksit")
        return

    taksit_list = opl_data["TaksitArr"].get("Taksit")
    if not taksit_list:
        print("⚠️ Taksit listesi boş → Opl.TaksitArr.Taksit")
        return

    if isinstance(taksit_list, dict):
        taksit_list = [taksit_list]

    print(f"📦 {len(taksit_list)} taksit bulundu")

    for idx, taksit in enumerate(taksit_list):
        vade_raw = taksit.get("VadeTarihi")
        tutar_raw = taksit.get("Planlanan")
        sira = taksit.get("Durum") or taksit.get("TaksitNo") or str(idx + 1)

        vade = parse_date(vade_raw)
        tutar = normalize_decimal(tutar_raw)

        if not vade or tutar is None:
            print(f"❌ Taksit atlandı: VadeTarihi={vade_raw}, Tutar={tutar_raw}")
            continue

        taksit_data = {
            "agency": policy.agency,
            "PoliceNoKombine": policy.PoliceNoKombine,
            "TaksitTutar": tutar
        }

        obj, created = PaymentPlan.objects.update_or_create(
            policy=policy,
            TaksitSirasi=str(sira),
            TaksitVadeTarihi=vade,
            defaults=taksit_data
        )

        print(f"{'✅ [NEW]' if created else '🔄 [UPDATE]'} Taksit: {obj.TaksitSirasi} → {tutar} / {vade}")


def create_asset_car_katilim(policy, insured, response_data, log=None):
    print("🚗 [Araç Varlık] Kayıt işlemi başlıyor...")

    sasi_no = response_data.get("AracSasiNo")
    plaka = response_data.get("VtPlaka") or response_data.get("AracPlakaTam")

    if not sasi_no and not plaka:
        print("⚠️ Araç bilgisi yok, kayıt atlandı.")
        return

    fields = {
        "policy": policy,
        "agency": policy.agency,
        "insured": insured,
        "PoliceNoKombine": policy.PoliceNoKombine,
        "AracPlakailKodu": response_data.get("AracPlakailKodu"),
        "AracPlakaNo": response_data.get("AracPlakaNo"),
        "AracPlakaTam": plaka.replace(" ", "") if plaka else None,
        "AracTescilSeriKod": response_data.get("AracTescilSeriKod"),
        "AracTescilSeriNo": response_data.get("AracTescilSeriNo"),
        "AracKullanimTarzi": response_data.get("AracKullanimTarzi"),
        "TramerAracTarz": response_data.get("TramerAracTarz"),
        "EGMUstCins": response_data.get("EGMUstCins"),
        "EGMAltCins": response_data.get("EGMAltCins"),
        "AracModelYili": response_data.get("AracModelYili"),
        "AracBirlikKodu": response_data.get("AracBirlikKodu"),
        "AracMarkaKodu": response_data.get("AracMarkaKodu"),
        "AracTipKodu": response_data.get("AracTipKodu"),
        "AracMarkaAdi": response_data.get("AracMarkaAdi"),
        "AracTipAdi": response_data.get("AracTipAdi"),
        "AracMotorNo": response_data.get("AracMotorNo"),
        "AracSasiNo": sasi_no,
        "AracKisiSayisi": response_data.get("AracKisiSayisi"),
        "AracRenk": response_data.get("AracRenk"),
        "AracMotorGucu": response_data.get("AracMotorGucu"),
        "AracSilindirHacmi": response_data.get("AracSilindirHacmi"),
        "AracYakitTipi": response_data.get("AracYakitTipi"),
        "AracTrafigeCikisTarihi": parse_date(response_data.get("AracTrafigeCikisTarihi")),
        "AracTescilTarihi": parse_date(response_data.get("AracTescilTarihi")),
        "AracTrafikKademe": response_data.get("AracTrafikKademe"),
        "AracKaskoKademe": response_data.get("AracKaskoKademe"),
        "AktifMi": True
    }

    lookup = {
        "insured": insured,
        "agency": policy.agency,
    }
    if sasi_no:
        lookup["AracSasiNo"] = sasi_no
    else:
        lookup["AracPlakaTam"] = plaka.replace(" ", "") if plaka else None

    obj, created = AssetCars.objects.update_or_create(
        insured=insured,
        AracSasiNo=sasi_no,
        agency=policy.agency,  # 👈 tenant kontrolü eklendi
        defaults=fields
    )

    print(f"{'🆕' if created else '♻️'} Araç kaydı işlendi → {obj}")

    PolicyAssetRelation.objects.get_or_create(policy=policy, asset_car=obj)


    if created:
        if log:
            log.cars_created += 1
            log.save(update_fields=["cars_created"])
        elif hasattr(policy, "log") and policy.log:
            policy.log.cars_created += 1
            policy.log.save(update_fields=["cars_created"])


def create_asset_home_katilim(policy, insured, response_data, log=None):
    response_data = response_data.get("Alanlar", response_data)

    print("🏠 [Konut Varlık] Kayıt işlemi başlıyor...")

    uavt_kod = response_data.get("RizikoUavtKod") or response_data.get("UavtAdresKodu") or response_data.get("UavtRizikoAdresKodu")
    print(f"🏠 Gelen UAVT → {uavt_kod}")  # ⬅️ BURAYI EKLE

    if not uavt_kod:
        print("⚠️ Konut bilgisi yok, kayıt atlandı.")
        return

    fields = {
        "RizikoDaskPoliceNo": response_data.get("RizikoDaskPoliceNo"),
        "RizikoDaskYenilemeNo": response_data.get("RizikoDaskYenilemeNo"),
        "RizikoUavtKod": response_data.get("RizikoUavtKod") or response_data.get("UavtAdresKodu") or response_data.get(
            "UavtRizikoAdresKodu"),
        "Riziko_il_kod": response_data.get("Riziko_il_kod") or response_data.get("UavtIlKodu") or response_data.get(
            "UavtRizikoIlKodu"),
        "Riziko_ilce_kodu": response_data.get("Riziko_ilce_kodu") or response_data.get(
            "UavtIlceKodu") or response_data.get("UavtRizikoIlceKodu"),
        "Riziko_Koy_kodu": response_data.get("Riziko_Koy_kodu") or response_data.get(
            "UavtKoyKodu") or response_data.get("UavtRizikoKoyKodu"),
        "Riziko_mahalle_kodu": response_data.get("Riziko_mahalle_kodu") or response_data.get(
            "UavtMahalleKodu") or response_data.get("UavtRizikoMahalleKodu"),
        "Riziko_csbm_kodu": response_data.get("Riziko_csbm_kodu") or response_data.get(
            "UavtCSBMKodu") or response_data.get("UavtRizikoCSBMKodu"),
        "Riziko_bina_kodu": response_data.get("Riziko_bina_kodu") or response_data.get(
            "UavtBinaKodu") or response_data.get("UavtRizikoBinaNoKodu"),
        "Riziko_bina_adi": response_data.get("Riziko_bina_adi") or response_data.get(
            "RizikoEvApartmanAdi") or response_data.get("UavtRizikoEvApartmanAdi"),
        "Riziko_daire_kodu": response_data.get("Riziko_daire_kodu") or response_data.get(
            "UavtDaireKodu") or response_data.get("UavtRizikoDaireKodu"),
        "Riziko_daire_no": response_data.get("Riziko_daire_no") or response_data.get(
            "RizikoEvDaire") or response_data.get("UavtRizikoEvDaire"),
        "RizikoDaireYuzOlcumu": response_data.get("RizikoDaireYuzOlcumu"),
        "RizikoDaskinsaYili": response_data.get("RizikoDaskinsaYili"),
        "RizikoDaskKullanimSekli": response_data.get("RizikoDaskKullanimSekli"),
        "RizikoDaskKatAraligi": response_data.get("RizikoDaskKatAraligi"),
        "RizikoDaskYapiTarzi": response_data.get("RizikoDaskYapiTarzi"),
        "RizikoDaskHasarDurumu": response_data.get("RizikoDaskHasarDurumu"),
        "RizikoSigortaEttireninSifati": response_data.get("RizikoSigortaEttireninSifati"),
        "RizikoKonum": response_data.get("RizikoKonum"),
        "RizikoKonutTipi": response_data.get("RizikoKonutTipi"),
        "RizikoAda": response_data.get("RizikoAda"),
        "RizikoPafta": response_data.get("RizikoPafta"),
        "RizikoParsel": response_data.get("RizikoParsel"),
        "Riziko_il_ad": response_data.get("Riziko_il_ad") or response_data.get("UavtRizikoEvIli"),
        "Riziko_ilce_adi": response_data.get("Riziko_ilce_adi") or response_data.get("UavtRizikoEvIlce"),
        "Riziko_koy_adi": response_data.get("Riziko_koy_adi") or response_data.get("UavtRizikoEvSemt"),
        "Riziko_mahalle_adi": response_data.get("Riziko_mahalle_adi") or response_data.get("UavtRizikoEvMahalle"),
        "Riziko_sokak_adi": response_data.get("Riziko_sokak_adi") or response_data.get("UavtRizikoEvSokak"),
        "RehinliAlacakliVar": response_data.get("RehinliAlacakliVar"),
        "DainiMurtehinAdi": response_data.get("DainiMurtehinAdi") or response_data.get(
            "DainiMurtehin") or response_data.get("BankaAdi"),
        "DaskBitisTarihi": parse_date(response_data.get("DaskBitisTarihi")),
    }

    lookup = {
        "insured": insured,
        "agency": policy.agency,
        "RizikoUavtKod": uavt_kod
    }

    defaults = {
        "policy": policy,
        "PoliceNoKombine": policy.PoliceNoKombine,
        "AktifMi": True
    }

    obj, created = AssetHome.objects.get_or_create(
        **lookup,
        defaults=defaults
    )

    updated = False
    for field, value in fields.items():
        if value not in [None, "", {}]:
            current_val = getattr(obj, field, None)
            if current_val in [None, "", {}] or field == "DaskBitisTarihi":
                setattr(obj, field, value)
                print(f"✏️ Güncellendi: {field} → {value}")
                updated = True
        else:
            print(f"⛔ Atlandı (boş): {field}")

    if updated:
        obj.save()
        print("💾 Kayıt güncellendi.")
    else:
        print("🔍 Güncellenecek alan yok.")

    PolicyAssetRelation.objects.get_or_create(policy=policy, asset_home=obj)

    if created:
        if log:
            log.homes_created += 1
            log.save(update_fields=["homes_created"])
        elif hasattr(policy, "log") and policy.log:
            policy.log.homes_created += 1
            policy.log.save(update_fields=["homes_created"])

    print(f"{'🆕' if created else '♻️'} Konut kaydı işlendi → {obj}")
