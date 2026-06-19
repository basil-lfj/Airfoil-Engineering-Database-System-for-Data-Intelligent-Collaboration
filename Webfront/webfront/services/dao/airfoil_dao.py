"""翼型相关 DAO：列表、详情、搜索、对比、增删改"""

import uuid
from datetime import datetime, timezone

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


# ═══════════════════════════════════════════════
# CRUD 操作：创建、更新、软删除
# ═══════════════════════════════════════════════

def create_airfoil(code, name, family, category, source_type,
                   is_generated=False, remark='', provider='',
                   username='system'):
    """新增翼型 — 在 airfoil + data_source + airfoil_version 三表中写入"""
    airfoil_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    with connection.cursor() as cursor:
        # 校验编码唯一性
        cursor.execute(
            "SELECT count(*) FROM airfoil WHERE airfoil_code = %s AND is_deleted = false",
            [code]
        )
        if cursor.fetchone()[0] > 0:
            return {'success': False, 'error': f'翼型编码 "{code}" 已存在'}

        # 查找操作用户（默认 system）
        cursor.execute(
            "SELECT user_id FROM user_account WHERE username = %s LIMIT 1",
            [username]
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT user_id FROM user_account LIMIT 1")
            row = cursor.fetchone()
        created_by = row[0] if row else None

        # 创建数据来源
        cursor.execute(
            "INSERT INTO data_source (source_id, source_type, provider) VALUES (%s, %s, %s)",
            [source_id, source_type, provider or None]
        )

        # 创建翼型
        cursor.execute(
            """INSERT INTO airfoil
               (airfoil_id, airfoil_code, name, category, family,
                is_generated, generation_method, remark,
                source_id, is_deleted, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s)""",
            [airfoil_id, code, name, category or None, family or None,
             is_generated,
             'generated' if is_generated else None,
             remark or None, source_id, now]
        )

        # 创建初始版本
        cursor.execute(
            """INSERT INTO airfoil_version
               (version_id, airfoil_id, version_no, version_type, status,
                is_current, change_note, created_by, created_at, is_deleted)
               VALUES (%s, %s, 1, %s, 'valid', true, %s, %s, %s, false)""",
            [version_id, airfoil_id,
             'imported' if not is_generated else 'synthetic',
             '初始创建' if not remark else remark[:200],
             created_by, now]
        )

    return {'success': True, 'airfoil_id': airfoil_id, 'code': code}


def update_airfoil(code, name=None, family=None, category=None,
                   is_generated=None, remark=None, provider=None):
    """更新翼型基本信息（不更新编码，编码是业务标识）"""
    sets = []
    params = []
    if name is not None:
        sets.append("name = %s"); params.append(name)
    if family is not None:
        sets.append("family = %s"); params.append(family)
    if category is not None:
        sets.append("category = %s"); params.append(category)
    if is_generated is not None:
        sets.append("is_generated = %s"); params.append(is_generated)
    if remark is not None:
        sets.append("remark = %s"); params.append(remark)

    if not sets:
        return {'success': False, 'error': '没有需要更新的字段'}

    params.append(code)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE airfoil SET {', '.join(sets)} WHERE airfoil_code = %s AND is_deleted = false",
            params
        )
        if cursor.rowcount == 0:
            return {'success': False, 'error': f'翼型 "{code}" 不存在或已被删除'}

    return {'success': True, 'code': code}


def delete_airfoil(code):
    """软删除翼型 — 标记 is_deleted = true"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT airfoil_id FROM airfoil WHERE airfoil_code = %s AND is_deleted = false",
            [code]
        )
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'error': f'翼型 "{code}" 不存在或已被删除'}
        airfoil_id = row[0]

        # 软删除翼型
        cursor.execute(
            "UPDATE airfoil SET is_deleted = true WHERE airfoil_id = %s",
            [airfoil_id]
        )
        # 级联软删除版本
        cursor.execute(
            "UPDATE airfoil_version SET is_deleted = true WHERE airfoil_id = %s",
            [airfoil_id]
        )
        # 级联软删除坐标点
        cursor.execute(
            "UPDATE coordinate_point SET is_deleted = true WHERE version_id IN "
            "(SELECT version_id FROM airfoil_version WHERE airfoil_id = %s)",
            [airfoil_id]
        )
        # 级联软删除性能记录
        cursor.execute(
            "UPDATE performance_record SET is_deleted = true WHERE version_id IN "
            "(SELECT version_id FROM airfoil_version WHERE airfoil_id = %s)",
            [airfoil_id]
        )

    return {'success': True, 'code': code}


def get_all_data_sources():
    """获取所有数据来源（供前端下拉选择）"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_id, source_type, provider FROM data_source GROUP BY source_id, source_type, provider ORDER BY source_type"
        )
        return dictfetchall(cursor)


# ═══════════════════════════════════════════════
# 版本管理 CRUD
# ═══════════════════════════════════════════════

def create_version(airfoil_code, version_type, change_note='', username='system'):
    """为指定翼型新建版本"""
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT airfoil_id FROM airfoil WHERE airfoil_code = %s AND is_deleted = false",
            [airfoil_code]
        )
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'error': f'翼型 "{airfoil_code}" 不存在'}
        airfoil_id = row[0]

        cursor.execute(
            "SELECT user_id FROM user_account WHERE username = %s LIMIT 1",
            [username]
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT user_id FROM user_account LIMIT 1")
            row = cursor.fetchone()
        created_by = row[0] if row else None

        # 获取最大版本号
        cursor.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 FROM airfoil_version WHERE airfoil_id = %s AND is_deleted = false",
            [airfoil_id]
        )
        new_version_no = cursor.fetchone()[0]

        # 将旧版本的 is_current 置为 false
        cursor.execute(
            "UPDATE airfoil_version SET is_current = false WHERE airfoil_id = %s AND is_current = true",
            [airfoil_id]
        )

        cursor.execute(
            """INSERT INTO airfoil_version
               (version_id, airfoil_id, version_no, version_type, status,
                is_current, change_note, created_by, created_at, is_deleted)
               VALUES (%s, %s, %s, %s, 'valid', true, %s, %s, %s, false)""",
            [version_id, airfoil_id, new_version_no, version_type,
             change_note or '新建版本', created_by, now]
        )

    return {'success': True, 'version_id': version_id, 'version_no': new_version_no}


def update_version_status(version_id, status):
    """更新版本状态（valid / invalid / draft）"""
    from django.db import IntegrityError

    with connection.cursor() as cursor:
        try:
            cursor.execute(
                "UPDATE airfoil_version SET status = %s WHERE version_id = %s AND is_deleted = false",
                [status, version_id]
            )
            if cursor.rowcount == 0:
                return {'success': False, 'error': '版本不存在'}
        except IntegrityError as e:
            return {'success': False, 'error': f'状态值不合法: {str(e)[:100]}'}
    return {'success': True}


def delete_version(version_id):
    """软删除版本"""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE airfoil_version SET is_deleted = true WHERE version_id = %s",
            [version_id]
        )
        # 级联删除坐标点
        cursor.execute(
            "UPDATE coordinate_point SET is_deleted = true WHERE version_id = %s",
            [version_id]
        )
        # 级联删除性能记录
        cursor.execute(
            "UPDATE performance_record SET is_deleted = true WHERE version_id = %s",
            [version_id]
        )
        if cursor.rowcount == 0:
            return {'success': False, 'error': '版本不存在'}
    return {'success': True}


# ═══════════════════════════════════════════════
# 坐标点 CRUD
# ═══════════════════════════════════════════════

def get_version_id_by_code(airfoil_code):
    """获取翼型当前有效版本的 version_id"""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT av.version_id FROM airfoil a
               JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
               WHERE a.airfoil_code = %s AND a.is_deleted = false
                 AND av.is_current = true AND av.is_deleted = false
               LIMIT 1""",
            [airfoil_code]
        )
        row = cursor.fetchone()
        return row[0] if row else None


def create_coordinate_points(airfoil_code, points):
    """批量新增坐标点
    points: [{'surface': 'upper'/'lower', 'point_order': int, 'x': float, 'y': float}, ...]
    """
    version_id = get_version_id_by_code(airfoil_code)
    if not version_id:
        return {'success': False, 'error': f'翼型 "{airfoil_code}" 无有效版本'}

    point_ids = []
    now = datetime.now(timezone.utc)
    with connection.cursor() as cursor:
        for p in points:
            pid = str(uuid.uuid4())
            point_ids.append(pid)
            cursor.execute(
                """INSERT INTO coordinate_point
                   (point_id, version_id, surface, point_order, x, y, is_deleted)
                   VALUES (%s, %s, %s, %s, %s, %s, false)""",
                [pid, version_id, p['surface'], p['point_order'], p['x'], p['y']]
            )
    return {'success': True, 'point_ids': point_ids, 'count': len(points)}


def update_coordinate_point(point_id, x=None, y=None, surface=None, point_order=None):
    """更新单个坐标点"""
    sets = []
    params = []
    if x is not None:
        sets.append("x = %s"); params.append(x)
    if y is not None:
        sets.append("y = %s"); params.append(y)
    if surface is not None:
        sets.append("surface = %s"); params.append(surface)
    if point_order is not None:
        sets.append("point_order = %s"); params.append(point_order)
    if not sets:
        return {'success': False, 'error': '没有需要更新的字段'}

    params.append(point_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE coordinate_point SET {', '.join(sets)} WHERE point_id = %s AND is_deleted = false",
            params
        )
        if cursor.rowcount == 0:
            return {'success': False, 'error': '坐标点不存在'}
    return {'success': True}


def delete_coordinate_points(point_ids):
    """批量软删除坐标点"""
    if not point_ids:
        return {'success': False, 'error': '未指定坐标点'}
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE coordinate_point SET is_deleted = true WHERE point_id = ANY(%s)",
            [point_ids]
        )
    return {'success': True, 'deleted': cursor.rowcount}


# ═══════════════════════════════════════════════
# 性能数据 CRUD（含实验条件）
# ═══════════════════════════════════════════════

def create_performance_record(airfoil_code, alpha_deg, reynolds_number,
                               cl, cd, l_over_d=None, source_type='experimental'):
    """新增性能记录（自动关联实验条件，使用找或创建策略）

    数据安全校验：
    - Cd >= 0（阻力系数不能为负）
    - alpha 在合理范围 (-20° ~ 20°)
    - Re > 0
    """
    # ── 数据校验 ──
    errors = []
    if cd is not None and float(cd) < 0:
        errors.append('阻力系数 Cd 不能为负')
    if alpha_deg is not None and (float(alpha_deg) < -20 or float(alpha_deg) > 20):
        errors.append('攻角 α 超出合理范围 (-20° ~ +20°)')
    if reynolds_number is not None and float(reynolds_number) <= 0:
        errors.append('雷诺数 Re 必须大于 0')
    if errors:
        return {'success': False, 'error': '；'.join(errors)}

    record_id = str(uuid.uuid4())
    condition_id = str(uuid.uuid4())

    with connection.cursor() as cursor:
        version_id = get_version_id_by_code(airfoil_code)
        if not version_id:
            return {'success': False, 'error': f'翼型 "{airfoil_code}" 无有效版本'}

        # 查找或创建实验条件
        cursor.execute(
            "SELECT condition_id FROM experiment_condition WHERE alpha_deg = %s AND reynolds_number = %s LIMIT 1",
            [alpha_deg, reynolds_number]
        )
        row = cursor.fetchone()
        if row:
            condition_id = row[0]
        else:
            cursor.execute(
                """INSERT INTO experiment_condition (condition_id, alpha_deg, reynolds_number)
                   VALUES (%s, %s, %s)""",
                [condition_id, alpha_deg, reynolds_number]
            )

        # 计算升阻比（如果未提供）
        if l_over_d is None and cd != 0:
            l_over_d = round(cl / cd, 4)

        cursor.execute(
            """INSERT INTO performance_record
               (record_id, version_id, condition_id, cl, cd, l_over_d, source_type, is_anomaly, is_deleted)
               VALUES (%s, %s, %s, %s, %s, %s, %s, false, false)""",
            [record_id, version_id, condition_id, cl, cd, l_over_d, source_type]
        )

    return {'success': True, 'record_id': record_id}


def update_performance_record(record_id, cl=None, cd=None, l_over_d=None, source_type=None):
    """更新性能记录"""
    sets = []
    params = []
    if cl is not None:
        sets.append("cl = %s"); params.append(cl)
    if cd is not None:
        sets.append("cd = %s"); params.append(cd)
    if l_over_d is not None:
        sets.append("l_over_d = %s"); params.append(l_over_d)
    elif cl is not None and cd is not None and cd != 0:
        # 如果更新了 cl/cd 但没给 l_over_d，自动重算
        sets.append("l_over_d = %s"); params.append(round(cl / cd, 4))
    if source_type is not None:
        sets.append("source_type = %s"); params.append(source_type)
    if not sets:
        return {'success': False, 'error': '没有需要更新的字段'}

    params.append(record_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE performance_record SET {', '.join(sets)} WHERE record_id = %s AND is_deleted = false",
            params
        )
        if cursor.rowcount == 0:
            return {'success': False, 'error': '性能记录不存在'}
    return {'success': True}


def delete_performance_record(record_id):
    """软删除性能记录"""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE performance_record SET is_deleted = true WHERE record_id = %s",
            [record_id]
        )
        if cursor.rowcount == 0:
            return {'success': False, 'error': '性能记录不存在'}
    return {'success': True}


def get_performance_records(airfoil_code):
    """获取翼型的所有性能数据（带实验条件）"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pr.record_id, ec.alpha_deg, ec.reynolds_number,
                   pr.cl, pr.cd, COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
                   pr.source_type, pr.is_anomaly
            FROM performance_record pr
            JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
            JOIN airfoil_version av ON av.version_id = pr.version_id
            JOIN airfoil a ON a.airfoil_id = av.airfoil_id
            WHERE a.airfoil_code = %s AND a.is_deleted = false
              AND pr.is_deleted = false AND av.is_deleted = false
            ORDER BY ec.reynolds_number, ec.alpha_deg
        """, [airfoil_code])
        return dictfetchall(cursor)