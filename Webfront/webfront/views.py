import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .services import airfoil_service

logger = logging.getLogger(__name__)


def index(request):
    stats = airfoil_service.get_statistics()
    recent_airfoils = airfoil_service.get_recent_airfoils()
    top_performers = airfoil_service.get_top_performers()
    anomaly_stats = airfoil_service.get_anomaly_stats()
    return render(request, 'webfront/index.html', {
        **stats,
        'recent_airfoils': recent_airfoils,
        'top_performers': top_performers,
        'anomaly_stats': anomaly_stats,
    })


def airfoil_list(request):
    airfoils = airfoil_service.get_all_airfoils()
    return render(request, 'webfront/airfoil_list.html', {'airfoils': airfoils})


def airfoil_detail(request, code):
    result = airfoil_service.get_airfoil_detail(code)
    if result[0] is None:
        return render(request, 'webfront/404.html', {'code': code}, status=404)
    airfoil, geometry, versions, performances = result
    return render(request, 'webfront/airfoil_detail.html', {
        'airfoil': airfoil,
        'geometry': geometry,
        'versions': versions,
        'performances': performances,
        'code': code,
    })


def search_airfoils(request):
    query = request.GET.get('q', '')
    alpha = request.GET.get('alpha', '')
    reynolds = request.GET.get('reynolds', '')
    results = []

    if query:
        results = airfoil_service.search_airfoils_by_name(query)
    elif alpha and reynolds:
        results = airfoil_service.search_airfoils_by_condition(alpha, reynolds)

    return render(request, 'webfront/search.html', {
        'query': query,
        'alpha': alpha,
        'reynolds': reynolds,
        'results': results,
    })


def compare_airfoils(request):
    codes_str = request.GET.get('codes', '')
    reynolds_str = request.GET.get('reynolds', '100000')
    result = []

    if codes_str:
        codes = [c.strip() for c in codes_str.split(',') if c.strip()]
        if codes and reynolds_str:
            result = airfoil_service.compare_airfoils(codes, reynolds_str)
    else:
        suggested = airfoil_service.get_suggested_airfoils()
        codes_str = ','.join(r['airfoil_code'] for r in suggested)

    return render(request, 'webfront/compare.html', {
        'codes_str': codes_str,
        'reynolds': reynolds_str,
        'result': result,
    })


def anomaly_list(request):
    anomalies = airfoil_service.get_anomalies()
    return render(request, 'webfront/anomaly_list.html', {'anomalies': anomalies})


def visualize(request):
    top_performers = airfoil_service.get_top_performers()
    anomaly_stats = airfoil_service.get_anomaly_stats()
    stats = airfoil_service.get_statistics()
    return render(request, 'webfront/visualize.html', {
        **stats,
        'top_performers': top_performers,
        'anomaly_stats': anomaly_stats,
    })


# ── NL2SQL 智能查询 ──────────────────────────────────────────────────

def nl2sql(request):
    """NL2SQL 主页面"""
    return render(request, 'webfront/nl2sql.html')


def nl2sql_api(request):
    """AJAX API：自然语言 → SQL → 执行 → 解释 → 返回 JSON"""
    question = request.GET.get('q', '').strip()
    schema_mode = request.GET.get('schema_mode', 'strong')
    if not question:
        return JsonResponse({'error': '请输入自然语言问题'}, status=400)

    try:
        from .services.collab_service import nl2sql_query
        result = nl2sql_query(question, schema_mode=schema_mode)
        return JsonResponse(result)
    except Exception as e:
        logger.exception('NL2SQL API 异常')
        return JsonResponse({'error': f'服务内部错误: {str(e)[:200]}'}, status=500)


def nl2sql_audit_list(request):
    from .models import NL2SQLAudit

    audits = NL2SQLAudit.objects.select_related("query").order_by("-created_at")[:200]
    return render(request, "webfront/nl2sql_audit_list.html", {"audits": audits})


@require_http_methods(["GET", "POST"])
def nl2sql_audit_detail(request, audit_id):
    from .models import NL2SQLAudit

    audit = get_object_or_404(NL2SQLAudit.objects.select_related("query"), audit_id=audit_id)

    if request.method == "POST":
        audit_status = (request.POST.get("audit_status") or "").strip()
        audited_sql = (request.POST.get("audited_sql") or "").strip()
        error_types_json = (request.POST.get("error_types_json") or "").strip()
        notes = (request.POST.get("notes") or "").strip()

        NL2SQLAudit.objects.filter(audit_id=audit.audit_id).update(
            audit_status=audit_status or audit.audit_status,
            audited_sql=audited_sql or None,
            error_types_json=error_types_json or None,
            notes=notes or None,
        )
        return redirect("webfront:nl2sql_audit_detail", audit_id=audit.audit_id)

    return render(request, "webfront/nl2sql_audit_detail.html", {"audit": audit})


def explain_audit_list(request):
    from .models import ResultExplainAudit

    audits = ResultExplainAudit.objects.select_related("query").order_by("-created_at")[:200]
    return render(request, "webfront/explain_audit_list.html", {"audits": audits})


@require_http_methods(["GET", "POST"])
def explain_audit_detail(request, explain_id):
    from .models import ResultExplainAudit

    audit = get_object_or_404(ResultExplainAudit.objects.select_related("query"), explain_id=explain_id)

    if request.method == "POST":
        judgement = (request.POST.get("judgement") or "").strip()
        issues_json = (request.POST.get("issues_json") or "").strip()

        ResultExplainAudit.objects.filter(explain_id=audit.explain_id).update(
            judgement=judgement or audit.judgement,
            issues_json=issues_json or None,
        )
        return redirect("webfront:explain_audit_detail", explain_id=audit.explain_id)

    return render(request, "webfront/explain_audit_detail.html", {"audit": audit})
