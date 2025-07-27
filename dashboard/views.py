import json
import calendar
from collections import defaultdict
from datetime import timedelta, date
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, Min, Max
from django.db.models.functions import TruncMonth, ExtractYear, ExtractMonth
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils.timezone import now
from django.shortcuts import render

from agency.models import AgencyCompany
from database.models import Collection, Products, Policy, InsuranceCompany, PolicyBranch
from datetime import timedelta
from datetime import datetime

@login_required
def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html')


def get_collection_totals(agency, *, start_date=None, end_date=None):
    queryset = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__isnull=False
    )
    if start_date and end_date:
        queryset = queryset.filter(policy__PoliceTanzimTarihi__range=(start_date, end_date))

    return queryset.aggregate(
        brut_total=Sum("BrutPrimTL"),
        net_total=Sum("NetPrimTL"),
        komisyon_total=Sum("KomisyonPrimTL")
    )


def get_branch_summary_by_period(agency, start_date=None, end_date=None):
    queryset = Collection.objects.filter(
        agency=agency,
        policy__PoliceAnaKey__isnull=False,
        policy__SirketUrunNo__isnull=False,
        policy__PoliceTanzimTarihi__isnull=False
    )

    if start_date and end_date:
        queryset = queryset.filter(policy__PoliceTanzimTarihi__range=(start_date, end_date))

    queryset = queryset.values(
        "policy__company_id",
        "policy__SirketUrunNo",
        "policy__PoliceAnaKey"
    ).annotate(
        brut=Sum("BrutPrimTL")
    )

    # Ürün → branş eşleşmesi
    product_map = {
        (p.company_id, p.code): p.branch.name if p.branch else "Bilinmeyen"
        for p in Products.objects.select_related("branch")
    }

    summary = defaultdict(lambda: {"brut": 0, "adet_set": set()})

    for row in queryset:
        branch_name = product_map.get((row["policy__company_id"], row["policy__SirketUrunNo"]), "Bilinmeyen")
        summary[branch_name]["brut"] += float(row["brut"] or 0)
        summary[branch_name]["adet_set"].add(row["policy__PoliceAnaKey"])

    return [
        {
            "branch": branch,
            "brut": round(data["brut"], 2),
            "adet": len(data["adet_set"])
        }
        for branch, data in summary.items()
    ]

def get_branch_month_comparison_extended(agency, year, month):
    today = date.today()
    start_of_this_month = date(year, month, 1)
    start_of_next_month = (start_of_this_month + timedelta(days=32)).replace(day=1)
    start_of_last_month = (start_of_this_month - timedelta(days=1)).replace(day=1)
    start_of_year = date(year, 1, 1)

    def get_data(start_date, end_date):
        queryset = Collection.objects.filter(
            agency=agency,
            policy__PoliceAnaKey__isnull=False,
            policy__SirketUrunNo__isnull=False,
            policy__PoliceTanzimTarihi__range=(start_date, end_date)
        ).values(
            "policy__company_id",
            "policy__SirketUrunNo",
            "policy__PoliceAnaKey"
        ).annotate(
            brut=Sum("BrutPrimTL")
        )

        product_map = {
            (p.company_id, p.code): p.branch.name if p.branch else "Bilinmeyen"
            for p in Products.objects.select_related("branch")
        }

        summary = defaultdict(lambda: {"brut": 0, "adet_set": set()})
        for row in queryset:
            branch_name = product_map.get(
                (row["policy__company_id"], row["policy__SirketUrunNo"]), "Bilinmeyen"
            )
            summary[branch_name]["brut"] += float(row["brut"] or 0)
            summary[branch_name]["adet_set"].add(row["policy__PoliceAnaKey"])

        return {
            branch: {
                "brut": round(data["brut"], 2),
                "adet": len(data["adet_set"])
            }
            for branch, data in summary.items()
        }

    # 🔸 Tüm ay verilerini al
    data_this_month = get_data(start_of_this_month, start_of_next_month)
    data_last_month = get_data(start_of_last_month, start_of_this_month)
    data_ytd = get_data(start_of_year, start_of_next_month)

    all_branches = (
        set(data_ytd.keys()) |
        set(data_this_month.keys()) |
        set(data_last_month.keys())
    )

    def calc_pct(new, old):
        if old == 0:
            return None
        return round(((new - old) / old) * 100, 1)

    return sorted([
        {
            "branch": branch,
            "ytd_adet": data_ytd.get(branch, {}).get("adet", 0),
            "ytd_brut": data_ytd.get(branch, {}).get("brut", 0),
            "this_month_adet": data_this_month.get(branch, {}).get("adet", 0),
            "this_month_brut": data_this_month.get(branch, {}).get("brut", 0),
            "prev_month_adet": data_last_month.get(branch, {}).get("adet", 0),
            "prev_month_brut": data_last_month.get(branch, {}).get("brut", 0),
            "adet_change_pct": calc_pct(
                data_this_month.get(branch, {}).get("adet", 0),
                data_last_month.get(branch, {}).get("adet", 0)
            ),
            "brut_change_pct": calc_pct(
                data_this_month.get(branch, {}).get("brut", 0),
                data_last_month.get(branch, {}).get("brut", 0)
            ),
        }
        for branch in all_branches
    ], key=lambda x: x["this_month_brut"], reverse=True)

def get_company_summary_by_period(agency, year, branch_code=None):
    product_map = {
        (p.company_id, p.code): p.branch.name if p.branch else None
        for p in Products.objects.select_related("branch")
    }

    if branch_code:
        target_products = {
            (cid, code)
            for (cid, code), name in product_map.items()
            if name == branch_code
        }

    queryset = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__year=year,
        policy__PoliceAnaKey__isnull=False,
        policy__company_id__isnull=False,
        policy__SirketUrunNo__isnull=False
    ).annotate(
        month=ExtractMonth("policy__PoliceTanzimTarihi")
    ).values(
        "policy__company_id", "policy__SirketUrunNo", "month"
    ).annotate(
        brut=Sum("BrutPrimTL"),
        adet=Count("policy__PoliceAnaKey", distinct=True)
    )

    # Şirket + ay bazlı veriyi tut
    result = defaultdict(lambda: [{"brut": 0, "adet": 0} for _ in range(12)])

    for row in queryset:
        key = (row["policy__company_id"], row["policy__SirketUrunNo"])
        if branch_code and key not in target_products:
            continue
        month_idx = row["month"] - 1
        cid = row["policy__company_id"]
        result[cid][month_idx]["brut"] += float(row["brut"] or 0)
        result[cid][month_idx]["adet"] += row["adet"]

    company_map = {
        c.id: c.name for c in InsuranceCompany.objects.filter(is_active=True)
    }

    table_data = []
    for cid, monthly in result.items():
        total_brut = sum(m["brut"] for m in monthly)
        total_adet = sum(m["adet"] for m in monthly)
        table_data.append({
            "company": company_map.get(cid, f"Şirket-{cid}"),
            "values": monthly,
            "total": {"brut": round(total_brut, 2), "adet": total_adet}
        })

    return sorted(table_data, key=lambda x: x["total"]["brut"], reverse=True)

def get_monthly_chart_data(agency, year=None, all_time=False):
    queryset = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__isnull=False
    )

    if not all_time and year:
        queryset = queryset.filter(policy__PoliceTanzimTarihi__year=year)

    queryset = queryset.annotate(
        month=TruncMonth("policy__PoliceTanzimTarihi")
    ).values("month").annotate(
        brut=Sum("BrutPrimTL"),
        komisyon=Sum("KomisyonPrimTL"),
        adet=Count("policy__PoliceAnaKey", distinct=True)
    )

    data_by_month = {
        row["month"].strftime("%Y-%m"): {
            "brut": float(row["brut"] or 0),
            "komisyon": float(row["komisyon"] or 0),
            "adet": row["adet"]
        }
        for row in queryset
    }

    if all_time:
        first_date = queryset.aggregate(m=Min("month"))["m"]
        last_date = queryset.aggregate(m=Max("month"))["m"]
    else:
        first_date = date(year, 1, 1)
        last_date = date(year, 12, 1)

    labels, brut_values, komisyon_values, adet_values = [], [], [], []
    d = first_date
    while d <= last_date:
        key = d.strftime("%Y-%m")
        labels.append(d.strftime("%b %Y"))
        brut_values.append(data_by_month.get(key, {}).get("brut", 0))
        komisyon_values.append(data_by_month.get(key, {}).get("komisyon", 0))
        adet_values.append(data_by_month.get(key, {}).get("adet", 0))
        d = (d + timedelta(days=32)).replace(day=1)

    return {
        "months": labels,
        "brut_values": brut_values,
        "komisyon_values": komisyon_values,
        "adet_values": adet_values
    }


@login_required
def dashboard_combined_data(request):
    agency = request.user.agency
    year = request.GET.get("year")
    all_time = year == "all"

    if not all_time:
        try:
            year = int(year)
        except ValueError:
            return JsonResponse({"error": "Geçersiz yıl"}, status=400)

    # 🔹 Grafik verileri
    chart = get_monthly_chart_data(agency, year=year, all_time=all_time)

    # 🔹 Özet kutular
    summary_qs = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__isnull=False
    )
    if not all_time:
        summary_qs = summary_qs.filter(policy__PoliceTanzimTarihi__year=year)

    summary = summary_qs.aggregate(
        brut_total=Sum("BrutPrimTL") or 0,
        net_total=Sum("NetPrimTL") or 0,
        komisyon_total=Sum("KomisyonPrimTL") or 0
    )
    summary["policy_count"] = summary_qs.values("policy__PoliceAnaKey").distinct().count()

    # 🔹 Pasta grafik
    pie_qs = summary_qs.filter(
        policy__PoliceAnaKey__isnull=False,
        policy__SirketUrunNo__isnull=False
    ).values("policy__company_id", "policy__SirketUrunNo") \
     .annotate(total=Sum("BrutPrimTL"))

    product_map = {
        (p.company_id, p.code): p.branch.name if p.branch else "Bilinmeyen"
        for p in Products.objects.select_related("branch")
    }

    branch_summary = defaultdict(float)
    for row in pie_qs:
        branch = product_map.get((row["policy__company_id"], row["policy__SirketUrunNo"]), "Bilinmeyen")
        branch_summary[branch] += float(row["total"] or 0)

    total = sum(branch_summary.values()) or 1
    labels = list(branch_summary.keys())
    values = [round(v, 2) for v in branch_summary.values()]
    percentages = [round((v / total) * 100) for v in branch_summary.values()]

    comparison_data = get_yearly_comparison_until_current_month(agency)

    return JsonResponse({
        "chart": chart,
        "summary": summary,
        "pie": {
            "labels": labels,
            "values": values,
            "percentages": percentages
        },
        "comparison": comparison_data
    })



@login_required
def branch_monthly_table_data(request):
    agency = request.user.agency
    year = request.GET.get("year", datetime.now().year)
    empty = request.GET.get("empty") == "1"

    queryset = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__year=year,
        policy__PoliceAnaKey__isnull=False,
        policy__SirketUrunNo__isnull=False
    )

    if not empty:
        queryset = queryset.values("policy__company_id", "policy__SirketUrunNo") \
            .annotate(
                month=ExtractMonth("policy__PoliceTanzimTarihi"),
                brut=Sum("BrutPrimTL"),
                adet=Count("policy__PoliceAnaKey", distinct=True)
            ) \
            .order_by("month")
    else:
        queryset = []

    # 🔹 Ürün-Branş eşleşmesi
    product_map = {
        (p.company_id, p.code): p.branch.name if p.branch else "Bilinmeyen"
        for p in Products.objects.select_related("branch")
    }

    result = defaultdict(lambda: defaultdict(lambda: {"brut": 0.0, "adet": 0}))

    if not empty:
        for row in queryset:
            branch = product_map.get((row["policy__company_id"], row["policy__SirketUrunNo"]), "Bilinmeyen")
            month = str(row["month"])
            result[branch][month]["brut"] += float(row["brut"] or 0)
            result[branch][month]["adet"] += row["adet"]
            result[branch]["total"]["brut"] += float(row["brut"] or 0)
            result[branch]["total"]["adet"] += row["adet"]

    # 🔹 Tüm branşlar tabloya eklensin
    all_branches = list(PolicyBranch.objects.values_list("name", flat=True))
    for branch in all_branches:
        if branch not in result:
            for m in range(1, 13):
                result[branch][str(m)] = {"brut": 0.0, "adet": 0}
            result[branch]["total"] = {"brut": 0.0, "adet": 0}

    data = []
    for branch, months_data in result.items():
        row = {
            "branch": branch,
            "values": [months_data[str(m)] for m in range(1, 13)],
            "total": months_data["total"]
        }
        data.append(row)

    return JsonResponse({"data": data})


@login_required
def company_monthly_table_data(request):
    agency = request.user.agency
    year = request.GET.get("year")
    branch_code = request.GET.get("branch")  # ⬅️ yeni parametre (opsiyonel)

    try:
        year = int(year)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Geçersiz yıl"}, status=400)

    # Ürün → Branş eşlemesi
    product_map = {
        (p.company_id, p.code): p.branch.name if p.branch else None
        for p in Products.objects.select_related("branch")
    }

    if branch_code:
        target_products = {
            (cid, code)
            for (cid, code), name in product_map.items()
            if name == branch_code
        }

    queryset = (
        Collection.objects
        .filter(
            agency=agency,
            policy__PoliceAnaKey__isnull=False,
            policy__company_id__isnull=False,
            policy__SirketUrunNo__isnull=False,
            policy__PoliceTanzimTarihi__year=year
        )
        .annotate(month=ExtractMonth("policy__PoliceTanzimTarihi"))
        .values("policy__company_id", "policy__SirketUrunNo", "month")
        .annotate(
            brut=Sum("BrutPrimTL"),
            adet=Count("policy__PoliceAnaKey", distinct=True)
        )
    )

    company_map = {
        c.id: {"name": c.name, "code": c.company_code}
        for c in InsuranceCompany.objects.filter(is_active=True)
    }

    result = defaultdict(lambda: [{"brut": 0.0, "adet": 0} for _ in range(12)])

    for row in queryset:
        key = (row["policy__company_id"], row["policy__SirketUrunNo"])
        if branch_code and key not in target_products:
            continue
        month_idx = row["month"] - 1
        cid = row["policy__company_id"]
        result[cid][month_idx]["brut"] += float(row["brut"] or 0)
        result[cid][month_idx]["adet"] += row["adet"]

    table_data = []
    for cid, monthly in result.items():
        company = company_map.get(cid)
        if not company:
            continue
        total_brut = sum(m["brut"] for m in monthly)
        total_adet = sum(m["adet"] for m in monthly)
        table_data.append({
            "company": company["name"],
            "code": company["code"],
            "values": monthly,
            "total": {
                "brut": round(total_brut, 2),
                "adet": total_adet
            }
        })

    return JsonResponse({
        "data": sorted(table_data, key=lambda x: x["total"]["brut"], reverse=True)
    })

def get_yearly_comparison_until_current_month(agency):
    today = date.today()
    current_year = today.year
    current_month = today.month

    # 🔹 Ocak – Bugüne kadar olan tarih aralıkları
    current_year_start = date(current_year, 1, 1)
    current_year_end = today

    prev_year_start = date(current_year - 1, 1, 1)
    prev_year_end = date(current_year - 1, today.month, today.day)

    # 🔹 Bu ayın başı ve bugüne kadar
    this_month_start = date(current_year, current_month, 1)
    this_month_end = today

    last_year_same_month_start = date(current_year - 1, current_month, 1)
    last_year_same_month_end = date(current_year - 1, current_month, today.day)

    # 🔸 Brüt Prim
    current_total = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(current_year_start, current_year_end)
    ).aggregate(total=Sum("BrutPrimTL"))["total"] or 0

    prev_total = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(prev_year_start, prev_year_end)
    ).aggregate(total=Sum("BrutPrimTL"))["total"] or 0

    # 🔸 Bu ay (Brüt)
    current_month_total = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(this_month_start, this_month_end)
    ).aggregate(total=Sum("BrutPrimTL"))["total"] or 0

    prev_month_total = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(last_year_same_month_start, last_year_same_month_end)
    ).aggregate(total=Sum("BrutPrimTL"))["total"] or 0

    # 🔸 Komisyon
    current_comm = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(current_year_start, current_year_end)
    ).aggregate(c=Sum("KomisyonPrimTL"))["c"] or 0

    prev_comm = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(prev_year_start, prev_year_end)
    ).aggregate(c=Sum("KomisyonPrimTL"))["c"] or 0

    # 🔸 Bu ay (Komisyon)
    current_month_comm = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(this_month_start, this_month_end)
    ).aggregate(c=Sum("KomisyonPrimTL"))["c"] or 0

    prev_month_comm = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(last_year_same_month_start, last_year_same_month_end)
    ).aggregate(c=Sum("KomisyonPrimTL"))["c"] or 0

    # 🔸 Poliçe adedi (toplam yıl)
    current_adet = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(current_year_start, current_year_end)
    ).values("policy__PoliceAnaKey").distinct().count()

    prev_adet = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(prev_year_start, prev_year_end)
    ).values("policy__PoliceAnaKey").distinct().count()

    # 🔸 Poliçe adedi (bu ay)
    current_month_adet = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(this_month_start, this_month_end)
    ).values("policy__PoliceAnaKey").distinct().count()

    prev_month_adet = Collection.objects.filter(
        agency=agency,
        policy__PoliceTanzimTarihi__range=(last_year_same_month_start, last_year_same_month_end)
    ).values("policy__PoliceAnaKey").distinct().count()

    # 🔹 Yüzdeler
    percent_change_year = ((current_total - prev_total) / prev_total * 100) if prev_total else (100 if current_total > 0 else 0)
    percent_change_month = ((current_month_total - prev_month_total) / prev_month_total * 100) if prev_month_total else (100 if current_month_total > 0 else 0)
    percent_change_comm = ((current_comm - prev_comm) / prev_comm * 100) if prev_comm else (100 if current_comm > 0 else 0)
    percent_change_comm_month = ((current_month_comm - prev_month_comm) / prev_month_comm * 100) if prev_month_comm else (100 if current_month_comm > 0 else 0)
    percent_change_adet = ((current_adet - prev_adet) / prev_adet * 100) if prev_adet else (100 if current_adet > 0 else 0)
    percent_change_adet_month = ((current_month_adet - prev_month_adet) / prev_month_adet * 100) if prev_month_adet else (100 if current_month_adet > 0 else 0)

    return {
        # 🔹 Brüt Prim
        "current": round(current_total, 2),
        "previous": round(prev_total, 2),
        "percent_change": round(percent_change_year, 2),
        "is_increase": percent_change_year >= 0,
        "difference": round(current_total - prev_total, 2),

        # 🔹 Aylık Brüt Prim
        "monthly_current": round(current_month_total, 2),
        "monthly_previous": round(prev_month_total, 2),
        "monthly_percent_change": round(percent_change_month, 2),
        "monthly_is_increase": percent_change_month >= 0,
        "monthly_difference": round(current_month_total - prev_month_total, 2),

        # 🔹 Komisyon
        "commission_current": round(current_comm, 2),
        "commission_previous": round(prev_comm, 2),
        "commission_percent_change": round(percent_change_comm, 2),
        "commission_difference": round(current_comm - prev_comm, 2),
        "commission_is_increase": percent_change_comm >= 0,

        # 🔹 Aylık Komisyon
        "commission_monthly_current": round(current_month_comm, 2),
        "commission_monthly_previous": round(prev_month_comm, 2),
        "commission_monthly_percent_change": round(percent_change_comm_month, 2),
        "commission_monthly_difference": round(current_month_comm - prev_month_comm, 2),
        "commission_monthly_is_increase": percent_change_comm_month >= 0,

        # 🔹 Poliçe adedi (toplam)
        "adet_current": current_adet,
        "adet_previous": prev_adet,
        "adet_percent_change": round(percent_change_adet, 2),
        "adet_difference": current_adet - prev_adet,
        "adet_is_increase": percent_change_adet >= 0,

        # 🔹 Poliçe adedi (bu ay)
        "adet_monthly_current": current_month_adet,
        "adet_monthly_previous": prev_month_adet,
        "adet_monthly_percent_change": round(percent_change_adet_month, 2),
        "adet_monthly_difference": current_month_adet - prev_month_adet,
        "adet_monthly_is_increase": percent_change_adet_month >= 0,
    }

@login_required
def get_company_branch_monthly_summary(request):
    agency = request.user.agency
    year = request.GET.get("year")
    branch = request.GET.get("branch")
    empty = request.GET.get("empty") == "1"

    if not year:
        return JsonResponse({"error": "Yıl gerekli"}, status=400)

    try:
        year = int(year)
    except ValueError:
        return JsonResponse({"error": "Yıl geçersiz"}, status=400)

    company_ids = AgencyCompany.objects.filter(agency=agency).values_list("company_id", flat=True)
    company_qs = InsuranceCompany.objects.filter(id__in=company_ids, is_active=True)

    company_map = {c.id: c.name for c in company_qs}
    code_map = {c.id: c.company_code for c in company_qs}
    result = defaultdict(lambda: [{"brut": 0, "adet": 0} for _ in range(12)])

    if not empty:
        queryset = Collection.objects.filter(
            agency=agency,
            policy__PoliceAnaKey__isnull=False,
            policy__company_id__isnull=False,
            policy__PoliceTanzimTarihi__year=year
        )

        if branch:
            queryset = queryset.filter(policy__SirketUrunNo__in=[
                p.code for p in Products.objects.filter(branch__name=branch)
            ])

        queryset = queryset.annotate(month=ExtractMonth("policy__PoliceTanzimTarihi")) \
            .values("policy__company_id", "month") \
            .annotate(
                brut=Sum("BrutPrimTL"),
                adet=Count("policy__PoliceAnaKey", distinct=True)
            )

        for row in queryset:
            company_id = row["policy__company_id"]
            month_idx = row["month"] - 1
            result[company_id][month_idx] = {
                "brut": round(float(row["brut"] or 0), 2),
                "adet": row["adet"]
            }

    data = []
    for company_id in company_map:
        monthly = result[company_id]
        total_brut = sum(m["brut"] for m in monthly)
        total_adet = sum(m["adet"] for m in monthly)
        data.append({
            "company": company_map[company_id],
            "code": code_map[company_id],
            "values": monthly,
            "total": {
                "brut": round(total_brut, 2),
                "adet": total_adet
            }
        })

    return JsonResponse({"data": sorted(data, key=lambda x: x["company"])})



@login_required
def dashboard_sales(request):
    agency = request.user.agency
    today = now().date()
    start_of_month = today.replace(day=1)
    last_7_days = today - timedelta(days=7)
    start_of_year = datetime(today.year, 1, 1).date()

    # 🔹 Ay isimleri
    turkish_months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    current_month_name = turkish_months[today.month - 1]
    prev_month_name = turkish_months[(today.replace(day=1) - timedelta(days=1)).month - 1]

    # 🔹 Yıl listesi
    first_year = (
        Collection.objects
        .filter(agency=agency)
        .aggregate(min_year=Min(ExtractYear("policy__PoliceTanzimTarihi")))["min_year"]
    ) or today.year
    year_range = list(range(today.year, first_year - 1, -1))

    # 🔹 Branş listesi
    all_branches = (
        Products.objects
        .select_related("branch")
        .filter(branch__isnull=False)
        .values_list("branch__name", flat=True)
        .distinct()
    )

    context = {
        "year_range": year_range,
        "current_year": today.year,
        "now": now(),
        "current_month_name": current_month_name,
        "prev_month_name": prev_month_name,
        "turkish_months_short": turkish_months,
        "all_branches": sorted(all_branches),
    }
    return render(request, "dashboard/sales/index.html", context)

