import json

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from database.models import InsuranceCompany, ServiceConfiguration
from .models import Users, Department, Title, Role
from agency.models import Agency, Branch, AgencyCompany, AgencyPasswords, AgencyServiceAuthorization, \
    AgencyOfferServiceAuthorization
from django.contrib.auth.hashers import make_password
import secrets
import string
from INSAI.utils import send_email  # utils.py'den send_email fonksiyonunu içe aktar
from django.shortcuts import render
from django.db import IntegrityError
from django.core.paginator import Paginator
from django.db.models import Q


def add_user(request, agency_id):
    if request.method == 'POST':
        agency = get_object_or_404(Agency, id=agency_id)
        key_guid = request.POST.get("key_guid")

        username = request.POST.get('username')
        identity_no = request.POST.get('identity_no')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        birth_date = request.POST.get('birth_date')
        branch_id = request.POST.get('branch')
        department_id = request.POST.get('department')
        title_id = request.POST.get('title')
        role_id = request.POST.get('role')
        manager_id = request.POST.get('manager')

        branch = get_object_or_404(Branch, id=branch_id) if branch_id else None
        department = get_object_or_404(Department, id=department_id) if department_id else None
        title = get_object_or_404(Title, id=title_id) if title_id else None
        role = get_object_or_404(Role, id=role_id) if role_id else None
        manager = get_object_or_404(Users, id=manager_id) if manager_id else None

        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        hashed_password = make_password(password)

        try:
            user = Users.objects.create(
                key_guid=key_guid,
                username=username,
                identity_no=identity_no,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                birth_date=birth_date,
                agency=agency,
                branch=branch,
                department=department,
                title=title,
                role=role,
                manager=manager,
                password=hashed_password
            )

            context = {
                'user': {
                    'first_name': first_name,
                    'last_name': last_name,
                    'username': username,
                    'email': email,
                },
                'password': password,
                'login_url': 'http://127.0.0.1:8000/login/',
                'agency_name': agency.name
            }

            subject = "Hesabınız Oluşturuldu"
            template_name = 'agencyusers/add_user.html'


            # email_sent = send_email(subject, email, context=context, template_name=template_name)
            email_sent = send_email(subject, email, context=context, template_name=template_name)

            if email_sent:
                return JsonResponse({'success': True, 'password': password})
            else:
                return JsonResponse({'success': False, 'error': 'E-posta gönderilemedi.'})

        except IntegrityError as e:
            error_msg = str(e)
            if "identity_no" in error_msg:
                return JsonResponse({'success': False, 'error': 'Bu T.C. kimlik numarası zaten kayıtlı.'})
            elif "email" in error_msg:
                return JsonResponse({'success': False, 'error': 'Bu e-posta adresi zaten kullanımda.'})
            elif "username" in error_msg:
                return JsonResponse({'success': False, 'error': 'Bu kullanıcı adı zaten kullanımda.'})
            elif "phone_number" in error_msg:
                return JsonResponse({'success': False, 'error': 'Bu telefon numarası zaten kullanımda.'})
            else:
                return JsonResponse({'success': False, 'error': 'Bu bilgilerle kayıtlı başka bir kullanıcı mevcut.'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Geçersiz istek.'})

@csrf_exempt
def toggle_user_active(request, agency_id, user_id):
    if request.method == "POST":
        try:
            user = get_object_or_404(Users, id=user_id, agency_id=agency_id)
            user.is_active = not user.is_active
            user.save()
            return JsonResponse({"success": True, "is_active": user.is_active})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Geçersiz istek."})


def get_users(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)
    query = request.GET.get('q')
    users = Users.objects.filter(agency=agency)

    if query:
        users = users.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    page_range = paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1)

    return render(request, "agency/users_tab.html", {
        "page_obj": page_obj,
        "query": query,
        "page_range": page_range,
        "branches": Branch.objects.filter(agency=agency),
        "departments": Department.objects.all(),
        "titles": Title.objects.all(),
        "roles": Role.objects.all(),
    })


def get_user_details(request, agency_id, user_id):
    try:
        agency = get_object_or_404(Agency, id=agency_id)
        user = Users.objects.get(id=user_id, agency=agency)
        data = {
            'identity_no': user.identity_no,
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': user.phone_number,
            'birth_date': user.birth_date.isoformat() if user.birth_date else None,
            'branch': {'id': user.branch.id, 'name': user.branch.name} if user.branch else None,
            'department': {'id': user.department.id, 'name': user.department.name} if user.department else None,
            'title': {'id': user.title.id, 'name': user.title.name} if user.title else None,
            'role': {'id': user.role.id, 'name': user.role.name} if user.role else None,
            'manager': {'id': user.manager.id, 'name': f"{user.manager.first_name} {user.manager.last_name}"} if user.manager else None,
        }
        # --- BURAYA DİKKAT ---
        return JsonResponse({'success': True, 'data': data})
    except Users.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Kullanıcı bulunamadı veya bu acenteye ait değil.'})


def update_user(request, agency_id, user_id):
    if request.method == 'POST':
        # İlgili kullanıcıyı bul
        user = get_object_or_404(Users, id=user_id, agency_id=agency_id)

        # Temel bilgileri güncelle
        user.username = request.POST.get('username')
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.phone_number = request.POST.get('phone_number')
        user.birth_date = request.POST.get('birth_date')

        # İlişkisel alanları güncelle
        branch_id = request.POST.get('branch')
        department_id = request.POST.get('department')
        title_id = request.POST.get('title')
        role_id = request.POST.get('role')
        manager_id = request.POST.get('manager')

        if branch_id:
            user.branch = get_object_or_404(Branch, id=branch_id)
        else:
            user.branch = None

        if department_id:
            user.department = get_object_or_404(Department, id=department_id)
        else:
            user.department = None

        if title_id:
            user.title = get_object_or_404(Title, id=title_id)
        else:
            user.title = None

        if role_id:
            user.role = get_object_or_404(Role, id=role_id)
        else:
            user.role = None

        if manager_id:
            user.manager = get_object_or_404(Users, id=manager_id)
        else:
            user.manager = None

        # Değişiklikleri kaydet
        user.save()

        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Geçersiz istek.'})

#/////////////////////////////////////////////////////////////

@csrf_exempt
def save_company(request, agency_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."})

    # Şirket seçimi veya eklemesi
    company_id = request.POST.get("insurance_company")  # select ile gelen ID (varsa)
    company_code = request.POST.get("company_code")
    company_name = request.POST.get("name")
    # Şifre/kullanıcı alanları
    username = request.POST.get("username")
    password = request.POST.get("password")
    web_username = request.POST.get("web_username")
    web_password = request.POST.get("web_password")
    partaj_code = request.POST.get("partaj_code")
    cookie = request.POST.get("cookie")

    try:
        agency = get_object_or_404(Agency, id=agency_id)

        # Eğer var olan şirket seçildiyse
        if company_id:
            company = get_object_or_404(InsuranceCompany, id=company_id)
        else:
            # Hiç yoksa yeni bir şirket oluştur
            company, _ = InsuranceCompany.objects.get_or_create(
                company_code=company_code,
                defaults={"name": company_name, "is_active": True}
            )

        # Acente-şirket ilişkisini kur (varsa tekrar etmez)
        AgencyCompany.objects.get_or_create(agency=agency, company=company)

        # Şifre ve kullanıcı bilgilerini kaydet/güncelle
        AgencyPasswords.objects.update_or_create(
            agency=agency,
            insurance_company=company,
            defaults={
                "username": username,
                "password": password,
                "web_username": web_username,
                "web_password": web_password,
                "partaj_code": partaj_code,
                "cookie": cookie,
            }
        )

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

def get_available_companies(request, agency_id):
    existing_company_ids = AgencyCompany.objects.filter(
        agency_id=agency_id
    ).values_list('company_id', flat=True)

    companies = InsuranceCompany.objects.exclude(id__in=existing_company_ids)

    data = [
        {
            'id': c.id,
            'name': c.name,
            'company_code': c.company_code
        } for c in companies
    ]
    return JsonResponse({'companies': data})

@require_POST
def delete_agency_company(request, agency_id, company_id):
    try:
        agency = get_object_or_404(Agency, id=agency_id)
        company = get_object_or_404(InsuranceCompany, id=company_id)

        # İlişkiyi sil
        AgencyCompany.objects.filter(agency=agency, company=company).delete()

        # Şifreleri de sil
        AgencyPasswords.objects.filter(agency=agency, insurance_company=company).delete()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

def get_company_details(request, agency_id, company_id):
    agency = get_object_or_404(Agency, id=agency_id)
    company = get_object_or_404(InsuranceCompany, id=company_id)

    # Acente bu şirketle eşleşmiş mi kontrol et
    relation = get_object_or_404(AgencyCompany, agency=agency, company=company)

    password_info = AgencyPasswords.objects.filter(agency=agency, insurance_company=company).first()

    data = {
        "company_id": company.id,
        "company_name": company.name,
        "company_code": company.company_code,
        "username": password_info.username if password_info else "",
        "password": password_info.password if password_info else "",
        "web_username": password_info.web_username if password_info else "",
        "web_password": password_info.web_password if password_info else "",
        "partaj_code": password_info.partaj_code if password_info else "",
        "cookie": password_info.cookie if password_info else "",
    }

    return JsonResponse({"success": True, "data": data})


@csrf_exempt
def update_company(request, agency_id):
    if request.method == "POST":
        try:
            agency = get_object_or_404(Agency, id=agency_id)

            company_id = request.POST.get("company_id")
            company_name = request.POST.get("name")
            company_code = request.POST.get("company_code")
            username = request.POST.get("username")
            password = request.POST.get("password")
            partaj_code = request.POST.get("partaj_code")
            web_username = request.POST.get("web_username")
            web_password = request.POST.get("web_password")
            cookie = request.POST.get("cookie")

            # 🔄 Şirketi güncelle
            company = get_object_or_404(InsuranceCompany, id=company_id)
            company.name = company_name
            company.company_code = company_code
            company.save()

            # ⛓️ AgencyCompany ilişkisini tekrar etme gerek yok (zaten varsa)

            # 🔐 Şifre tablosunu güncelle
            AgencyPasswords.objects.update_or_create(
                agency=agency,
                insurance_company=company,
                defaults={
                    "username": username,
                    "password": password,
                    "web_username": web_username,
                    "web_password": web_password,
                    "partaj_code": partaj_code,
                    "cookie": cookie
                }
            )

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek yöntemi"})

@csrf_exempt
def add_branch(request, agency_id):
    if request.method == "POST":
        try:
            name = request.POST.get("name")
            branch_type = request.POST.get("branch_type")
            is_main = request.POST.get("is_main") == "on"

            agency = get_object_or_404(Agency, id=agency_id)

            Branch.objects.create(
                agency=agency,
                name=name,
                branch_type=branch_type,
                is_main=is_main
            )

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek"})

def get_branch_details(request, agency_id, branch_id):
    try:
        branch = get_object_or_404(Branch, id=branch_id, agency_id=agency_id)

        return JsonResponse({
            "success": True,
            "data": {
                "id": branch.id,
                "name": branch.name,
                "branch_type": branch.branch_type,
                "is_main": branch.is_main,
            }
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        })

@csrf_exempt
def update_branch(request, agency_id):
    if request.method == "POST":
        try:
            branch_id = request.POST.get("branch_id")
            name = request.POST.get("name")
            branch_type = request.POST.get("branch_type")
            is_main = request.POST.get("is_main") == "on"

            branch = get_object_or_404(Branch, id=branch_id, agency_id=agency_id)

            branch.name = name
            branch.branch_type = branch_type
            branch.is_main = is_main
            branch.save()

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek türü."})

@csrf_exempt
def delete_branch(request, agency_id, branch_id):
    if request.method == "POST":
        try:
            branch = get_object_or_404(Branch, id=branch_id, agency_id=agency_id)
            branch.delete()
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek."})

@csrf_exempt
def toggle_service_status(request, agency_id, service_auth_id):
    if request.method == "POST":
        try:
            auth = get_object_or_404(AgencyServiceAuthorization, id=service_auth_id, agency_id=agency_id)
            auth.is_active = not auth.is_active
            auth.save()
            return JsonResponse({"success": True, "is_active": auth.is_active})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Geçersiz istek."})

@csrf_exempt
def authorize_service(request, agency_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            service_id = data.get("service_id")

            if not service_id:
                return JsonResponse({"success": False, "error": "Servis ID gerekli."})

            agency = get_object_or_404(Agency, id=agency_id)
            service = get_object_or_404(ServiceConfiguration, id=service_id)

            # Zaten ekliyse uyar
            if AgencyServiceAuthorization.objects.filter(agency=agency, service=service).exists():
                return JsonResponse({"success": False, "error": "Bu servis zaten yetkilendirilmiş."})

            AgencyServiceAuthorization.objects.create(
                agency=agency,
                service=service,
                is_active=True
            )

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek."})

@csrf_exempt
def toggle_offer_service_status(request, agency_id, offer_service_auth_id):
    if request.method == "POST":
        try:
            auth = get_object_or_404(
                AgencyOfferServiceAuthorization,
                id=offer_service_auth_id,
                agency_id=agency_id
            )
            auth.is_active = not auth.is_active
            auth.save(update_fields=["is_active"])
            return JsonResponse({"success": True, "is_active": auth.is_active})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Geçersiz istek."}, status=405)

def get_unassigned_services(request, agency_id):
    agency = get_object_or_404(Agency, id=agency_id)
    assigned_ids = AgencyServiceAuthorization.objects.filter(
        agency=agency
    ).values_list("service_id", flat=True)

    services = ServiceConfiguration.objects.exclude(id__in=assigned_ids)

    data = [
        {
            "id": s.id,
            "name": s.service_name,
            "company": s.insurance_company.name
        }
        for s in services.select_related("insurance_company")
    ]
    return JsonResponse({"services": data})

