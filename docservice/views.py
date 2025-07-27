import json
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from offer.utils import redis_client
from .tasks import fetch_pdf_from_service
from celery.result import AsyncResult

@require_POST
@login_required
def request_pdf(request):
    data = json.loads(request.body)
    service_id = data["service_id"]
    agency_id = request.user.agency_id
    params = data.get("params", {})

    print("GELEN PARAMS:", params)

    task = fetch_pdf_from_service.delay(service_id, agency_id, params)
    return JsonResponse({"success": True, "task_id": task.id})



@require_GET
@login_required
def poll_pdf_result(request):
    task_id = request.GET.get("task_id")
    if not task_id:
        return JsonResponse({"success": False, "error": "task_id zorunlu."})

    # Redis'ten task sonucunu al
    result_json = redis_client.get(task_id)
    if result_json:
        try:
            data = json.loads(result_json)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Geçersiz JSON sonucu."})

        if data.get("success") and (data.get("pdf_base64") or data.get("pdf_url")):
            return JsonResponse({"success": True, **{k: data[k] for k in ("pdf_base64", "pdf_url") if k in data}})
        elif data.get("error"):
            return JsonResponse({"success": False, "error": data["error"]})
        else:
            # PDF henüz hazır değil, ancak Redis'te sonuç var, beklemede demek
            return JsonResponse({"success": False, "pending": True})

    # Redis'te sonuç yoksa, task büyük ihtimalle henüz tamamlanmamış
    return JsonResponse({"success": False, "pending": True})

