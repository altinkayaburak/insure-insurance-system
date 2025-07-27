import sys

import pandas as pd
import os
import django

sys.path.append(r"C:\Users\burak\PycharmProjects\INSAI2")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
django.setup()

from agencyusers.models import Users

df = pd.read_excel(r"C:\Users\burak\PycharmProjects\INSAI2\static\kullanicilar.xlsx")

for i, row in df.iterrows():
    try:
        user = Users.objects.get(identity_no=row['identity_no'])
        user.first_name = row['first_name']
        user.last_name = row['last_name']
        user.save()
        print(f"✅ Güncellendi: {user.username}")
    except Exception as e:
        print(f"❌ Hata: {row['identity_no']} — {str(e)}")
