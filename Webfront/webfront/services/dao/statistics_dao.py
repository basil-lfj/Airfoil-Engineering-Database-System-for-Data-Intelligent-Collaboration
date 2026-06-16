"""统计相关 DAO：首页仪表盘、排行等聚合查询"""

from django.db import connection, ProgrammingError
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
    """获取系统统计数据（优先查物化视图 + 缓存，视图不存在则回退到原始查询）"""
    cached = cache.get('dashboard_stats')
    if cached:
        return cached
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM mv_airfoil_stats")
            result = dictfetchall(cursor)[0]
    except ProgrammingError:
        # 物化视图未创建（迁移脚本未执行），回退到原始 COUNT 查询
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM airfoil WHERE is_deleted = false")
            airfoil_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM airfoil_version WHERE is_deleted = false")
            version_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM coordinate_point WHERE is_deleted = false")
            coord_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM performance_record WHERE is_deleted = false")
            perf_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM anomaly_record WHERE status = 'open'")
            anomaly_count = cursor.fetchone()[0]
        result = {
            'airfoil_count': airfoil_count,
            'version_count': version_count,
            'coord_count': coord_count,
            'perf_count': perf_count,
            'anomaly_count': anomaly_count,
        }
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