import json
import re,requests,xmltodict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from jinja2 import Template

from INSAI.utils import apply_company_field_mapping, create_or_update_customer_generic, generate_referans_no, \
    normalize_decimal
from agency.models import AgencyPasswords
from database.models import CompanyFieldMapping, Customer, Policy, Collection, PaymentPlan, AssetCars, AssetHome, \
    PolicyAssetRelation, CustomerRelationship
from transfer.models import TransferLogDetail, CurrencyMapping
from transfer.views import SSLAdapter, clean_namespaces, get_by_path,\
  parse_date



def transfer_katilim(
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
    print("🚚 [Katılım] Transfer servisi başlatıldı")

    success_count = 0
    updated_count = 0
    total_customers = 0

    password_info = AgencyPasswords.objects.filter(
        agency_id=agency_id,
        insurance_company_id=company_id
    ).first()

    referans_no = generate_referans_no(agency_id, 0, 19)

    context = {
        "web_username": (password_info.web_username or "").strip(),
        "web_password": (password_info.web_password or "").strip(),
        "partaj_code": (password_info.partaj_code or "").strip(),
        "baslangicTarihi": start_date.strftime("%d.%m.%Y"),
        "bitisTarihi": end_date.strftime("%d.%m.%Y"),
        "referance_no": referans_no,
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
            print("💾 DEBUG RESPONSE:", json.dumps(data_dict, indent=2)[:2000])
            print(f"🧚‍♂️ Denenen path: {path.strip()} → {type(police_list)}")
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

    print(f"📄 Toplam poliçe sayısı: {len(police_list)}")

    if mapping_qs is None:
        mapping_qs = CompanyFieldMapping.objects.filter(
            company_id=company_id,
            service_id=service_config.id,
            is_active=True
        ).select_related("key", "parameter")

    for police_data in police_list:
        nested_policies = police_data.get("ListOfPolicies", {}).get("Policy")

        if nested_policies:
            if isinstance(nested_policies, dict):
                nested_policies = [nested_policies]
            for inner_policy in nested_policies:
                process_katilim_policy(
                    agency_id,
                    company_id,
                    inner_policy,
                    mapping_qs,
                    service_config,
                    log,
                    success_count,
                    updated_count,
                    total_customers
                )
            continue

        # Nested değilse doğrudan işle
        process_katilim_policy(
            agency_id,
            company_id,
            police_data,
            mapping_qs,
            service_config,
            log,
            success_count,
            updated_count,
            total_customers
        )

    if log:
        log.created_count = success_count
        log.updated_count = updated_count
        log.customers_created = total_customers
        log.save(update_fields=[
            "created_count", "updated_count", "customers_created"
        ])

    return {
        "success": True,
        "message": f"{len(police_list)} kayıt alındı ve müşteri işlendi",
        "total": len(police_list),
        "customers_created": total_customers
    }


def process_katilim_policy(
    agency_id,
    company_id,
    police_data,
    mapping_qs,
    service_config,
    log,
    success_count_ref,
    updated_count_ref,
    total_customers_ref,
):
    mapped = apply_company_field_mapping(police_data, mapping_qs)
    print("📆 Mapping sonucu:", mapped)

    insured_tc = mapped.get("SigortaliKimlikNo") or mapped.get("SigortaliVergiKimlikNo")
    ettiren_tc = mapped.get("SigortaEttirenKimlikNo") or mapped.get("SigortaEttirenVergiKimlikNo")

    customer_list = []
    if insured_tc and insured_tc != "0":
        customer_list.append({
            "identity_number": insured_tc,
            "full_name": f"{mapped.get('SigortaliAdi', '')} {mapped.get('SigortaliSoyadi', '')}".strip(),
            "birth_date": mapped.get("SigortaliDogumTarihi"),
            "SigortaliCepTelefonu": mapped.get("SigortaliCepTelefonu"),
        })

    if ettiren_tc and ettiren_tc != insured_tc and ettiren_tc != "0":
        customer_list.append({
            "identity_number": ettiren_tc,
            "full_name": f"{mapped.get('SigortaEttirenAdi', '')} {mapped.get('SigortaEttirenSoyadi', '')}".strip(),
            "birth_date": mapped.get("SigortaEttirenDogumTarihi"),
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
        return

    created_ids = create_or_update_customer_generic(agency_id, customer_list)

    primary_customer = None
    for tc in created_ids:
        primary_customer = Customer.objects.filter(identity_number=tc, agency_id=agency_id).first()
        if primary_customer:
            break

    # Diğer sigortalılar
    extra_ids = []
    try:
        diger_json = None
        keyvalue_set = police_data.get("PolicyResultKeySet", {}).get("KeyValueSet", [])
        if isinstance(keyvalue_set, dict):
            keyvalue_set = [keyvalue_set]
        for kv in keyvalue_set:
            if kv.get("KeyName") == "Diğer Sigortalılar":
                diger_json = kv.get("KeyValueList", {}).get("KeyValue")
                break
        if diger_json and primary_customer:
            extra_ids = create_customers_from_other_insured_list(
                agency_id=agency_id,
                insured_json_str=diger_json,
                primary_customer=primary_customer,
                relationship_type_id=7
            ) or []
    except Exception as ex:
        print(f"❌ Diğer sigortalılar müşteri oluşturma hatası: {ex}")

    total_customers_ref += len(set(created_ids + extra_ids))

    # Ana müşteri poliçesi
    try:
        policy_result = create_policy_katilim(
            mapped=mapped,
            agency_id=agency_id,
            company_id=company_id,
            customer=primary_customer,
            insured=primary_customer,
            police_data=police_data,
            log=log,
            service_id=service_config.id
        )
        policy_obj = policy_result.get("policy")
        if isinstance(policy_obj, Policy):
            create_collection_katilim_from_table(mapped, agency_id, policy_obj, primary_customer, primary_customer, company_id)
            create_payment_plans_katilim(policy=policy_obj, table_row=police_data, agency_id=agency_id)
            is_created = policy_result.get("created", False)
            if is_created:
                success_count_ref += 1
            else:
                updated_count_ref += 1
            if log:
                TransferLogDetail.objects.create(
                    log=log,
                    police_no=policy_obj.PoliceNoKombine,
                    status="created" if is_created else "updated",
                    message="Poliçe kaydedildi",
                    record_type="policy",
                    policy=policy_obj,
                    customer_identity_number=primary_customer.identity_number,
                    data_source="katilim"
                )
    except Exception as ex:
        print(f"❌ Poliçe oluşturma hatası: {ex}")

    # Ek sigortalı poliçeleri
    for extra_customer in extra_ids:
        if not extra_customer or extra_customer.identity_number == primary_customer.identity_number:
            continue
        try:
            policy_result = create_policy_katilim(
                mapped=mapped,
                agency_id=agency_id,
                company_id=company_id,
                customer=primary_customer,
                insured=extra_customer,
                police_data=police_data,
                log=log,
                service_id=service_config.id,
                is_extra=True
            )
            policy_obj = policy_result.get("policy")
            if isinstance(policy_obj, Policy):
                create_collection_katilim_from_table(
                    table_row=mapped,
                    agency_id=agency_id,
                    policy_obj=policy_obj,
                    customer=primary_customer,
                    insured=extra_customer,
                    company_id=company_id,
                    is_extra=True
                )
                is_created = policy_result.get("created", False)
                if is_created:
                    success_count_ref += 1
                else:
                    updated_count_ref += 1
                if log:
                    TransferLogDetail.objects.create(
                        log=log,
                        police_no=policy_obj.PoliceNoKombine,
                        status="created" if is_created else "updated",
                        message="Ek sigortalı poliçesi kaydedildi",
                        record_type="policy",
                        policy=policy_obj,
                        customer_identity_number=extra_customer.identity_number,
                        data_source="katilim"
                    )
        except Exception as ex:
            print(f"❌ Ek sigortalı poliçe oluşturma hatası: {ex}")


def create_customers_from_other_insured_list(
    agency_id: int,
    insured_json_str,
    primary_customer: Customer,
    relationship_type_id: int = 7
):
    created_customers = []

    try:
        if isinstance(insured_json_str, list):
            insured_list = insured_json_str
        else:
            insured_list = json.loads(str(insured_json_str).strip())

        if not isinstance(insured_list, list):
            print("⚠️ Beklenen liste değil")
            return []

        for insured in insured_list:
            print("🔍 Diğer sigortalı verisi:", insured)

            tc_raw = insured.get("idnumber")
            tc = str(tc_raw).strip() if tc_raw else ""
            full_name = f"{insured.get('name', '').strip()} {insured.get('surname', '').strip()}".strip()
            gender = insured.get("gender")
            cinsiyet = "E" if gender == "1" else "K" if gender == "2" else None

            if not tc or not full_name:
                print(f"⛔ Geçersiz TC veya ad soyad: tc='{tc}', full_name='{full_name}' → Kayıt atlandı")
                continue

            data = {
                "identity_number": tc,
                "full_name": full_name,
                "birth_date": parse_date(insured.get("birthdate")),
                "DogumYeri": insured.get("birthplace"),
                "Cinsiyet": cinsiyet,
                "BabaAdi": insured.get("fathername"),
                "Uyruk": insured.get("nationalitycode"),
                "RizikoAcikAdres": insured.get("addresS1"),
                "Riziko_il_kod": insured.get("citY1CODE"),
                "agency_id": agency_id,
            }

            try:
                with transaction.atomic():
                    obj, created = Customer.objects.update_or_create(
                        identity_number=tc,
                        agency_id=agency_id,
                        defaults=data
                    )
                    print(f"{'➕' if created else '♻️'} Diğer sigortalı işlendi: {tc} - {full_name}")
                    created_customers.append(obj)

                    CustomerRelationship.objects.get_or_create(
                        from_customer=primary_customer,
                        to_customer=obj,
                        relationship_type_id=relationship_type_id
                    )

            except Exception as ex:
                print(f"❌ Diğer sigortalı kayıt hatası ({tc}): {ex}")

    except Exception as e:
        print(f"❌ JSON parse/general hata: {e}")
        return []

    return created_customers


def create_policy_katilim(mapped, agency_id, company_id, customer, insured, police_data, log=None, service_id=None, is_extra=False):
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
                data_source="katilim"
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
                data_source="katilim"
            )
        return {"policy": None, "collection_created": False, "created": False}

    # ✅ Desenden iptal kontrolü
    iptal_raw = police_data.get("policyStatus")
    if isinstance(iptal_raw, bool):
        is_active = iptal_raw is False
    else:
        iptal_str = str(iptal_raw).strip().lower()
        is_active = iptal_str in ["false", "0", "hayır", "no"]

    if is_active:
        cleaned["PolicyStatus_id"] = 221
        cleaned["AktifMi"] = "1"
    else:
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
                data_source="katilim"
            )

    if is_extra:
        # Ek sigortalılar için prim alanlarını sıfırla
        for prim_field in ["BrutPrim", "BrutPrimTL", "NetPrim", "NetPrimTL", "Komisyon", "KomisyonTL"]:
            if prim_field in cleaned:
                cleaned[prim_field] = 0

    policy, created = Policy.objects.update_or_create(
        PoliceNo=police_no,
        ZeyilNo=zeyil_no,
        YenilemeNo=yenileme_no,
        insured_id=cleaned["insured_id"],
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
            data_source="katilim"
        )

    return {
        "policy": policy,
        "collection_created": not is_extra,
        "created": created
    }



def create_collection_katilim_from_table(
    table_row, agency_id, policy_obj, customer, insured, company_id, is_extra=False
):
    print(
        f"🏷️ [Tahsilat] is_extra={is_extra} | NetPrim={table_row.get('NetPrim')} | Komisyon={table_row.get('Komisyon')} | BrutPrim={table_row.get('BrutPrim')}"
    )

    try:
        exchange_raw = (table_row.get("DovizCinsi") or "").strip()
        currency = CurrencyMapping.objects.filter(
            company_id=company_id,
            raw_value__iexact=exchange_raw,
            is_active=True
        ).first()

        try:
            kur_raw = table_row.get("exchangeRate", "1")
            kur = Decimal(str(kur_raw).replace(",", ".")) if kur_raw else Decimal("1")
        except Exception:
            kur = Decimal("1")

        values = {
            "policy": policy_obj,
            "agency_id": agency_id,
            "customer": customer,
            "insured": insured,
            "PoliceNoKombine": policy_obj.PoliceNoKombine,
            "DovizCinsi": currency.currency_code if currency else None,
            "DovizKuru": kur,
            "TaksitSayisi": int(table_row.get("TaksitSayisi") or 0),  # ✅ düzeltildi
            "OdemeSekli": (table_row.get("OdemeSekli") or "").strip() or None,  # ✅ düzeltildi
            "KKBlokeli": None,
        }

        if not is_extra:
            def safe_decimal(key):
                try:
                    val = table_row.get(key)
                    return Decimal(str(val).replace(",", ".")) if val not in [None, ""] else Decimal("0")
                except Exception:
                    return Decimal("0")

            net = safe_decimal("NetPrim")
            kom = safe_decimal("Komisyon")
            brut = safe_decimal("BrutPrim")

            values.update({
                "NetPrim": net,
                "Komisyon": kom,
                "BrutPrim": brut,
                "NetPrimTL": net * kur,
                "KomisyonPrimTL": kom * kur,
                "BrutPrimTL": brut * kur,
            })
        else:
            values.update({
                "NetPrim": Decimal("0"),
                "Komisyon": Decimal("0"),
                "BrutPrim": Decimal("0"),
                "NetPrimTL": Decimal("0"),
                "KomisyonPrimTL": Decimal("0"),
                "BrutPrimTL": Decimal("0"),
            })

        collection, created = Collection.objects.update_or_create(
            PoliceNoKombine=policy_obj.PoliceNoKombine,
            agency_id=agency_id,
            insured=insured,
            defaults=values
        )

        collection.save()
        print(f"{'➕' if created else '♻️'} Tahsilat kaydedildi → {collection.PoliceNoKombine}")
        return collection

    except Exception as ex:
        print(f"❌ Katılım tahsilat hatası: {ex}")
        return None



def create_payment_plans_katilim(policy, table_row, agency_id):
    print("📌 [Katılım] TAKSİT PLANLARI FONKSİYONU ÇAĞRILDI")

    try:
        installment_data = (
            table_row.get("PriceInfo", {})
            .get("InstallmentDetailInfo", {})
            .get("InstallmentDetail")
        )

        if not installment_data:
            print("⚠️ InstallmentDetail listesi boş")
            return

        if isinstance(installment_data, dict):
            installment_data = [installment_data]

        for idx, inst in enumerate(installment_data):
            try:
                vade = parse_date(inst.get("PaymentDate"))
                tutar = normalize_decimal(inst.get("PaymentAmountTL"))
                sira = inst.get("InstallmentNo") or str(idx + 1)

                if not vade or tutar is None:
                    print(f"❌ Taksit atlandı: {inst}")
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

                print(f"{'✅ [NEW]' if created else '🔄 [UPDATE]'} Taksit: {sira} → {tutar} / {vade}")

            except Exception as inner_ex:
                print(f"❌ Taksit işleme hatası: {inner_ex}")

    except Exception as ex:
        print(f"❌ Taksit planı genel hata: {ex}")

