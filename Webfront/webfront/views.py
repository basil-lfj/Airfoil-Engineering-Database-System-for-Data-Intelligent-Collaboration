import logging
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

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


@require_http_methods(["GET", "POST"])
def airfoil_list(request):
    """
    翼型全功能列表页面（GET：展示列表+表单；POST：新增/编辑/删除）
    """
    if request.method == "POST":
        action = request.POST.get('action', '')
        code = request.POST.get('code', '').strip()

        # ── 删除 ──
        if action == 'delete':
            result = airfoil_service.delete_airfoil(code)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse(result)
            return redirect(f'{request.path}?{"success=删除成功" if result["success"] else "error=" + result["error"]}')

        # ── 新增 ──
        if action == 'create':
            name = request.POST.get('name', '').strip()
            family = request.POST.get('family', '').strip()
            category = request.POST.get('category', '').strip()
            source_type = request.POST.get('source_type', '').strip() or 'imported'
            is_generated = request.POST.get('is_generated', 'false') == 'true'
            remark = request.POST.get('remark', '').strip()
            provider = request.POST.get('provider', '').strip()

            # 服务端校验
            errors = []
            if not code:
                errors.append('翼型编码不能为空')
            elif len(code) > 100:
                errors.append('翼型编码不能超过100个字符')
            if not name:
                errors.append('翼型名称不能为空')
            elif len(name) > 200:
                errors.append('翼型名称不能超过200个字符')

            if errors:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': '; '.join(errors)})
                return redirect(f'{request.path}?error={"".join(errors)}')

            result = airfoil_service.create_airfoil(
                code=code, name=name, family=family,
                category=category, source_type=source_type,
                is_generated=is_generated, remark=remark,
                provider=provider,
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse(result)
            return redirect(f'{request.path}?{"success=新增成功" if result["success"] else "error=" + result["error"]}')

        # ── 编辑 ──
        if action == 'update':
            name = request.POST.get('name', '').strip()
            family = request.POST.get('family', '').strip()
            category = request.POST.get('category', '').strip()
            is_generated_str = request.POST.get('is_generated', '')
            remark = request.POST.get('remark', '').strip()

            kw = {}
            if name:
                kw['name'] = name
            if family:
                kw['family'] = family
            if category:
                kw['category'] = category
            if is_generated_str:
                kw['is_generated'] = is_generated_str == 'true'
            if remark:
                kw['remark'] = remark

            result = airfoil_service.update_airfoil(code=code, **kw)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse(result)
            return redirect(f'{request.path}?{"success=更新成功" if result["success"] else "error=" + result["error"]}')

        return redirect(f'{request.path}?error=未知操作')

    # ── GET：展示列表页面 ──
    airfoils = airfoil_service.get_all_airfoils()
    sources = airfoil_service.get_all_data_sources()
    error = request.GET.get('error', '')
    success = request.GET.get('success', '')
    return render(request, 'webfront/airfoil_list.html', {
        'airfoils': airfoils,
        'sources': sources,
        'error': error,
        'success': success,
    })


@require_http_methods(["GET", "POST"])
def airfoil_detail(request, code):
    """翼型详情页 + 版本/坐标/性能数据管理 POST"""
    if request.method == "POST":
        action = request.POST.get('action', '')

        # ── 版本管理 ──
        if action == 'create_version':
            version_type = request.POST.get('version_type', '').strip()
            change_note = request.POST.get('change_note', '').strip()
            result = airfoil_service.create_version(code, version_type, change_note)
            return JsonResponse(result)

        if action == 'delete_version':
            version_id = request.POST.get('version_id', '').strip()
            result = airfoil_service.delete_version(version_id)
            return JsonResponse(result)

        # ── 坐标点管理 ──
        if action == 'create_coordinates':
            import json
            try:
                points_json = request.POST.get('points', '[]')
                points = json.loads(points_json)
            except (json.JSONDecodeError, TypeError):
                points = []
            if not points:
                return JsonResponse({'success': False, 'error': '坐标点数据格式错误'})
            result = airfoil_service.create_coordinate_points(code, points)
            return JsonResponse(result)

        if action == 'delete_coordinates':
            import json
            try:
                point_ids_json = request.POST.get('point_ids', '[]')
                point_ids = json.loads(point_ids_json)
            except (json.JSONDecodeError, TypeError):
                point_ids = []
            result = airfoil_service.delete_coordinate_points(point_ids)
            return JsonResponse(result)

        if action == 'update_coordinate':
            point_id = request.POST.get('point_id', '').strip()
            surface = request.POST.get('surface', '').strip()
            try:
                x = float(request.POST.get('x', 0))
                y = float(request.POST.get('y', 0))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': '坐标值格式错误'})
            result = airfoil_service.update_coordinate_point(
                point_id, x=x, y=y, surface=surface
            )
            return JsonResponse(result)

        # ── 性能数据管理 ──
        if action == 'create_performance':
            try:
                alpha_deg = float(request.POST.get('alpha_deg', 0))
                reynolds_number = float(request.POST.get('reynolds_number', 0))
                cl = float(request.POST.get('cl', 0))
                cd = float(request.POST.get('cd', 0))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': '数值格式错误'})
            source_type = request.POST.get('source_type', 'experimental').strip()
            result = airfoil_service.create_performance_record(
                code, alpha_deg, reynolds_number, cl, cd, source_type=source_type
            )
            return JsonResponse(result)

        if action == 'delete_performance':
            record_id = request.POST.get('record_id', '').strip()
            result = airfoil_service.delete_performance_record(record_id)
            return JsonResponse(result)

        if action == 'update_performance':
            record_id = request.POST.get('record_id', '').strip()
            try:
                cl = float(request.POST.get('cl', 0))
                cd = float(request.POST.get('cd', 0))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': '数值格式错误'})
            source_type = request.POST.get('source_type', '').strip()
            result = airfoil_service.update_performance_record(
                record_id, cl=cl, cd=cd, source_type=source_type
            )
            return JsonResponse(result)

        return JsonResponse({'success': False, 'error': '未知操作'})

    # ── GET：展示翼型详情 ──
    result = airfoil_service.get_airfoil_detail(code)
    if result[0] is None:
        return render(request, 'webfront/404.html', {'code': code}, status=404)
    airfoil, geometry, versions, performances = result

    # 获取单独的性能列表（供管理页面用）
    perf_list = airfoil_service.get_performance_records(code)

    return render(request, 'webfront/airfoil_detail.html', {
        'airfoil': airfoil,
        'geometry': geometry,
        'versions': versions,
        'performances': performances,
        'perf_list': perf_list,
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


import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def compare_airfoils(request):
    codes_str = request.GET.get('codes', '')
    reynolds_str = request.GET.get('reynolds', '100000')
    result = []
    summary = []

    if codes_str:
        codes = [c.strip() for c in codes_str.split(',') if c.strip()]
        if codes and reynolds_str:
            result = airfoil_service.compare_airfoils(codes, reynolds_str)
            
            # 计算摘要统计
            for code in codes:
                points = [p for p in result if p['airfoil_code'] == code]
                if not points: continue
                
                max_cl = max(p['cl'] for p in points)
                max_ld = max(p['l_over_d'] for p in points if p['l_over_d'] is not None)
                min_cd = min(p['cd'] for p in points)
                # 寻找最大升阻比对应的攻角
                opt_alpha = next(p['alpha_deg'] for p in points if p['l_over_d'] == max_ld)
                # 失速角（粗略估计：Cl 达到最大时的攻角）
                stall_alpha = next(p['alpha_deg'] for p in points if p['cl'] == max_cl)
                
                summary.append({
                    'code': code,
                    'max_cl': float(max_cl),
                    'max_ld': float(max_ld),
                    'min_cd': float(min_cd),
                    'opt_alpha': float(opt_alpha),
                    'stall_alpha': float(stall_alpha)
                })
    else:
        suggested = airfoil_service.get_suggested_airfoils()
        codes_str = ','.join(r['airfoil_code'] for r in suggested)

    # 转换 result 中的 Decimal，便于直接转 JSON
    safe_result = []
    for r in result:
        safe_r = {}
        for k, v in r.items():
            if isinstance(v, Decimal):
                safe_r[k] = float(v)
            else:
                safe_r[k] = v
        safe_result.append(safe_r)

    return render(request, 'webfront/compare.html', {
        'codes_str': codes_str,
        'reynolds': reynolds_str,
        'result': safe_result,
        'result_json': json.dumps(safe_result, cls=DecimalEncoder),
        'summary': summary,
        'summary_json': json.dumps(summary, cls=DecimalEncoder),
    })


def anomaly_list(request):
    """异常数据列表页（GET，支持分页）"""
    page = int(request.GET.get('page', 1))
    limit = 50
    offset = (page - 1) * limit
    
    anomalies = airfoil_service.get_anomalies(limit=limit, offset=offset)
    total_count = airfoil_service.get_anomaly_count()
    detail_stats = airfoil_service.get_anomaly_detail_stats()
    
    total_pages = (total_count + limit - 1) // limit
    
    return render(request, 'webfront/anomaly_list.html', {
        'anomalies': anomalies,
        'detail_stats': detail_stats,
        'page': page,
        'total_pages': total_pages,
        'total_count': total_count,
        'page_range': range(max(1, page - 2), min(total_pages, page + 2) + 1),
    })


@require_http_methods(["POST"])
def anomaly_scan_api(request):
    """
    POST /anomalies/scan/
    触发全库异常检测扫描
    """
    result = airfoil_service.scan_all_performance()
    return JsonResponse(result)


@require_http_methods(["GET"])
def anomaly_detail_api(request):
    """
    GET /anomalies/api/detail/
    返回异常统计详情（按翼型/按规则/按时间）
    """
    stats = airfoil_service.get_anomaly_detail_stats()
    annotations = airfoil_service.get_anomaly_annotations()
    return JsonResponse({'stats': stats, 'annotations': annotations})


# ── 翼型数据管理 CRUD ─────────────────────────────────────────────

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
