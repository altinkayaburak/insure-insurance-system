from django.db import models

from agencyusers.models import Users
from database.models import ServiceConfiguration, OfferServiceConfiguration
from agency.models import Agency


class ProposalServiceLog(models.Model):
    proposal_id = models.PositiveIntegerField(null=True, blank=True)
    product_code = models.CharField(max_length=100, null=True, blank=True)
    sub_product_code = models.CharField(max_length=50, null=True, blank=True)  # ✅ Yeni alan eklendi

    agency = models.ForeignKey(Agency, on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(Users, on_delete=models.SET_NULL, null=True)

    offer_service = models.ForeignKey(OfferServiceConfiguration, null=True, blank=True, on_delete=models.SET_NULL)
    info_service = models.ForeignKey(ServiceConfiguration, null=True, blank=True, on_delete=models.SET_NULL)

    request_data = models.TextField()
    response_data = models.TextField()
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposalservicelog"



class UavtDetails(models.Model):
    proposal_id = models.IntegerField()
    product_code = models.CharField(max_length=50)
    service_id = models.IntegerField(null=True, blank=True)
    agency_id = models.IntegerField()
    user_id = models.IntegerField(null=True, blank=True)

    uavt_code = models.CharField(max_length=20, unique=True)

    il_kodu = models.CharField(max_length=10, null=True, blank=True)
    ilce_kodu = models.CharField(max_length=10, null=True, blank=True)
    koy_kodu = models.CharField(max_length=10, null=True, blank=True)
    mahalle_kodu = models.CharField(max_length=10, null=True, blank=True)
    csbm_kodu = models.CharField(max_length=10, null=True, blank=True)
    bina_kodu = models.CharField(max_length=20, null=True, blank=True)
    bina_adi = models.CharField(max_length=255, null=True, blank=True)
    daire_kodu = models.CharField(max_length=20, null=True, blank=True)
    daire_numarasi = models.CharField(max_length=20, null=True, blank=True)
    il_adi = models.CharField(max_length=20, null=True, blank=True)
    ilce_adi = models.CharField(max_length=20, null=True, blank=True)
    acik_adres = models.CharField(max_length=255, null=True, blank=True)

    daire_metrekare = models.CharField(max_length=10, null=True, blank=True, db_column="daire_metrekare")  # key_104
    dask_insa_yili = models.CharField(max_length=10, null=True, blank=True, db_column="dask_insa_yili")  # key_105
    dask_kullanim_sekli = models.CharField(max_length=100, null=True, blank=True,db_column="dask_kullanim_sekli")  # key_106
    dask_kat_araligi = models.CharField(max_length=100, null=True, blank=True, db_column="dask_kat_araligi")  # key_107
    dask_yapi_tarzi = models.CharField(max_length=100, null=True, blank=True, db_column="dask_yapi_tarzi")  # key_108
    dask_hasar_durumu = models.CharField(max_length=100, null=True, blank=True,db_column="dask_hasar_durumu")  # key_109
    sigorta_ettiren_sifati = models.CharField(max_length=100, null=True, blank=True,db_column="sigorta_ettiren_sifati")  # key_112

    # UavtDetails modeline eklenecek alanlar

    riziko_konum = models.CharField(max_length=255, null=True, blank=True, db_column="riziko_konum")  # key_118
    riziko_tipi = models.CharField(max_length=100, null=True, blank=True, db_column="riziko_tipi")  # key_164
    riziko_ada = models.CharField(max_length=50, null=True, blank=True, db_column="riziko_ada")  # key_115
    riziko_pafta = models.CharField(max_length=50, null=True, blank=True, db_column="riziko_pafta")  # key_114
    riziko_parsel = models.CharField(max_length=50, null=True, blank=True, db_column="riziko_parsel")  # key_116

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'uavtdetails'
        verbose_name = 'UAVT Detayı'
        verbose_name_plural = 'UAVT Detayları'

    def __str__(self):
        return f"{self.uavt_code}"
