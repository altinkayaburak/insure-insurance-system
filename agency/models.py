from django.db import models
from database.models import InsuranceCompany, ServiceConfiguration, OfferServiceConfiguration


class Agency(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!
    name = models.CharField(max_length=255, unique=True)
    domain = models.CharField(max_length=255, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    logo = models.ImageField(upload_to='agency_logos/', null=True, blank=True)  # Yeni alan
    insurance_companies = models.ManyToManyField(
        InsuranceCompany,
        related_name="agency_insurance_companies",
        blank=True
    )

    def save(self, *args, **kwargs):
        super(Agency, self).save(*args, **kwargs)
        if not Branch.objects.filter(agency=self, is_main=True).exists():
            Branch.objects.create(name="Main Branch", agency=self, is_main=True, branch_type="own")

    class Meta:
        db_table = "agency"
        verbose_name = "Acente"
        verbose_name_plural = "Acenteler"

    def __str__(self):
        return self.name


class Branch(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!

    """Şube Modeli"""
    name = models.CharField(max_length=255)  # Şube adı
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="branches")  # Acente ile ilişki
    is_main = models.BooleanField(default=False)  # Bu şube ana şube mi?
    branch_type = models.CharField(
        max_length=10,
        choices=[('own', 'Own Branch'), ('partner', 'Partner Branch')],
        default="own"
    )  # Şube türü

    class Meta:
        db_table = "agencybranch"
        verbose_name = "Şube"
        verbose_name_plural = "Şubeler"

    def __str__(self):
        return f"{self.name} - {self.agency.name}"


class AgencyCompany(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!

    """Acente ile Sigorta Şirketi Arasındaki İlişki"""
    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="agency_company_agencies"  # Benzersiz related_name
    )
    company = models.ForeignKey(
        InsuranceCompany,
        on_delete=models.CASCADE,
        related_name="agency_company_companies"  # Benzersiz related_name
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agencycompany"
        verbose_name = 'Acente-Şirket İlişkisi'
        verbose_name_plural = 'Acente-Şirket İlişkileri'
        unique_together = ('agency', 'company')  # Aynı acente ve şirket kombinasyonu tekrar edemez

    def __str__(self):
        return f"{self.agency.name} - {self.company.name}"


class AgencyPasswords(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!

    """Acentelere Özel Sigorta Şirketi Giriş Bilgileri"""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="passwords")  # Acente
    insurance_company = models.ForeignKey(InsuranceCompany, on_delete=models.CASCADE, related_name="passwords")  # Sigorta Şirketi
    username = models.CharField(max_length=255, null=True, blank=True)  # Kullanıcı adı
    password = models.CharField(max_length=255, null=True, blank=True)  # Şifre
    partaj_code = models.CharField(max_length=255, null=True, blank=True)  # Partaj kodu
    web_username = models.CharField(max_length=255, null=True, blank=True)  # Web kullanıcı adı
    web_password = models.CharField(max_length=255, null=True, blank=True)  # Web şifresi
    otp_secret = models.CharField(max_length=255, null=True, blank=True)  # OTP Secret (yeni eklendi)
    cookie = models.TextField(null=True, blank=True)  # Cookie bilgisi
    created_at = models.DateTimeField(auto_now_add=True)  # Oluşturulma tarihi
    appSecurityKey = models.CharField(max_length=255, null=True, blank=True)
    authenticationKey = models.TextField(null=True, blank=True)
    token_username = models.CharField(max_length=255, null=True, blank=True)
    token_password = models.CharField(max_length=255, null=True, blank=True)
    client_id = models.CharField(max_length=255, null=True, blank=True)
    secret_id = models.CharField(max_length=255, null=True, blank=True)
    token_url = models.URLField(null=True, blank=True)  # ✅ Yeni alan burası
    sube_kod = models.CharField(max_length=50, null=True, blank=True)  # ✅ Şube kodu
    kaynak_kod = models.CharField(max_length=50, null=True, blank=True)  # ✅ Kaynak kod

    class Meta:
        db_table = "agencypasswords"  # Veritabanında tablo adı
        verbose_name = 'Acente Şifre Bilgisi'
        verbose_name_plural = 'Acente Şifre Bilgileri'
        unique_together = ('agency', 'insurance_company')  # Aynı acente ve şirket kombinasyonu tekrar edemez

    def __str__(self):
        return f"{self.agency.name} - {self.insurance_company.name}"


class AgencyServiceAuthorization(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="authorized_services"
    )
    service = models.ForeignKey(
        ServiceConfiguration,
        on_delete=models.CASCADE,
        related_name="authorized_agencies"
    )
    is_active = models.BooleanField(default=True)  # ✅ Yeni eklendi
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agencyserviceauthorization"
        verbose_name = "Yetkilendirilmiş Servis"
        verbose_name_plural = "Yetkilendirilmiş Servisler"
        unique_together = ("agency", "service")

    def __str__(self):
        return f"{self.agency.name} - {self.service.service_name}"

class AgencyOfferServiceAuthorization(models.Model):
    id = models.BigAutoField(primary_key=True)  # Bunu ekle!

    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name="authorized_offer_services"
    )
    offer_service = models.ForeignKey(
        OfferServiceConfiguration,
        on_delete=models.CASCADE,
        related_name="authorized_agencies"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agencyofferserviceauthorization"
        verbose_name = "Yetkilendirilmiş Teklif Servisi"
        verbose_name_plural = "Yetkilendirilmiş Teklif Servisleri"
        unique_together = ("agency", "offer_service")

    def __str__(self):
        return f"{self.agency.name} - {self.offer_service.service_name}"

class AgencyTransferServiceAuthorization(models.Model):
    agency = models.ForeignKey("Agency", on_delete=models.CASCADE)
    transfer_service = models.ForeignKey("database.TransferServiceConfiguration", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("agency", "transfer_service")
        db_table = "agencytransferserviceauthorization"  # 🔧 MSSQL'deki tablo adı ile birebir


