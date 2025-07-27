import json,ssl,random,requests
from django.db.models import Q
from django.db import transaction
from offer.tasks import run_offer_service_async
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_GET
from requests.adapters import HTTPAdapter
from agency.models import AgencyOfferServiceAuthorization, AgencyPasswords
from database.models import Customer, Key, KeyParameters, ServiceConfiguration, InsuranceCompany, \
    OfferServiceConfiguration, PolicyBranch, TravelCountry
from offer.models import ProposalUUIDMapping, OfferFixedValue, ProposalKey, CustomerCompany, ProposalDetails, Proposal
from offer.utils import get_keys_with_parameters, FORM_KEY_MAPPING, PRODUCT_BUNDLE_MAP
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Case, When, IntegerField, Value
from datetime import datetime


class SSLAdapter(HTTPAdapter):
    """Legacy SSL bağlantılarını ve sertifika doğrulamasını devre dışı bırakır."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


def set_ettiren(request):
    try:
        data = json.loads(request.body)
        ettiren = data.get("ettiren")
        if ettiren:
            request.session["sigorta_ettiren"] = ettiren
            return JsonResponse({"success": True})
        return JsonResponse({"success": False, "error": "Eksik veri"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

@login_required
def open_proposal_form(request):
    form_type = request.GET.get("form_type")
    customer_key = request.GET.get("key")
    product_code = request.GET.get("product_code")
    sigorta_ettiren = request.session.get("sigorta_ettiren")  # <-- Session'dan oku!

    if not form_type or not product_code or not customer_key:
        return HttpResponseBadRequest("Eksik parametre")

    proposal_id = get_next_proposal_id()
    blocks = FORM_KEY_MAPPING.get(form_type, {})

    def get_keys_with_parameters_sorted(key_ids):
        key_objs = get_keys_with_parameters(key_ids)
        priority_ids = [998, 576, 999]
        for key in key_objs:
            params = list(key.get('parameters', []))
            priority_params = [p for p in params if p.get('ParameterID') in priority_ids]
            other_params = sorted(
                [p for p in params if p.get('ParameterID') not in priority_ids],
                key=lambda x: x.get('ParameterName')
            )
            key['parameters'] = priority_params + other_params
        return key_objs

    all_keys = {block: get_keys_with_parameters_sorted(key_ids) for block, key_ids in blocks.items()}

    customer = Customer.objects.filter(customer_key=customer_key).first()
    companies = InsuranceCompany.objects.all().order_by('name')

    # 👇 Önce birincil, yoksa herhangi bir telefon
    primary_phone = None
    if customer:
        contact = customer.contacts.filter(contact_type='phone', is_primary=True).order_by('id').first()
        if not contact:
            contact = customer.contacts.filter(contact_type='phone').order_by('id').first()
        if contact:
            primary_phone = contact.value

    priority_country_ids = [998, 576, 999]
    all_countries = list(TravelCountry.objects.all())
    priority_countries = [c for c in all_countries if c.country_code in priority_country_ids]
    other_countries = sorted(
        [c for c in all_countries if c.country_code not in priority_country_ids],
        key=lambda x: x.country_name
    )
    countries = priority_countries + other_countries

    return render(request, f"offer/forms/{form_type}.html", {
        "proposal_id": proposal_id,
        "form_type": form_type,
        "product_code": product_code,
        "customer": customer,
        "customer_key": customer_key,
        "blocks": all_keys,
        "companies": companies,
        "countries": countries,
        "primary_phone": primary_phone,
        "selected_ettiren": sigorta_ettiren,
        "gender": customer.Cinsiyet if customer else None,
        "age": f"{customer.age:03}" if customer and customer.age is not None else "",  # ✅ burası eklendi
    })

def get_next_proposal_id():
    while True:
        random_id = random.randint(100000000, 999999999)  # 🔥 9 haneli
        if not ProposalUUIDMapping.objects.filter(proposal_id=random_id).exists():
            return random_id

@require_GET
def get_offer_fixed_values(request):
    try:
        product_code = request.GET.get("product_code")
        if not product_code:
            return JsonResponse({"error": "product_code gerekli"}, status=400)

        items = OfferFixedValue.objects.filter(product_code=product_code)
        data = [
            {
                "key_id": item.key_id,
                "value": item.value,
                "multiply_with_key_id": item.multiply_with_key_id
            }
            for item in items
        ]
        return JsonResponse({"success": True, "data": data})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})




def get_field_from_form(form_data, key):
    return form_data.get(f"key_{key}") or form_data.get(str(key)) or None

@require_http_methods(["POST"])
def create_proposal_entry(request):
    try:
        data = json.loads(request.body)

        proposal_id = data.get("proposal_id")
        product_code = data.get("product_code")
        form_type = data.get("form_type")
        agency_id = data.get("agency_id")
        user_id = data.get("user_id")
        branch_id = data.get("branch_id")
        customer_id = data.get("customer_id")
        form_data = data.get("form_data", {})

        start_date = get_field_from_form(form_data, 55)
        end_date = get_field_from_form(form_data, 56)
        property_identifier = get_field_from_form(form_data, 102) or get_field_from_form(form_data, 77)

        # === property_info ÜRÜNE GÖRE ===
        if str(product_code) in ["102", "103"]:
            property_info = get_field_from_form(form_data, 200) or ""
        elif str(product_code) in ["104", "105"]:
            property_info = {
                "belge_seri": get_field_from_form(form_data, 79)
            }
        else:
            property_info = ""

        if start_date and isinstance(start_date, str):
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except Exception:
                pass
        if end_date and isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except Exception:
                pass

        created_details = 0
        proposal_ids = {}
        uuids = {}
        parent_obj = None

        bundle_codes = PRODUCT_BUNDLE_MAP.get(str(product_code), [str(product_code)])

        for idx, bundle_code in enumerate(bundle_codes):
            pid = proposal_id if idx == 0 else get_next_proposal_id()

            with transaction.atomic():
                proposal, _ = Proposal.objects.update_or_create(
                    proposal_id=pid,
                    defaults={
                        "product_code": bundle_code,
                        "form_type": form_type,
                        "agency_id": agency_id,
                        "created_by_id": user_id,
                        "branch_id": branch_id,
                        "customer_id": customer_id,
                        "policy_start_date": start_date,
                        "policy_end_date": end_date,
                        "property_identifier": property_identifier,
                        "property_info": property_info,
                        "parent_proposal": parent_obj if idx > 0 else None
                    }
                )

                if idx == 0:
                    parent_obj = proposal

                mapping, _ = ProposalUUIDMapping.objects.get_or_create(proposal_id=proposal.proposal_id)
                proposal_ids[str(bundle_code)] = proposal.proposal_id
                uuids[str(bundle_code)] = str(mapping.uuid)

                authorized_services = AgencyOfferServiceAuthorization.objects.filter(
                    agency_id=agency_id,
                    offer_service__product_code=str(bundle_code),
                    offer_service__is_active=True,
                    is_active=True
                ).select_related("offer_service", "offer_service__insurance_company")

                for auth in authorized_services:
                    offer_service = auth.offer_service
                    insurance_company = offer_service.insurance_company

                    detail = ProposalDetails.objects.create(
                        proposal=proposal,
                        proposal_code=proposal.proposal_id,
                        agency_id=agency_id,
                        user_id=user_id,
                        insurance_company=insurance_company,
                        product_code=bundle_code,
                        sub_product_code=offer_service.sub_product_code,
                        status='pending'
                    )
                    run_offer_service_async.delay(detail.id, form_data or {})
                    created_details += 1

                for key_id, value in form_data.items():
                    try:
                        int_key_id = int(key_id)
                        ProposalKey.objects.update_or_create(
                            proposal_id=pid,
                            product_code=bundle_code,
                            key_id=int_key_id,
                            defaults={
                                "key_value": value,
                                "agency_id": agency_id,
                                "user_id": user_id
                            }
                        )
                    except ValueError:
                        continue

        return JsonResponse({
            "success": True,
            "details_created": created_details,
            "proposal_ids": proposal_ids,
            "uuids": uuids
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})



@login_required(login_url='/login/')
def get_customer_companies_by_identity(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Sadece POST istekleri kabul edilir."}, status=405)

    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")

        if not identity_number:
            return JsonResponse({"success": False, "error": "Kimlik numarası gerekli."}, status=400)

        entries = CustomerCompany.objects.filter(identity_number=identity_number)

        result = []
        for entry in entries:
            result.append({
                "company_id": entry.company.id,  # <-- burada id dönüyoruz
                "customer_no": entry.customer_no
            })

        return JsonResponse({
            "success": True,
            "data": result
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@login_required(login_url='/login/')
def create_proposal_details_from_authorized_services(proposal):
    """
    Yeni oluşturulan bir proposal için, acentenin yetkili olduğu
    teklif servislerini kontrol eder ve her biri için boş ProposalDetails kaydı oluşturur.
    """
    agency = proposal.agency
    product_code = str(proposal.product_code)

    authorized_services = AgencyOfferServiceAuthorization.objects.filter(
        agency=agency,
        offer_service__product_code=product_code,
        offer_service__is_active=True
    ).select_related("offer_service", "offer_service__insurance_company")

    created_count = 0
    for auth in authorized_services:
        offer_service = auth.offer_service

        ProposalDetails.objects.create(
            proposal=proposal,
            proposal_code=proposal.proposal_id,  # ✅ dış sistem proposal_id
            agency=agency,
            user=proposal.created_by,
            insurance_company=offer_service.insurance_company,
            product_code=offer_service.product_code,
            sub_product_code=offer_service.sub_product_code,
            status='pending'
        )
        created_count += 1

    return created_count

@login_required(login_url='/login/')
def send_soap_request(url, soap_body, soap_action):
    from offer.views import SSLAdapter
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": soap_action,
    }

    session = requests.Session()
    session.mount("https://", SSLAdapter())  # 🔒 Sertifika doğrulama devre dışı
    response = session.post(url, data=soap_body, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

@login_required(login_url='/login/')
def check_proposal_status(request, proposal_id):
    """
    Bu teklif için ProposalDetails varsa artık tekrar servis çağrılmamalı.
    """
    already_exists = ProposalDetails.objects.filter(proposal_id=proposal_id).exists()
    return JsonResponse({"refresh_needed": not already_exists})

@login_required(login_url='/login/')
def proposal_detail_page(request, uuid):
    mapping = get_object_or_404(ProposalUUIDMapping, uuid=uuid)
    ana_proposal_id = mapping.proposal_id  # DASK veya ilk ürün

    # Ana teklifin bilgileri
    proposal = get_object_or_404(Proposal, proposal_id=ana_proposal_id)
    product_code = str(proposal.product_code)

    # --- Dinamik Bundle Map ---
    parent_id = proposal.parent_proposal_id or proposal.id
    bundle_proposals = Proposal.objects.filter(
        Q(parent_proposal_id=parent_id) | Q(id=parent_id),
        is_deleted=False
    )

    bundle_codes = list(bundle_proposals.values_list("product_code", flat=True).distinct())

    # 🧭 Yeni proposal_map → her ürünün proposal_id ve uuid’si
    proposal_map = {}
    for pr in bundle_proposals:
        map_obj = ProposalUUIDMapping.objects.filter(proposal_id=pr.proposal_id).first()
        proposal_map[str(pr.product_code)] = {
            "proposal_id": pr.proposal_id,
            "uuid": str(map_obj.uuid) if map_obj else None
        }

    # --- Key mapping ---
    keys = ProposalKey.objects.filter(proposal_id=ana_proposal_id)
    key_data = {}
    for k in keys:
        key_obj = Key.objects.filter(KeyID=k.key_id).first()
        key_name = key_obj.KeyName if key_obj else ""
        value = k.key_value
        param_name = None
        # Eğer key bir tarih ise
        if key_name.lower().endswith("tarihi") or key_name.lower().endswith("date"):
            try:
                if value and "-" in value:
                    d = datetime.strptime(value, "%Y-%m-%d")
                    value = d.strftime("%d.%m.%Y")
            except Exception:
                pass
        if value and value.isdigit():
            param = KeyParameters.objects.filter(KeyID=k.key_id, ParameterID=value).select_related(
                "ParameterID").first()
            if param and param.ParameterID:
                param_name = param.ParameterID.ParameterName
        customer_key = None
        if key_name in ["SigortaEttirenKimlikNo", "SigortaliKimlikNo"] and value:
            customer = Customer.objects.filter(identity_number=value, agency_id=proposal.agency_id).first()
            if customer:
                customer_key = customer.customer_key
                print(f"🔍 key_name: {key_name}, value: {value}, matched_customer: {customer}")

        key_data[k.key_id] = {
            "key_id": k.key_id,
            "key_name": key_name,
            "value": value,
            "parameter_name": param_name,
            "customer_key": customer.customer_key if customer else None  # 🟡 BUNU EKLE
        }

    # Detaylar
    details = ProposalDetails.objects.filter(proposal__proposal_id=ana_proposal_id) \
        .select_related("insurance_company", "proposal", "proposal__agency") \
        .annotate(
        premium_sort=Case(
            When(premium__gt=0, then=Value(0)),
            When(premium=0, then=Value(1)),
            When(premium__isnull=True, then=Value(2)),
            default=Value(3),
            output_field=IntegerField()
        )
    ) \
        .order_by('premium_sort', 'premium')

    pdf_services = ServiceConfiguration.objects.filter(service_name="PdfWs")
    pdf_service_map = {s.insurance_company_id: s.id for s in pdf_services}

    # 🟡 PDF butonları için agency_code (partaj_code) eşlemesi
    pdf_agency_code_map = {}
    for d in details:
        agency_id = d.agency_id or (d.proposal.agency_id if d.proposal else None)
        company_id = d.insurance_company_id
        partaj_code = None

        if agency_id and company_id:
            partaj_code = AgencyPasswords.objects.filter(
                agency_id=agency_id,
                insurance_company_id=company_id
            ).values_list("partaj_code", flat=True).first()

        if partaj_code:
            pdf_agency_code_map[str(d.id)] = partaj_code  # ✅ string key

    # === Dinamik sekmeler: PolicyBranch.name ve teklif (premium dolu) sayısı ile ===
    product_tabs = []
    for code in bundle_codes:
        branch = PolicyBranch.objects.filter(code=code).first()
        label = branch.name if branch else f"Ürün {code}"
        pr = Proposal.objects.filter(product_code=code, created_by=proposal.created_by).order_by('-id').first()
        offer_count = 0
        if pr:
            offer_count = ProposalDetails.objects.filter(
                proposal=pr,
                premium__isnull=False
            ).exclude(premium=0).count()
        product_tabs.append({
            "code": str(code),
            "label": label,
            "offer_count": offer_count
        })

    # HATALI YERİ DIŞARI AL
    product_proposals = []
    for tab in product_tabs:
        code = tab["code"]
        label = tab["label"]
        proposal_id = proposal_map.get(code, {}).get("proposal_id", "")
        product_proposals.append({"label": label, "proposal_id": proposal_id})

        print("🧾 PDF Agency Code MAP:", pdf_agency_code_map)

    return render(request, 'offer/proposal_detail.html', {
        "proposal_id": ana_proposal_id,
        "uuid": uuid,
        "data": key_data,
        "details": details,
        "proposal_map": json.dumps({str(k): v["proposal_id"] for k, v in proposal_map.items()}),
        "pdf_service_map": pdf_service_map,
        "pdf_agency_code_map": json.dumps(pdf_agency_code_map),
        "product_code": product_code,
        "product_tabs": product_tabs,
        "product_proposals": product_proposals,
    })


@login_required(login_url='/login/')
def get_proposal_details(request, proposal_id):
    # 1. PDF servislerini mapping olarak hazırla
    pdf_services = ServiceConfiguration.objects.filter(service_name="PdfWs")
    pdf_service_map = {s.insurance_company_id: s.id for s in pdf_services}

    # 2. Teklif detaylarını çek
    details = ProposalDetails.objects.filter(
        proposal__proposal_id=proposal_id
    ).select_related("insurance_company").annotate(
        premium_sort=Case(
            When(premium__gt=0, then=Value(0)),
            When(premium=0, then=Value(1)),
            When(premium__isnull=True, then=Value(2)),
            default=Value(3),
            output_field=IntegerField()
        )
    ).order_by('premium_sort', 'premium')

    offer_cards = ""
    for idx, d in enumerate(details):
        logo_url = f"/static/logos/{d.insurance_company.company_code}.png"
        badge = '<div class="offer-badge badge-secondary">EN UYGUN</div>' if idx == 0 and d.premium and d.premium > 0 else ''

        # Dinamik olarak sub_product_description getir
        description = None
        if d.sub_product_code:
            offer_conf = OfferServiceConfiguration.objects.filter(
                product_code=d.product_code,
                sub_product_code=d.sub_product_code,
                insurance_company=d.insurance_company
            ).first()
            if offer_conf and offer_conf.sub_product_description:
                description = offer_conf.sub_product_description

        features = f'<span class="feature-tag"><i class="bi bi-check-circle"></i> <strong>{description or d.sub_product_code or d.product_code}</strong></span>'

        if d.premium is not None and d.premium > 0:
            price_html = f"""
                <div class="offer-price">
                    <div class="price-amount">₺{d.premium:.2f}</div>
                    <div class="price-period">yıllık</div>
                </div>
            """
        else:
            price_html = """
                <div class="offer-price">
                    <span class="badge badge-warning">Beklemede</span>
                </div>
            """
        service_id = pdf_service_map.get(d.insurance_company.id, "")

        offer_cards += f"""
        <div class="offer-card loading-state"
             data-company-id="{d.insurance_company.id}"
             data-product-code="{d.product_code}"
             data-sub-product-code="{d.sub_product_code or ''}"
             data-proposal-id="{proposal_id}">
            <div class="loading-overlay">
                <img src="/static/img/loading.svg" alt="Yükleniyor..." class="loading-spinner">
            </div>
            <div class="offer-logo">
                <img src="{logo_url}" alt="{d.insurance_company.name}" style="height: 40px;">
            </div>
            <div class="offer-content">
                <div class="offer-header">
                    <div class="offer-company">{d.insurance_company.name}</div>
                    {badge}
                </div>
                <div class="offer-number">Teklif No: {d.offer_number or '-'}</div>
                <div class="offer-features">{features}</div>
            </div>
            {price_html}
            <div class="offer-actions">
                <button class="btn-primary"><i class="bi bi-cart"></i> Satın Al</button>
                <div class="action-links">
                    <span class="action-link revise-btn"
                          data-company-id="{d.insurance_company.id}"
                          data-product-code="{d.product_code}"
                          data-offer-id="{d.id}"
                          title="Revize Et">
                      <i class="bi bi-pencil-square" style="pointer-events: none;"></i>
                    </span>
                    <span class="action-link pdf-btn"
                          data-service-id="{service_id}"
                          data-policy="{d.offer_number or ''}"
                          data-pdf-type="teklif"
                          data-product-code="{d.product_code}" 
                          title="PDF İndir">
                        <i class="bi bi-file-earmark-text"></i>
                    </span>
                    <span class="action-link" title="Detaylar"><i class="bi bi-info-circle"></i></span>
                </div>
            </div>
        </div>
        """

    # --- Yeni: Tüm tablar için teklif (offer) sayıları ---
    proposal = Proposal.objects.filter(proposal_id=proposal_id).first()
    user = proposal.created_by if proposal else None

    # Ürünün bundle mapini bul (ör: DASK+KONUT varsa ikisi birden)
    product_code = str(proposal.product_code) if proposal else ""
    bundle_codes = PRODUCT_BUNDLE_MAP.get(product_code, [product_code])

    counts = {}
    for code in bundle_codes:
        pr = Proposal.objects.filter(product_code=code, created_by=user).order_by('-id').first()
        if pr:
            cnt = ProposalDetails.objects.filter(
                proposal=pr,
                premium__isnull=False
            ).exclude(premium=0).count()
            counts[str(code)] = cnt
        else:
            counts[str(code)] = 0

    # Aktif ürün için teklif sayısı
    offer_count = details.filter(premium__isnull=False).exclude(premium=0).count()

    return JsonResponse({
        "html": offer_cards,
        "count": offer_count,   # aktif tab
        "counts": counts        # tüm tablar (tab kodu: teklif sayısı)
    })















