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