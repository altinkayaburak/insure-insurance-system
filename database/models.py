import string,random
from datetime import datetime,date
from django.db import models




class City(models.Model):
    CityCode = models.PositiveIntegerField(primary_key=True)
    CityName = models.CharField(max_length=100)
    MapCode = models.CharField(max_length=10, null=True, blank=True)  # 🔽 örn: "tr-34"

    def __str__(self):
        return self.CityName

    class Meta:
        db_table = "City"
        verbose_name = "City"
        verbose_name_plural = "Cities"


class TravelCountry(models.Model):
    country_code = models.IntegerField(unique=True)
    country_name = models.CharField(max_length=120)

    class Meta:
        db_table = "travel_country"
        verbose_name = "Travel Country"
        verbose_name_plural = "Travel Countries"

    def __str__(self):
        return f"{self.country_name} ({self.country_code})"

class Key(models.Model):
    KeyID = models.AutoField(primary_key=True)  # Otomatik artan anahtar
    KeyName = models.CharField(max_length=255)  # Teknik ad
    Description = models.TextField(blank=True, null=True)  # Formda gösterilecek açıklama/etiket

    InputType = models.CharField(max_length=50, null=True, blank=True)  # text, select, checkbox, date...
    MinLength = models.IntegerField(null=True, blank=True)
    MaxLength = models.IntegerField(null=True, blank=True)
    RegexPattern = models.CharField(max_length=255, blank=True, null=True)

    # Koşullu görünürlük için:
    VisibleIfKey = models.CharField(max_length=255, blank=True, null=True)
    VisibleIfValue = models.CharField(max_length=255, blank=True, null=True)

    # Sistemsel alanlar
    IsActive = models.BooleanField(default=True)
    CreatedDate = models.DateTimeField(auto_now_add=True)
    UpdatedDate = models.DateTimeField(null=True, auto_now=True)
    DeletedDate = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'keys'

    def __str__(self):
        return self.KeyName

class Parameter(models.Model):
    ParameterID = models.AutoField(primary_key=True)  # ✅ Primary Key olarak tanımlandı
    ParameterName = models.CharField(max_length=100)
    DefaultValue = models.CharField(max_length=255, null=True, blank=True)
    CreatedDate = models.DateTimeField(auto_now_add=True)
    UpdatedDate = models.DateTimeField(null=True,auto_now=True)
    IsActive = models.BooleanField(default=True)

    class Meta:
        db_table = 'parameters'  # Tablo adı

class KeyParameters(models.Model):
    KeyParameterID = models.AutoField(primary_key=True)  # Anahtar
    KeyID = models.ForeignKey('Key', on_delete=models.CASCADE, db_column='KeyID', to_field="KeyID")  # Key tablosuna bağlı
    ParameterID = models.ForeignKey('Parameter', on_delete=models.CASCADE, db_column='ParameterID', to_field="ParameterID")  # Parameter tablosuna bağlı
    CreatedDate = models.DateTimeField(auto_now_add=True)  # Oluşturulma tarihi

    class Meta:
        db_table = 'keyparameters'
        unique_together = ('KeyID', 'ParameterID')  # Aynı Key ve Parameter ikilisi tekrar olamaz

    def __str__(self):
        return f"Key: {self.KeyID} - Parameter: {self.ParameterID}"

class InsuranceCompany(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    company_code = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    parser_function = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="Yanıtları işlemek için kullanılacak parser fonksiyon adı"
    )

    has_credit_card_task = models.BooleanField(
        default=False,
        help_text="Bu şirketin kredi kartı servisi Celery task ile ayrı çalışır"
    )

    credit_card_handler_function = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Kredi kartı task'ını tetikleyecek fonksiyon adı"
    )

    class Meta:
        db_table = 'insurancecompany'
        verbose_name = 'Sigorta Şirketi'
        verbose_name_plural = 'Sigorta Şirketleri'

    def __str__(self):
        return self.name

class ServiceConfiguration(models.Model):
    id = models.AutoField(primary_key=True)  # <<< BU SATIRI EN ÜSTE EKLE!
    insurance_company = models.ForeignKey(
        'InsuranceCompany',
        on_delete=models.CASCADE,
        null=False,
        related_name='service_configurations'
    )
    service_name = models.CharField(max_length=255)
    url = models.URLField()
    soap_action = models.CharField(max_length=255, null=True, blank=True)
    soap_template = models.TextField(null=True, blank=True)

    # ✅ Ortak Auth alanları
    requires_auth = models.BooleanField(default=False)
    auth_username = models.CharField(max_length=255, null=True, blank=True)
    auth_password = models.CharField(max_length=255, null=True, blank=True)
    custom_headers = models.JSONField(null=True, blank=True)

    # ✅ API ile ilgili alanlar
    is_api = models.BooleanField(default=False)
    http_method = models.CharField(max_length=10, choices=[('GET', 'GET'), ('POST', 'POST')], default='POST')
    content_type = models.CharField(max_length=50, default='application/json')
    request_template = models.TextField(null=True, blank=True)

    # ✅ PDF/Belge servisi için yeni alanlar:
    response_type = models.CharField(
        max_length=20,
        choices=[
            ('url', 'URL'),
            ('base64', 'Base64'),
            ('bytes', 'Bytes/Binary'),
        ],
        default='url',
        help_text="Servis PDF çıktısı hangi formatta döner? Örn: url, base64, bytes"
    )
    pdf_field_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Cevapta PDF verisinin bulunduğu path (XML veya JSON key, ör: .//Base64)"
    )

    error_field_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Hata/uyarı mesajı XML veya JSON key path (ör: .//Message, .//faultstring)"
    )

    policy_list_path = models.TextField(
        null=True,
        blank=True,
        help_text="Poliçe listesi path (birden fazla path için | ile ayır)"
    )

    requires_detail_service = models.BooleanField(
        default=True,
        help_text="Bu servis için detay servisine çıkılması gerekiyor mu? (True=Çıkılacak, False=Tek response ile tamam)"
    )

    detail_service = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='master_services',
        help_text="İlk servis sonrası çıkılacak detay servis (örn: detay/lookup servisi)."
    )

    has_full_detail_in_first_service = models.BooleanField(
        default=False,
        help_text="Müşteri/varlık/tahsilat gibi detaylar ilk toplu serviste geliyor mu? (True: Evet, False: Hayır)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'serviceconfigurations'
        verbose_name = 'Servis Yapılandırması'
        verbose_name_plural = 'Servis Yapılandırmaları'

    def __str__(self):
        return f"{self.service_name} ({self.insurance_company})"

class OfferServiceConfiguration(models.Model):
    insurance_company = models.ForeignKey('InsuranceCompany', on_delete=models.CASCADE, related_name='offer_services')
    service_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    product_code = models.CharField(max_length=50)
    sub_product_code = models.CharField(max_length=50, null=True, blank=True)
    sub_product_description = models.CharField(max_length=255, null=True, blank=True)
    url = models.URLField()
    soap_action = models.CharField(max_length=255, null=True, blank=True)
    soap_template = models.TextField(null=True, blank=True)

    # ✅ Ortak Auth alanları
    requires_auth = models.BooleanField(default=False)
    auth_username = models.CharField(max_length=255, null=True, blank=True)
    auth_password = models.CharField(max_length=255, null=True, blank=True)
    custom_headers = models.JSONField(null=True, blank=True)

    # ✅ API ile ilgili yeni alanlar
    is_api = models.BooleanField(default=False)
    http_method = models.CharField(max_length=10, choices=[('GET', 'GET'), ('POST', 'POST')], default='POST')
    content_type = models.CharField(max_length=50, default='application/json')
    request_template = models.TextField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    parser_function = models.CharField(max_length=100, null=True, blank=True,help_text="Yanıtları işlemek için kullanılacak parser fonksiyon adı")

    class Meta:
        db_table = 'offer_service_configurations'
        verbose_name = 'Teklif Servisi'
        verbose_name_plural = 'Teklif Servisleri'

    def __str__(self):
        return f"{self.insurance_company.name} - {self.service_name}"

class TransferServiceConfiguration(models.Model):
    insurance_company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)
    service_name = models.CharField(max_length=255)
    url = models.URLField()
    soap_action = models.CharField(max_length=255, null=True, blank=True)
    soap_template = models.TextField(null=True, blank=True)

    policy_list_path = models.TextField(null=True, blank=True)
    error_field_path = models.CharField(max_length=255, null=True, blank=True)

    requires_detail_service = models.BooleanField(default=True)
    detail_service = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    has_full_detail_in_first_service = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    viewstate = models.TextField(null=True, blank=True)
    eventvalidation = models.TextField(null=True, blank=True)
    submit_ajax_template = models.TextField(
        null=True, blank=True,
        help_text="submitAjaxEventConfig içeriği için jinja2 template"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    date_format = models.CharField(
        max_length=20,
        default="%%d.%%m.%%Y",
        help_text="Servise gönderilecek tarih formatı"
    )

    handler_function = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Servisi çalıştıracak Python fonksiyonunun adı"
    )

    # API/TOKEN destekli servisler için ek alanlar
    is_api = models.BooleanField(default=False)
    http_method = models.CharField(
        max_length=10,
        choices=[('GET', 'GET'), ('POST', 'POST')],
        default='POST'
    )
    content_type = models.CharField(
        max_length=50,
        default='application/json'
    )
    request_template = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'transfer_service_configurations'


def generate_customer_key():
    today = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(random.choices(string.digits, k=8))  # 8 haneli random
    return f"CUS-{today}-{random_part}"

class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    customer_key = models.CharField(max_length=30, unique=True, editable=False)  # Sistem tarafından üretilir

    # Mapping/KeyName ile gelen universal alanlar
    identity_number = models.CharField(max_length=20)        # 256
    birth_date = models.DateField(null=True, blank=True)     # 257
    full_name = models.CharField(max_length=255, default="Bulunamadı")     # 258
    DogumYeri = models.CharField(max_length=100, null=True, blank=True)    # 259
    Cinsiyet = models.CharField(max_length=10, null=True, blank=True)      # 265
    BabaAdi = models.CharField(max_length=100, null=True, blank=True)      # 261
    AnneAdi = models.CharField(max_length=100, null=True, blank=True)      # 262
    MedeniDurum = models.CharField(max_length=50, null=True, blank=True)   # 263
    type = models.CharField(max_length=10, null=True, blank=True)          # Universal (bireysel/tüzel)
    VefatTarihi = models.DateField(null=True, blank=True)                  # 264
    Uyruk = models.CharField(max_length=10, null=True, blank=True)         # 266
    UyrukDiger = models.CharField(max_length=10, null=True, blank=True)    # 267

    RizikoUavtKod = models.CharField(max_length=50, null=True, blank=True)     # 102
    Riziko_il_kod = models.CharField(max_length=10, null=True, blank=True)    # 195
    Riziko_ilce_kodu = models.CharField(max_length=10, null=True, blank=True) # 196

    is_verified = models.BooleanField(default=False)
    agency_id = models.IntegerField()
    user_id = models.IntegerField(null=True, blank=True)
    branch_id = models.IntegerField(null=True, blank=True)

    RizikoAcikAdres = models.TextField(null=True, blank=True)      # 103
    image_url = models.URLField(null=True, blank=True)
    app_user_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'customers'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        unique_together = ("agency_id", "identity_number")  # ✅ tenant isolation için

    def __str__(self):
        return f"{self.identity_number} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.customer_key:
            self.customer_key = generate_customer_key()
        super().save(*args, **kwargs)

    @property
    def age(self):
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )


class CustomerContact(models.Model):
    CONTACT_TYPE_CHOICES = [
        ('phone', 'Phone'),
        ('email', 'Email'),
        # Gerekirse: ('fax', 'Fax'), ('whatsapp', 'WhatsApp'),
    ]
    LABEL_CHOICES = [
        ('main', 'Birincil'),    # Sadece ilk kayıt için kullanılabilir
        ('dask', 'DASK'),        # Servislerden otomatik gelebilir
        ('transfer', 'Transfer'),# Servislerden otomatik gelebilir
        ('other', 'Diğer'),      # Tüm manuel ve sonraki kayıtlar için default
    ]

    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='contacts')
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPE_CHOICES)
    value = models.CharField(max_length=100)  # Numara ya da e-posta

    label = models.CharField(
        max_length=20,
        choices=LABEL_CHOICES,
        default='other',
        help_text="Etiket kullanıcı tarafından seçilemez. İlk kayıt main, diğerleri other/servis otomatik."
    )
    is_verified = models.BooleanField(default=False)  # SMS/email doğrulaması ile
    is_primary = models.BooleanField(default=False)   # Sadece ilk kayıtta True olur
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    passive_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'customer_contacts'
        verbose_name = 'Customer Contact'
        verbose_name_plural = 'Customer Contacts'
        constraints = [
            models.UniqueConstraint(fields=['customer', 'value'], name='unique_customer_contact_value')
        ]

    def __str__(self):
        return f"{self.customer} - {self.get_contact_type_display()}: {self.value}"


class RelationshipType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    reverse_name = models.CharField(max_length=50, null=True, blank=True)  # ✅ EKLENDİ
    is_active = models.BooleanField(default=True)

    APPLICABLE_CHOICES = [
        ("individual_to_individual", "Bireysel → Bireysel"),
        ("individual_to_corporate",  "Bireysel → Tüzel"),
        ("corporate_to_individual",  "Tüzel → Bireysel"),
        ("corporate_to_corporate",   "Tüzel → Tüzel"),
    ]

    applicable_to = models.CharField(
        max_length=30,
        choices=APPLICABLE_CHOICES,
        default="individual_to_individual"
    )

    class Meta:
        db_table = "relationship_types"
        verbose_name = "Relationship Type"
        verbose_name_plural = "Relationship Types"

    def __str__(self):
        return self.name

class CustomerRelationship(models.Model):
    from_customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='related_customers')
    to_customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='related_to')
    relationship_type = models.ForeignKey('RelationshipType', on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_relationships"
        verbose_name = "Customer Relationship"
        verbose_name_plural = "Customer Relationships"
        constraints = [
            models.UniqueConstraint(
                fields=["from_customer", "to_customer", "relationship_type"],
                name="unique_customer_relationship"
            )
        ]

class PolicyMainBranch(models.Model):
    id = models.AutoField(primary_key=True)  # 🔧 SQL'de int olarak tanımlandıysa açıkça belirt
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "policy_main_branch"
        verbose_name = "Poliçe Ana Branş"
        verbose_name_plural = "Poliçe Ana Branşlar"

    def __str__(self):
        return self.name


class PolicyBranch(models.Model):
    id = models.AutoField(primary_key=True)  # 🔧 ForeignKey uyumu için int tipinde
    name = models.CharField(max_length=100)
    code = models.IntegerField(unique=True)
    main_branch = models.ForeignKey(PolicyMainBranch, on_delete=models.CASCADE)

    class Meta:
        db_table = "policy_branch"
        verbose_name = "Poliçe Branşı"
        verbose_name_plural = "Poliçe Branşları"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Products(models.Model):
    # Şirket bilgisi (ForeignKey)
    company = models.ForeignKey(
        InsuranceCompany,
        on_delete=models.CASCADE,
        verbose_name="Sigorta Şirketi"
    )

    # Ürün bilgileri
    code = models.CharField(max_length=100, verbose_name="Ürün Kodu")  # unique=True kaldırıldı
    name = models.CharField(max_length=255, verbose_name="Ürün Adı")

    # Branş ilişkileri
    branch = models.ForeignKey(
        PolicyBranch,
        on_delete=models.CASCADE,
        verbose_name="Alt Branş",
        null=True,
        blank=True
    )
    main_branch = models.ForeignKey(
        PolicyMainBranch,
        on_delete=models.CASCADE,
        verbose_name="Ana Branş",
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        db_table = 'products'
        verbose_name = "Ürün"
        verbose_name_plural = "Ürünler"
        unique_together = ('company', 'code')  # 🔥 Ekledik

class Policy(models.Model):
    id = models.AutoField(primary_key=True)

    uuid = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        null=True,
        blank=True
    )

    PoliceTipi = models.CharField(max_length=50, null=True, blank=True)                # 226
    PoliceTanzimTarihi = models.DateField(null=True, blank=True)                       # 54
    PoliceBaslangicTarihi = models.DateField(null=True, blank=True)                    # 55
    PoliceBitisTarihi = models.DateField(null=True, blank=True)                        # 56
    PoliceİptalTarihi = models.DateField(null=True, blank=True)                        # 227

    PoliceNo = models.CharField(max_length=50)                                         # 45
    ZeyilNo = models.CharField(max_length=5, null=True, blank=True)                    # 47
    YenilemeNo = models.CharField(max_length=5, default="0", null=True, blank=True)    # 46
    PoliceNoKombine = models.CharField(max_length=100, editable=False, db_index=True)  # 228

    PoliceAnaKey = models.CharField(
        max_length=100,
        editable=False,
        db_index=True,
        help_text="PoliceNo-YenilemeNo kombinasyonu ile benzersiz anahtar"
    )

    ZeyilKodu = models.CharField(max_length=10, null=True, blank=True)                 # 49
    ZeyilAdi = models.CharField(max_length=255, null=True, blank=True)                 # 48

    # ForeignKey alanlar birebir bu isimlerle
    user = models.ForeignKey(
        'agencyusers.Users', on_delete=models.SET_NULL, null=True, blank=True, related_name='policies'
    )
    agency = models.ForeignKey(
        'agency.Agency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='policies'
    )

    customer = models.ForeignKey(
        'database.Customer', on_delete=models.CASCADE, related_name='policies'
    )
    insured = models.ForeignKey(
        'database.Customer', on_delete=models.CASCADE, related_name='insured_policies', null=True, blank=True
    )

    company = models.ForeignKey('InsuranceCompany', on_delete=models.SET_NULL, null=True, db_column='company_id',related_name='policies')

    SirketUrunNo = models.CharField(max_length=100, null=True, blank=True)             # 41
    PoliceGirisiKullanici = models.CharField(max_length=100, null=True, blank=True)    # 253
    SatisKaynagi = models.CharField(max_length=50, null=True, blank=True)              # 229
    PoliceOlusturanKullanici = models.CharField(max_length=100, null=True, blank=True) # 231
    PoliceKesenKullanici = models.CharField(max_length=100, null=True, blank=True)     # 230

    AktifMi = models.CharField(max_length=10, null=True, blank=True)    # 44
    PolicyStatus = models.ForeignKey('database.PolicyStatus', on_delete=models.SET_NULL, null=True, blank=True)
    delete_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_synced_by = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'policies'
        verbose_name = 'Policy'
        verbose_name_plural = 'Policies'

    def save(self, *args, **kwargs):
        if not self.uuid:
            self.uuid = generate_customer_key().replace("CUS", "POL")  # Örn: POL-20250629-12345678

        renewal = self.YenilemeNo if self.YenilemeNo is not None else "0"
        zeyil = self.ZeyilNo if self.ZeyilNo is not None else "0"
        self.PoliceNoKombine = f"{self.PoliceNo}-{zeyil}-{renewal}"
        self.PoliceAnaKey = f"{self.PoliceNo}-{renewal}"

        try:
            self.PoliceTipi = "Zeyil" if int(zeyil) > 0 else "Police"
        except Exception:
            self.PoliceTipi = None

        super().save(*args, **kwargs)

class ExternalTramerPolicy(models.Model):
    agency = models.ForeignKey('agency.Agency', on_delete=models.CASCADE, null=True, related_name='external_tramer_policies')
    customer = models.ForeignKey('database.Customer', on_delete=models.SET_NULL, null=True, related_name='external_tramer_policies')
    asset_car = models.ForeignKey('database.AssetCars', on_delete=models.SET_NULL, null=True, related_name='external_tramer_policies')
    branch = models.ForeignKey("PolicyBranch", on_delete=models.SET_NULL, null=True, blank=True,related_name="external_tramer_policies")

    IptalMi = models.BooleanField(default=False)
    AcentePartajNo = models.CharField(max_length=20, null=True, blank=True)
    PoliceTanzimTarihi = models.DateTimeField(null=True, blank=True)
    PoliceBaslangicTarihi = models.DateTimeField(null=True, blank=True)
    PoliceBitisTarihi = models.DateTimeField(null=True, blank=True)
    SigortaSirketiKodu = models.CharField(max_length=10, null=True, blank=True)
    PoliceNo = models.CharField(max_length=30, null=True, blank=True)
    YenilemeNo = models.CharField(max_length=10, null=True, blank=True)
    ZeyilNo = models.CharField(max_length=10, null=True, blank=True)
    ZeyilAdi = models.CharField(max_length=255, null=True, blank=True)
    ZeyilKodu = models.CharField(max_length=10, null=True, blank=True)
    ZeyilTanzimTarihi = models.DateTimeField(null=True, blank=True)
    PoliceOnayTarihi = models.DateTimeField(null=True, blank=True)
    ZeyilBaslangicTarihi = models.DateTimeField(null=True, blank=True)
    ZeyilBitisTarihi = models.DateTimeField(null=True, blank=True)
    AracTrafikKademe = models.CharField(max_length=10, null=True, blank=True)
    AracKaskoKademe = models.CharField(max_length=10, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "external_tramer_policy"
        unique_together = ("agency", "PoliceNo", "YenilemeNo", "ZeyilNo")


class PolicyStatus(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "policy_status"

class Collection(models.Model):
    id = models.AutoField(primary_key=True)  # INT olur
    PoliceNoKombine = models.CharField(max_length=100, db_index=True)

    policy = models.ForeignKey(
        'database.Policy',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='collections'
    )
    agency = models.ForeignKey(
        'agency.Agency',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='collections',
        db_column='agency_id'
    )
    customer = models.ForeignKey(
        'database.Customer',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='collections_by_customer'
    )

    insured = models.ForeignKey(
        'database.Customer',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    BrutPrim = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    NetPrim = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    Komisyon = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    BrutPrimTL = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    NetPrimTL = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    KomisyonPrimTL = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ZeyilKomisyonu = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    EkKomisyon = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    GHP = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    GiderVergisi = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    THGF = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    YSV = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    SGKPayi = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    TaksitSayisi = models.IntegerField(null=True, blank=True)
    TaksitTipiAciklama = models.CharField(max_length=255, null=True, blank=True)
    KKBlokeli = models.BooleanField(null=True, blank=True)
    OdemeSekli = models.CharField(max_length=20, null=True, blank=True)

    DovizKuru = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    DovizCinsi = models.CharField(max_length=10, null=True, blank=True)

    KartSahibi = models.CharField(max_length=100, null=True, blank=True)
    KrediKartNo = models.CharField(max_length=30, null=True, blank=True)

    KomisyonOran = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    KomisyonOranNet = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    PaylasimOran = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delete_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "collection"
        verbose_name = "Collection"
        verbose_name_plural = "Collections"
        indexes = [
            models.Index(fields=['PoliceNoKombine']),
        ]

    def __str__(self):
        return f"{self.PoliceNoKombine}"

    def save(self, *args, **kwargs):
        # Komisyon Oranı: KomisyonPrimTL / BrutPrimTL
        if self.BrutPrimTL and self.KomisyonPrimTL:
            try:
                oran = (self.KomisyonPrimTL / self.BrutPrimTL) * 100
                self.KomisyonOran = round(oran, 2)
            except ZeroDivisionError:
                self.KomisyonOran = None

        # Komisyon Net Oranı: KomisyonPrimTL / NetPrimTL
        if self.NetPrimTL and self.KomisyonPrimTL:
            try:
                oran_net = (self.KomisyonPrimTL / self.NetPrimTL) * 100
                self.KomisyonOranNet = round(oran_net, 2)
            except ZeroDivisionError:
                self.KomisyonOranNet = None

        super().save(*args, **kwargs)


class PaymentPlan(models.Model):
    id = models.AutoField(primary_key=True)  # INT olur
    policy = models.ForeignKey(
        'database.Policy', on_delete=models.CASCADE, null=True, blank=True, related_name='payment_plans'
    )
    agency = models.ForeignKey(
        'agency.Agency', on_delete=models.CASCADE, null=True, blank=True, related_name='payment_plans'
    )

    PoliceNoKombine = models.CharField(max_length=100, db_index=True)
    TaksitSirasi = models.CharField(max_length=10, null=True, blank=True)  # Örn: "P", "2", "3", "4"
    TaksitVadeTarihi = models.DateField(null=True, blank=True)
    TaksitTutar = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delete_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payment_plan"
        verbose_name = "Payment Plan"
        verbose_name_plural = "Payment Plans"


    def __str__(self):
        return f"{self.PoliceNoKombine} | {self.TaksitSirasi} | {self.TaksitVadeTarihi} → {self.TaksitTutar}"

class PolicyAssetRelation(models.Model):
    policy = models.ForeignKey("database.Policy", on_delete=models.CASCADE)
    asset_car = models.ForeignKey("database.AssetCars", null=True, blank=True, on_delete=models.CASCADE)
    asset_home = models.ForeignKey("database.AssetHome", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        db_table = "policy_asset_relation"
        verbose_name = "Poliçe Varlık İlişkisi"
        verbose_name_plural = "Poliçe Varlık İlişkileri"
        constraints = [
            models.UniqueConstraint(fields=["policy", "asset_car"], name="unique_policy_car"),
            models.UniqueConstraint(fields=["policy", "asset_home"], name="unique_policy_home"),
        ]

    def __str__(self):
        if self.asset_car:
            return f"{self.policy_id} → Araç: {self.asset_car}"
        if self.asset_home:
            return f"{self.policy_id} → Konut: {self.asset_home}"
        return f"{self.policy_id} → Varlık Yok"

class AssetCars(models.Model):
    policy = models.ForeignKey(
        'database.Policy', on_delete=models.CASCADE,
        null=True, blank=True, related_name='car_assets'
    )

    agency = models.ForeignKey(
        'agency.Agency', on_delete=models.CASCADE,
        related_name='car_assets'
    )
    insured = models.ForeignKey(
        'database.Customer', on_delete=models.CASCADE,
        related_name='vehicle_assets'
    )

    PoliceNoKombine = models.CharField(max_length=100, db_index=True)
    AktifMi = models.BooleanField(default=True)

    AracPlakailKodu = models.CharField(max_length=10, null=True, blank=True)
    AracPlakaNo = models.CharField(max_length=10, null=True, blank=True)
    AracPlakaTam = models.CharField(max_length=20, null=True, blank=True)
    AracTescilSeriKod = models.CharField(max_length=20, null=True, blank=True)
    AracTescilSeriNo = models.CharField(max_length=20, null=True, blank=True)
    AracTescilTam = models.CharField(max_length=20, null=True, blank=True)

    AracKullanimTarzi = models.CharField(max_length=50, null=True, blank=True)
    TramerAracTarz = models.CharField(max_length=50, null=True, blank=True)
    EGMUstCins = models.CharField(max_length=50, null=True, blank=True)
    EGMAltCins = models.CharField(max_length=50, null=True, blank=True)
    AracModelYili = models.CharField(max_length=10, null=True, blank=True)
    AracBirlikKodu = models.CharField(max_length=20, null=True, blank=True)
    AracMarkaKodu = models.CharField(max_length=20, null=True, blank=True)
    AracTipKodu = models.CharField(max_length=20, null=True, blank=True)
    AracMarkaAdi = models.CharField(max_length=50, null=True, blank=True)
    AracTipAdi = models.CharField(max_length=50, null=True, blank=True)
    AracMotorNo = models.CharField(max_length=30, null=True, blank=True)
    AracSasiNo = models.CharField(max_length=30, null=True, blank=True)
    AracKisiSayisi = models.CharField(max_length=10, null=True, blank=True)
    AracRenk = models.CharField(max_length=100, null=True, blank=True)
    AracMotorGucu = models.CharField(max_length=20, null=True, blank=True)
    AracSilindirHacmi = models.CharField(max_length=20, null=True, blank=True)
    AracYakitTipi = models.CharField(max_length=20, null=True, blank=True)
    AracTrafigeCikisTarihi = models.DateField(null=True, blank=True)
    AracTescilTarihi = models.DateField(null=True, blank=True)
    AracTrafikKademe = models.CharField(max_length=10, null=True, blank=True)
    AracKaskoKademe = models.CharField(max_length=10, null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delete_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "asset_cars"
        verbose_name = "Asset Cars"
        verbose_name_plural = "Asset Cars"
        indexes = [
            models.Index(fields=['PoliceNoKombine', 'insured']),
        ]
        unique_together = ("insured", "AracSasiNo")

    def __str__(self):
        return f"{self.PoliceNoKombine} - {self.AracPlakaTam}"

    def save(self, *args, **kwargs):
        # 🔧 Plaka tam birleştirme (eğer boşsa)
        if not self.AracPlakaTam and (self.AracPlakailKodu or self.AracPlakaNo):
            self.AracPlakaTam = f"{self.AracPlakailKodu or ''}{self.AracPlakaNo or ''}".strip()

        # 🔧 Tescil tam birleştirme (eğer boşsa)
        if not self.AracTescilTam and (self.AracTescilSeriKod or self.AracTescilSeriNo):
            self.AracTescilTam = f"{self.AracTescilSeriKod or ''}{self.AracTescilSeriNo or ''}".strip()

        super().save(*args, **kwargs)


class AssetHome(models.Model):
    policy = models.ForeignKey(
        'database.Policy', on_delete=models.CASCADE,
        null=True, blank=True, related_name='home_assets'
    )
    agency = models.ForeignKey(
        'agency.Agency', on_delete=models.CASCADE,
        related_name='home_assets'
    )
    insured = models.ForeignKey(
        'database.Customer', on_delete=models.CASCADE,
        related_name='home_assets'
    )

    PoliceNoKombine = models.CharField(max_length=100, db_index=True)
    AktifMi = models.BooleanField(default=True)

    RizikoDaskPoliceNo = models.CharField(max_length=50, null=True, blank=True)
    RizikoDaskYenilemeNo = models.CharField(max_length=50, null=True, blank=True)
    RizikoUavtKod = models.CharField(max_length=30, null=True, blank=True)
    RizikoAcikAdres = models.CharField(max_length=255, null=True, blank=True)
    Riziko_il_kod = models.CharField(max_length=10, null=True, blank=True)
    Riziko_ilce_kodu = models.CharField(max_length=10, null=True, blank=True)
    Riziko_Koy_kodu = models.CharField(max_length=10, null=True, blank=True)
    Riziko_mahalle_kodu = models.CharField(max_length=10, null=True, blank=True)
    Riziko_csbm_kodu = models.CharField(max_length=10, null=True, blank=True)
    Riziko_bina_kodu = models.CharField(max_length=20, null=True, blank=True)
    Riziko_bina_adi = models.CharField(max_length=50, null=True, blank=True)
    Riziko_daire_kodu = models.CharField(max_length=20, null=True, blank=True)
    Riziko_daire_no = models.CharField(max_length=10, null=True, blank=True)
    RizikoDaireYuzOlcumu = models.IntegerField(null=True, blank=True)
    RizikoDaskinsaYili = models.CharField(max_length=10, null=True, blank=True)
    RizikoDaskKullanimSekli = models.CharField(max_length=50, null=True, blank=True)
    RizikoDaskKatAraligi = models.CharField(max_length=20, null=True, blank=True)
    RizikoDaskYapiTarzi = models.CharField(max_length=50, null=True, blank=True)
    RizikoDaskHasarDurumu = models.CharField(max_length=50, null=True, blank=True)
    RizikoSigortaEttireninSifati = models.CharField(max_length=50, null=True, blank=True)
    RizikoKonum = models.CharField(max_length=50, null=True, blank=True)
    RizikoKonutTipi = models.CharField(max_length=50, null=True, blank=True)
    RizikoAda = models.CharField(max_length=20, null=True, blank=True)
    RizikoPafta = models.CharField(max_length=20, null=True, blank=True)
    RizikoParsel = models.CharField(max_length=20, null=True, blank=True)
    Riziko_il_ad = models.CharField(max_length=50, null=True, blank=True)
    Riziko_ilce_adi = models.CharField(max_length=50, null=True, blank=True)
    Riziko_koy_adi = models.CharField(max_length=50, null=True, blank=True)
    Riziko_mahalle_adi = models.CharField(max_length=50, null=True, blank=True)
    Riziko_sokak_adi = models.CharField(max_length=50, null=True, blank=True)
    RehinliAlacakliVar = models.CharField(max_length=10, null=True, blank=True)
    DainiMurtehinAdi = models.CharField(max_length=100, null=True, blank=True)
    DaskBitisTarihi = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False, help_text="Adres detayı doğrulandı mı?")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delete_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "asset_home"
        verbose_name = "Asset Home"
        verbose_name_plural = "Asset Homes"
        indexes = [
            models.Index(fields=['PoliceNoKombine', 'insured']),
        ]
        unique_together = ("insured", "RizikoUavtKod")

    def __str__(self):
        return f"{self.PoliceNoKombine} - {self.RizikoAcikAdres}"

class CompanyParameterMapping(models.Model):
    id = models.AutoField(primary_key=True)

    insurance_company = models.ForeignKey('InsuranceCompany', on_delete=models.CASCADE)
    product_code = models.CharField(max_length=50)

    key = models.ForeignKey('Key', on_delete=models.CASCADE)
    parameter = models.ForeignKey('Parameter', on_delete=models.CASCADE, null=True, blank=True)

    target_company_key = models.CharField(max_length=255, null=True, blank=True)       # 🔑 Servisin beklediği key
    company_parameter = models.CharField(max_length=255, null=True, blank=True)        # 🔢 Gönderilecek kod (örn: E, H)
    company_parameter_value = models.CharField(max_length=255, null=True, blank=True)  # 🏷️ Açıklama (örn: Evet, Hayır)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, auto_now=True)

    class Meta:
        db_table = 'company_parameter_mappings'
        unique_together = ('insurance_company', 'product_code', 'key', 'parameter')

    def __str__(self):
        return f"{self.insurance_company.name} | {self.product_code} | {self.target_company_key} = {self.company_parameter}"

class CompanyFieldMapping(models.Model):
    company = models.ForeignKey('InsuranceCompany', on_delete=models.CASCADE, related_name='field_mappings')
    service = models.ForeignKey('TransferServiceConfiguration', on_delete=models.CASCADE, null=True, blank=True,related_name='company_field_mappings')
    key = models.ForeignKey('Key', on_delete=models.SET_NULL, null=True, blank=True)
    parameter = models.ForeignKey('Parameter', on_delete=models.SET_NULL, null=True, blank=True)

    company_key = models.CharField(max_length=100, help_text="Şirketten gelen XML/JSON field/yolu")
    company_parameter = models.CharField(max_length=100, null=True, blank=True)
    company_parameter_value = models.CharField(max_length=100, null=True, blank=True)

    response_field = models.CharField(max_length=100, null=True, blank=True,help_text="XML/JSON path veya node (örn: Policeler.Police.PoliceNo, details.1.value)")
    parse_type = models.CharField(
        max_length=20,
        choices=[
            ('field', 'Field'),
            ('dict', 'DictField'),
            ('xpath', 'XPath'),
            ('jsonpath', 'JsonPath'),
        ],
        default='field',
        help_text="Parse metodu: Düz alan, nested dict, XPath, JsonPath"
    )
    expected_value = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Filtre veya eşleşme için beklenen değer (örn: 'K', 'Evet')"
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "company_field_mapping"
        unique_together = (
            'company', 'service', 'company_key', 'company_parameter', 'company_parameter_value', 'key', 'parameter'
        )

class CompanyServiceFieldMapping(models.Model):
    id = models.AutoField(primary_key=True)

    company = models.ForeignKey('InsuranceCompany', on_delete=models.CASCADE, related_name='verification_field_mappings')
    service = models.ForeignKey('ServiceConfiguration', on_delete=models.CASCADE, related_name='company_field_mappings')
    key = models.ForeignKey('Key', on_delete=models.SET_NULL, null=True, blank=True)
    parameter = models.ForeignKey('Parameter', on_delete=models.SET_NULL, null=True, blank=True)

    company_key = models.CharField(max_length=255, help_text="Şirketten gelen XML/JSON field/yolu")
    company_parameter = models.CharField(max_length=100, null=True, blank=True)
    company_parameter_value = models.CharField(max_length=100, null=True, blank=True)

    response_field = models.CharField(max_length=100, null=True, blank=True, help_text="XML/JSON path veya node")
    parse_type = models.CharField(
        max_length=20,
        choices=[
            ('field', 'Field'),
            ('dict', 'DictField'),
            ('xpath', 'XPath'),
            ('jsonpath', 'JsonPath'),
        ],
        default='field',
        help_text="Parse metodu"
    )
    expected_value = models.CharField(max_length=50, null=True, blank=True, help_text="Filtre veya eşleşme değeri")
    description = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "company_service_field_mapping"
        unique_together = (
            'company', 'service', 'company_key', 'company_parameter', 'company_parameter_value', 'key', 'parameter'
        )

# agency/models.py
class CookieLog(models.Model):
    agency = models.ForeignKey("agency.Agency", on_delete=models.CASCADE)
    company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)
    username = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=[("success", "Başarılı"), ("fail", "Hatalı")])
    message = models.TextField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=[("auto", "Zamanlı"), ("manual", "Elle")], default="auto")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cookie_log"
        verbose_name = "Cookie Log"
        verbose_name_plural = "Cookie Logları"
        ordering = ['-created_at']



