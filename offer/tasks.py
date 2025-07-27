from celery import shared_task
from celery.exceptions import Retry
from offer.models import ProposalDetails
from offer.core import run_offer_service  # Eğer ayrı bir dosyadaysa

@shared_task(bind=True, max_retries=3, default_retry_delay=2)
def run_offer_service_async(self, detail_id, form_data):
    print(f"🌀 Celery görevi başladı: detail_id={detail_id}")

    try:
        detail = ProposalDetails.objects.get(id=detail_id)
        run_offer_service(detail, form_data)

    except ProposalDetails.DoesNotExist:
        print(f"⏳ ProposalDetails({detail_id}) DB'de henüz hazır değil, retry ediliyor...")
        raise self.retry(exc=Exception(f"ProposalDetail {detail_id} not ready"), countdown=2)

    except Exception as e:
        print(f"❌ Genel teklif hatası: {e}")
        raise e  # diğer hataları doğrudan yükselt
