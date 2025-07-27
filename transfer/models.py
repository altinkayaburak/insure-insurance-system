from django.db import models
from django.db.models import JSONField





class PolicyTransferTemp(models.Model):
    PoliceNo = models.CharField(max_length=50, db_index=True)
    ZeyilNo = models.CharField(max_length=5, null=True, blank=True, db_index=True)
    YenilemeNo = models.CharField(max_length=5, null=True, blank=True, db_index=True)
    PoliceTanzimTarihi = models.DateField(null=True, blank=True)
    batch_id = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=20, default="pending")  # pending, failed, done
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    raw_data = models.JSONField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    agency_id = models.IntegerField(db_index=True)
    company_id = models.IntegerField(null=True, blank=True, db_index=True)  # ✅ eklendi
    service_id = models.IntegerField(null=True, blank=True, db_index=True)  # ✅ eklendi
    source = models.CharField(max_length=50, null=True, blank=True)         # ✅ eklendi

    TahsilatTahakkuk = models.CharField(max_length=4, null=True, blank=True)
    SirketUrunNo = models.CharField(max_length=100, null=True, blank=True)             # 41


    class Meta:
        db_table = "policy_transfer_temp"
        verbose_name = "Geçici Poliçe Transferi"
        verbose_name_plural = "Geçici Poliçe Transferleri"
        unique_together = ("PoliceNo", "ZeyilNo", "YenilemeNo", "batch_id", "agency_id")

    def __str__(self):
        return f"{self.PoliceNo}-{self.ZeyilNo or '0'}-{self.YenilemeNo or '0'} (batch: {self.batch_id})"


class TransferLog(models.Model):
    agency = models.ForeignKey("agency.Agency", on_delete=models.CASCADE)
    company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    block_start = models.DateField()
    block_end = models.DateField()

    total_count = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)

    customers_created = models.IntegerField(default=0)
    cars_created = models.IntegerField(default=0)
    homes_created = models.IntegerField(default=0)

    request_sent = models.BooleanField(default=False)
    response_received = models.BooleanField(default=False)
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    batch_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    retry_count = models.IntegerField(default=0)
    source = models.CharField(max_length=30, choices=[("manual", "Manuel"), ("auto", "Zamanlanmış"), ("api", "API")], default="manual")
    user = models.ForeignKey("agencyusers.Users", null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)


class TransferLogDetail(models.Model):
    log = models.ForeignKey("TransferLog", on_delete=models.CASCADE, related_name="details")
    police_no = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=[
            ("created", "Oluşturuldu"),
            ("updated", "Güncellendi"),
            ("skipped", "Atlandı"),
            ("failed", "Hatalı")
        ]
    )
    record_type = models.CharField(max_length=20, null=True, blank=True)
    customer_identity_number = models.CharField(max_length=11, null=True, blank=True)
    policy = models.ForeignKey("database.Policy", on_delete=models.SET_NULL, null=True, blank=True)  # ✅ düzeltildi
    data_source = models.CharField(max_length=30, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transfer_log_detail"
        verbose_name = "Transfer Poliçe Log Detayı"
        verbose_name_plural = "Transfer Poliçe Log Detayları"

class TransferPostProcessLog(models.Model):
    log = models.ForeignKey("TransferLog", on_delete=models.CASCADE, related_name="postprocess_logs")

    # ✅ Doğrulama sayıları
    customer_verified_count = models.IntegerField(default=0)
    cars_verified_count = models.IntegerField(default=0)
    homes_verified_count = models.IntegerField(default=0)

    # ✅ Potansiyel işler
    cars_traffic_potential = models.IntegerField(default=0)
    cars_kasko_potential = models.IntegerField(default=0)
    certificate_found_count = models.IntegerField(default=0)

    homes_dask_potential = models.IntegerField(default=0)
    homes_konut_potential = models.IntegerField(default=0)

    # ✅ Dijital müşteri
    digital_customer_count = models.IntegerField(default=0)

    # ✅ Ek bilgi
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transfer_postprocess_log"
        verbose_name = "Transfer Sonrası İşlem Logu"
        verbose_name_plural = "Transfer Sonrası İşlem Logları"



class CurrencyMapping(models.Model):
    id = models.AutoField(primary_key=True)

    company = models.ForeignKey("database.InsuranceCompany", on_delete=models.CASCADE)
    raw_value = models.CharField(max_length=20, db_index=True)  # Gelen değer (örn: "1", "USD", "TL")
    currency_code = models.CharField(max_length=10)  # Standart kod (örn: USD, EUR, TL)
    currency_name = models.CharField(max_length=100, null=True, blank=True)  # Açıklama (örn: ABD Doları)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "currency_mapping"
        unique_together = ("company", "raw_value")
        verbose_name = "Döviz Eşlemesi"
        verbose_name_plural = "Döviz Eşlemeleri"

    def __str__(self):
        return f"[{self.company.company_code}] {self.raw_value} → {self.currency_code}"
