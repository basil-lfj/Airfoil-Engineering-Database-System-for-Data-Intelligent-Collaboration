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
    mode = request.GET.get('mode', 'name')
    results = []

    if mode == 'condition' and alpha and reynolds:
        results = airfoil_service.search_airfoils_by_condition(alpha, reynolds)
    elif query:
        results = airfoil_service.search_airfoils_by_name(query)

    return render(request, 'webfront/search.html', {
        'query': query,
        'alpha': alpha,
        'reynolds': reynolds,
        'results': results,
        'mode': mode,
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

    # 解析筛选参数（从对比页面跳转携带）
    filter_codes = request.GET.get('codes', '')
    filter_reynolds = request.GET.get('reynolds', '')

    return render(request, 'webfront/visualize.html', {
        **stats,
        'top_performers': top_performers,
        'anomaly_stats': anomaly_stats,
        'filter_codes': filter_codes,
        'filter_reynolds': filter_reynolds,
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


# ── 可视化 JSON API ──────────────────────────────────────────────────


def visualize_api_foil_profiles(request):
    """API: 翼型轮廓数据"""
    from .services.dao.airfoil_dao import get_all_airfoils
    airfoils = get_all_airfoils()
    codes = [a['airfoil_code'] for a in airfoils[:10]]
    return JsonResponse({'codes': codes})


def visualize_api_cl_alpha(request):
    """API: 升力系数 Cl — 攻角 α 关系"""
    from .services.dao.airfoil_dao import compare_airfoils
    codes_str = request.GET.get('codes', 'NACA_2412,NACA_4412,NACA_0006')
    reynolds = request.GET.get('reynolds', '300000')
    codes = [c.strip() for c in codes_str.split(',') if c.strip()]
    data = compare_airfoils(codes, reynolds) if codes else []
    return JsonResponse({'data': data, 'codes': codes, 'reynolds': reynolds})


def visualize_api_cd_ld(request):
    """API: 阻力与升阻比数据"""
    from .services.dao.airfoil_dao import compare_airfoils
    codes_str = request.GET.get('codes', 'NACA_2412,NACA_4412,NACA_0006')
    reynolds = request.GET.get('reynolds', '300000')
    codes = [c.strip() for c in codes_str.split(',') if c.strip()]
    data = compare_airfoils(codes, reynolds) if codes else []
    return JsonResponse({'data': data, 'codes': codes, 'reynolds': reynolds})


def visualize_api_multi_comparison(request):
    """API: 多翼型性能对比"""
    from .services.dao.airfoil_dao import compare_airfoils
    codes_str = request.GET.get('codes', 'NACA_2412,NACA_4412,NACA_0006,NACA_0012,NACA_4421')
    reynolds = request.GET.get('reynolds', '300000')
    codes = [c.strip() for c in codes_str.split(',') if c.strip()]
    data = compare_airfoils(codes, reynolds) if codes else []
    return JsonResponse({'data': data, 'codes': codes, 'reynolds': reynolds})


def visualize_api_anomaly_detection(request):
    """API: 异常数据检测"""
    from .services.dao.anomaly_dao import get_anomaly_stats
    stats = get_anomaly_stats()
    return JsonResponse({'stats': stats})


def visualize_api_data_overview(request):
    """API: 数据规模总览"""
    from .services.dao.statistics_dao import get_statistics
    stats = get_statistics()
    return JsonResponse(stats)


# ── NL2SQL 历史查询 API ─────────────────────────────────────────────


def nl2sql_history(request):
    """返回最近 50 条 NL2SQL 查询历史"""
    from .models import QueryLog
    logs = QueryLog.objects.filter(query_type='nl2sql').order_by('-at')[:50]
    history = []
    for log in logs:
        history.append({
            'query_id': str(log.query_id),
            'question': log.parameters_json[:100] if log.parameters_json else '',
            'is_success': log.is_success,
            'at': log.at.strftime('%Y-%m-%d %H:%M:%S') if log.at else '',
        })
    return JsonResponse({'history': history})
