import os
import django
import pandas as pd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "INSAI.settings")
django.setup()

from agency.models import Branch
from database.models import Customer

excel_file_path = r'C:\Users\burak\PycharmProjects\INSAI2\Kitap1.xlsx'
df = pd.read_excel(excel_file_path)

errors = []

# Toplu veri için gerekirse baştan slicing kaldır (full dosyayı alacağız)
# df = df.head(500)  # <<< test satırı artık kaldırılacak!

for index, row in df.iterrows():
    try:
        identity_number = str(row['identity_number']).strip()
        full_name = str(row['full_name']).strip() if not pd.isna(row['full_name']) else None
        birth_date = row['birth_date'] if not pd.isna(row['birth_date']) else None
        branch_id = int(row['branch']) if not pd.isna(row['branch']) else None
        agency_id = int(row['agency_id']) if not pd.isna(row['agency_id']) else None
        user_id = int(row['user_id']) if not pd.isna(row['user_id']) else None
        phone_number = str(row['phone_number']).strip() if not pd.isna(row['phone_number']) else None
        phone_1 = str(row['phone_1']).strip() if not pd.isna(row['phone_1']) else None
        phone_2 = str(row['phone_2']).strip() if not pd.isna(row['phone_2']) else None
        phone_3 = str(row['phone_3']).strip() if not pd.isna(row['phone_3']) else None
        transfer_phone = str(row['transfer_phone']).strip() if not pd.isna(row['transfer_phone']) else None
        transfer_email = str(row['transfer_email']).strip() if not pd.isna(row['transfer_email']) else None

        branch = None
        if branch_id:
            branch = Branch.objects.filter(id=branch_id, agency_id=agency_id).first()

        customer, created = Customer.objects.update_or_create(
            identity_number=identity_number,
            defaults={
                'full_name': full_name,
                'birth_date': birth_date,
                'branch': branch,
                'agency_id': agency_id,
                'user_id': user_id,
                'phone_number': phone_number,
                'phone_1': phone_1,
                'phone_2': phone_2,
                'phone_3': phone_3,
                'transfer_phone': transfer_phone,
                'transfer_email': transfer_email,
            }
        )

        # --- İŞTE ÖZEL KURALLAR ---
        if len(identity_number) == 10:
            customer.type = "0"
            customer.is_verified = True
        elif len(identity_number) == 11:
            customer.type = "1"
            if birth_date:
                today = pd.to_datetime('today')
                age = (today - pd.to_datetime(birth_date)).days // 365
                if age < 18:
                    customer.is_verified = True
        # --------------------------------------

        customer.save()

    except Exception as e:
        errors.append(f"Satır {index}: {str(e)}")

if errors:
    print(f"❌ {len(errors)} hata oluştu:")
    for err in errors:
        print(err)
else:
    print("✅ Tüm kayıtlar başarıyla yüklendi.")
