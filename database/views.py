from django.contrib.auth.decorators import login_required
from django.db.models.functions import Coalesce
from django.shortcuts import render
from datetime import datetime, date, timedelta
from django_ratelimit.decorators import ratelimit
from agency.models import AgencyPasswords, AgencyServiceAuthorization, AgencyCompany
from gateway.models import ProposalServiceLog
from offer.models import ProposalKey, Proposal, ProposalUUIDMapping, CompanyRevisableKey
from .models import Key, Parameter, KeyParameters, Products, Customer, RelationshipType, generate_customer_key, \
    CustomerRelationship, PolicyMainBranch, PolicyBranch, Policy, OfferServiceConfiguration, CompanyParameterMapping, \
    CustomerContact, TransferServiceConfiguration, Collection, PaymentPlan, AssetCars, AssetHome, PolicyAssetRelation
from .forms import KeyForm,ParameterForm,InsuranceCompanyForm
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.shortcuts import get_object_or_404
from .models import ServiceConfiguration, InsuranceCompany
import json
from django.template.loader import render_to_string
from django.db.models import Q, OuterRef, Subquery, F, Value, Sum
import xml.dom.minidom
from database.models import CookieLog
from cookie.tasks import update_all_cookies_for_agency
from django.shortcuts import render, redirect


def get_page_range(current_page, total_pages, delta=2):
    """
    Sayfa numaraları için aralık oluşturur.
    Örnek: [1, '...', 4, 5, 6, '...', 10]
    """
    left = max(current_page - delta, 1)
    right = min(current_page + delta, total_pages)

    range_list = []
    if left > 1:
        range_list.append(1)
        if left > 2:
            range_list.append("...")

    for i in range(left, right + 1):
        range_list.append(i)

    if right < total_pages:
        if right < total_pages - 1:
            range_list.append("...")
        range_list.append(total_pages)

    return range_list

@login_required
def key_list(request):
    query = request.GET.get('q', '')
    keys = Key.objects.all().order_by('KeyName')

    if query:
        keys = keys.filter(
            Q(KeyName__icontains=query) |
            Q(KeyID__iexact=query)  # ← Burada KeyID kullanılıyor!
        )

    paginator = Paginator(keys, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Her key için parametre olup olmadığını belirle
    from database.models import KeyParameters
    for key in page_obj:
        key.has_parameters = KeyParameters.objects.filter(KeyID=key.KeyID).exists()

    page_range = get_page_range(page_obj.number, paginator.num_pages)
    form = KeyForm()

    return render(request, 'database/keyslist.html', {
        'page_obj': page_obj,
        'form': form,
        'query': query,
        'page_range': page_range,
    })


@login_required
def api_key_list(request):
    query = request.GET.get('q', '')
    keys = Key.objects.filter(IsActive=True).order_by('KeyName')

    if query:
        keys = keys.filter(
            Q(KeyName__icontains=query) |
            Q(KeyID__iexact=query)
        )

    data = [{"id": k.KeyID, "name": k.KeyName, "desc": k.Description or ""} for k in keys]
    return JsonResponse(data, safe=False)

@login_required
@csrf_exempt
def save_key(request, key_id=None):
    if request.method == 'POST':
        if key_id:
            try:
                key = Key.objects.get(pk=key_id)
            except Key.DoesNotExist:
                return JsonResponse({'error': 'Key not found'}, status=404)
        else:
            key = Key()

        key.KeyName = request.POST.get("KeyName")
        key.Description = request.POST.get("Description")
        key.InputType = request.POST.get("InputType")
        key.MinLength = request.POST.get("MinLength") or None
        key.MaxLength = request.POST.get("MaxLength") or None
        key.RegexPattern = request.POST.get("RegexPattern")
        key.VisibleIfKey = request.POST.get("VisibleIfKey") or None
        key.VisibleIfValue = request.POST.get("VisibleIfValue") or None
        key.IsActive = request.POST.get("IsActive") == "true"
        key.save()

        return JsonResponse({'success': True})

    # 🚨 POST dışında başka istek gelirse hata dön
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def key_detail(request, key_id):
    try:
        key = Key.objects.get(pk=key_id)
        data = {
            "id": key.KeyID,
            "name": key.KeyName,
            "description": key.Description,
            "input_type": key.InputType,
            "min_length": key.MinLength,
            "max_length": key.MaxLength,
            "regex": key.RegexPattern,
            "visible_if_key": key.VisibleIfKey,
            "visible_if_value": key.VisibleIfValue,
            "is_active": key.IsActive,
        }
        return JsonResponse(data)
    except Key.DoesNotExist:
        return JsonResponse({"error": "Key bulunamadı"}, status=404)

@login_required
def get_parameters_for_key(request):
    key_id = request.GET.get('key_id')
    if not key_id:
        return JsonResponse([], safe=False)

    from .models import KeyParameters, Parameter
    param_ids = KeyParameters.objects.filter(KeyID=key_id).values_list('ParameterID', flat=True)
    parameters = Parameter.objects.filter(ParameterID__in=param_ids, IsActive=True).order_by('ParameterName')
    data = [{"id": p.ParameterID, "name": p.ParameterName} for p in parameters]
    return JsonResponse(data, safe=False)

#----------------------------------------------
@login_required
def parameters_list(request):
    query = request.GET.get('q', '')
    parameters = Parameter.objects.all()

    if query:
        parameters = parameters.filter(ParameterName__icontains=query)

    paginator = Paginator(parameters, 10)  # Sayfa başına 10 kayıt
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Sayfa aralığını oluştur
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'database/parameters_list.html', {
        'page_obj': page_obj,
        'query': query,
        'page_range': page_range,
    })

@login_required
def add_parameters(request):
    if request.method == 'POST':
        data = request.POST
        key_id = data.get('KeyID')
        parameter_names = data.getlist('ParameterName[]')
        default_values = data.getlist('DefaultValue[]')

        # Key'i bul
        key = get_object_or_404(Key, pk=key_id)

        # Her bir parametre için işlem yap
        for name, default in zip(parameter_names, default_values):
            if name.strip():  # Boş olmayan parametreleri kaydet
                # Parameter tablosuna ekle
                parameter, created = Parameter.objects.get_or_create(
                    ParameterName=name.strip(),
                    defaults={'DefaultValue': default.strip(), 'IsActive': True}
                )
                # KeyParameters tablosuna ekle
                KeyParameters.objects.get_or_create(KeyID=key, ParameterID=parameter)

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def edit_parameter(request, param_id):
    parameter = get_object_or_404(Parameter, pk=param_id)

    if request.method == 'POST':
        form = ParameterForm(request.POST, instance=parameter)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def search_keys(request):
    query = request.GET.get('q', '')
    if query:
        keys = Key.objects.filter(KeyName__icontains=query)[:10]  # İlk 10 sonucu al
        data = [{'KeyID': key.KeyID, 'KeyName': key.KeyName} for key in keys]
        return JsonResponse({'keys': data})
    return JsonResponse({'keys': []})  # Boş sorgu için boş JSON dön

@require_POST
@login_required
def delete_key_parameter(request, key_id, parameter_id):
    try:
        from .models import KeyParameters
        deleted, _ = KeyParameters.objects.filter(KeyID=key_id, ParameterID=parameter_id).delete()
        if deleted:
            return JsonResponse({"success": True})
        return JsonResponse({"success": False, "error": "Kayıt bulunamadı"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

#------------------------------------------------
@login_required
def insurance_company_list(request):
    query = request.GET.get('q', '')
    companies = InsuranceCompany.objects.all()

    if query:
        companies = companies.filter(name__icontains=query)

    paginator = Paginator(companies, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Aynı fonksiyon burada da kullanılıyor
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'database/insurance_company_list.html', {
        'page_obj': page_obj,
        'query': query,
        'page_range': page_range,
    })

@login_required
def save_insurance_company(request):
    if request.method == 'POST':
        company_id = request.POST.get('id')
        if company_id:
            company = get_object_or_404(InsuranceCompany, id=company_id)
            form = InsuranceCompanyForm(request.POST, instance=company)
        else:
            form = InsuranceCompanyForm(request.POST)

        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def search_insurance_companies(request):
    query = request.GET.get('q', '')
    if query:
        companies = InsuranceCompany.objects.filter(name__icontains=query)[:10]
        data = [{'id': company.id, 'name': company.name} for company in companies]
        return JsonResponse({'companies': data})
    return JsonResponse({'companies': []})

#--------------------------------------------------
@login_required
def product_list(request):
    query = request.GET.get('q', '')
    products = Products.objects.select_related('company', 'main_branch', 'branch').all()

    if query:
        products = products.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
        )

    paginator = Paginator(products, 10)

    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'database/products.html', {
        'page_obj': page_obj,
        'query': query,
        'page_range': page_range,
        'companies': InsuranceCompany.objects.all(),
        'main_branches': PolicyMainBranch.objects.all(),
        'branches': PolicyBranch.objects.all(),
    })

@login_required
def add_product(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        name = request.POST.get('name')
        company_id = request.POST.get('company_id')
        branch_id = request.POST.get('branch_id')
        main_branch_id = request.POST.get('main_branch_id')

        try:
            Products.objects.create(
                code=code,
                name=name,
                company_id=company_id,
                branch_id=branch_id or None,
                main_branch_id=main_branch_id or None,
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

@login_required
def update_product(request):
    if request.method == 'POST':
        product_id = request.POST.get('id')
        code = request.POST.get('code')
        name = request.POST.get('name')
        company_id = request.POST.get('company_id')
        branch_id = request.POST.get('branch_id')
        main_branch_id = request.POST.get('main_branch_id')

        try:
            product = Products.objects.get(id=product_id)
            product.code = code
            product.name = name
            product.company_id = company_id
            product.branch_id = branch_id or None
            product.main_branch_id = main_branch_id or None
            product.save()
            return JsonResponse({'success': True})
        except Products.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Ürün bulunamadı'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})

#--------------------------------------------------
@login_required
@require_GET
def get_policy_branches(request):
    branches = PolicyBranch.objects.select_related('main_branch').all()
    data = [
        {"id": b.code, "label": f"{b.code} - {b.name}"}
        for b in branches
    ]
    return JsonResponse(data, safe=False)

#--------------------------------------------------

@login_required
def offer_service_configurations_view(request):
    query = request.GET.get('q', '')
    services = OfferServiceConfiguration.objects.select_related('insurance_company').all()

    if query:
        services = services.filter(
            Q(service_name__icontains=query) |
            Q(product_code__icontains=query) |
            Q(sub_product_code__icontains=query) |
            Q(sub_product_description__icontains=query) |
            Q(soap_action__icontains=query) |
            Q(insurance_company__name__icontains=query)
        )

    paginator = Paginator(services, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'database/offer_service_configurations.html', {
        'page_obj': page_obj,
        'query': query,
        'page_range': paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1),
    })

@login_required
@require_http_methods(["GET"])
def get_offer_services(request):
    services = OfferServiceConfiguration.objects.select_related('insurance_company').all()
    result = []
    for s in services:
        result.append({
            "id": s.id,
            "insurance_company": s.insurance_company.id,
            "insurance_company_name": s.insurance_company.name,
            "product_code": s.product_code,
            "sub_product_code": s.sub_product_code,
            "sub_product_description": s.sub_product_description,
            "service_name": s.service_name,
            "url": s.url,
            "soap_action": s.soap_action,
            "soap_template": s.soap_template
        })
    return JsonResponse(result, safe=False)

@login_required
@require_http_methods(["GET"])
def get_offer_service_detail(request, service_id):
    s = get_object_or_404(OfferServiceConfiguration, id=service_id)
    return JsonResponse({
        "id": s.id,
        "insurance_company": s.insurance_company.id,
        "product_code": s.product_code,
        "sub_product_code": s.sub_product_code,
        "sub_product_description": s.sub_product_description,
        "service_name": s.service_name,
        "url": s.url,
        "soap_action": s.soap_action,
        "soap_template": s.soap_template,
        "request_template": s.request_template,
    })

@login_required
@require_http_methods(["POST", "PUT"])
def create_or_update_offer_service(request, service_id=None):
    data = json.loads(request.body)
    company = get_object_or_404(InsuranceCompany, id=data["insurance_company"])
    product_branch = get_object_or_404(PolicyBranch, code=data["product_code"])

    if request.method == "POST":
        s = OfferServiceConfiguration.objects.create(
            insurance_company=company,
            product_code=product_branch.code,
            sub_product_code=data.get("sub_product_code", ""),
            sub_product_description=data.get("sub_product_description", ""),
            service_name=data["service_name"],
            url=data["url"],
            soap_action=data["soap_action"],
            soap_template=data.get("soap_template", "")
        )
    else:
        s = get_object_or_404(OfferServiceConfiguration, id=service_id)
        s.insurance_company = company
        s.product_code = product_branch.code
        s.sub_product_code = data.get("sub_product_code", "")
        s.sub_product_description = data.get("sub_product_description", "")
        s.service_name = data["service_name"]
        s.url = data["url"]
        s.soap_action = data["soap_action"]
        # DİKKAT: GÜNCELLERKEN ŞABLONA DOKUNMA!
        # s.soap_template = data.get("soap_template", "")
        s.save()

    return JsonResponse({"success": True, "id": s.id})


@login_required
@require_http_methods(["PATCH"])
def update_offer_soap_template(request, service_id):
    s = get_object_or_404(OfferServiceConfiguration, id=service_id)
    data = json.loads(request.body)

    if "soap_template" in data:
        s.soap_template = data["soap_template"]
    if "request_template" in data:
        s.request_template = data["request_template"]

    s.save()
    return JsonResponse({"success": True})

#--------------------------------------------------

@login_required
@require_http_methods(["GET"])
def get_service_detail(request, service_id):
    service = get_object_or_404(ServiceConfiguration, id=service_id)
    return JsonResponse({
        "id": service.id,
        "insurance_company": service.insurance_company.id,
        "service_name": service.service_name,
        "url": service.url,
        "soap_action": service.soap_action,
        "soap_template": service.soap_template,
        "request_template": service.request_template,  # ✅ eklendi
    })

@login_required
def service_configurations_view(request):
    query = request.GET.get('q', '')
    services = ServiceConfiguration.objects.select_related('insurance_company').all()

    if query:
        services = services.filter(
            Q(service_name__icontains=query) |
            Q(url__icontains=query) |
            Q(soap_action__icontains=query) |
            Q(insurance_company__name__icontains=query)  # ilişkili tablodan da arama
        )

    paginator = Paginator(services, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'database/service_configurations.html', {
        'page_obj': page_obj,
        'query': query,
        'page_range': paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1),
    })

def get_companies(request):
    companies = InsuranceCompany.objects.filter(is_active=True).values("id", "name")
    return JsonResponse(list(companies), safe=False)


@require_http_methods(["GET"])
def get_services(request):
    services = ServiceConfiguration.objects.all()
    result = []
    for s in services:
        result.append({
            "id": s.id,
            "insurance_company": s.insurance_company.id if s.insurance_company else None,
            "service_name": s.service_name,
            "url": s.url,
            "soap_action": s.soap_action,
            "soap_template": s.soap_template,
        })
    return JsonResponse(result, safe=False)

@require_http_methods(["POST", "PUT"])
def create_or_update_service(request, service_id=None):
    data = json.loads(request.body)
    company_id = data.get("insurance_company")
    company = get_object_or_404(InsuranceCompany, id=company_id)

    if request.method == "POST":
        service = ServiceConfiguration.objects.create(
            insurance_company=company,
            service_name=data["service_name"],
            url=data["url"],
            soap_action=data["soap_action"],
            soap_template=data.get("soap_template", "")
        )
    else:
        service = get_object_or_404(ServiceConfiguration, id=service_id)
        service.insurance_company = company
        service.service_name = data["service_name"]
        service.url = data["url"]
        service.soap_action = data["soap_action"]
        # >>> BU SATIRI SİL: service.soap_template = data.get("soap_template", "")
        service.save()

    return JsonResponse({"success": True, "id": service.id})

@require_http_methods(["PATCH"])
def update_template(request, service_id):
    service = get_object_or_404(ServiceConfiguration, id=service_id)
    data = json.loads(request.body)
    service.soap_template = data.get("soap_template", "")
    service.request_template = data.get("request_template", "")  # ✅ eklendi
    service.save()
    return JsonResponse({"success": True})


#--------------------------------------------------

@login_required
def transfer_service_list_view(request):
    query = request.GET.get("q", "").strip()
    transfer_services = TransferServiceConfiguration.objects.select_related("insurance_company").filter(is_active=True)

    if query:
        transfer_services = transfer_services.filter(
            Q(service_name__icontains=query) |
            Q(soap_action__icontains=query) |
            Q(insurance_company__name__icontains=query)
        )

    paginator = Paginator(transfer_services.order_by("-updated_at"), 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "database/transfer_service_configurations.html", {
        "page_obj": page_obj,
        "query": query,
        "page_range": paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1),
    })

@login_required
@require_http_methods(["GET"])
def get_transfer_services(request):
    services = TransferServiceConfiguration.objects.select_related('insurance_company').filter(is_active=True)

    result = []
    for s in services:
        result.append({
            "id": s.id,
            "insurance_company_id": s.insurance_company.id,
            "insurance_company_name": s.insurance_company.name,
            "service_name": s.service_name,
            "url": s.url,
            "soap_action": s.soap_action,
            "soap_template": s.soap_template,
            "policy_list_path": s.policy_list_path,
            "error_field_path": s.error_field_path,
            "requires_detail_service": s.requires_detail_service,
            "has_full_detail_in_first_service": s.has_full_detail_in_first_service,
        })

    return JsonResponse(result, safe=False)

@login_required
@require_http_methods(["POST", "PUT"])
def create_or_update_transfer_service(request, service_id=None):
    data = json.loads(request.body)
    company = get_object_or_404(InsuranceCompany, id=data["insurance_company"])
    detail_service_id = data.get("detail_service")

    detail_service = None
    if detail_service_id:
        detail_service = get_object_or_404(TransferServiceConfiguration, id=detail_service_id)

    if request.method == "POST":
        s = TransferServiceConfiguration.objects.create(
            insurance_company=company,
            service_name=data["service_name"],
            url=data["url"],
            soap_action=data.get("soap_action", ""),
            soap_template=data.get("soap_template", ""),
            policy_list_path=data.get("policy_list_path", ""),
            error_field_path=data.get("error_field_path", ""),
            requires_detail_service=data.get("requires_detail_service", True),
            has_full_detail_in_first_service=data.get("has_full_detail_in_first_service", False),
            detail_service=detail_service,
            is_active=data.get("is_active", True)
        )
    else:
        s = get_object_or_404(TransferServiceConfiguration, id=service_id)
        s.insurance_company = company
        s.service_name = data["service_name"]
        s.url = data["url"]
        s.soap_action = data.get("soap_action", "")
        s.policy_list_path = data.get("policy_list_path", "")
        s.error_field_path = data.get("error_field_path", "")
        s.requires_detail_service = data.get("requires_detail_service", True)
        s.has_full_detail_in_first_service = data.get("has_full_detail_in_first_service", False)
        s.detail_service = detail_service
        s.is_active = data.get("is_active", True)
        s.save()

    return JsonResponse({"success": True, "id": s.id})


@login_required
@require_http_methods(["PATCH"])
def update_transfer_soap_template(request, service_id):
    s = get_object_or_404(TransferServiceConfiguration, id=service_id)
    data = json.loads(request.body)
    s.soap_template = data.get("soap_template", "")
    s.request_template = data.get("request_template", "")  # 👈 bu satırı ekle
    s.save()
    return JsonResponse({"success": True})



@login_required
@require_http_methods(["GET"])
def get_transfer_service_by_id(request, service_id):
    s = get_object_or_404(TransferServiceConfiguration, id=service_id)
    return JsonResponse({
        "id": s.id,
        "insurance_company": s.insurance_company.id,
        "service_name": s.service_name,
        "url": s.url,
        "soap_action": s.soap_action,
        "soap_template": s.soap_template,
        "request_template": s.request_template,  # ✅ yeni eklendi
        "policy_list_path": s.policy_list_path,
        "error_field_path": s.error_field_path,
        "requires_detail_service": s.requires_detail_service,
        "has_full_detail_in_first_service": s.has_full_detail_in_first_service,
        "detail_service_id": s.detail_service.id if s.detail_service else None,
        "is_active": s.is_active,
    })



#--------------------------------------------------
@ratelimit(key='user', rate='5/m', method='POST', block=False)
@login_required(login_url='/login/')
def get_customer(request):
    try:
        data = json.loads(request.body)
        identity_number = data.get("identity_number")
        primary_customer_key = data.get("primary_customer_key")

        agency_id = request.user.agency_id
        customer = Customer.objects.filter(identity_number=identity_number, agency_id=agency_id).first()

        if not customer:
            return JsonResponse({"success": False, "message": "Müşteri bulunamadı."})

        phone_number = ""
        contact = customer.contacts.filter(contact_type='phone', is_primary=True).order_by('id').first()
        if contact:
            phone_number = contact.value

        relation_exists = False
        if primary_customer_key:
            primary_customer = Customer.objects.filter(customer_key=primary_customer_key, agency_id=agency_id).first()
            if primary_customer:
                relation_exists = CustomerRelationship.objects.filter(
                    (Q(from_customer=primary_customer, to_customer=customer) |
                     Q(from_customer=customer, to_customer=primary_customer))
                ).exists()

        return JsonResponse({
            "success": True,
            "redirect_url": f"/database/customer/?key={customer.customer_key}",
            "full_name": customer.full_name or "",
            "birth_date": customer.birth_date.strftime("%Y-%m-%d") if customer.birth_date else "",
            "phone_number": phone_number,
            "customer_key": customer.customer_key,
            "relation_exists": relation_exists,
            "is_verified": customer.is_verified,
            "type": customer.type if hasattr(customer, "type") and customer.type is not None else 1
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)



@login_required
def save_or_update_customer(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            identity_number = data.get("identity_number")
            birth_date = data.get("birth_date")
            full_name = data.get("full_name")
            phone_number = data.get("phone_number")
            incoming_is_verified = data.get("is_verified", True)

            agency_id = request.user.agency_id
            user_id = request.user.id

            customer = Customer.objects.filter(identity_number=identity_number, agency_id=agency_id).first()
            created = False

            if not customer:
                is_verified = incoming_is_verified
                try:
                    if birth_date:
                        if "-" in birth_date:
                            dob = datetime.strptime(birth_date, "%Y-%m-%d").date()
                        else:
                            dob = datetime.strptime(birth_date, "%d.%m.%Y").date()
                        today = date.today()
                        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                        if age < 18:
                            is_verified = False
                except Exception as e:
                    print("❗ Doğum tarihi parse hatası:", e)

                customer = Customer.objects.create(
                    identity_number=identity_number,
                    birth_date=birth_date,
                    full_name=full_name,
                    agency_id=agency_id,
                    user_id=user_id,
                    is_verified=is_verified,
                )
                created = True
            else:
                is_verified = customer.is_verified or incoming_is_verified
                customer.birth_date = birth_date
                customer.full_name = full_name
                customer.user_id = user_id
                customer.is_verified = is_verified
                customer.save()

            if phone_number:
                contact, contact_created = CustomerContact.objects.get_or_create(
                    customer=customer,
                    value=phone_number,
                    contact_type='phone',
                    defaults={
                        'label': 'main',
                        'is_verified': True,
                        'is_primary': True
                    }
                )
                if not contact_created:
                    contact.label = 'main'
                    contact.is_verified = True
                    contact.is_primary = True
                    contact.save()
                CustomerContact.objects.filter(
                    customer=customer,
                    contact_type='phone',
                    is_primary=True
                ).exclude(id=contact.id).update(is_primary=False)

            return JsonResponse({
                "success": True,
                "created": created,
                "customer_id": customer.id,
                "customer_key": customer.customer_key,
                "redirect_url": f"/database/customer/?key={customer.customer_key}",
            })

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"error": "Sadece POST desteklenir"}, status=405)



@login_required
def customer_detail(request):
    customer_key = request.GET.get("key")
    if not customer_key:
        return render(request, "customer.html", {"error": "Müşteri anahtarı belirtilmedi."})

    customer = get_object_or_404(Customer, customer_key=customer_key)
    contact = customer.contacts.filter(contact_type='phone').order_by('id').first()
    primary_phone = contact.value if contact else None

    # 👇👇👇  İLİŞKİ VAR MI?  👇👇👇
    has_relation = CustomerRelationship.objects.filter(
        Q(from_customer=customer) | Q(to_customer=customer)
    ).exists()

    return render(request, "customer.html", {
        "customer": customer,
        "primary_phone": primary_phone,
        "has_primary_phone": bool(primary_phone),
        "has_relation": has_relation,  # <--- Bunu ekle!
    })


@login_required
def customer_search_page(request):
    customers = Customer.objects.filter(is_verified=True).order_by('-created_at')[:7]
    return render(request, "AddCustomer.html", {
        "customers": customers
    })

#-------------------------------------------------------

@login_required
def save_customer_with_relationship(request):
    if request.method != "POST":
        return JsonResponse({"error": "Sadece POST desteklenir"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))

        identity_number = data.get("identity_number")
        birth_date = data.get("birth_date")
        phone_number = data.get("phone_number")
        full_name = data.get("full_name")
        relationship_type_id = data.get("relationship_type_id")
        primary_customer_key = data.get("primary_customer_key")
        is_verified = data.get("is_verified", False)

        # ✅ Giriş yapan kullanıcının acentesi alınır
        agency_id = request.user.agency_id
        user_id = request.user.id

        related_customer = Customer.objects.filter(
            identity_number=identity_number,
            agency_id=agency_id
        ).first()

        if not related_customer:
            related_customer = Customer.objects.create(
                identity_number=identity_number,
                birth_date=birth_date,
                full_name=full_name,
                agency_id=agency_id,
                user_id=user_id,
                is_verified=is_verified
            )
        else:
            updated = False
            if not related_customer.birth_date and birth_date:
                related_customer.birth_date = birth_date
                updated = True
            if not related_customer.full_name and full_name:
                related_customer.full_name = full_name
                updated = True
            if updated:
                related_customer.save()

        if phone_number:
            contact, contact_created = CustomerContact.objects.get_or_create(
                customer=related_customer,
                value=phone_number,
                contact_type='phone',
                defaults={
                    'label': 'main',
                    'is_verified': True,
                    'is_primary': True
                }
            )
            if not contact_created:
                contact.label = 'main'
                contact.is_verified = True
                contact.is_primary = True
                contact.save()

            CustomerContact.objects.filter(
                customer=related_customer,
                contact_type='phone',
                is_primary=True
            ).exclude(id=contact.id).update(is_primary=False)

        from_customer = Customer.objects.get(customer_key=primary_customer_key, agency_id=agency_id)
        from_customer.is_verified = True
        from_customer.save()

        relationship_type = RelationshipType.objects.get(id=relationship_type_id)

        if CustomerRelationship.objects.filter(
            from_customer=from_customer,
            to_customer=related_customer,
            relationship_type=relationship_type
        ).exists():
            return JsonResponse({"success": False, "error": "Bu müşteri ile bu ilişki zaten mevcut!"})

        CustomerRelationship.objects.create(
            from_customer=from_customer,
            to_customer=related_customer,
            relationship_type=relationship_type
        )

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def get_relationship_types(request):
    try:
        if request.method == "POST":
            data = json.loads(request.body)
            from_id = data.get("from_identity_number", "")
            to_id = data.get("to_identity_number", "")

            if not from_id or not to_id:
                return JsonResponse({"success": False, "error": "Kimlik numaraları eksik."}, status=400)

            from_type = "individual" if len(from_id) == 11 else "corporate"
            to_type = "individual" if len(to_id) == 11 else "corporate"
            applicable_key = f"{from_type}_to_{to_type}"

            # 🔍 Filtreleme
            types = RelationshipType.objects.filter(
                is_active=True,
                applicable_to=applicable_key
            ).order_by("name")
        else:
            # GET gibi durumlarda hepsini getir (isteğe bağlı)
            types = RelationshipType.objects.filter(is_active=True).order_by("name")

        data = [{"id": t.id, "name": t.name, "applicable_to": t.applicable_to} for t in types]
        return JsonResponse({"success": True, "data": data})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@login_required
def get_customer_relationships(request):
    try:
        data = json.loads(request.body)
        customer_key = data.get("customer_key")
        page_number = data.get("page", 1)
        response_mode = data.get("mode", "html")  # 🟡 varsayılan "html"

        customer = Customer.objects.get(customer_key=customer_key)

        relationships = CustomerRelationship.objects.select_related(
            "from_customer", "to_customer", "relationship_type"
        ).filter(
            Q(from_customer=customer) | Q(to_customer=customer)
        ).order_by("-created_at")

        paginator = Paginator(relationships, 10)
        page_obj = paginator.get_page(page_number)

        if response_mode == "json":
            relationship_list = []
            for rel in page_obj:
                person = rel.to_customer if rel.from_customer == customer else rel.from_customer

                # Telefon numarasını CustomerContact'tan çek
                contact = person.contacts.filter(contact_type="phone", is_primary=True).first()
                phone_number = contact.value if contact else ""

                relationship_list.append({
                    "id": rel.id,
                    "full_name": person.full_name,
                    "identity_number": person.identity_number,
                    "phone_number": phone_number,
                    "birth_date": person.birth_date.strftime('%Y-%m-%d') if person.birth_date else "",
                    "relationship_type": rel.relationship_type.name if rel.relationship_type else ""
                })

            return JsonResponse({"success": True, "relationships": relationship_list})

        else:
            html = render_to_string("partials/tab_relationships.html", {
                "page_obj": page_obj,
                "relationships": page_obj,
                "customer": customer
            })
            return JsonResponse({"success": True, "html": html})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_POST
def delete_customer_relationship(request, relation_id):
    try:
        relation = CustomerRelationship.objects.get(pk=relation_id)
        relation.delete()
        return JsonResponse({"success": True, "message": "İlişki silindi."})
    except CustomerRelationship.DoesNotExist:
        return JsonResponse({"success": False, "error": "İlişki bulunamadı."}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

#-------------------------------------------------------

@login_required
def policy_list_page(request):
    return render(request, "database/policy_list.html")


@login_required
def get_policy_list_json(request):
    user = request.user
    agency_id = user.agency_id

    query = request.GET.get("q", "").strip()
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    company_id = request.GET.get("company_id")
    branch_id = request.GET.get("branch_id")

    # Eğer hiçbir filtre yoksa boş döndür
    if not any([query, start_date_str, end_date_str, company_id, branch_id]):
        return JsonResponse({"data": []})

    # PDF servis haritası
    pdf_service_map = {
        s.insurance_company_id: s.id
        for s in ServiceConfiguration.objects.filter(service_name="PdfWs")
    }

    latest_collection = Collection.objects.filter(policy_id=OuterRef('pk')).order_by('-id')

    base_queryset = Policy.objects.filter(agency_id=agency_id).select_related(
        'customer', 'insured', 'user__branch'
    ).annotate(
    company_name=Coalesce(
        Subquery(
            InsuranceCompany.objects.filter(id=OuterRef('company_id')).values('name')[:1]
        ),
        Value('Tanımsız'),
    ),
    user_name=F('user__first_name'),
    user_surname=F('user__last_name'),
    user_branch=F('user__branch__name'),

    # ✅ TL Bazlı Tutarlar
    brut_prim=Subquery(latest_collection.values('BrutPrimTL')[:1]),
    net_prim=Subquery(latest_collection.values('NetPrimTL')[:1]),
    komisyon_prim=Subquery(latest_collection.values('KomisyonPrimTL')[:1]),

    # ✅ Döviz Bazlı Tutarlar
    brut_prim_doviz=Subquery(latest_collection.values('BrutPrim')[:1]),
    net_prim_doviz=Subquery(latest_collection.values('NetPrim')[:1]),
    komisyon_doviz=Subquery(latest_collection.values('Komisyon')[:1]),

    # ✅ Döviz Bilgileri
    doviz_kuru=Subquery(latest_collection.values('DovizKuru')[:1]),
    doviz_cinsi=Subquery(latest_collection.values('DovizCinsi')[:1]),
)


    # 📅 Tarih filtresi
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%d.%m.%Y").date()
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y").date()
            base_queryset = base_queryset.filter(PoliceBaslangicTarihi__range=(start_date, end_date))
        except:
            pass

    # 🏢 Şirket filtresi
    if company_id and company_id.isdigit():
        base_queryset = base_queryset.filter(company_id=int(company_id))

    # 🧭 Branş filtresi → SirketUrunNo + Products.branch
    if branch_id and branch_id.isdigit():
        codes = Products.objects.filter(
            branch_id=int(branch_id)
        ).values_list("code", flat=True)
        base_queryset = base_queryset.filter(SirketUrunNo__in=codes)

    # 🔍 Arama filtresi
    if query:
        base_queryset = base_queryset.filter(
            Q(PoliceNo__icontains=query) |
            Q(customer__identity_number__icontains=query) |
            Q(customer__full_name__icontains=query) |
            Q(insured__identity_number__icontains=query) |
            Q(insured__full_name__icontains=query) |
            Q(car_assets__AracPlakaTam__icontains=query)
        )

    # 🔄 Veri dönüştürme
    data = []
    for p in base_queryset.order_by('-id')[:1000]:  # ✅ Maksimum 1000 kayıt
        try:
            urun_kodu_raw = p.SirketUrunNo or ""
            urun_kodu = str(int(float(urun_kodu_raw))) if urun_kodu_raw.replace(".", "").isdigit() else urun_kodu_raw.strip()

            product = Products.objects.filter(
                company_id=p.company_id,
                code=urun_kodu
            ).select_related("branch").first()

            branch_name = product.branch.name if product and product.branch else "Tanımsız"
        except:
            branch_name = "Tanımsız"

        password_info = AgencyPasswords.objects.filter(
            agency_id=agency_id, insurance_company_id=p.company_id
        ).first()
        agency_code = password_info.partaj_code if password_info else ""

        data.append({
            "id": p.id,
            "uuid": p.uuid,
            "aktif": p.AktifMi or "",
            "baslangic": p.PoliceBaslangicTarihi.strftime("%d.%m.%Y") if p.PoliceBaslangicTarihi else "",
            "bitis": p.PoliceBitisTarihi.strftime("%d.%m.%Y") if p.PoliceBitisTarihi else "",
            "police_no": p.PoliceNo,
            "zeyil": p.ZeyilNo or "0",
            "yenileme": p.YenilemeNo or "0",
            "zeyil_adi": p.ZeyilAdi or "",
            "customer": p.customer.full_name if p.customer else "",
            "insured": p.insured.full_name if p.insured else "",
            "sigorta_ettiren_tc": p.customer.identity_number if p.customer else "",
            "sigortali_tc": p.insured.identity_number if p.insured else "",
            "plaka": (
                p.car_assets.filter(AktifMi=True).first().AracPlakaTam
                if hasattr(p, "car_assets") and p.car_assets.exists() else ""
            ),
            "company": p.company_name,
            "company_id": p.company_id,
            "product_code": str(p.SirketUrunNo or "").strip(),
            "branch": branch_name,
            "user": f"{p.user_name} {p.user_surname}",
            "user_branch": p.user_branch,
            "brut_prim": f"{(p.brut_prim or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "net_prim": f"{(p.net_prim or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "komisyon_prim": f"{(p.komisyon_prim or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "pdf_service_id": pdf_service_map.get(p.company_id),
            "agency_code": agency_code,
            "branch_id": product.branch.id if product and product.branch else "",
            "police_tanzim": p.PoliceTanzimTarihi.strftime("%d.%m.%Y") if p.PoliceTanzimTarihi else "",
            "police_iptal": p.PoliceİptalTarihi.strftime("%d.%m.%Y") if p.PoliceİptalTarihi else "",
            "zeyil_kodu": p.ZeyilKodu or "",
            "olusturan": p.PoliceOlusturanKullanici or "",
            "kesen": p.PoliceKesenKullanici or "",
            "brut_prim_raw": float(p.brut_prim or 0),
            "net_prim_raw": float(p.net_prim or 0),
            "komisyon_raw": float(p.komisyon_prim or 0),
            "doviz_kuru": float(getattr(p, "doviz_kuru", 0) or 0),
            "doviz_cinsi": p.doviz_cinsi or "",
        })

    return JsonResponse({"data": data})


@login_required
def get_filter_options(request):
    agency_id = request.user.agency_id

    # 🔐 Sadece acente ile ilişkili ürünlerden alt branşlar
    company_ids = AgencyCompany.objects.filter(
        agency_id=agency_id
    ).values_list("company_id", flat=True)

    product_codes = Products.objects.filter(
        company_id__in=company_ids
    ).values_list("code", flat=True)

    branch_ids = Products.objects.filter(
        code__in=product_codes
    ).values_list("branch_id", flat=True).distinct()

    companies = InsuranceCompany.objects.filter(
        id__in=company_ids, is_active=True
    ).values("id", "name").order_by("name")

    branches = PolicyBranch.objects.filter(
        id__in=branch_ids
    ).values("id", "name").order_by("name")

    return JsonResponse({
        "companies": list(companies),
        "branches": list(branches),
    })



@login_required
def customer_policy_list(request, customer_id):
    agency_id = request.user.agency_id

    # 🔒 Acente kontrolü eklendi
    customer = get_object_or_404(Customer, id=customer_id, agency_id=agency_id)
    page = int(request.GET.get("page", 1))

    # 🔒 Sadece acente poliçeleri çekiliyor
    policies = (
        Policy.objects
        .select_related("company", "customer", "insured", "PolicyStatus")
        .filter(customer=customer, agency_id=agency_id)
        .order_by("-PoliceTanzimTarihi")
    )

    paginator = Paginator(policies, 10)
    page_obj = paginator.get_page(page)

    # ✅ Plaka bilgisi (policy__agency kontrolü opsiyonel çünkü policy zaten filtreli)
    from database.models import PolicyAssetRelation
    relations = PolicyAssetRelation.objects.select_related("asset_car").filter(
        policy__in=page_obj
    )
    plate_map = {
        r.policy_id: r.asset_car.AracPlakaTam
        for r in relations
        if r.asset_car and r.asset_car.AracPlakaTam
    }

    # ✅ Branş bilgisi
    from database.models import Products
    branch_map = {}
    for policy in page_obj:
        try:
            product = Products.objects.select_related("branch").get(
                company=policy.company, code=policy.SirketUrunNo
            )
            branch_map[policy.id] = product.branch.name if product.branch else "-"
        except:
            branch_map[policy.id] = "-"

    html = render_to_string("partials/tab_policies.html", {
        "policies": page_obj,
        "plate_map": plate_map,
        "branch_map": branch_map,
        "page_obj": page_obj,
    }, request=request)

    return JsonResponse({"success": True, "html": html})


def get_branch_name(policy):
    from database.models import Products
    try:
        raw_code = str(policy.SirketUrunNo or "").strip()
        code = str(int(float(raw_code))) if raw_code.replace(".", "").isdigit() else raw_code
        product = Products.objects.select_related("branch").get(company=policy.company, code=code)
        return product.branch.name if product.branch else "-"
    except:
        return "-"


def get_plate_number(policy):
    from database.models import PolicyAssetRelation
    try:
        relation = PolicyAssetRelation.objects.select_related("asset_car").filter(policy=policy).first()
        if relation and relation.asset_car and relation.asset_car.AracPlakaTam:
            return relation.asset_car.AracPlakaTam
        return "-"
    except:
        return "-"


@login_required
def policy_detail_page(request, uuid):
    policy = get_object_or_404(
        Policy.objects.select_related("company", "customer", "insured"),
        uuid=uuid,
        agency=request.user.agency
    )

    pdf_service = ServiceConfiguration.objects.filter(
        insurance_company=policy.company,
        service_name__icontains="PdfWs"
    ).first()

    pdf_service_id = None
    if pdf_service:
        has_auth = AgencyServiceAuthorization.objects.filter(
            agency=request.user.agency,
            service=pdf_service
        ).exists()
        if has_auth:
            pdf_service_id = pdf_service.id

    # ✅ Acente kodu → AgencyPasswords
    password_info = AgencyPasswords.objects.filter(
        agency=request.user.agency,
        insurance_company=policy.company
    ).first()
    agency_code = password_info.partaj_code if password_info else ""

    # ✅ Ürün kodu → SirketUrunNo
    product_code = str(policy.SirketUrunNo or "").strip()

    # ✅ Poliçe no → PoliceNo
    policy_number = policy.PoliceNo or ""

    company_code = policy.company.company_code if policy.company else None
    company_name = policy.company.name if policy.company else "Bilinmeyen Şirket"
    user = policy.user
    branch = user.branch.name if user and user.branch else "-"
    branch_agency = user.branch.agency.name if user and user.branch and user.branch.agency else "-"
    username = user.get_full_name() if user else "-"
    insured = policy.insured

    relation_qs = PolicyAssetRelation.objects.filter(policy=policy)

    car = relation_qs.filter(asset_car__isnull=False, asset_car__AktifMi=True).select_related("asset_car").first()
    home = relation_qs.filter(asset_home__isnull=False, asset_home__AktifMi=True).select_related("asset_home").first()

    asset_info = []
    if car:
        car = car.asset_car
        asset_info += [
            ("Plaka", car.AracPlakaTam),
            ("Tescil", car.AracTescilTam),
            ("Tarz", car.AracKullanimTarzi),
            ("Kod", car.AracBirlikKodu),
            ("Marka", car.AracMarkaAdi),
            ("Model", car.AracTipAdi),
            ("Yıl", car.AracModelYili),
            ("Şasi No", car.AracSasiNo),
            ("Motor No", car.AracMotorNo),
            ("Renk", car.AracRenk),
            ("Yakıt Tipi", car.AracYakitTipi),
            ("İlk Tescil", car.AracTrafigeCikisTarihi),
            ("Son Tescil", car.AracTescilTarihi),
        ]
    elif home:
        home = home.asset_home
        asset_info += [
            ("UAVT", home.RizikoUavtKod),
            ("Dask No", home.RizikoDaskPoliceNo),
            ("MetreKare", home.RizikoDaireYuzOlcumu),
            ("İl", home.Riziko_il_ad),
            ("İlçe", home.Riziko_ilce_adi),
            ("Köy", home.Riziko_koy_adi),
            ("Mahalle", home.Riziko_mahalle_adi),
            ("Sokak", home.Riziko_sokak_adi),
            ("Bina", home.Riziko_bina_adi),
            ("Daire", home.Riziko_daire_no),
            ("Konut Konum", home.RizikoKonum),
            ("Konut Tipi", home.RizikoKonutTipi),
            ("DM", home.DainiMurtehinAdi),
        ]

    asset_info = [(k, v) for k, v in asset_info if v]

    payment_list = PaymentPlan.objects.filter(
        PoliceNoKombine=policy.PoliceNoKombine,
        agency=request.user.agency  # tenant izolasyonu
    ).order_by("TaksitSirasi")

    insured = policy.insured
    insured_info = []
    if insured:
        insured_info = [
            ("Ad Soyad", insured.full_name or "-", insured.customer_key),
            ("TCKN", insured.identity_number or "-", insured.customer_key),
            ("Doğum Tarihi", insured.birth_date.strftime("%d.%m.%Y") if insured.birth_date else "-",
             insured.customer_key),
            ("Cinsiyet", insured.Cinsiyet or "-", None),
            ("Uyruk", insured.Uyruk or "-", None),
        ]
        if insured.Uyruk == "Diğer":
            insured_info.append(("Uyruk Detayı", insured.UyrukDiger or "-", None))
    else:
        insured_info = [
            ("Ad Soyad", "-", None),
            ("TCKN", "-", None),
            ("Doğum Tarihi", "-", None),
        ]

    customer = policy.customer
    customer_info = []
    if customer:
        customer_info = [
            ("Ad Soyad", customer.full_name or "-", customer.customer_key),
            ("TCKN", customer.identity_number or "-", customer.customer_key),
            ("Doğum Tarihi", customer.birth_date.strftime("%d.%m.%Y") if customer.birth_date else "-",
             customer.customer_key),
        ]
    else:
        customer_info = [
            ("Ad Soyad", "-", None),
            ("TCKN", "-", None),
            ("Doğum Tarihi", "-", None),
        ]

    # Şirket ürün bilgisi
    product_info = {"main": "-", "branch": "-", "name": "-"}
    if policy.SirketUrunNo and policy.company:
        product = Products.objects.filter(
            company=policy.company,
            code=policy.SirketUrunNo
        ).select_related("branch", "main_branch").first()
        if product:
            product_info["main"] = product.main_branch.name if product.main_branch else "-"
            product_info["branch"] = product.branch.name if product.branch else "-"
            product_info["name"] = product.name

    # Toplam tahsilat verileri
    try:
        collections_qs = policy.collections.all()
        totals = collections_qs.aggregate(
            brut_total_tl=Sum("BrutPrimTL"),
            brut_total=Sum("BrutPrim"),
            net_total_tl=Sum("NetPrimTL"),
            net_total=Sum("NetPrim"),
            komisyon_total_tl=Sum("KomisyonPrimTL"),
            komisyon_total=Sum("Komisyon")
        )
    except Exception as e:
        print("❌ Collection toplamı alınamadı:", e)
        totals = {"brut_total": 0, "net_total": 0, "komisyon_total": 0}

    collection_obj = policy.collections.first()
    currency = collection_obj.DovizCinsi.strip() if collection_obj and collection_obj.DovizCinsi else ""
    currency_symbols = {"TRY": "₺", "USD": "$", "EUR": "€"}
    currency_symbol = currency_symbols.get(currency.upper(), "")

    # Poliçe bilgileri tek liste halinde
    poli_info_list = [
        ("Alt Branş", product_info["branch"]),
        ("Ürün Adı", product_info["name"]),
        ("Zeyil No", policy.ZeyilNo or "0"),
        ("Zeyil Kodu", policy.ZeyilKodu or "-"),
        ("Zeyil Adı", policy.ZeyilAdi or "-"),
        ("Yenileme No", policy.YenilemeNo or "0"),
        ("Kart Sahibi", collection_obj.KartSahibi if collection_obj and collection_obj.KartSahibi else "-"),
        ("Kredi Kartı No",f"**** **** **** {collection_obj.KrediKartNo[-4:]}" if collection_obj and collection_obj.KrediKartNo else "-"),
        ("Tanzim Tarihi", policy.PoliceTanzimTarihi.strftime("%d.%m.%Y") if policy.PoliceTanzimTarihi else "-"),
        ("Başlangıç", policy.PoliceBaslangicTarihi.strftime("%d.%m.%Y") if policy.PoliceBaslangicTarihi else "-"),
        ("Bitiş", policy.PoliceBitisTarihi.strftime("%d.%m.%Y") if policy.PoliceBitisTarihi else "-"),
        ("Şube", branch),
        ("Kullanıcı", username),
    ]

    context = {
        "policy": policy,
        "customer": policy.customer,
        "insured": policy.insured,
        "collection": policy.collections.first(),
        "payments": policy.payment_plans.order_by("TaksitSirasi"),
        "car_assets": policy.car_assets.filter(AktifMi=True),
        "home_assets": policy.home_assets.filter(AktifMi=True),
        "company_name": company_name,
        "company_code": company_code,
        "poli_info_list": poli_info_list,
        "brut_total": totals.get("brut_total") or 0,
        "brut_total_tl": totals.get("brut_total_tl") or 0,
        "net_total": totals.get("net_total") or 0,
        "net_total_tl": totals.get("net_total_tl") or 0,
        "komisyon_total": totals.get("komisyon_total") or 0,
        "komisyon_total_tl": totals.get("komisyon_total_tl") or 0,
        "brut_currency": currency_symbol,
        "net_currency": currency_symbol,
        "komisyon_currency": currency_symbol,
        "insured_info": insured_info,
        "customer_info": customer_info,
        "payment_list": payment_list,
        "asset_info": asset_info,
        "is_active": bool(policy.AktifMi),
        "pdf_service_id": pdf_service_id,
        "pdf_agency_code": agency_code,
        "pdf_policy_number": policy_number,
        "pdf_product_code": product_code,
        "card_info": {
        },
    }

    return render(request, "database/policy_detail.html", context)


#-------------------------------------------------------
def pretty_xml(xml_str):
    try:
        parsed = xml.dom.minidom.parseString(xml_str)
        return parsed.toprettyxml(indent="  ")
    except Exception:
        return xml_str  # parse edemezse orijinalini döner

@login_required
def service_log_list(request):
    proposal_id = request.GET.get("proposal_id")
    logs = []
    proposal_keys_json = None

    if proposal_id:
        logs_qs = ProposalServiceLog.objects.filter(proposal_id=proposal_id).select_related("offer_service", "info_service").order_by("-created_at")

        paginator = Paginator(logs_qs, 10)
        page = request.GET.get("page")
        page_obj = paginator.get_page(page)

        for log in page_obj:
            service_obj = log.offer_service or log.info_service
            logs.append({
                "id": log.id,
                "proposal_id": log.proposal_id,
                "service_name": getattr(service_obj, "service_name", "Tanımsız Servis"),
                "company_name": getattr(getattr(service_obj, "insurance_company", None), "name", "-"),
                "status": "✅" if log.success else "❌",
                "created_at": log.created_at,
                "request_data": log.request_data,
                "response_data": pretty_xml(log.response_data),
            })

        key_qs = ProposalKey.objects.filter(proposal_id=proposal_id)
        if key_qs.exists():
            key_dict = {f"key_{k.key_id}": k.key_value for k in key_qs}
            proposal_keys_json = json.dumps(key_dict, indent=2, ensure_ascii=False)

        return render(request, "database/proposal_log_list.html", {
            "proposal_id": proposal_id,
            "logs": logs,
            "page_obj": page_obj,
            "proposal_keys": proposal_keys_json
        })

    return render(request, "database/proposal_log_list.html", {
        "proposal_id": proposal_id,
        "logs": [],
        "proposal_keys": None
    })

@login_required
def service_mapping_page(request):
    """
    Şirket-Ürün Mapping Ekleme sayfasını render eder.
    """
    return render(request, "database/service_mapping.html")


def get_unmapped_product_codes(request):
    company_id = request.GET.get("company_id")
    if not company_id:
        return JsonResponse([], safe=False)

    # Mapping'te olan ürün kodlarını bul
    mapped_product_codes = CompanyParameterMapping.objects.filter(
        insurance_company_id=company_id
    ).values_list('product_code', flat=True).distinct()

    # Sadece mapping'te olmayan branşları getir
    from .models import PolicyBranch
    branches = PolicyBranch.objects.exclude(code__in=mapped_product_codes).all()
    data = [
        {"code": b.code, "label": f"{b.code} - {b.name}"}
        for b in branches
    ]
    return JsonResponse(data, safe=False)

@require_POST
def save_mappings(request):
    try:
        data = json.loads(request.body)
        mappings = data.get('mappings', [])
        already_exists = []
        created_count = 0

        for m in mappings:
            company = InsuranceCompany.objects.get(id=m['company_id'])
            key = Key.objects.get(KeyID=m['key_id'])
            param = Parameter.objects.get(ParameterID=m['parameter_id']) if m['parameter_id'] else None

            # Unique kontrol
            obj, created = CompanyParameterMapping.objects.get_or_create(
                insurance_company=company,
                product_code=m['product_code'],
                key=key,
                parameter=param,
                defaults={
                    'target_company_key': m['target_company_key'],
                    'company_parameter': m['company_parameter'],
                    'company_parameter_value': m['company_parameter_value']
                }
            )
            if created:
                created_count += 1
            else:
                already_exists.append(f"{company.name} / {m['product_code']} / {key.KeyName} / {param.ParameterName if param else '-'}")

        if already_exists:
            return JsonResponse({"success": False, "exists": already_exists})
        return JsonResponse({"success": True, "created": created_count})
    except Exception as ex:
        return JsonResponse({"success": False, "error": str(ex)})

#-------------------------------------------------------

@login_required(login_url='/login/')
def proposal_list(request, customer_id=None):
    user = request.user
    agency_id = user.agency_id

    offers = Proposal.objects.select_related(
        "customer", "created_by", "branch", "policy_branch"
    ).filter(
        agency_id=agency_id
    )

    if customer_id is not None:
        offers = offers.filter(customer_id=customer_id)

    offers = offers.order_by("-created_at")

    paginator = Paginator(offers, request.GET.get("count", 12))
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)
    branch_map = {b.code: b.name for b in PolicyBranch.objects.all()}
    uuid_map = {m.proposal_id: m.uuid for m in ProposalUUIDMapping.objects.filter(
        proposal_id__in=[offer.proposal_id for offer in page_obj]
    )}

    context = {
        "page_obj": page_obj,
        "page_range": page_range,
        "count_choices": [10, 25, 50, 100],
        "count": int(request.GET.get("count", 12)),
        "query": request.GET.get("q", ""),
        "branch_map": branch_map,
        "uuid_map": uuid_map if uuid_map else {},
    }
    return render(request, "database/proposal.html", context)



@login_required
def get_customer_proposals(request):
    if request.method == "POST":
        data = json.loads(request.body)

        identity_number = data.get('identity_number')
        page_number = data.get('page', 1)
        agency_id = request.user.agency_id

        offers = Proposal.objects.select_related(
            'customer', 'created_by', 'branch', 'policy_branch'
        ).filter(
            customer__identity_number=identity_number,
            agency_id=agency_id
        ).order_by('-created_at')

        paginator = Paginator(offers, 10)
        page_obj = paginator.get_page(page_number)

        uuid_map = {m.proposal_id: m.uuid for m in ProposalUUIDMapping.objects.filter(
            proposal_id__in=[offer.proposal_id for offer in page_obj]
        )}
        branch_map = {b.code: b.name for b in PolicyBranch.objects.all()}

        html = render_to_string('partials/tab_proposals.html', {
            'page_obj': page_obj,
            'uuid_map': uuid_map,
            'branch_map': branch_map,
        })

        return JsonResponse({
            'success': True,
            'html': html
        })

    return JsonResponse({'success': False, 'error': 'Geçersiz istek'})


#-------------------------------------------------------

@login_required
def get_customer_contacts(request):
    if request.method == "POST":
        data = json.loads(request.body)
        identity_number = data.get('identity_number')
        page_number = data.get('page', 1)

        customer = Customer.objects.filter(identity_number=identity_number, agency_id=request.user.agency_id).first()
        if not customer:
            return JsonResponse({'success': False, 'error': 'Müşteri bulunamadı.'})

        contacts = customer.contacts.all().order_by('-is_primary', '-is_verified', '-created_at')
        paginator = Paginator(contacts, 10)
        page_obj = paginator.get_page(page_number)

        html = render_to_string('partials/tab_contacts.html', {
            'contacts': page_obj.object_list,
            'page_obj': page_obj,
        })

        return JsonResponse({'success': True, 'html': html})
    return JsonResponse({'success': False, 'error': 'Geçersiz istek.'})


def add_customer_contact(request):
    if request.method == "POST":
        try:
            import re
            data = json.loads(request.body)
            identity_number = data.get("identity_number")
            value = str(data.get("value", "")).strip()
            contact_type = data.get("contact_type")
            is_primary_req = bool(data.get("is_primary", False))  # Kullanıcıdan gelen is_primary isteği

            # 1️⃣ Müşteri kontrolü
            customer = Customer.objects.filter(identity_number=identity_number).first()
            if not customer:
                return JsonResponse({"success": False, "error": "Müşteri bulunamadı."})

            # 2️⃣ Telefon ise: başındaki 0'ı sil, format, prefix ve fake numara kontrolü
            if contact_type == "phone":
                value = value.lstrip("0")
                # Sadece rakam ve 10 hane şartı
                if not (value.isdigit() and len(value) == 10):
                    return JsonResponse({"success": False, "error": "Telefon 10 haneli olmalı (başında 0 olmadan)!"})

                VALID_PREFIXES = {
                    "501", "502", "503", "504", "505", "506", "507", "508", "509",
                    "530", "531", "532", "533", "534", "535", "536", "537", "538", "539",
                    "541", "542", "543", "544", "545", "546", "547", "548", "549",
                    "550", "551", "552", "553", "554", "555", "556",
                }
                prefix = value[:3]
                if prefix not in VALID_PREFIXES:
                    return JsonResponse({"success": False, "error": f"Geçersiz GSM numarası prefixi: {prefix}"})

                # Fake numara ve pattern engeli
                FAKE_NUMBERS = {
                    "1111111111", "2222222222", "3333333333", "4444444444", "5555555555",
                    "6666666666", "7777777777", "8888888888", "9999999999",
                    "1234567890", "0123456789", "0000000000"
                }
                last_7 = value[-7:]
                if value in FAKE_NUMBERS or re.match(r'(\d)\1{6,}', last_7):
                    return JsonResponse({"success": False, "error": "Sahte numara/pattern ile kayıt yapılamaz."})
                if last_7 in {"1234567", "2345678", "3456789", "4567890", "0123456"}:
                    return JsonResponse({"success": False, "error": "Sahte numara paternine izin verilmez."})

            elif contact_type == "email":
                # Eposta format ve fake pattern kontrolü
                if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$', value):
                    return JsonResponse({"success": False, "error": "Geçersiz email formatı!"})
                if value.startswith("test") or value.endswith("@mail.com"):
                    return JsonResponse({"success": False, "error": "Sahte email eklenemez."})

            # 3️⃣ Kendi müşterisinde aynı value varsa update
            existing = CustomerContact.objects.filter(
                customer=customer,
                value=value
            ).first()
            if existing:
                # Birincil numara güncellemesi OTP olmadan yapılamaz
                if is_primary_req and not existing.is_primary:
                    return JsonResponse({"success": False, "error": "Birincil numara değişikliği OTP doğrulama gerektirir!"})
                # Diğer update'ler
                existing.is_verified = False
                existing.save()
                return JsonResponse({"success": True, "updated": True})

            # 4️⃣ İlk birincil: sadece ilk eklenen olabilir, sonrası otomatik other ve is_primary=False olur
            has_primary = CustomerContact.objects.filter(
                customer=customer,
                contact_type=contact_type,
                is_primary=True
            ).exists()
            if not has_primary:
                is_primary = True
            else:
                is_primary = False

            # 5️⃣ Etiket sadece backendde belirlenir, kullanıcı seçemez; ilk kayıt değilse "other" zorunlu
            label = "main" if is_primary else "other"

            # 6️⃣ Yeni kayıt (onaysız başlat)
            contact = CustomerContact.objects.create(
                customer=customer,
                contact_type=contact_type,
                value=value,
                label=label,
                is_verified=False,
                is_primary=is_primary,
            )
            return JsonResponse({"success": True, "created": True, "is_primary": is_primary})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek."})


def delete_customer_contact(request):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        contact_id = data.get("contact_id")

        # Güvenlik için: sadece ilgili müşteriye ait iletişimi sil!
        try:
            contact = CustomerContact.objects.get(id=contact_id)
            contact.delete()
            return JsonResponse({"success": True})
        except CustomerContact.DoesNotExist:
            return JsonResponse({"success": False, "error": "İletişim kaydı bulunamadı."})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek."})


#----------------------------------------------------------

@login_required
def customer_assets_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, agency_id=request.user.agency_id)

    # ✅ Araç varlıkları
    cars = AssetCars.objects.filter(insured=customer)
    homes = AssetHome.objects.filter(insured=customer)

    all_assets = []

    for c in cars:
        all_assets.append({
            "id": c.id,
            "type": "Araç",
            "aktif": c.AktifMi,
            "verified": c.is_verified,
            "aciklama": c.AracPlakaTam or "-",
            "created_at": c.created_at,
        })

    for h in homes:
        all_assets.append({
            "id": h.id,
            "type": "Konut",
            "aktif": h.AktifMi,
            "verified": h.is_verified,
            "aciklama": h.RizikoUavtKod or "-",
            "created_at": h.created_at,
        })

    html = render_to_string("partials/tab_asset.html", {"assets": all_assets}, request=request)

    return JsonResponse({"success": True, "html": html})


#----------------------------------------------------------

def get_company_revision_options(request):
    insurance_company_id = request.GET.get("company_id")
    product_code = request.GET.get("product_code")

    if not (insurance_company_id and product_code):
        return JsonResponse({"error": "Eksik parametre"}, status=400)

    revisable_keys = CompanyRevisableKey.objects.filter(
        insurance_company_id=insurance_company_id,
        product_code=product_code,
        is_active=True
    ).select_related("key")

    result = []

    for item in revisable_keys:
        key_description = item.key.Description
        target_key = item.target_company_key

        param_mappings = CompanyParameterMapping.objects.filter(
            insurance_company_id=insurance_company_id,
            product_code=product_code,
            target_company_key=target_key
        ).values(
            "company_parameter", "company_parameter_value"
        ).distinct()

        result.append({
            "key_id": item.key.KeyID,
            "key_description": key_description,
            "target_company_key": target_key,
            "template_variable": item.template_variable,
            "parameters": [
                {
                    "label": p["company_parameter_value"],
                    "value": p["company_parameter"]
                }
                for p in param_mappings
            ]
        })

    return JsonResponse({"data": result})

#----------------------------------------------------------

@login_required
def cookie_log_view(request):
    agency_id = request.user.agency_id

    if request.method == "POST":
        update_all_cookies_for_agency.delay(agency_id, source="manual")
        return redirect("cookie_logs")

    logs = CookieLog.objects.filter(agency_id=agency_id)\
                .select_related("company", "agency")\
                .order_by("-created_at")[:20]  # 🔹 sadece son 10 kayıt

    return render(request, "database/cookie.html", {"logs": logs})
