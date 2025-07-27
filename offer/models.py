import uuid
from django.db import models
from agency.models import Branch,Agency
from agencyusers.models import Users
from database.models import Customer, PolicyBranch, InsuranceCompany
from gateway.models import ServiceConfiguration  # Servis modeli


def generate_uuid():
    return str(uuid.uuid4())

class ProposalUUIDMapping(models.Model):
    uuid = models.CharField(
        max_length=36,
        default=generate_uuid,
        unique=True,
        editable=False
    )

    proposal_id = models.PositiveIntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"UUID: {self.uuid} -> Proposal ID: {self.proposal_id}"

    class Meta:
        db_table = 'proposal_uuid_mapping'

class OfferFixedValue(models.Model):
    product_code = models.CharField(max_length=50)
    key_id = models.IntegerField()  # Hedef key
    value = models.FloatField()  # Sabit değer ya da çarpan
    multiply_with_key_id = models.IntegerField(null=True, blank=True)  # 🔥 Opsiyonel çarpım için kaynak key ID
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.product_code} - key_{self.key_id}"


class DaskMapping(models.Model):
    service = models.ForeignKey(ServiceConfiguration, on_delete=models.CASCADE)  # Hangi servis?
    service_key = models.CharField(max_length=100)       # Örn: "YapiTarzi"
    company_value = models.CharField(max_length=50)      # Örn: "4"
    key_id = models.IntegerField()                       # key_108 gibi
    parameter_id = models.IntegerField()                 # Parameter ID (eşleşecek)

    class Meta:
        unique_together = ('service', 'service_key', 'company_value', 'key_id')
        db_table = 'dask_mapping'

    def __str__(self):
        return f"[{self.service_id}] {self.service_key}={self.company_value} → key_{self.key_id} param_{self.parameter_id}"

class CustomerCompany(models.Model):
    identity_number = models.CharField(max_length=11, db_index=True)  # TC/VKN
    company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)  # Sigorta şirketi
    customer_no = models.CharField(max_length=100)  # Şirketten alınan müşteri numarası

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_company"
        unique_together = ("identity_number", "company")
        verbose_name = "Customer Company"
        verbose_name_plural = "Customer Companies"

    def __str__(self):
        return f"{self.identity_number} - {self.company.company_code} - {self.customer_no}"

class ProposalKey(models.Model):
    proposal_id = models.CharField(max_length=100)
    product_code = models.CharField(max_length=50)
    key_id = models.IntegerField()
    key_value = models.TextField(null=True, blank=True)

    agency = models.ForeignKey("agency.Agency", on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey("agencyusers.Users", on_delete=models.SET_NULL, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposalkeys"
        verbose_name = "Teklif Key Bilgisi"
        verbose_name_plural = "Teklif Key Bilgileri"
        unique_together = ("proposal_id", "product_code", "key_id")


class Proposal(models.Model):
    id = models.AutoField(primary_key=True)

    # Temel Kimlikler
    proposal_id = models.BigIntegerField(unique=True)
    uuid = models.CharField(
        max_length=36,
        default=generate_uuid,
        unique=True,
        editable=False
    )

    # İlişkili Varlıklar
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(Users, null=True, blank=True, on_delete=models.SET_NULL)

    # Ürün/Form Bilgisi
    form_type = models.CharField(max_length=50)
    product_code = models.IntegerField()
    policy_branch = models.ForeignKey(PolicyBranch, null=True, blank=True, on_delete=models.SET_NULL)

    # Durum (STATÜ)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Beklemede'),
            ('processing', 'İşleniyor'),
            ('completed', 'Tamamlandı'),
        ],
        default='pending'
    )

    # Teklif Bilgileri
    policy_start_date = models.DateField(null=True, blank=True)
    policy_end_date = models.DateField(null=True, blank=True)

    # Ürüne özgü varlık bilgisi
    property_identifier = models.CharField(max_length=100, null=True, blank=True)
    property_info = models.JSONField(null=True, blank=True)

    # Parent-child ilişki
    parent_proposal = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='child_proposals'
    )

    # Kayıt Bilgisi
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)  # <-- SOFT DELETE

    class Meta:
        db_table = "proposal"

class ProposalDetails(models.Model):
    id = models.AutoField(primary_key=True)

    proposal = models.ForeignKey("offer.Proposal", on_delete=models.CASCADE, related_name="details")
    proposal_code = models.BigIntegerField(null=True, blank=True)  # dış sistemdeki 9 haneli ID

    insurance_company = models.ForeignKey(InsuranceCompany, on_delete=models.CASCADE)

    product_code = models.CharField(max_length=50)
    sub_product_code = models.CharField(max_length=50, null=True, blank=True)

    gross_premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    premium = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    offer_number = models.CharField(max_length=255, null=True, blank=True)

    authorization_code = models.CharField(max_length=255, null=True, blank=True)
    authorization_detail = models.TextField(null=True, blank=True)

    currency = models.CharField(max_length=10, default="TRY")
    received_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Beklemede'),
            ('approved', 'Onaylandı'),
            ('rejected', 'Reddedildi'),
            ('timeout', 'Zaman Aşımı'),  # EKLEMEN ÖNERİLİR!
        ],
        default='pending'
    )

    agency = models.ForeignKey(Agency, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(Users, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposaldetails"
        indexes = [
            models.Index(fields=["proposal"]),
            models.Index(fields=["insurance_company"]),
            models.Index(fields=["product_code"]),
        ]

    def __str__(self):
        return f"{self.proposal_code} - {self.insurance_company.name} - {self.status}"

from django.db import models

class CompanyRevisableKey(models.Model):
    insurance_company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)
    product_code = models.CharField(max_length=50)
    sub_product_code = models.CharField(max_length=50, null=True, blank=True)

    key = models.ForeignKey("database.Key", on_delete=models.CASCADE)  # 'database' app label'ı gerekli
    target_company_key = models.CharField(max_length=255)
    template_variable = models.CharField(max_length=255)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "company_revisable_keys"
        unique_together = ("insurance_company", "product_code", "key", "target_company_key")

    def __str__(self):
        return f"{self.insurance_company.name} | {self.product_code} | {self.key.KeyName} → {self.target_company_key}"



