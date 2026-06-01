from django.db import connection
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
    return {
        'airfoil_count': airfoil_count,
        'version_count': version_count,
        'coord_count': coord_count,
        'perf_count': perf_count,
        'anomaly_count': anomaly_count,
    }


def get_recent_airfoils():
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
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT airfoil_code FROM airfoil
            WHERE is_deleted = false
            ORDER BY airfoil_code
            LIMIT 5
        """)
        return dictfetchall(cursor)


def get_top_performers():
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


def get_anomaly_stats():
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