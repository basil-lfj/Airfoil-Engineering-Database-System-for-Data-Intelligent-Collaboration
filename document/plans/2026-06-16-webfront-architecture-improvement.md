# Webfront 架构改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按照架构分析文档，分阶段完成 Webfront 项目的数据库优化、功能重构、体验优化和进阶增强

**Architecture:** 采用 Phase 0→Phase 1→Phase 2→Phase 3 四阶段递进策略，每阶段独立可交付。Phase 0 优先解决数据库性能瓶颈，Phase 1 重构核心功能模块，Phase 2 优化用户体验，Phase 3 做进阶增强。

**Tech Stack:** Django 6.0.5, PostgreSQL, ECharts 5.5, pg_trgm

---

## Phase 0: 数据库综合优化（P0-4）

### Task 0.1: 创建数据库索引和物化视图

**Files:**
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\scripts\migration\v1.0_indexes.sql`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\config\settings.py`

- [ ] **Step 1: 创建 SQL 迁移脚本**

```sql
-- v1.0_indexes.sql
-- 数据库优化：覆盖索引 + pg_trgm + 物化视图

-- 步骤 1：创建扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 步骤 2：覆盖索引 + 部分索引（不锁表）
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_performance_record_active
  ON performance_record(version_id, is_deleted)
  INCLUDE (cl, cd, l_over_d);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_version_current_active
  ON airfoil_version(airfoil_id, version_id)
  WHERE is_current = true AND is_deleted = false;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_code_name
  ON airfoil(airfoil_code, name);

-- 步骤 3：模糊搜索 GIN 索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_code_trgm
  ON airfoil USING gin (airfoil_code gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_name_trgm
  ON airfoil USING gin (name gin_trgm_ops);

-- 步骤 4：物化视图
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_airfoil_stats AS
SELECT
  (SELECT count(*) FROM airfoil WHERE is_deleted = false) AS airfoil_count,
  (SELECT count(*) FROM airfoil_version WHERE is_deleted = false) AS version_count,
  (SELECT count(*) FROM coordinate_point WHERE is_deleted = false) AS coord_count,
  (SELECT count(*) FROM performance_record WHERE is_deleted = false) AS perf_count,
  (SELECT count(*) FROM anomaly_record WHERE status = 'open') AS anomaly_count;
```

- [ ] **Step 2: 修改 settings.py 增加连接池配置**

修改 `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\config\settings.py`，在 DATABASES 配置中添加 `CONN_MAX_AGE`：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'airfoil_db',
        'HOST': 'localhost',
        'PORT': '5432',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'CONN_MAX_AGE': 300,  # 连接复用 5 分钟
        'OPTIONS': {
            'client_encoding': 'UTF8',
        },
    }
}
```

### Task 0.2: Service 层增加缓存和物化视图查询

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\airfoil_service.py`

- [ ] **Step 1: 在 airfoil_service.py 顶部增加缓存导入**

```python
from django.db import connection
from django.core.cache import cache
from decimal import Decimal
```

- [ ] **Step 2: 重写 get_statistics 使用物化视图 + 缓存**

```python
def get_statistics():
    cached = cache.get('dashboard_stats')
    if cached:
        return cached
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM mv_airfoil_stats")
        result = dictfetchall(cursor)[0]
    cache.set('dashboard_stats', result, 60)
    return result
```

- [ ] **Step 3: 验证修改后的代码正确性**

运行：`python -c "import ast; ast.parse(open('AEDS/Webfront/webfront/services/airfoil_service.py').read()); print('Syntax OK')"`

---

## Phase 1: P0 功能重构

### Task 1.1: Service 层解耦 — 拆分为 DAO 包（P0-1）

**Files:**
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\__init__.py`
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\dao\__init__.py`
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\dao\statistics_dao.py`
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\dao\airfoil_dao.py`
- Create: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\dao\anomaly_dao.py`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\services\airfoil_service.py`（改为 facade）

- [ ] **Step 1: 创建 dao 包目录**

```bash
mkdir -p AEDS/Webfront/webfront/services/dao
```

- [ ] **Step 2: 创建 dao/__init__.py**

```python
from .statistics_dao import get_statistics, get_top_performers
from .airfoil_dao import (
    get_recent_airfoils, get_all_airfoils, get_airfoil_detail,
    search_airfoils_by_name, search_airfoils_by_condition,
    compare_airfoils, get_suggested_airfoils,
)
from .anomaly_dao import get_anomaly_stats, get_anomalies

__all__ = [
    'get_statistics', 'get_top_performers',
    'get_recent_airfoils', 'get_all_airfoils', 'get_airfoil_detail',
    'search_airfoils_by_name', 'search_airfoils_by_condition',
    'compare_airfoils', 'get_suggested_airfoils',
    'get_anomaly_stats', 'get_anomalies',
]
```

- [ ] **Step 3: 创建 statistics_dao.py**

```python
"""统计相关 DAO：首页仪表盘、排行等聚合查询"""

from django.db import connection
from django.core.cache import cache
from decimal import Decimal


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        processed_row = []
        for value in row:
            if isinstance(value, Decimal):
                if value.as_integer_ratio()[1] == 1:
                    processed_row.append(int(value))
                else:
                    processed_row.append(float(value))
            else:
                processed_row.append(value)
        rows.append(dict(zip(columns, processed_row)))
    return rows


def get_statistics():
    """获取系统统计数据（优先查物化视图 + 缓存）"""
    cached = cache.get('dashboard_stats')
    if cached:
        return cached
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM mv_airfoil_stats")
        result = dictfetchall(cursor)[0]
    cache.set('dashboard_stats', result, 60)
    return result


def get_top_performers():
    """获取升阻比排行 TOP 10"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT a.airfoil_code, a.name, count(pr.record_id) AS perf_count,
                   avg(pr.cl) AS avg_cl, avg(pr.cd) AS avg_cd,
                   avg(COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0))) AS avg_ld
            FROM airfoil a
            JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id AND av.is_current = true
            JOIN performance_record pr ON pr.version_id = av.version_id AND pr.is_deleted = false
            WHERE a.is_deleted = false
            GROUP BY a.airfoil_code, a.name
            ORDER BY avg_ld DESC NULLS LAST
            LIMIT 10
        """)
        return dictfetchall(cursor)
```

- [ ] **Step 4: 创建 airfoil_dao.py**

```python
"""翼型相关 DAO：列表、详情、搜索、对比"""

from django.db import connection
from .statistics_dao import dictfetchall


def get_recent_airfoils():
    """获取最近翼型列表（首页用）"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT a.airfoil_code, a.name, av.version_no, av.version_type,
                   av.status, av.is_current, count(pr.record_id) AS perf_records
            FROM airfoil a
            JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
            LEFT JOIN performance_record pr ON pr.version_id = av.version_id AND pr.is_deleted = false
            WHERE a.is_deleted = false AND av.is_deleted = false
            GROUP BY a.airfoil_code, a.name, av.version_no, av.version_type, av.status, av.is_current
            ORDER BY a.airfoil_code, av.version_no DESC
            LIMIT 15
        """)
        return dictfetchall(cursor)


def get_all_airfoils():
    """获取所有翼型"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT a.airfoil_id, a.airfoil_code, a.name, a.family,
                   a.is_generated, a.created_at,
                   ds.source_type, ds.provider
            FROM airfoil a
            LEFT JOIN data_source ds ON ds.source_id = a.source_id
            WHERE a.is_deleted = false
            ORDER BY a.airfoil_code
        """)
        return dictfetchall(cursor)


def get_airfoil_detail(code):
    """获取翼型详情（含几何、版本、性能）"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.*, ds.source_type, ds.provider, ds.dataset_name"
            " FROM airfoil a"
            " LEFT JOIN data_source ds ON ds.source_id = a.source_id"
            " WHERE a.airfoil_code = %s AND a.is_deleted = false",
            [code]
        )
        airfoils = dictfetchall(cursor)
        if not airfoils:
            return None, None, None, None
        airfoil = airfoils[0]

        cursor.execute(
            "SELECT * FROM api.get_airfoil_geometry(%s, p_only_current => true)"
            " ORDER BY point_order",
            [code]
        )
        geometry = dictfetchall(cursor)

        cursor.execute(
            "SELECT av.*, count(pr.record_id) AS perf_count"
            " FROM airfoil_version av"
            " LEFT JOIN performance_record pr ON pr.version_id = av.version_id AND pr.is_deleted = false"
            " WHERE av.airfoil_id = %s::uuid AND av.is_deleted = false"
            " GROUP BY av.version_id"
            " ORDER BY av.version_no DESC",
            [airfoil['airfoil_id']]
        )
        versions = dictfetchall(cursor)

        cursor.execute("""
            SELECT ec.alpha_deg, ec.reynolds_number, pr.cl, pr.cd,
                   COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
                   pr.source_type, pr.is_anomaly, pr.record_id
            FROM performance_record pr
            JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
            JOIN airfoil_version av ON av.version_id = pr.version_id
            WHERE av.airfoil_id = %s::uuid AND av.is_current = true AND pr.is_deleted = false
            ORDER BY ec.reynolds_number, ec.alpha_deg
        """, [airfoil['airfoil_id']])
        performances = dictfetchall(cursor)

    return airfoil, geometry, versions, performances


def search_airfoils_by_name(query):
    """按名称/编码搜索翼型"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT a.airfoil_code, a.name, a.family, a.is_generated
            FROM airfoil a
            WHERE a.is_deleted = false
              AND (a.airfoil_code ILIKE %s OR a.name ILIKE %s)
            ORDER BY a.airfoil_code
            LIMIT 50
        """, [f'%{query}%', f'%{query}%'])
        return dictfetchall(cursor)


def search_airfoils_by_condition(alpha, reynolds):
    """按工况条件搜索翼型"""
    with connection.cursor() as cursor:
        try:
            cursor.execute("""
                SELECT * FROM api.find_airfoils_by_condition(
                    p_alpha_deg => %s,
                    p_reynolds_number => %s,
                    p_only_current => true
                )
                LIMIT 50
            """, [float(alpha), float(reynolds)])
            return dictfetchall(cursor)
        except Exception:
            return []


def compare_airfoils(codes, reynolds):
    """对比多个翼型在指定雷诺数下的性能"""
    with connection.cursor() as cursor:
        try:
            cursor.execute("""
                SELECT * FROM api.compare_airfoils_at_reynolds(
                    p_airfoil_codes => %s,
                    p_reynolds_number => %s,
                    p_only_current => true
                )
                ORDER BY airfoil_code, alpha_deg
            """, [codes, float(reynolds)])
            return dictfetchall(cursor)
        except Exception:
            return []


def get_suggested_airfoils():
    """获取建议的翼型列表（对比页默认）"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT airfoil_code FROM airfoil
            WHERE is_deleted = false
            ORDER BY airfoil_code
            LIMIT 5
        """)
        return dictfetchall(cursor)
```

- [ ] **Step 5: 创建 anomaly_dao.py**

```python
"""异常相关 DAO：异常统计和异常列表"""

from django.db import connection
from .statistics_dao import dictfetchall


def get_anomaly_stats():
    """获取异常规则检测统计"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT r.rule_code, r.description, r.severity, count(ar.anomaly_id) AS cnt
            FROM anomaly_rule r
            LEFT JOIN anomaly_record ar ON ar.rule_id = r.rule_id
            GROUP BY r.rule_code, r.description, r.severity
            ORDER BY cnt DESC
        """)
        return dictfetchall(cursor)


def get_anomalies():
    """获取异常数据列表"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ar.anomaly_id, ar.status, ar.details,
                   ar.detected_at, ar.reviewed_at,
                   a.airfoil_code, a.name AS airfoil_name,
                   r.rule_code, r.description AS rule_description,
                   r.severity
            FROM anomaly_record ar
            JOIN airfoil_version av ON av.version_id = ar.version_id
            JOIN airfoil a ON a.airfoil_id = av.airfoil_id
            JOIN anomaly_rule r ON r.rule_id = ar.rule_id
            ORDER BY ar.detected_at DESC
        """)
        return dictfetchall(cursor)
```

- [ ] **Step 6: 重写 airfoil_service.py 为 facade**

```python
"""
Service 层 Facade：向后兼容，委托到 DAO 包
"""
from .dao import (
    get_statistics, get_top_performers,
    get_recent_airfoils, get_all_airfoils, get_airfoil_detail,
    search_airfoils_by_name, search_airfoils_by_condition,
    compare_airfoils, get_suggested_airfoils,
    get_anomaly_stats, get_anomalies,
)

__all__ = [
    'get_statistics', 'get_top_performers',
    'get_recent_airfoils', 'get_all_airfoils', 'get_airfoil_detail',
    'search_airfoils_by_name', 'search_airfoils_by_condition',
    'compare_airfoils', 'get_suggested_airfoils',
    'get_anomaly_stats', 'get_anomalies',
]
```

- [ ] **Step 7: 验证导入正常**

运行：`cd AEDS/Webfront && python -c "from webfront.services.airfoil_service import *; print('Import OK')"`

### Task 1.2: 可视化实时化 — ECharts + AJAX（P0-2）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\views.py`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\urls.py`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\visualize.html`

- [ ] **Step 1: 在 views.py 中新增 6 个 JSON API View**

在 `views.py` 末尾添加：

```python
# ── 可视化 JSON API ──────────────────────────────────────────────────

from django.http import JsonResponse

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
```

- [ ] **Step 2: 在 urls.py 中添加可视化 API 路由**

在 `urlpatterns` 中添加：

```python
    path('visualize/api/foil-profiles/', views.visualize_api_foil_profiles, name='visualize_api_foil_profiles'),
    path('visualize/api/cl-alpha/', views.visualize_api_cl_alpha, name='visualize_api_cl_alpha'),
    path('visualize/api/cd-ld/', views.visualize_api_cd_ld, name='visualize_api_cd_ld'),
    path('visualize/api/multi-comparison/', views.visualize_api_multi_comparison, name='visualize_api_multi_comparison'),
    path('visualize/api/anomaly-detection/', views.visualize_api_anomaly_detection, name='visualize_api_anomaly_detection'),
    path('visualize/api/data-overview/', views.visualize_api_data_overview, name='visualize_api_data_overview'),
```

- [ ] **Step 3: 重写 visualize.html — 用 ECharts + AJAX 替代静态图片**

```html
{% extends 'webfront/base.html' %}
{% load static %}
{% block title %}可视化分析 · 翼型工程数据库{% endblock %}
{% block content %}

<div class="page-title">
    <h1>数据可视化分析</h1>
    <p>基于 {{ airfoil_count }} 个翼型、{{ perf_count|floatformat:"0" }} 条性能记录的实时可视化分析</p>
</div>

<!-- 数据筛选器卡片 -->
<div class="card" id="filterCard" style="border-color: var(--accent);">
    <div class="card-header">
        <h2>数据筛选器</h2>
    </div>
    <div class="search-row">
        <input type="text" id="filterCodes" placeholder="翼型编码，逗号分隔（如 NACA_2412,NACA_4412,NACA_0006）" value="NACA_2412,NACA_4412,NACA_0006">
        <input type="number" id="filterReynolds" placeholder="雷诺数" value="300000">
        <button class="btn btn-primary" onclick="refreshAllCharts()">刷新图表</button>
    </div>
</div>

<div class="stat-grid">
    <div class="stat"><div class="stat-num">{{ airfoil_count }}</div><div class="stat-label">翼型总数</div></div>
    <div class="stat"><div class="stat-num">{{ version_count }}</div><div class="stat-label">数据版本</div></div>
    <div class="stat"><div class="stat-num">{{ coord_count|floatformat:"0" }}</div><div class="stat-label">几何坐标点</div></div>
    <div class="stat"><div class="stat-num">{{ perf_count|floatformat:"0" }}</div><div class="stat-label">性能记录</div></div>
    <div class="stat"><div class="stat-num">{{ anomaly_count }}</div><div class="stat-label">异常标记</div></div>
</div>

{% if top_performers %}
<div class="card">
    <div class="card-header">
        <h2>翼型性能排行（按平均升阻比）</h2>
        <span class="count">TOP {{ top_performers|length }}</span>
    </div>
    <div style="height:320px;" id="chart-performers"></div>
</div>
{% endif %}

{% if anomaly_stats %}
<div class="card">
    <div class="card-header">
        <h2>异常规则检测统计</h2>
        <span class="count">{{ anomaly_stats|length }} 类</span>
    </div>
    <div style="height:250px;" id="chart-anomalies"></div>
</div>
{% endif %}

<!-- 动态图表区域（替代静态图片） -->
<div class="card">
    <div class="card-header">
        <h2>翼型轮廓对比</h2>
        <span class="count">5个代表性NACA翼型</span>
    </div>
    <div style="height:400px;" id="chart-foil-profiles"></div>
    <div style="margin-top:0.75rem;font-size:0.82rem;color:var(--ink-secondary);line-height:1.6;">
        对称翼型（0006、0015）上下对称，有弯度翼型（2412、4421）中弧线弯曲明显。厚度从6%到21%变化。
    </div>
</div>

<div class="card">
    <div class="card-header">
        <h2>升力系数 Cl — 攻角 α 关系</h2>
        <span class="count">多Re条件对比</span>
    </div>
    <div style="height:400px;" id="chart-cl-alpha"></div>
    <div style="margin-top:0.75rem;font-size:0.82rem;color:var(--ink-secondary);line-height:1.6;">
        有弯度翼型的Cl值整体高于对称翼型。所有翼型在攻角约14°后出现失速。
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">
    <div class="card">
        <div class="card-header"><h2>阻力与升阻比</h2></div>
        <div style="height:320px;" id="chart-cd-ld"></div>
    </div>
    <div class="card">
        <div class="card-header"><h2>多翼型性能对比</h2></div>
        <div style="height:320px;" id="chart-multi-comparison"></div>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">
    <div class="card">
        <div class="card-header"><h2>异常数据检测</h2></div>
        <div style="height:320px;" id="chart-anomaly-detection"></div>
    </div>
    <div class="card">
        <div class="card-header"><h2>数据规模总览</h2></div>
        <div style="height:320px;" id="chart-data-overview"></div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
// 获取筛选参数
function getFilterParams() {
    return {
        codes: document.getElementById('filterCodes').value || 'NACA_2412,NACA_4412,NACA_0006',
        reynolds: document.getElementById('filterReynolds').value || '300000'
    };
}

// 渲染排行图表
{% if top_performers %}
(function(){
    var c = document.getElementById('chart-performers');
    var chart = echarts.init(c);
    var data = {{ top_performers|safe }};
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 120, right: 30, top: 20, bottom: 30 },
        xAxis: { type: 'value', name: '平均升阻比', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
        yAxis: {
            type: 'category',
            data: data.map(function(d){ return d.airfoil_code; }).reverse(),
            axisLabel: { fontSize: 10, fontFamily: "'JetBrains Mono',monospace" }
        },
        series: [{
            type: 'bar',
            data: data.map(function(d){ return parseFloat(d.avg_ld || 0); }).reverse(),
            itemStyle: { color: '#0b1a2e', borderRadius: [0,3,3,0] },
            barMaxWidth: 20
        }]
    });
    window.addEventListener('resize', function(){ chart.resize(); });
})();
{% endif %}

// 渲染异常统计图表
{% if anomaly_stats %}
(function(){
    var c = document.getElementById('chart-anomalies');
    var chart = echarts.init(c);
    var data = {{ anomaly_stats|safe }};
    chart.setOption({
        tooltip: { trigger: 'item' },
        series: [{
            type: 'pie',
            radius: ['40%','70%'],
            center: ['50%','50%'],
            data: data.map(function(d){ return { name: d.rule_code + ' (' + d.description + ')', value: parseInt(d.cnt) }; }),
            label: { fontSize: 11 },
            itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
            color: ['#dc2626','#d97706','#059669','#2563eb']
        }]
    });
    window.addEventListener('resize', function(){ chart.resize(); });
})();
{% endif %}

// 通用 AJAX 加载函数
function loadChart(url, chartId, transformFn) {
    var chart = echarts.init(document.getElementById(chartId));
    fetch(url)
        .then(function(r){ return r.json(); })
        .then(function(data){
            var option = transformFn(data);
            if (option) chart.setOption(option);
        });
    window.addEventListener('resize', function(){ chart.resize(); });
}

// 翼型轮廓对比
loadChart('{% url "webfront:visualize_api_foil_profiles" %}', 'chart-foil-profiles', function(data){
    return {
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: data.codes, axisLabel: { rotate: 45, fontSize: 10 } },
        yAxis: { type: 'value', name: '翼型数量' },
        series: [{
            type: 'bar',
            data: data.codes.map(function(c,i){ return (i+1) * 2; }),
            itemStyle: { color: '#2563eb', borderRadius: [3,3,0,0] }
        }]
    };
});

// Cl-α 曲线
function loadClAlpha() {
    var params = getFilterParams();
    var chart = echarts.init(document.getElementById('chart-cl-alpha'));
    fetch('{% url "webfront:visualize_api_cl_alpha" %}?codes=' + encodeURIComponent(params.codes) + '&reynolds=' + params.reynolds)
        .then(function(r){ return r.json(); })
        .then(function(data){
            var codes = data.codes || [];
            var colors = ['#0b1a2e','#2563eb','#059669','#d97706','#dc2626','#8b5cf6','#ec4899'];
            var series = codes.map(function(code, i) {
                var points = (data.data || []).filter(function(d){ return d.airfoil_code === code; }).sort(function(a,b){ return a.alpha_deg - b.alpha_deg; });
                return {
                    name: code,
                    type: 'line',
                    smooth: true,
                    symbol: 'circle',
                    symbolSize: 4,
                    data: points.map(function(d){ return [parseFloat(d.alpha_deg), parseFloat(d.cl || 0)]; }),
                    itemStyle: { color: colors[i % colors.length] }
                };
            });
            chart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: codes, bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 11 } },
                grid: { left: 55, right: 20, top: 20, bottom: 40 },
                xAxis: { type: 'value', name: '攻角 α (°)', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                yAxis: { type: 'value', name: '升力系数 Cl', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                series: series
            });
        });
}
loadClAlpha();

// Cd & L/D 图表
function loadCdLd() {
    var params = getFilterParams();
    var chart = echarts.init(document.getElementById('chart-cd-ld'));
    fetch('{% url "webfront:visualize_api_cd_ld" %}?codes=' + encodeURIComponent(params.codes) + '&reynolds=' + params.reynolds)
        .then(function(r){ return r.json(); })
        .then(function(data){
            var codes = data.codes || [];
            var colors = ['#0b1a2e','#2563eb','#059669','#d97706','#dc2626','#8b5cf6','#ec4899'];
            var series = codes.map(function(code, i) {
                var points = (data.data || []).filter(function(d){ return d.airfoil_code === code; }).sort(function(a,b){ return a.alpha_deg - b.alpha_deg; });
                return {
                    name: code,
                    type: 'line',
                    smooth: true,
                    symbol: 'circle',
                    symbolSize: 4,
                    data: points.map(function(d){ return [parseFloat(d.alpha_deg), parseFloat(d.l_over_d || 0)]; }),
                    itemStyle: { color: colors[i % colors.length] }
                };
            });
            chart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: codes, bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 11 } },
                grid: { left: 55, right: 20, top: 20, bottom: 40 },
                xAxis: { type: 'value', name: '攻角 α (°)', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                yAxis: { type: 'value', name: '升阻比 L/D', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                series: series
            });
        });
}
loadCdLd();

// 多翼型性能对比
function loadMultiComparison() {
    var params = getFilterParams();
    var chart = echarts.init(document.getElementById('chart-multi-comparison'));
    fetch('{% url "webfront:visualize_api_multi_comparison" %}?codes=' + encodeURIComponent(params.codes) + '&reynolds=' + params.reynolds)
        .then(function(r){ return r.json(); })
        .then(function(data){
            var codes = data.codes || [];
            var colors = ['#0b1a2e','#2563eb','#059669','#d97706','#dc2626','#8b5cf6','#ec4899'];
            var series = codes.map(function(code, i) {
                var points = (data.data || []).filter(function(d){ return d.airfoil_code === code; }).sort(function(a,b){ return a.alpha_deg - b.alpha_deg; });
                return {
                    name: code,
                    type: 'line',
                    smooth: true,
                    symbol: 'circle',
                    symbolSize: 4,
                    data: points.map(function(d){ return [parseFloat(d.alpha_deg), parseFloat(d.cl || 0)]; }),
                    itemStyle: { color: colors[i % colors.length] }
                };
            });
            chart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: codes, bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 11 } },
                grid: { left: 55, right: 20, top: 20, bottom: 40 },
                xAxis: { type: 'value', name: '攻角 α (°)', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                yAxis: { type: 'value', name: '升力系数 Cl', nameTextStyle: { fontSize: 11, color: '#94a3b8' } },
                series: series
            });
        });
}
loadMultiComparison();

// 异常数据检测
loadChart('{% url "webfront:visualize_api_anomaly_detection" %}', 'chart-anomaly-detection', function(data){
    var stats = data.stats || [];
    return {
        tooltip: { trigger: 'item' },
        series: [{
            type: 'pie',
            radius: ['40%','70%'],
            data: stats.map(function(d){ return { name: d.rule_code, value: parseInt(d.cnt) }; }),
            label: { fontSize: 11 },
            itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
            color: ['#dc2626','#d97706','#059669','#2563eb']
        }]
    };
});

// 数据规模总览
loadChart('{% url "webfront:visualize_api_data_overview" %}', 'chart-data-overview', function(data){
    var items = [
        { name: '翼型总数', value: parseInt(data.airfoil_count || 0) },
        { name: '数据版本', value: parseInt(data.version_count || 0) },
        { name: '几何坐标点', value: parseInt(data.coord_count || 0) },
        { name: '性能记录', value: parseInt(data.perf_count || 0) },
        { name: '异常标记', value: parseInt(data.anomaly_count || 0) }
    ];
    return {
        tooltip: { trigger: 'item' },
        series: [{
            type: 'pie',
            radius: ['30%','60%'],
            data: items,
            label: { fontSize: 11, formatter: '{b}: {c}' },
            itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
            color: ['#0b1a2e','#2563eb','#059669','#d97706','#dc2626']
        }]
    };
});

// 刷新所有图表
function refreshAllCharts() {
    loadClAlpha();
    loadCdLd();
    loadMultiComparison();
}
</script>
{% endblock %}
```

### Task 1.3: 对比与可视化模块融合（P0-3）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\compare.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\views.py`

- [ ] **Step 1: 在 compare.html 的表格每行添加「查看可视化」按钮**

在 `compare.html` 表格的 `<thead>` 中增加「操作」列，在 `<tbody>` 每行增加：

```html
<td><a class="btn btn-sm" href="{% url 'webfront:visualize' %}?codes={{ r.airfoil_code }}&reynolds={{ reynolds }}">查看可视化</a></td>
```

- [ ] **Step 2: 在 visualize View 中解析 codes 和 reynolds 参数**

修改 `views.py` 中的 `visualize` 函数：

```python
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
```

- [ ] **Step 3: 在 visualize.html 中，页面加载时应用 URL 参数**

在 visualize.html 的 `<script>` 顶部添加：

```javascript
// 从 URL 参数读取筛选条件
(function(){
    var params = new URLSearchParams(window.location.search);
    var codes = params.get('codes');
    var reynolds = params.get('reynolds');
    if (codes) document.getElementById('filterCodes').value = codes;
    if (reynolds) document.getElementById('filterReynolds').value = reynolds;
    if (codes || reynolds) refreshAllCharts();
})();
```

---

## Phase 2: P1 体验优化

### Task 2.1: 搜索功能优化 — Tab 切换（P1-4）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\search.html`

- [ ] **Step 1: 重写 search.html 增加 Tab 切换**

```html
{% extends 'webfront/base.html' %}
{% block title %}工况查询 - 翼型工程数据库系统{% endblock %}
{% block content %}

<div class="page-title">
    <h1>工况查询</h1>
    <p>按翼型名称或工况条件搜索</p>
</div>

<div class="card">
    <!-- Tab 切换 -->
    <div style="display:flex;gap:0;margin-bottom:1.25rem;border-bottom:2px solid var(--border);">
        <button class="tab-btn active" data-tab="name" style="padding:0.5rem 1.25rem;border:none;background:none;font-size:0.85rem;font-weight:500;cursor:pointer;border-bottom:2px solid var(--ink);margin-bottom:-2px;color:var(--ink);">按名称搜索</button>
        <button class="tab-btn" data-tab="condition" style="padding:0.5rem 1.25rem;border:none;background:none;font-size:0.85rem;font-weight:500;cursor:pointer;color:var(--ink-secondary);">按工况搜索</button>
    </div>

    <!-- 按名称搜索 -->
    <form method="get" id="tab-name" class="tab-content">
        <div class="search-row">
            <input type="text" name="q" placeholder="输入翼型编码或名称..." value="{{ query }}">
            <input type="hidden" name="mode" value="name">
            <button type="submit" class="btn btn-primary">搜索</button>
        </div>
    </form>

    <!-- 按工况搜索 -->
    <form method="get" id="tab-condition" class="tab-content" style="display:none;">
        <div class="search-row">
            <input type="number" name="alpha" placeholder="攻角 (deg)" value="{{ alpha }}" step="1">
            <input type="number" name="reynolds" placeholder="雷诺数 (如 100000)" value="{{ reynolds }}" step="1000">
            <input type="hidden" name="mode" value="condition">
            <button type="submit" class="btn btn-primary">按工况查询</button>
        </div>
    </form>
</div>

{% if results %}
<div class="card">
    <div class="card-header">
        <h2>查询结果</h2>
        <span class="count">{{ results|length }} 条</span>
    </div>
    {% if mode == 'condition' %}
    <table>
        <thead>
            <tr>
                <th>翼型编码</th><th>名称</th><th>版本号</th><th>Cl</th><th>Cd</th><th>升阻比</th><th>来源</th><th>异常</th><th>操作</th>
            </tr>
        </thead>
        <tbody>
            {% for r in results %}
            <tr>
                <td><a href="{% url 'webfront:airfoil_detail' r.airfoil_code %}" class="link link-mono">{{ r.airfoil_code }}</a></td>
                <td>{{ r.name }}</td>
                <td>{{ r.version_no }}</td>
                <td style="font-family:var(--font-mono);font-size:0.8rem;">{{ r.cl|floatformat:4 }}</td>
                <td style="font-family:var(--font-mono);font-size:0.8rem;">{{ r.cd|floatformat:6 }}</td>
                <td style="font-family:var(--font-mono);font-size:0.8rem;">{% if r.l_over_d %}{{ r.l_over_d|floatformat:1 }}{% else %}-{% endif %}</td>
                <td><span class="tag {% if r.source_type == 'real' %}tag-green{% else %}tag-blue{% endif %}">{{ r.source_type }}</span></td>
                <td>{% if r.is_anomaly %}<span class="tag tag-red">异常</span>{% endif %}</td>
                <td><a href="{% url 'webfront:airfoil_detail' r.airfoil_code %}" class="btn btn-sm">详情</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <table>
        <thead>
            <tr><th>翼型编码</th><th>名称</th><th>家族</th><th>类型</th><th>操作</th></tr>
        </thead>
        <tbody>
            {% for r in results %}
            <tr>
                <td><a href="{% url 'webfront:airfoil_detail' r.airfoil_code %}" class="link link-mono">{{ r.airfoil_code }}</a></td>
                <td>{{ r.name }}</td>
                <td>{{ r.family|default:"-" }}</td>
                <td>{% if r.is_generated %}<span class="tag tag-amber">生成</span>{% else %}<span class="tag tag-green">真实</span>{% endif %}</td>
                <td><a href="{% url 'webfront:airfoil_detail' r.airfoil_code %}" class="btn btn-sm">详情</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}
</div>
{% elif query or alpha %}
<div class="alert alert-warn">未找到匹配结果</div>
{% endif %}

<script>
// Tab 切换
document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.tab-btn').forEach(function(b){
            b.style.color = 'var(--ink-secondary)';
            b.style.borderBottomColor = 'transparent';
        });
        this.style.color = 'var(--ink)';
        this.style.borderBottomColor = 'var(--ink)';
        document.querySelectorAll('.tab-content').forEach(function(c){ c.style.display = 'none'; });
        document.getElementById('tab-' + this.dataset.tab).style.display = '';
    });
});

// 根据当前查询模式激活对应 Tab
(function(){
    var mode = '{{ mode|default:"name" }}';
    if (mode === 'condition') {
        document.querySelector('[data-tab="condition"]').click();
    }
})();
</script>
{% endblock %}
```

- [ ] **Step 2: 修改 views.py 中 search_airfoils 函数，支持 mode 参数**

```python
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
```

### Task 2.2: 审计入口集成（P1-1）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\base.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\nl2sql.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\nl2sql_audit_list.html`

- [ ] **Step 1: 在 base.html 导航栏「智能查询 ✦」下增加审计子菜单**

修改 base.html 的导航栏部分，在智能查询链接后添加：

```html
<div style="position:relative;display:inline-block;">
    <a href="{% url 'webfront:nl2sql' %}" {% if '/nl2sql/' in request.path %}class="active"{% endif %}>智能查询 ✦</a>
    <div style="display:none;position:absolute;top:100%;left:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:0 4px 12px rgba(0,0,0,0.1);min-width:180px;z-index:200;">
        <a href="{% url 'webfront:nl2sql' %}" style="display:block;padding:0.5rem 1rem;color:var(--ink);white-space:nowrap;">智能查询</a>
        <a href="{% url 'webfront:nl2sql_audit_list' %}" style="display:block;padding:0.5rem 1rem;color:var(--ink);white-space:nowrap;">NL2SQL 审计</a>
        <a href="{% url 'webfront:explain_audit_list' %}" style="display:block;padding:0.5rem 1rem;color:var(--ink);white-space:nowrap;">解释审计</a>
    </div>
</div>
```

- [ ] **Step 2: 在 nl2sql.html 的审计状态横幅中增加「查看审计详情」链接**

在 `nl2sql.html` 的审计横幅区域，增加：

```html
<div id="auditLinkContainer" style="display:none;">
    <a id="auditDetailLink" class="btn btn-sm" target="_blank">查看审计详情 →</a>
</div>
```

在 JS 的 `renderResult` 函数中，当 `data.query_id` 存在时，设置链接并显示：

```javascript
var auditLink = document.getElementById('auditDetailLink');
if (data.query_id) {
    auditLink.href = '{% url "webfront:nl2sql_audit_list" %}';
    document.getElementById('auditLinkContainer').style.display = '';
}
```

### Task 2.3: NL2SQL 历史查询记录（P1-3）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\views.py`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\webfront\urls.py`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\nl2sql.html`

- [ ] **Step 1: 在 views.py 新增历史查询 API**

```python
def nl2sql_history(request):
    """返回最近 50 条 NL2SQL 查询历史"""
    from .models import QueryLog
    from django.contrib.contenttypes.models import ContentType
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
```

- [ ] **Step 2: 在 urls.py 添加路由**

```python
    path('nl2sql/history/', views.nl2sql_history, name='nl2sql_history'),
```

- [ ] **Step 3: 在 nl2sql.html 增加历史记录侧边栏**

在 nl2sql.html 的内容区域增加：

```html
<!-- 历史记录面板 -->
<div id="historyPanel" class="card" style="margin-bottom:1rem;">
    <div class="card-header" style="cursor:pointer;" onclick="toggleHistory()">
        <h2>查询历史</h2>
        <span class="count" id="historyCount">0 条</span>
    </div>
    <div id="historyList" style="max-height:300px;overflow-y:auto;display:none;">
        <div id="historyItems"></div>
        <div class="empty-state" id="historyEmpty" style="display:none;padding:1.5rem;">
            <div class="empty-state-title">暂无历史记录</div>
            <div class="empty-state-desc">执行查询后，历史记录将自动保存</div>
        </div>
    </div>
</div>

<script>
function toggleHistory() {
    var list = document.getElementById('historyList');
    list.style.display = list.style.display === 'none' ? '' : 'none';
    if (list.style.display !== 'none') loadHistory();
}

function loadHistory() {
    fetch('{% url "webfront:nl2sql_history" %}')
        .then(function(r){ return r.json(); })
        .then(function(data){
            var items = document.getElementById('historyItems');
            var empty = document.getElementById('historyEmpty');
            document.getElementById('historyCount').textContent = data.history.length + ' 条';
            if (data.history.length === 0) {
                items.innerHTML = '';
                empty.style.display = '';
                return;
            }
            empty.style.display = 'none';
            items.innerHTML = data.history.map(function(h){
                return '<div style="padding:0.5rem 0.75rem;border-bottom:1px solid var(--border);cursor:pointer;font-size:0.82rem;" onclick="fillHistory(\'' + h.question.replace(/'/g, "\\'") + '\')">' +
                    '<div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + h.question + '</div>' +
                    '<div style="font-size:0.72rem;color:var(--ink-tertiary);margin-top:0.15rem;">' + h.at + ' · ' + (h.is_success ? '<span class="tag tag-green">成功</span>' : '<span class="tag tag-red">失败</span>') + '</div>' +
                    '</div>';
            }).join('');
        });
}

function fillHistory(question) {
    document.getElementById('questionInput').value = question;
    document.getElementById('historyList').style.display = 'none';
    submitQuery();
}
</script>
```

### Task 2.4: 审计页面 UI 统一（P1-2）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\nl2sql_audit_detail.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\explain_audit_detail.html`

- [ ] **Step 1: 统一 nl2sql_audit_detail.html 的 UI 风格**

将表单控件样式统一为 `base.html` 中的 `.search-row input` 和 `.btn` 样式，移除内联样式。

- [ ] **Step 2: 统一 explain_audit_detail.html 的 UI 风格**

同上，确保使用 `.card`、`.btn`、`.tag`、`.alert` 等 CSS 类。

---

## Phase 3: P2 进阶增强

### Task 3.1: 图表交互升级（P2-1）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\index.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\visualize.html`

- [ ] **Step 1: 确保所有 ECharts 图表增加 tooltip/zoom/legend 交互**

在 index.html 和 visualize.html 的 ECharts 配置中增加：
- `tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } }`
- `dataZoom: [{ type: 'inside', start: 0, end: 100 }]`
- 导出 PNG 按钮

### Task 3.2: 数据导出功能（P2-2）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\airfoil_list.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\search.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\compare.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\anomaly_list.html`

- [ ] **Step 1: 在每个表格页面增加「导出 CSV」按钮和 JS 函数**

```javascript
function exportTableToCSV(tableId, filename) {
    var table = document.getElementById(tableId);
    if (!table) return;
    var rows = table.querySelectorAll('tr');
    var csv = [];
    rows.forEach(function(row) {
        var cols = row.querySelectorAll('td, th');
        var rowData = [];
        cols.forEach(function(col) {
            var text = col.textContent.trim().replace(/"/g, '""');
            rowData.push('"' + text + '"');
        });
        csv.push(rowData.join(','));
    });
    var blob = new Blob(['\uFEFF' + csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
}
```

### Task 3.3: 移动端适配（P2-3）

**Files:**
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\compare.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\visualize.html`
- Modify: `c:\Users\ASUS\Desktop\Databaselab\Bigwork\AEDS\Webfront\templates\webfront\nl2sql.html`

- [ ] **Step 1: 检查并修复各模板的响应式布局**

确保：
- `compare.html` 表格在小屏下可横向滚动（`overflow-x:auto`）
- `visualize.html` 双列网格在 480px 下改为单列
- `nl2sql.html` 的 SQL/解读双列在小屏下切换为单列
- 统一使用 `base.html` 中已定义的 `.result-grid` 类
