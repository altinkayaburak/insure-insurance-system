# gateway/tasks.py (veya uygun bir yere ekle)
from celery import shared_task
import logging
logger = logging.getLogger(__name__)





@shared_task
def update_katilim_cookies(agency_id, source="auto"):
    import os
    import django
    import logging
    import pyotp

    logger = logging.getLogger(__name__)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords
    from database.models import CookieLog

    try:
        pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=35)
        otp_code = pyotp.TOTP(pwd.otp_secret).now()
        logger.warning(f"🔑 Katılım OTP üretildi: {otp_code}")

        cookie_string = extract_katilim_cookies(pwd, otp_code, logger)

        if cookie_string:
            pwd.cookie = cookie_string
            pwd.save()
            logger.warning(f"✅ Katılım cookie güncellendi → agency_id={agency_id}")
            CookieLog.objects.create(
                agency_id=agency_id,
                company_id=35,
                username=pwd.username,
                status="success",
                source=source,
                message="Cookie başarıyla alındı."
            )
        else:
            raise Exception("Cookie boş döndü, işlem başarısız.")

    except Exception as e:
        logger.exception(f"🚨 Katılım cookie alma sırasında hata oluştu: {e}")
        CookieLog.objects.create(
            agency_id=agency_id,
            company_id=35,
            username=pwd.username if 'pwd' in locals() else "bilinmiyor",
            status="fail",
            source=source,
            message=str(e)
        )

def extract_katilim_cookies(pwd, otp_code, logger):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logger.warning(f"▶️ Katılım giriş başlatılıyor... username={pwd.username}")
        page.goto('https://portal.turkiyekatilimsigorta.com.tr/')
        page.fill("#Username", pwd.username)
        page.fill("#Password", pwd.password)
        page.click("button[name='button'][value='login']")
        logger.warning("✅ Kullanıcı adı ve şifre gönderildi, OTP bekleniyor...")
        page.wait_for_timeout(3000)

        page.fill("#Code", otp_code)
        page.click("button[name='button'][value='verify']")
        logger.warning("✅ OTP girildi, giriş tamamlanıyor...")
        page.wait_for_timeout(5000)

        cookies = context.cookies()
        cookie_dict = {}
        for c in cookies:
            if c["name"] in ("XX", "ASP.NET_SessionId") and "turkiyekatilimsigorta.com.tr" in c["domain"]:
                cookie_dict[c["name"]] = c["value"]

        logger.warning(f"📦 Katılım → Toplam alınan cookie sayısı: {len(cookie_dict)}")

        needed_keys = ["XX", "ASP.NET_SessionId"]
        cookie_string = "; ".join(f"{k}={cookie_dict[k]}" for k in needed_keys if k in cookie_dict)

        context.close()
        browser.close()
        return cookie_string


@shared_task
def update_neova_cookies(agency_id, source="auto"):
    import os
    import django
    import logging

    logger = logging.getLogger(__name__)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords
    from database.models import CookieLog

    try:
        pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=26)
        cookie_string = extract_neova_cookies(pwd, logger)

        if cookie_string:
            pwd.cookie = cookie_string
            pwd.save()
            logger.warning(f"✅ Neova cookie güncellendi → agency_id={agency_id}")
            CookieLog.objects.create(
                agency_id=agency_id,
                company_id=26,
                username=pwd.username,
                status="success",
                source=source,
                message="Cookie başarıyla alındı."
            )
        else:
            raise Exception("Cookie boş döndü, işlem başarısız.")

    except Exception as e:
        logger.exception(f"🚨 Neova cookie alma sırasında hata oluştu: {e}")
        CookieLog.objects.create(
            agency_id=agency_id,
            company_id=26,
            username=pwd.username if 'pwd' in locals() else "bilinmiyor",
            status="fail",
            source=source,
            message=str(e)
        )

def extract_neova_cookies(pwd, logger):
    import time
    import pyotp
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logger.warning(f"▶️ Neova giriş başlatılıyor... username={pwd.username}")
        page.goto("https://sigorta.neova.com.tr:4443/Login.aspx?ReturnUrl=%2fUIFrameSet.aspx", timeout=60000)
        time.sleep(3)

        if page.locator("#txtUsername").is_visible():
            logger.warning("🔐 Oturum kapalı, giriş yapılacak...")
            page.fill("#txtUsername", pwd.username)
            page.fill("#txtPassword", pwd.password)

            try:
                page.wait_for_selector("#btnLoginUser td.x-btn-center > em", timeout=15000)
                page.click("#btnLoginUser td.x-btn-center > em")
                logger.warning("✅ Kullanıcı adı ve şifre gönderildi, OTP bekleniyor...")

                try:
                    page.wait_for_selector("#txtGAKod", timeout=15000)
                    otp_code = pyotp.TOTP(pwd.otp_secret).now()
                    page.fill("#txtGAKod", otp_code)

                    page.wait_for_selector("#btnValidateTwoFactor td.x-btn-center > em", timeout=15000)
                    page.click("#btnValidateTwoFactor td.x-btn-center > em")
                    logger.warning("✅ OTP girildi, giriş tamamlanıyor...")
                    time.sleep(5)

                except Exception as e:
                    logger.warning(f"⚠️ OTP işlemi başarısız: {e}")

            except Exception as e:
                logger.warning(f"❌ Giriş butonuna tıklanamadı: {e}")
        else:
            logger.warning("✅ Oturum zaten açık, login ekranı atlandı.")

        cookies = context.cookies()
        cookie_dict = {
            c["name"]: c["value"]
            for c in cookies
            if "sigorta.neova.com.tr" in c["domain"]
        }

        logger.warning(f"📦 Toplam alınan cookie sayısı: {len(cookie_dict)}")
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        context.close()
        browser.close()
        return cookie_string

@shared_task
def update_bereket_cookies(agency_id, source="auto"):
    import os
    import django
    import logging

    logger = logging.getLogger(__name__)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
    django.setup()

    from agency.models import AgencyPasswords
    from database.models import CookieLog

    try:
        pwd = AgencyPasswords.objects.get(agency_id=agency_id, insurance_company_id=12)
        cookie_string = extract_bereket_cookies(pwd, logger)

        if cookie_string:
            pwd.cookie = cookie_string
            pwd.save()
            logger.warning(f"✅ Bereket cookie güncellendi → agency_id={agency_id}")
            CookieLog.objects.create(
                agency_id=agency_id,
                company_id=12,
                username=pwd.username,
                status="success",
                source=source,
                message="Cookie başarıyla alındı."
            )
        else:
            raise Exception("Cookie boş döndü, işlem başarısız.")

    except Exception as e:
        logger.exception(f"🚨 Bereket cookie alma sırasında hata oluştu: {e}")
        CookieLog.objects.create(
            agency_id=agency_id,
            company_id=12,
            username=pwd.username if 'pwd' in locals() else "bilinmiyor",
            status="fail",
            source=source,
            message=str(e)
        )

def extract_bereket_cookies(pwd, logger):
    import time
    import pyotp
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logger.warning(f"▶️ Bereket giriş başlatılıyor... username={pwd.username}")
        page.goto("https://nareks.bereket.com.tr/Login.aspx?ReturnUrl=%2f")
        time.sleep(3)

        if page.locator("#txtUsername").is_visible():
            logger.warning("🔐 Oturum kapalı, giriş yapılacak...")

            page.fill("#txtUsername", pwd.username)
            page.fill("#txtPassword", pwd.password)
            page.click("#ext-gen30")
            logger.warning("✅ Kullanıcı adı ve şifre gönderildi, OTP bekleniyor...")

            try:
                page.wait_for_selector("#txtGAKod", timeout=15000)
                otp_code = pyotp.TOTP(pwd.otp_secret).now()
                page.fill("#txtGAKod", otp_code)
                page.click("#ext-gen69")
                logger.warning("✅ OTP girildi, giriş tamamlanıyor...")
                time.sleep(5)
            except Exception:
                logger.warning("⚠️ OTP alanı çıkmadı, sayfa yönlendirilmiş olabilir.")
        else:
            logger.warning("✅ Oturum zaten açık, login ekranı atlandı.")

        cookies = context.cookies()
        cookie_dict = {
            c["name"]: c["value"]
            for c in cookies
            if "bereket.com.tr" in c["domain"]
        }

        logger.warning(f"📦 Toplam alınan cookie sayısı: {len(cookie_dict)}")
        cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

        context.close()
        browser.close()
        return cookie_string


@shared_task
def update_all_cookies_for_agency(agency_id, source="manual"):
    from cookie.tasks import (
        update_katilim_cookies,
        update_neova_cookies,
        update_bereket_cookies,
    )

    update_katilim_cookies.delay(agency_id, source=source)
    update_neova_cookies.delay(agency_id, source=source)
    update_bereket_cookies.delay(agency_id, source=source)







