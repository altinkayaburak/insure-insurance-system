import os
import django
import pyotp
import asyncio
from asgiref.sync import sync_to_async

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
django.setup()

from agency.models import AgencyPasswords

def playwright_block(pwd, otp_code, agency_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('https://portal.turkiyekatilimsigorta.com.tr/')
        page.fill("#Username", pwd.username)
        page.fill("#Password", pwd.password)
        page.click("button[name='button'][value='login']")
        page.wait_for_timeout(3000)
        page.fill("#Code", otp_code)
        page.click("button[name='button'][value='verify']")
        page.wait_for_timeout(5000)
        cookies = page.context.cookies()
        # SADECE ilk bulunan XX ve ilk bulunan ASP.NET_SessionId
        cookie_dict = {}
        for c in cookies:
            if c["name"] in ("XX", "ASP.NET_SessionId") and "turkiyekatilimsigorta.com.tr" in c["domain"]:
                if c["name"] not in cookie_dict:  # Sadece ilkini al
                    cookie_dict[c["name"]] = c["value"]
        # Sıralama önemli: XX önce, ASP.NET_SessionId sonra
        needed_keys = ["XX", "ASP.NET_SessionId"]
        cookie_string = "; ".join(f"{k}={cookie_dict[k]}" for k in needed_keys if k in cookie_dict)
        browser.close()
        return cookie_string



async def run_blocking_playwright(agency_id):
    pwd = await sync_to_async(AgencyPasswords.objects.get)(agency_id=agency_id, insurance_company_id=35)
    otp_code = pyotp.TOTP(pwd.otp_secret).now()
    cookie_string = await sync_to_async(playwright_block)(pwd, otp_code, agency_id)
    pwd.cookie = cookie_string
    await sync_to_async(pwd.save)()
    print(f"✅ Cookie güncellendi! Acente: {agency_id}")

if __name__ == "__main__":
    # Çoklu acente için:
    agency_ids = [3]  # veya [3, 5, 7, ...]
    asyncio.run(run_blocking_playwright(agency_ids[0]))
