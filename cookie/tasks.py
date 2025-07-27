# gateway/tasks.py (veya uygun bir yere ekle)
from celery import shared_task

@shared_task
def update_katilim_cookies(agency_id):
    import os
    import django
    import pyotp

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords

    def playwright_block(pwd, otp_code, agency_id):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto('https://portal.turkiyekatilimsigorta.com.tr/')
            page.fill("#Username", pwd.username)
            page.fill("#Password", pwd.password)
            page.click("button[name='button'][value='login']")
            page.wait_for_timeout(3000)
            page.fill("#Code", otp_code)
            page.click("button[name='button'][value='verify']")
            page.wait_for_timeout(5000)

            cookies = context.cookies()
            cookie_dict = {}
            for c in cookies:
                if c["name"] in ("XX", "ASP.NET_SessionId") and "turkiyekatilimsigorta.com.tr" in c["domain"]:
                    if c["name"] not in cookie_dict:
                        cookie_dict[c["name"]] = c["value"]

            needed_keys = ["XX", "ASP.NET_SessionId"]
            cookie_string = "; ".join(f"{k}={cookie_dict[k]}" for k in needed_keys if k in cookie_dict)

            context.close()
            browser.close()
            return cookie_string

    pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=35)
    otp_code = pyotp.TOTP(pwd.otp_secret).now()
    cookie_string = playwright_block(pwd, otp_code, agency_id)
    pwd.cookie = cookie_string
    pwd.save()
    print(f"✅ Cookie güncellendi! Acente: {agency_id}")


@shared_task
def update_bereket_cookies(agency_id):
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords

    try:
        pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=12)
        cookie_string = extract_bereket_cookies(pwd)
        if cookie_string:
            pwd.cookie = cookie_string
            pwd.save()
            print(f"✅ Bereket cookie güncellendi → agency_id={agency_id}")
        else:
            print(f"❌ Cookie alınamadı → agency_id={agency_id}")
    except Exception as e:
        print(f"🚨 Hata oluştu: {e}")

@shared_task
def update_neova_cookies(agency_id):
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords
    from cookie.tasks import extract_neova_cookies  # Yoluna göre güncelle

    try:
        pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=26)  # Neova ID
        cookie_string = extract_neova_cookies(pwd)
        if cookie_string:
            pwd.cookie = cookie_string
            pwd.save()
            print(f"✅ Neova cookie güncellendi → agency_id={agency_id}")
        else:
            print(f"❌ Cookie alınamadı → agency_id={agency_id}")
    except Exception as e:
        print(f"🚨 Hata oluştu: {e}")




def extract_bereket_cookies(pwd):
    import time
    import pyotp
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"▶️ Bereket giriş başlatılıyor... username={pwd.username}")
        page.goto("https://nareks.bereket.com.tr/Login.aspx?ReturnUrl=%2f")
        time.sleep(3)

        if page.locator("#txtUsername").is_visible():
            print("🔐 Oturum kapalı, giriş yapılacak...")

            page.fill("#txtUsername", pwd.username)
            page.fill("#txtPassword", pwd.password)
            page.click("#ext-gen30")
            print("✅ Kullanıcı adı ve şifre gönderildi, OTP bekleniyor...")

            try:
                page.wait_for_selector("#txtGAKod", timeout=15000)
                otp_code = pyotp.TOTP(pwd.otp_secret).now()
                page.fill("#txtGAKod", otp_code)
                page.click("#ext-gen69")
                print("✅ OTP girildi, giriş tamamlanıyor...")
                time.sleep(5)
            except Exception as e:
                print("⚠️ OTP alanı çıkmadı, sayfa yönlendirilmiş olabilir.")
        else:
            print("✅ Oturum zaten açık, login ekranı atlandı.")

        cookies = context.cookies()
        cookie_dict = {
            c["name"]: c["value"]
            for c in cookies
            if "bereket.com.tr" in c["domain"]
        }

        print(f"📦 Toplam alınan cookie sayısı: {len(cookie_dict)}")
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

        context.close()
        browser.close()
        return cookie_string

def extract_neova_cookies(pwd):
    import time
    import pyotp
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print(f"▶️ Neova giriş başlatılıyor... username={pwd.username}")
        page.goto("https://sigorta.neova.com.tr:4443/Login.aspx?ReturnUrl=%2fUIFrameSet.aspx", timeout=60000)
        time.sleep(3)

        if page.locator("#txtUsername").is_visible():
            print("🔐 Oturum kapalı, giriş yapılacak...")
            page.fill("#txtUsername", pwd.username)
            page.fill("#txtPassword", pwd.password)

            try:
                # 🔐 Kullanıcı adı ve şifre giriş butonu
                page.wait_for_selector("#btnLoginUser td.x-btn-center > em", timeout=15000)
                page.click("#btnLoginUser td.x-btn-center > em")
                print("✅ Kullanıcı adı ve şifre gönderildi, OTP bekleniyor...")

                try:
                    # 🔐 OTP alanı ve onay butonu
                    page.wait_for_selector("#txtGAKod", timeout=15000)
                    otp_code = pyotp.TOTP(pwd.otp_secret).now()
                    page.fill("#txtGAKod", otp_code)

                    page.wait_for_selector("#btnValidateTwoFactor td.x-btn-center > em", timeout=15000)
                    page.click("#btnValidateTwoFactor td.x-btn-center > em")
                    print("✅ OTP girildi, giriş tamamlanıyor...")
                    time.sleep(5)

                except Exception as e:
                    print(f"⚠️ OTP işlemi başarısız: {e}")

            except Exception as e:
                print(f"❌ Giriş butonuna tıklanamadı: {e}")
        else:
            print("✅ Oturum zaten açık, login ekranı atlandı.")

        # 🍪 Cookie alma
        cookies = context.cookies()
        cookie_dict = {
            c["name"]: c["value"]
            for c in cookies
            if "sigorta.neova.com.tr" in c["domain"]
        }

        print(f"📦 Toplam alınan cookie sayısı: {len(cookie_dict)}")
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        context.close()
        browser.close()
        return cookie_string





