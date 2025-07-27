from django.utils import timezone
from django.utils.crypto import get_random_string
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout,update_session_auth_hash
from django.contrib import messages
from django.utils.timezone import now
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.urls import reverse
from INSAI.utils import send_email
from agencyusers.models import Users
from account.models import OTP,LoginActivity
from django.http import JsonResponse
from random import randint
from django.contrib.sessions.models import Session



def custom_404_view(request, exception):
    return render(request, "404.html", status=404)

@csrf_protect
def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        step = request.POST.get("step")

        # ✅ OTP Gönderme Adımı
        if request.headers.get("x-requested-with") == "XMLHttpRequest" and step == "otp_send":
            username = request.POST.get("username")
            password = request.POST.get("password")
            user = authenticate(request, username=username, password=password)

            if not user:
                return JsonResponse({"success": False, "message": " Geçersiz kullanıcı adı veya şifre"})

            if not user.is_active:
                return JsonResponse({"success": False, "message": " Kullanıcı hesabı aktif değil"})

            # --- Eğer kullanıcı ilk kez giriş yapıyorsa OTP'ye gerek yok! ---
            if user.first_login:
                request.session["pending_user_id"] = user.id
                return JsonResponse({"success": True, "redirect": "/account/password_change/"})

            # --- Aşağıdan itibaren eski OTP işlemleri aynen devam ediyor ---
            request.session["temp_user_id"] = user.id

            existing_otp = OTP.objects.filter(user=user).first()
            if existing_otp and (timezone.now() - existing_otp.last_sent_at).total_seconds() < 30:
                return JsonResponse({
                    "success": False,
                    "message": "⚠️ OTP kodu kısa süre önce gönderildi. Lütfen 30 saniye sonra tekrar deneyin."
                })

            otp_code = f"{randint(100000, 999999)}"
            OTP.objects.update_or_create(user=user, defaults={
                "code": otp_code,
                "is_verified": False,
                "agency": user.agency,
                "branch": user.branch,
                "last_sent_at": timezone.now()
            })

            send_email(
                subject="INSAI OTP Giriş Kodu",
                to_email=user.email,
                context={
                    "name": user.first_name,
                    "otp_code": otp_code
                },
                template_name="agencyusers/otp_email.html"
            )

            return JsonResponse({"success": True, "message": "✅ OTP kodu e-posta adresinize gönderildi."})

        # ✅ OTP Doğrulama Adımı
        elif request.headers.get("x-requested-with") == "XMLHttpRequest" and step == "otp_verify":
            otp_input = request.POST.get("otp")
            user_id = request.session.get("temp_user_id")
            if not user_id:
                return JsonResponse({"success": False, "message": "Oturum bilgisi bulunamadı."})

            user = get_object_or_404(Users, id=user_id)
            otp_obj = OTP.objects.filter(user=user, code=otp_input, is_verified=False).first()

            if not otp_obj:
                return JsonResponse({"success": False, "message": "❌ Geçersiz veya süresi dolmuş OTP kodu."})

            otp_obj.is_verified = True
            otp_obj.save()
            del request.session["temp_user_id"]

            # ✅ İlk giriş ise → login yapmadan şifre değiştirmeye yönlendir
            if user.first_login:
                request.session["pending_user_id"] = user.id
                return JsonResponse({"success": True, "redirect": "/account/password_change/"})

            # 🔓 Diğer girişlerde kullanıcıyı login et
            login(request, user)
            logout_other_sessions(user, request.session.session_key)

            # 🔍 IP ve cihaz bilgisi
            ip_address = request.META.get("REMOTE_ADDR", "")
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            login_time = timezone.now()

            # 🔁 Daha önceki girişle karşılaştır
            last_login = LoginActivity.objects.filter(user=user).order_by('-login_time').first()
            if last_login and (last_login.ip_address != ip_address or last_login.user_agent != user_agent):
                send_email(
                    subject="Farklı Cihazdan Giriş Yapıldı",
                    to_email=user.email,
                    context={
                        "name": user.first_name,
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                        "login_time": login_time
                    },
                    template_name="agencyusers/login_alert_email.html"
                )

            # 📌 LoginActivity tablosuna kayıt
            LoginActivity.objects.create(
                user_id=user.id,
                agency_id=user.agency_id,
                branch_id=user.branch_id,
                ip_address=ip_address,
                user_agent=user_agent,
                login_time=login_time
            )

            # 🧾 Şifre politikası yönlendirme
            if user.password_updated_at and user.password_updated_at < timezone.now() - timedelta(days=90):
                return JsonResponse({"success": True, "redirect": reverse("password_change")})

            return JsonResponse({"success": True, "redirect": "/account/password_change/"})

    return render(request, "dashboard/login.html")



def password_change(request):
    pending_user_id = request.session.get("pending_user_id")

    if not pending_user_id:
        return redirect("login")

    user = get_object_or_404(Users, id=pending_user_id)

    # İlk girişte eski şifreyi sormasın!
    FormClass = SetPasswordForm if user.first_login else PasswordChangeForm

    if request.method == "POST":
        form = FormClass(user, request.POST)
        if form.is_valid():
            form.save()
            user.refresh_from_db()
            user.first_login = False
            user.password_updated_at = timezone.now()
            user.save()

            ip_address = request.META.get("REMOTE_ADDR", "")
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            login_time = timezone.now()

            last_login = LoginActivity.objects.filter(user=user).order_by('-login_time').first()
            if last_login and (last_login.ip_address != ip_address or last_login.user_agent != user_agent):
                send_email(
                    subject="Farklı Cihazdan Giriş Yapıldı",
                    to_email=user.email,
                    context={
                        "name": user.first_name,
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                        "login_time": login_time
                    },
                    template_name="agencyusers/login_alert_email.html"
                )

            LoginActivity.objects.create(
                user_id=user.id,
                agency_id=user.agency_id,
                branch_id=user.branch_id,
                ip_address=ip_address,
                user_agent=user_agent,
                login_time=login_time
            )

            del request.session["pending_user_id"]
            logout(request)

            # Şifre başarıyla değişti, login sayfasına yönlendir
            return redirect("login")

        else:
            return render(request, "dashboard/password_change.html", {
                "form": form,
                "form_errors": form.errors
            })
    else:
        form = FormClass(user)

    return render(request, "dashboard/password_change.html", {"form": form})


def set_password(self, raw_password):
    super().set_password(raw_password)
    self.password_updated_at = timezone.now()
    # self.first_login = True  # BUNU YORUMA AL! Sadece kullanıcı oluşturulurken veya "şifremi unuttum"da True olmalı
    self.save()


@csrf_protect
def forgot_password(request):
    if request.method == "POST":
        username = request.POST.get("username")
        user = Users.objects.filter(username=username).first()

        if user:
            new_password = get_random_string(length=8)
            user.set_password(new_password)
            user.first_login = True  # İlk giriş olarak işaretle
            user.save()

            context = {
                "user": user,
                "new_password": new_password
            }

            success = send_email(
                subject="INSAI | Yeni Şifreniz",
                to_email=user.email,
                context=context,
                template_name="agencyusers/forgot_password_email.html"
            )

            if success:
                messages.success(request, "Yeni şifreniz e-posta adresinize gönderildi.")
            else:
                messages.error(request, "E-posta gönderilirken bir hata oluştu.")
        else:
            messages.error(request, "❗ Bu kullanıcı adına ait bir kullanıcı bulunamadı.")

    return render(request, "agencyusers/forgot_password.html")

@login_required
@require_POST
@csrf_protect
def user_logout(request):
    """ Kullanıcıyı çıkış yaptığında login sayfasına yönlendirir ve oturumu tamamen sonlandırır. """
    logout(request)
    messages.success(request, "Başarıyla çıkış yaptınız.")
    request.session.flush()  # Oturum bilgilerini temizle
    return redirect("login")

def logout_other_sessions(user, current_session_key):
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in sessions:
        data = session.get_decoded()
        if data.get('_auth_user_id') == str(user.id) and session.session_key != current_session_key:
            session.delete()


def home_redirect(request):
    """ Kullanıcı giriş yapmamışsa login sayfasına yönlendir, oturumu varsa devam et. """
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("dashboard")

@login_required
def upload_profile_picture(request, key_guid):
    if request.method == 'POST':
        # 🔐 Case-insensitive karşılaştırma
        if str(request.user.key_guid).lower() != str(key_guid).lower():
            messages.error(request, "Başka bir kullanıcının profil fotoğrafını değiştiremezsiniz!")
            return redirect('profile', key_guid=str(key_guid).lower())

        profile_picture = request.FILES.get('profile_picture')
        if profile_picture:
            if profile_picture.size > 5 * 1024 * 1024:
                messages.error(request, "Dosya boyutu 5MB'den büyük olamaz!")
            elif not profile_picture.content_type.startswith('image/'):
                messages.error(request, "Sadece resim dosyaları yükleyebilirsiniz!")
            else:
                request.user.profile_picture = profile_picture
                request.user.save()
                messages.success(request, "Profil fotoğrafı başarıyla güncellendi!")
        else:
            messages.error(request, "Lütfen bir dosya seçin!")

    return redirect('profile', key_guid=str(key_guid).lower())


@login_required
def user_profile(request, key_guid):
    user = get_object_or_404(Users, key_guid=key_guid)

    is_own_profile = str(request.user.key_guid).lower() == str(key_guid).lower()
    print("🔍 request.user.key_guid:", request.user.key_guid)
    print("🔍 URL'den gelen key_guid:", key_guid)
    print("✅ is_own_profile sonucu:", is_own_profile)

    context = {
        'profile_user': user,
        'is_own_profile': is_own_profile
    }
    return render(request, 'dashboard/profile.html', context)




