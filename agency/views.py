from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_http_methods

from database.models import OfferServiceConfiguration, TransferServiceConfiguration
from database.views import get_page_range
from .models import Agency, AgencyPasswords, Branch, AgencyCompany, AgencyOfferServiceAuthorization, \
    AgencyTransferServiceAuthorization
from agency.models import InsuranceCompany,AgencyServiceAuthorization, ServiceConfiguration
from agencyusers.models import Department,Title,Role,Users
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from .forms import AgencyPasswordForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
import json

@login_required
def agency_list(request):
    """Tüm acenteleri listele + arama + sıralama"""
    query = request.GET.get('q', '')

    agencies = Agency.objects.all()

    if query:
        agencies = agencies.filter(
            Q(name__icontains=query) |
            Q(domain__icontains=query)
        )

    agencies = agencies.order_by("-created_at").select_related()  # Daha performanslı

    paginator = Paginator(agencies, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'agency/agency_list.html', {
        'page_obj': page_obj,
        'query': query
    })

@login_required
def agency_detail(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    # Şirket ve şifre bilgileri
    agency_companies = agency.agency_company_agencies.all()
    agency_companies_with_passwords = []
    for agency_company in agency_companies:
        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=agency_company.company
        ).first()
        agency_companies_with_passwords.append({
            'agency_company': agency_company,
            'password_info': password_info
        })

    # Şubeler
    branches = agency.branches.all()

    # Yetkilendirilmiş servisler
    agency_services = AgencyServiceAuthorization.objects.filter(
        agency=agency
    ).select_related("service", "service__insurance_company")

    # Servis listesi (tüm sistemde tanımlı olanlar)
    all_services = ServiceConfiguration.objects.all()

    # Diğer dropdown verileri
    departments = Department.objects.all()
    titles = Title.objects.all()
    roles = Role.objects.all()
    users = Users.objects.all()

    return render(request, 'agency/agency_detail.html', {
        'agency': agency,
        'agency_companies_with_passwords': agency_companies_with_passwords,
        'branches': branches,
        'departments': departments,
        'titles': titles,
        'roles': roles,
        'users': users,
        'agency_services': agency_services,       # ✅ services_tab.html için
        'all_services': all_services,             # ✅ servis ekleme dropdown'u için
    })

@login_required
def add_agency(request):
    if request.method == "POST":
        name = request.POST.get("name")
        domain = request.POST.get("domain")
        logo = request.FILES.get("logo")
        is_active = request.POST.get("is_active") == "on"

        try:
            agency = Agency.objects.create(
                name=name,
                domain=domain,
                logo=logo,
                is_active=is_active
            )
            return JsonResponse({"success": True, "id": agency.id})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid method"})

@login_required
def save_agency_password(request, agency_id, company_id):
    agency = get_object_or_404(Agency, id=agency_id)
    company = get_object_or_404(InsuranceCompany, id=company_id)

    # AgencyPasswords kaydını bul veya oluştur
    agency_password, created = AgencyPasswords.objects.get_or_create(
        agency=agency,
        insurance_company=company,
    )

    if request.method == 'POST':
        form = AgencyPasswordForm(request.POST, instance=agency_password)
        if form.is_valid():
            form.save()
            messages.success(request, 'Şifre bilgileri başarıyla kaydedildi.')
            return redirect('agency_detail', agency_id=agency.id)
    else:
        form = AgencyPasswordForm(instance=agency_password)

    return render(request, 'agency/agency_detail.html', {'agency': agency, 'form': form})

@login_required
def branch_list(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)
    branches = agency.branches.all()
    return render(request, 'agency/branch_list.html', {'agency': agency, 'branches': branches})

@login_required
def save_branch(request, agency_id, branch_id):
    agency = get_object_or_404(Agency, id=agency_id)
    branch = get_object_or_404(Branch, id=branch_id, agency=agency)

    if request.method == 'POST':
        # Formdan gelen verileri güncelle
        branch.name = request.POST.get('name')
        branch.branch_type = request.POST.get('branch_type')
        branch.is_main = request.POST.get('is_main') == 'on'  # Checkbox için özel kontrol
        branch.save()

        messages.success(request, 'Şube bilgileri başarıyla kaydedildi.')
        return redirect('agency_detail', agency_id=agency.id)

    return render(request, 'agency/agency_detail.html', {'agency': agency})

@login_required
def add_branch(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    if request.method == 'POST':
        # Formdan gelen verileri al
        name = request.POST.get('name')
        branch_type = request.POST.get('branch_type')
        is_main = request.POST.get('is_main') == 'on'  # Checkbox için özel kontrol

        # Yeni şube oluştur
        Branch.objects.create(
            name=name,
            agency=agency,
            branch_type=branch_type,
            is_main=is_main
        )

        messages.success(request, 'Yeni şube başarıyla eklendi.')
        return redirect('agency_detail', agency_id=agency.id)

    return render(request, 'agency/branches_tab.html', {'agency': agency})

@login_required
def update_agency_logo(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    if request.method == 'POST':
        # Formdan gelen dosyayı al
        logo = request.FILES.get('logo')
        if logo:
            # Dosya türünü kontrol et (sadece JPEG veya PNG)
            allowed_types = ['image/jpeg', 'image/png']
            if logo.content_type not in allowed_types:
                messages.error(request, 'Sadece JPEG veya PNG dosyaları yükleyebilirsiniz.')
                return redirect('agency_detail', agency_id=agency.id)

            # Dosya boyutunu kontrol et (5 MB'den büyükse hata ver)
            if logo.size > 5 * 1024 * 1024:  # 5 MB'den büyükse
                messages.error(request, 'Dosya boyutu 5 MB\'den küçük olmalıdır.')
                return redirect('agency_detail', agency_id=agency.id)

            # Logoyu güncelle
            agency.logo = logo
            agency.save()
            messages.success(request, 'Logo başarıyla güncellendi.')
        else:
            messages.error(request, 'Lütfen bir logo dosyası seçin.')

        return redirect('agency_detail', agency_id=agency.id)

    return render(request, 'agency/agency_detail.html', {'agency': agency})

@login_required
@require_http_methods(["POST"])
def authorize_service(request, agency_id):
    try:
        data = json.loads(request.body)
        service_id = data.get("service_id")

        agency = get_object_or_404(Agency, id=agency_id)
        service = get_object_or_404(ServiceConfiguration, id=service_id)

        # Zaten varsa tekrar ekleme
        if AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
            return JsonResponse({"error": "Zaten yetkilendirilmiş."}, status=400)

        AgencyServiceAuthorization.objects.create(agency=agency, service=service)
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def authorize_offer_service(request, agency_id):
    try:
        data = json.loads(request.body)
        offer_service_id = data.get("offer_service_id")

        agency = get_object_or_404(Agency, id=agency_id)
        offer_service = get_object_or_404(OfferServiceConfiguration, id=offer_service_id)

        # Zaten varsa tekrar ekleme
        if AgencyOfferServiceAuthorization.objects.filter(agency=agency, offer_service=offer_service).exists():
            return JsonResponse({"error": "Zaten yetkilendirilmiş."}, status=400)

        AgencyOfferServiceAuthorization.objects.create(agency=agency, offer_service=offer_service)
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def get_unassigned_services(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    # 1️⃣ Zaten yetkili servisleri dışarıda tut
    assigned_services = AgencyServiceAuthorization.objects.filter(
        agency=agency
    ).values_list("service_id", flat=True)

    # 2️⃣ Geriye kalanları getir
    available_services = ServiceConfiguration.objects.exclude(
        id__in=assigned_services
    ).select_related("insurance_company")

    # 3️⃣ JSON yanıt hazırla
    services_data = [
        {
            "id": service.id,
            "name": service.service_name,
            "company": service.insurance_company.name
        }
        for service in available_services
    ]

    return JsonResponse({"services": services_data})

@login_required
def get_unassigned_offer_services(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    # Bu acenteye zaten yetkilendirilmiş servisleri bul
    assigned_ids = AgencyOfferServiceAuthorization.objects.filter(
        agency=agency
    ).values_list('offer_service_id', flat=True)

    # Geriye kalan servisleri getir
    unassigned_services = OfferServiceConfiguration.objects.exclude(id__in=assigned_ids).select_related('insurance_company')

    service_list = [
        {
            "id": service.id,
            "name": service.service_name,
            "company": service.insurance_company.name
        }
        for service in unassigned_services
    ]

    return JsonResponse({"services": service_list})

@login_required
def remove_service_authorization(request, agency_id, service_id):
    if request.method == "DELETE":
        agency = get_object_or_404(Agency, id=agency_id)
        service = get_object_or_404(ServiceConfiguration, id=service_id)

        AgencyServiceAuthorization.objects.filter(agency=agency, service=service).delete()
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Only DELETE allowed."}, status=405)

@login_required
def remove_offer_service_authorization(request, agency_id, offer_service_id):
    if request.method == "DELETE":
        agency = get_object_or_404(Agency, id=agency_id)
        offer_service = get_object_or_404(AgencyOfferServiceAuthorization, id=offer_service_id)

        AgencyOfferServiceAuthorization.objects.filter(agency=agency, offer_service=offer_service).delete()
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Only DELETE allowed."}, status=405)


# ✅ Acenteye Transfer Servis Yetkilendirme
@require_http_methods(["POST"])
@login_required
def authorize_transfer_service(request, agency_id):
    try:
        data = json.loads(request.body)
        service_id = data.get("transfer_service_id")
        agency = get_object_or_404(Agency, id=agency_id)
        service = get_object_or_404(TransferServiceConfiguration, id=service_id)

        obj, created = AgencyTransferServiceAuthorization.objects.get_or_create(
            agency=agency,
            transfer_service=service,
            defaults={"is_active": True}
        )
        if not created:
            return JsonResponse({"success": False, "error": "Bu servis zaten yetkilendirilmiş."})
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


# ✅ Acenteden Transfer Servis Yetkisini Kaldırma
@login_required
@require_http_methods(["POST"])
def remove_transfer_service_authorization(request, agency_id, transfer_service_id):
    auth = get_object_or_404(
        AgencyTransferServiceAuthorization,
        agency_id=agency_id,
        transfer_service_id=transfer_service_id
    )
    auth.delete()
    return JsonResponse({"success": True})


# ✅ Yetkili Olmayan Transfer Servisleri Getir
@login_required
def get_unassigned_transfer_services(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    # Zaten eklenmiş servis ID'leri
    assigned_ids = AgencyTransferServiceAuthorization.objects.filter(
        agency=agency
    ).values_list("transfer_service_id", flat=True)

    # Bu agency için henüz eklenmemiş tüm servisler
    unassigned_services = TransferServiceConfiguration.objects.exclude(
        id__in=assigned_ids
    ).select_related("insurance_company")

    result = [
        {
            "id": service.id,
            "name": service.service_name,
            "company": service.insurance_company.name
        }
        for service in unassigned_services
    ]

    return JsonResponse({ "services": result })

@csrf_exempt
def toggle_transfer_service_status(request, agency_id, service_auth_id):
    if request.method == "POST":
        try:
            auth = get_object_or_404(
                AgencyTransferServiceAuthorization,
                id=service_auth_id,
                agency_id=agency_id
            )
            auth.is_active = not auth.is_active
            auth.save()
            return JsonResponse({"success": True, "is_active": auth.is_active})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Geçersiz istek."})



def get_agency_tab(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)

    users = agency.users.select_related("branch", "department", "title", "role")

    page = request.GET.get("page", 1)
    paginator = Paginator(users, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, "agency/agency_tab.html", {
        "agency": agency,
        "page_obj": page_obj,
        "page_range": page_range,
    })

def get_users_tab(request, agency_id):
    query = request.GET.get("q", "")
    page = request.GET.get("page", 1)

    agency = get_object_or_404(Agency, id=agency_id)

    branches = agency.branches.all()
    departments = Department.objects.all()
    titles = Title.objects.all()
    roles = Role.objects.all()

    users = Users.objects.filter(agency=agency)

    if query:
        users = users.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, "agency/users_tab.html", {
        "agency": agency,
        "branches": branches,
        "departments": departments,
        "titles": titles,
        "roles": roles,
        "users": users,
        "page_obj": page_obj,
        "page_range": page_range,
        "query": query,
    })

def get_companies_tab(request, agency_id):
    page = request.GET.get("page", 1)
    query = request.GET.get("q", "").strip()  # 🔍 Arama parametresi

    agency = get_object_or_404(Agency, id=agency_id)

    # Şirketleri filtrele (arama varsa)
    agency_companies = AgencyCompany.objects.filter(agency=agency).select_related("company")
    if query:
        agency_companies = agency_companies.filter(company__name__icontains=query)
    agency_companies = agency_companies.order_by("company__name")  # 👈 İsim sırasına göre sırala

    data = []
    for relation in agency_companies:
        password_info = AgencyPasswords.objects.filter(
            agency=agency,
            insurance_company=relation.company
        ).first()
        data.append({
            'agency_company': relation,
            'password_info': password_info
        })

    paginator = Paginator(data, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'agency/companies_tab.html', {
        'agency': agency,
        'agency_companies_with_passwords': page_obj,
        'page_obj': page_obj,
        'page_range': page_range,
        'query': query,  # 🔍 Arama kutusu için query'i template'e gönder
    })


def get_branches_tab(request, agency_id):
    page = request.GET.get("page", 1)
    query = request.GET.get("q", "").strip()  # 🔍 Arama parametresi

    agency = get_object_or_404(Agency, id=agency_id)

    # 🔍 Arama uygulanıyor
    branches = Branch.objects.filter(agency=agency)
    if query:
        branches = branches.filter(name__icontains=query)
    branches = branches.order_by("name")  # 👈 Şube adına göre sıralı

    paginator = Paginator(branches, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, "agency/branches_tab.html", {
        "agency": agency,
        "page_obj": page_obj,
        "page_range": page_range,
        "query": query,  # Temizle butonu ve input için!
    })


def get_services_tab(request, agency_id):
    page = request.GET.get("page", 1)
    query = request.GET.get("q", "").strip()

    agency = get_object_or_404(Agency, id=agency_id)

    services = AgencyServiceAuthorization.objects.filter(agency=agency).select_related("service__insurance_company")

    if query:
        services = services.filter(
            Q(service__service_name__icontains=query) |      # Servis adı ile arama
            Q(service__insurance_company__name__icontains=query)  # Şirket adı ile arama
        )

    paginator = Paginator(services, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'agency/services_tab.html', {
        'agency': agency,
        'page_obj': page_obj,
        'page_range': page_range,
        'query': query,
    })


def get_offer_services_tab(request, agency_id):
    page = request.GET.get("page", 1)
    query = request.GET.get("q", "").strip()

    agency = get_object_or_404(Agency, id=agency_id)

    services = AgencyOfferServiceAuthorization.objects.filter(
        agency=agency
    ).select_related("offer_service__insurance_company")

    if query:
        services = services.filter(
            Q(offer_service__service_name__icontains=query) |
            Q(offer_service__insurance_company__name__icontains=query) |
            Q(offer_service__soap_action__icontains=query) |
            Q(offer_service__product_code__icontains=query) |
            Q(offer_service__sub_product_code__icontains=query) |
            Q(offer_service__sub_product_description__icontains=query)
        )

    paginator = Paginator(services, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'agency/offer_services_tab.html', {
        'agency': agency,
        'page_obj': page_obj,
        'page_range': page_range,
        'query': query,
    })

def get_transfer_services_tab(request, agency_id):
    page = request.GET.get("page", 1)
    query = request.GET.get("q", "").strip()

    agency = get_object_or_404(Agency, id=agency_id)

    services = AgencyTransferServiceAuthorization.objects.filter(
        agency=agency
    ).select_related("transfer_service__insurance_company")

    if query:
        services = services.filter(
            Q(transfer_service__service_name__icontains=query) |
            Q(transfer_service__insurance_company__name__icontains=query) |
            Q(transfer_service__soap_action__icontains=query)
        )

    paginator = Paginator(services, 10)
    page_obj = paginator.get_page(page)
    page_range = get_page_range(page_obj.number, paginator.num_pages)

    return render(request, 'agency/transfer_services_tab.html', {
        'agency': agency,
        'page_obj': page_obj,
        'page_range': page_range,
        'query': query,
    })
