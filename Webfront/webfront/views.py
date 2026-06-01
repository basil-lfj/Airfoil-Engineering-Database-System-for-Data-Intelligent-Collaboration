from django.shortcuts import render
from .services import airfoil_service


def index(request):
    stats = airfoil_service.get_statistics()
    recent_airfoils = airfoil_service.get_recent_airfoils()
    return render(request, 'webfront/index.html', {
        **stats,
        'recent_airfoils': recent_airfoils,
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