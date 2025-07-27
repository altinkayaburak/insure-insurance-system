from collections import defaultdict

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import calendar
from django.http import JsonResponse
from django.db.models import Count
from django.db.models.functions import TruncMonth, ExtractMonth, ExtractYear
from datetime import datetime
from database.models import Customer, Policy, City
from datetime import date

@login_required
def customer_dashboard_page(request):
    return render(request, "dashboard/customer/index.html")

@login_required
def get_customer_summary(request):
    agency_id = request.user.agency_id
    year = request.GET.get("year")

    customers = Customer.objects.filter(agency_id=agency_id)

    if year:
        try:
            year = int(year)
            customers = customers.filter(created_at__year=year)
        except ValueError:
            return JsonResponse({"error": "Geçersiz yıl"}, status=400)

    total_customers = customers.count()

    # Cinsiyet sayısı
    cinsiyet = customers.values("Cinsiyet").annotate(count=Count("id"))
    cinsiyet_dict = {"E": 0, "K": 0}
    for item in cinsiyet:
        if item["Cinsiyet"] in cinsiyet_dict:
            cinsiyet_dict[item["Cinsiyet"]] = item["count"]

    # Type istatistik
    type_stats = customers.values("type").annotate(count=Count("id"))
    type_dict = {"0": 0, "1": 0}
    for t in type_stats:
        type_key = str(t["type"])
        if type_key in type_dict:
            type_dict[type_key] = t["count"]

    # Gerçek ve potansiyel müşteri
    customer_ids_with_policy = Policy.objects.filter(
        agency_id=agency_id
    ).values_list("customer_id", flat=True).distinct()
    real_qs = customers.filter(id__in=customer_ids_with_policy)
    real_customers = real_qs.count()
    potential_customers = total_customers - real_customers

    # Medeni durum
    normalized_qs = customers.filter(type="1").exclude(MedeniDurum__isnull=True)
    married = normalized_qs.filter(MedeniDurum="EVLİ").count()
    single = normalized_qs.filter(MedeniDurum__in=["BEKÂR", "BOŞANMIŞ", "DUL"]).count()

    real_normalized_qs = real_qs.filter(type="1").exclude(MedeniDurum__isnull=True)
    real_married = real_normalized_qs.filter(MedeniDurum="EVLİ").count()
    real_single = real_normalized_qs.filter(MedeniDurum__in=["BEKÂR", "BOŞANMIŞ", "DUL"]).count()

    # 🔢 Tüm müşteriler için pasta grafik
    pie_labels = ["Kadın", "Erkek", "Tüzel"]
    pie_values = [
        cinsiyet_dict.get("K", 0),
        cinsiyet_dict.get("E", 0),
        type_dict.get("1", 0)
    ]
    pie_percentages = [
        round((v / total_customers) * 100, 1) if total_customers else 0
        for v in pie_values
    ]

    # 🔢 Poliçeli müşteriler için ikinci pasta grafik
    real_cinsiyet = real_qs.values("Cinsiyet").annotate(count=Count("id"))
    real_cinsiyet_dict = {"E": 0, "K": 0}
    for item in real_cinsiyet:
        if item["Cinsiyet"] in real_cinsiyet_dict:
            real_cinsiyet_dict[item["Cinsiyet"]] = item["count"]

    real_type_stats = real_qs.values("type").annotate(count=Count("id"))
    real_type_dict = {"0": 0, "1": 0}
    for t in real_type_stats:
        type_key = str(t["type"])
        if type_key in real_type_dict:
            real_type_dict[type_key] = t["count"]

    real_pie_values = [
        real_cinsiyet_dict.get("K", 0),
        real_cinsiyet_dict.get("E", 0),
        real_type_dict.get("1", 0)
    ]
    real_pie_percentages = [
        round((v / real_customers) * 100, 1) if real_customers else 0
        for v in real_pie_values
    ]

    return JsonResponse({
        "total_customers": total_customers,
        "cinsiyet": cinsiyet_dict,
        "type": type_dict,
        "real_customers": real_customers,
        "potential_customers": potential_customers,
        "pie": {
            "labels": pie_labels,
            "values": pie_values,
            "percentages": pie_percentages
        },
        "real_pie": {
            "labels": pie_labels,
            "values": real_pie_values,
            "percentages": real_pie_percentages
        },
        "married": married,
        "single": single,
        "real_married": real_married,
        "real_single": real_single,

    })


@login_required
def get_monthly_customer_policy_data(request):
    user = request.user
    year = request.GET.get("year")
    agency_id = user.agency_id

    try:
        year = int(year) if year else None
    except ValueError:
        return JsonResponse({"error": "Geçersiz yıl"}, status=400)

    customer_qs = Customer.objects.filter(agency_id=agency_id)
    if year:
        customer_qs = customer_qs.filter(created_at__year=year)

    customers = (
        customer_qs
        .annotate(month=ExtractMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    monthly_customer_ids = (
        customer_qs
        .annotate(month=ExtractMonth("created_at"))
        .values("month", "id")
    )

    month_customer_map = defaultdict(list)
    for item in monthly_customer_ids:
        month_customer_map[item["month"]].append(item["id"])

    policy_counts = {}
    for ay, customer_ids in month_customer_map.items():
        count = (
            Policy.objects.filter(
                agency_id=agency_id,
                customer_id__in=customer_ids,
                ZeyilNo="0"
            )
            .values("customer_id")
            .distinct()
            .count()
        )
        policy_counts[ay] = count

    # ✅ Türkçe aylar
    labels = [
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
    ]
    total_customers = [0] * 12
    with_policy = [0] * 12

    for c in customers:
        month_index = c["month"] - 1
        total_customers[month_index] = c["total"]

    for m in range(1, 13):
        with_policy[m - 1] = policy_counts.get(m, 0)

    # ✅ Dinamik yıl listesi
    years = Customer.objects.filter(agency_id=agency_id) \
        .annotate(y=ExtractYear("created_at")) \
        .values_list("y", flat=True).distinct().order_by("y")

    return JsonResponse({
        "labels": labels,
        "total_customers": total_customers,
        "with_policy": with_policy,
        "years": list(years)
    })


def get_customer_age_distribution(agency_id, with_policy=False):
    today = date.today()

    # 🔒 Sadece bireysel ve doğum tarihi olanlar
    base_qs = Customer.objects.filter(
        agency_id=agency_id,
        type="1",
        birth_date__isnull=False
    )

    if with_policy:
        customer_ids_with_policy = Policy.objects.filter(
            agency_id=agency_id
        ).values_list("customer_id", flat=True).distinct()
        base_qs = base_qs.filter(id__in=customer_ids_with_policy)

    age_group_counts = defaultdict(int)
    generation_counts = defaultdict(int)

    for customer in base_qs:
        birth_year = customer.birth_date.year
        age = today.year - birth_year

        # 🔢 Yaş grubu → 0–9, 10–19, ..., 90+
        group_start = (age // 10) * 10
        label = f"{group_start}-{group_start+9}" if group_start < 90 else "90+"
        age_group_counts[label] += 1

        # 🧬 Kuşak belirleme
        if 1946 <= birth_year <= 1964:
            generation = "Baby Boomer"
        elif 1965 <= birth_year <= 1980:
            generation = "X Kuşağı"
        elif 1981 <= birth_year <= 1996:
            generation = "Y Kuşağı"
        elif 1997 <= birth_year <= 2012:
            generation = "Z Kuşağı"
        elif birth_year >= 2013:
            generation = "Alpha Kuşağı"
        else:
            generation = "Bilinmeyen"

        generation_counts[generation] += 1

    # 🔁 Sıralı dönüş
    sorted_age_groups = dict(sorted(age_group_counts.items(), key=lambda x: int(x[0].split('-')[0].replace('+', ''))))
    sorted_generations = dict(sorted(generation_counts.items()))

    return {
        "age_groups": sorted_age_groups,
        "generations": sorted_generations
    }

@login_required
def get_customer_age_data(request):
    agency_id = request.user.agency_id

    all_data = get_customer_age_distribution(agency_id)
    real_data = get_customer_age_distribution(agency_id, with_policy=True)

    return JsonResponse({
        "age_groups": all_data["age_groups"],
        "generations": all_data["generations"],
        "real_age_groups": real_data["age_groups"],
        "real_generations": real_data["generations"]
    })

# 📊 Müşteri şehir dağılımı (harita + bar için)
def get_customer_city_distribution(agency_id):
    qs = Customer.objects.filter(
        agency_id=agency_id,
        Riziko_il_kod__isnull=False
    )

    city_counts = qs.values("Riziko_il_kod").annotate(count=Count("id")).order_by("-count")
    total = qs.count()

    # 🔄 CityCode ile MapCode eşlemesi yapılır
    city_map = {
        str(city.CityCode): {
            "name": city.CityName,
            "hc_key": city.MapCode.lower() if city.MapCode else None
        }
        for city in City.objects.filter(CityCode__in=[
            int(item["Riziko_il_kod"]) for item in city_counts if str(item["Riziko_il_kod"]).isdigit()
        ])
    }

    result = []
    for item in city_counts:
        code = str(item["Riziko_il_kod"])
        count = item["count"]

        city_info = city_map.get(code)
        if not city_info:
            continue  # 🚫 MapCode olmayan şehir atlanır

        result.append({
            "name": city_info["name"],
            "count": count,
            "percent": round((count / total) * 100, 1) if total else 0,
            "hc_key": city_info["hc_key"]
        })

    return result


# 🌍 Şehir verisini frontend'e JSON olarak döner
@login_required
def get_customer_city_data(request):
    agency_id = request.user.agency_id
    return JsonResponse({"cities": get_customer_city_distribution(agency_id)})
