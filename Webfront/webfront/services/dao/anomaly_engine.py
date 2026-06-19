"""
异常检测引擎 — 多层规则检测 + 批量扫描 + 实时校验

检测规则体系：
  1. negative_cd       — 阻力系数 Cd < 0（物理不可实现）         → HIGH
  2. excessive_cl      — 升力系数 Cl > 3.0（典型翼型不可达）     → HIGH
  3. negative_ld       — 升阻比 L/D < 0（反常）                  → HIGH
  4. cd_spike_lowalpha — 小攻角下阻力系数偏高（Cd > 0.05 @ |α|<2）→ MEDIUM
  5. cl_jump           — 相邻攻角 Cl 跳变 > 0.5（测量异常）       → MEDIUM
  6. ld_deviation      — 升阻比偏离翼型族均值 ±3σ               → MEDIUM
  7. missing_alpha_seq — 攻角序列不连续（数据完整性）             → LOW
  8. duplicate_cond    — 同一版本+同工况重复记录                  → LOW
"""

import uuid
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from django.db import connection
from .statistics_dao import dictfetchall

# ── 规则定义 ──
RULES = [
    {
        'rule_code': 'negative_cd',
        'description': '阻力系数为负 (Cd < 0) — 物理不可实现',
        'severity': 'high',
    },
    {
        'rule_code': 'excessive_cl',
        'description': '升力系数异常偏高 (Cl > 3.0) — 超出典型翼型范围',
        'severity': 'high',
    },
    {
        'rule_code': 'negative_ld',
        'description': '升阻比为负 (L/D < 0) — 力系数方向异常',
        'severity': 'high',
    },
    {
        'rule_code': 'cd_spike_lowalpha',
        'description': '小攻角下阻力系数偏高 (Cd > 0.05 且 |α| < 2°) — 可能测量误差',
        'severity': 'medium',
    },
    {
        'rule_code': 'cl_jump',
        'description': '相邻攻角升力系数跳变过大 (ΔCl > 0.5) — 可能传感器异常',
        'severity': 'medium',
    },
    {
        'rule_code': 'ld_deviation',
        'description': '升阻比显著偏离同类翼型统计范围',
        'severity': 'medium',
    },
    {
        'rule_code': 'missing_alpha_seq',
        'description': '攻角序列存在明显缺口 — 数据不完整',
        'severity': 'low',
    },
    {
        'rule_code': 'duplicate_cond',
        'description': '同一版本相同工况存在多条记录 — 数据冗余',
        'severity': 'low',
    },
]


def ensure_rules_exist(cursor):
    """确保 anomaly_rule 表中存在所有规则定义"""
    for rule in RULES:
        cursor.execute(
            """INSERT INTO anomaly_rule (rule_id, rule_code, description, severity, is_enabled)
               SELECT %s, %s, %s, %s, true
               WHERE NOT EXISTS (SELECT 1 FROM anomaly_rule WHERE rule_code = %s)""",
            [str(uuid.uuid4()), rule['rule_code'], rule['description'],
             rule['severity'], rule['rule_code']]
        )


# ═══════════════════════════════════════════════
# 单条记录检测（新增性能数据时实时调用）
# ═══════════════════════════════════════════════

def check_single_record(alpha_deg, cl, cd, l_over_d=None):
    """
    对单条性能记录执行所有可单行检测的规则。
    返回 [{'rule_code': str, 'details': str}, ...]
    """
    results = []
    alpha = float(alpha_deg)
    cl_val = float(cl) if cl is not None else None
    cd_val = float(cd) if cd is not None else None
    ld_val = float(l_over_d) if l_over_d is not None else (cl_val / cd_val if cd_val and cd_val != 0 else None)

    # 规则 1: Cd < 0
    if cd_val is not None and cd_val < 0:
        results.append({
            'rule_code': 'negative_cd',
            'details': f'Cd = {cd_val:.6f} < 0，阻力系数不能为负',
        })

    # 规则 2: Cl > 3.0
    if cl_val is not None and cl_val > 3.0:
        results.append({
            'rule_code': 'excessive_cl',
            'details': f'Cl = {cl_val:.4f} > 3.0，超出典型翼型升力系数范围',
        })

    # 规则 3: L/D < 0
    if ld_val is not None and ld_val < 0:
        results.append({
            'rule_code': 'negative_ld',
            'details': f'L/D = {ld_val:.4f} < 0，升阻比异常',
        })

    # 规则 4: 小攻角 Cd 偏高
    if cd_val is not None and abs(alpha) < 2.0 and cd_val > 0.05:
        results.append({
            'rule_code': 'cd_spike_lowalpha',
            'details': f'α = {alpha}°，Cd = {cd_val:.6f} > 0.05，小攻角下阻力偏高',
        })

    return results


# ═══════════════════════════════════════════════
# 批量检测 — 扫描全库性能记录
# ═══════════════════════════════════════════════

def scan_all_performance():
    """
    扫描全部性能记录，运行所有检测规则。
    将检测结果写入 anomaly_record 表（去重写入，已存在的相同规则+相同记录不重复插入）。
    返回 {'scanned': int, 'new_anomalies': int, 'by_rule': dict}
    """
    from django.db import transaction

    with transaction.atomic():
        with connection.cursor() as cursor:
            # 确保规则存在
            ensure_rules_exist(cursor)

            # 读取所有非删除的性能记录（含实验条件）
            cursor.execute("""
                SELECT pr.record_id, pr.version_id, pr.cl, pr.cd,
                       COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
                       pr.is_anomaly, ec.alpha_deg, ec.reynolds_number
                FROM performance_record pr
                JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
                WHERE pr.is_deleted = false
                ORDER BY pr.version_id, ec.reynolds_number, ec.alpha_deg
            """)
            all_records = dictfetchall(cursor)

        # ── 第1轮: 单行规则检测 ──
        single_rule_results = []  # [(record_id, rule_code, details)]
        for rec in all_records:
            for result in check_single_record(
                rec['alpha_deg'], rec['cl'], rec['cd'], rec.get('l_over_d')
            ):
                single_rule_results.append((rec['record_id'], result['rule_code'], result['details']))

        # ── 第2轮: 跨行检测 ──
        # cl_jump
        cl_jump_results = _check_cl_jumps(all_records)
        # ld_deviation
        ld_dev_results = _check_ld_deviation(all_records)
        # missing_alpha_seq
        missing_seq_results = _check_missing_alpha_seq(all_records)

        cross_results = []
        for r in cl_jump_results:
            cross_results.append((r['record_id'], r['rule_code'], r['details']))
        for r in ld_dev_results:
            cross_results.append((r['record_id'], r['rule_code'], r['details']))
        for r in missing_seq_results:
            cross_results.append((r['record_id'], r['rule_code'], r['details']))

        # ── 第3轮: 数据库聚合检测 ──
        dup_results = _check_duplicate_conditions(all_records)

        all_hits = single_rule_results + cross_results + dup_results

        # ── 写入 anomaly_record（去重） ──
        new_count = 0
        by_rule = defaultdict(int)
        with connection.cursor() as cursor:
            # 获取规则 ID 映射
            cursor.execute("SELECT rule_id, rule_code FROM anomaly_rule WHERE is_enabled = true")
            rule_map = {r['rule_code']: r['rule_id'] for r in dictfetchall(cursor)}

            # 获取已存在的异常记录（避免重复插入）
            cursor.execute("""
                SELECT ar.record_id, ar2.rule_code
                FROM anomaly_record ar
                JOIN anomaly_rule ar2 ON ar2.rule_id = ar.rule_id
                WHERE ar.status = 'open'
            """)
            existing = set()
            for r in dictfetchall(cursor):
                existing.add((str(r['record_id']), r['rule_code']))

            for record_id, rule_code, details in all_hits:
                if (record_id, rule_code) in existing:
                    by_rule[rule_code] += 1
                    continue
                if rule_code not in rule_map:
                    continue

                cursor.execute(
                    """INSERT INTO anomaly_record
                       (anomaly_id, version_id, record_id, rule_id, status, details, detected_at)
                       SELECT %s, pr.version_id, pr.record_id, %s, 'open', %s, %s
                       FROM performance_record pr WHERE pr.record_id = %s""",
                    [str(uuid.uuid4()), rule_map[rule_code], details,
                     datetime.now(timezone.utc), record_id]
                )
                new_count += 1
                by_rule[rule_code] += 1

            # 更新 performance_record 的 is_anomaly 标记
            cursor.execute("""
                UPDATE performance_record pr
                SET is_anomaly = EXISTS (
                    SELECT 1 FROM anomaly_record ar
                    WHERE ar.record_id = pr.record_id AND ar.status IN ('open', 'confirmed')
                )
                WHERE pr.is_deleted = false
            """)

    return {
        'scanned': len(all_records),
        'new_anomalies': new_count,
        'by_rule': dict(by_rule),
    }


# ═══════════════════════════════════════════════
# 检测辅助函数
# ═══════════════════════════════════════════════

def _check_cl_jumps(records):
    """检测相邻攻角 Cl 跳变 > 0.5"""
    anomalies = []
    sorted_recs = sorted(records, key=lambda r: (
        str(r.get('version_id', '')),
        float(r.get('reynolds_number', 0) or 0),
        float(r['alpha_deg'])
    ))
    for i in range(1, len(sorted_recs)):
        prev, curr = sorted_recs[i - 1], sorted_recs[i]
        if (prev.get('version_id') == curr.get('version_id')
                and prev.get('reynolds_number') == curr.get('reynolds_number')
                and prev['cl'] is not None and curr['cl'] is not None):
            jump = abs(float(curr['cl']) - float(prev['cl']))
            if jump > 0.5:
                anomalies.append({
                    'record_id': curr['record_id'],
                    'rule_code': 'cl_jump',
                    'details': (
                        f"攻角 {prev['alpha_deg']}°(Cl={float(prev['cl']):.4f}) → "
                        f"{curr['alpha_deg']}°(Cl={float(curr['cl']):.4f})，"
                        f"跳变 ΔCl={jump:.4f} > 0.5"
                    ),
                })
    return anomalies


def _check_ld_deviation(records):
    """检测升阻比显著偏离同类数据统计范围（±3σ）"""
    anomalies = []
    ld_values = [float(r['l_over_d']) for r in records
                 if r.get('l_over_d') is not None and float(r['l_over_d']) != 0]
    if len(ld_values) < 5:
        return anomalies
    mean = statistics.mean(ld_values)
    stdev = statistics.stdev(ld_values) if len(ld_values) > 1 else 0
    threshold = 3 * stdev if stdev > 1 else 3.0
    for r in records:
        if r.get('l_over_d') is not None and float(r['l_over_d']) != 0:
            ld = float(r['l_over_d'])
            if abs(ld - mean) > threshold:
                anomalies.append({
                    'record_id': r['record_id'],
                    'rule_code': 'ld_deviation',
                    'details': (
                        f"L/D={ld:.2f}，全库均值={mean:.2f}，"
                        f"偏差={abs(ld - mean):.2f} > 阈值={threshold:.2f}"
                    ),
                })
    return anomalies


def _check_missing_alpha_seq(records):
    """检测攻角序列中是否存在明显缺口（间隔 > 5°）"""
    anomalies = []
    by_version_re = defaultdict(list)
    for r in records:
        key = (str(r.get('version_id', '')), float(r.get('reynolds_number', 0) or 0))
        by_version_re[key].append(r)

    for (ver_id, re), recs in by_version_re.items():
        alphas = sorted(set(float(r['alpha_deg']) for r in recs if r['alpha_deg'] is not None))
        if len(alphas) < 3:
            continue
        gaps = []
        for i in range(1, len(alphas)):
            gap = alphas[i] - alphas[i - 1]
            if gap > 5.0:
                gaps.append((alphas[i - 1], alphas[i], gap))
        if gaps:
            gap_desc = '；'.join(f"{g[0]}°~{g[1]}°(间隔{g[2]:.1f}°)" for g in gaps)
            anomalies.append({
                'record_id': recs[0]['record_id'],
                'rule_code': 'missing_alpha_seq',
                'details': f"Re={re:.0f} 攻角序列存在缺口: {gap_desc}",
            })
    return anomalies


def _check_duplicate_conditions(records):
    """检测同一版本下是否存在重复工况"""
    anomalies = []
    seen = defaultdict(list)
    for r in records:
        key = (str(r.get('version_id', '')), float(r['alpha_deg']), float(r.get('reynolds_number', 0) or 0))
        seen[key].append(r['record_id'])

    for (ver_id, alpha, re), rec_ids in seen.items():
        if len(rec_ids) > 1:
            anomalies.append((
                rec_ids[0],
                'duplicate_cond',
                f"同一版本 α={alpha}° Re={re:.0f} 存在 {len(rec_ids)} 条重复记录",
            ))
    return anomalies


# ═══════════════════════════════════════════════
# 异常统计（按翼型分组）
# ═══════════════════════════════════════════════

def get_anomaly_detail_stats():
    """
    获取更详细的异常统计：
    - 按翼型分组统计
    - 按规则分组统计
    - 按严重度分组统计
    - 按时间段统计
    """
    with connection.cursor() as cursor:
        # 按翼型
        cursor.execute("""
            SELECT a.airfoil_code, a.name, count(ar.anomaly_id) AS cnt,
                   count(*) FILTER (WHERE r.severity = 'high') AS high_cnt,
                   count(*) FILTER (WHERE r.severity = 'medium') AS medium_cnt,
                   count(*) FILTER (WHERE r.severity = 'low') AS low_cnt
            FROM anomaly_record ar
            JOIN anomaly_rule r ON r.rule_id = ar.rule_id
            JOIN airfoil_version av ON av.version_id = ar.version_id
            JOIN airfoil a ON a.airfoil_id = av.airfoil_id
            WHERE ar.status IN ('open', 'confirmed')
            GROUP BY a.airfoil_code, a.name
            ORDER BY cnt DESC
            LIMIT 20
        """)
        by_airfoil = dictfetchall(cursor)

        # 按规则
        cursor.execute("""
            SELECT r.rule_code, r.description, r.severity,
                   count(ar.anomaly_id) AS cnt,
                   count(*) FILTER (WHERE ar.status = 'open') AS open_cnt,
                   count(*) FILTER (WHERE ar.status = 'confirmed') AS confirmed_cnt,
                   count(*) FILTER (WHERE ar.status = 'ignored') AS ignored_cnt
            FROM anomaly_rule r
            LEFT JOIN anomaly_record ar ON ar.rule_id = r.rule_id
            GROUP BY r.rule_code, r.description, r.severity
            ORDER BY cnt DESC
        """)
        by_rule = dictfetchall(cursor)

        # 按月统计
        cursor.execute("""
            SELECT to_char(ar.detected_at, 'YYYY-MM') AS month,
                   count(*) AS cnt,
                   count(*) FILTER (WHERE r.severity = 'high') AS high_cnt
            FROM anomaly_record ar
            JOIN anomaly_rule r ON r.rule_id = ar.rule_id
            GROUP BY month
            ORDER BY month
        """)
        by_month = dictfetchall(cursor)

        # 按状态
        cursor.execute("""
            SELECT ar.status, count(*) AS cnt
            FROM anomaly_record ar
            GROUP BY ar.status
        """)
        by_status = dictfetchall(cursor)

        # 按严重度
        cursor.execute("""
            SELECT r.severity, count(*) AS cnt
            FROM anomaly_record ar
            JOIN anomaly_rule r ON r.rule_id = ar.rule_id
            WHERE ar.status IN ('open', 'confirmed')
            GROUP BY r.severity
        """)
        by_severity = dictfetchall(cursor)

    return {
        'by_airfoil': by_airfoil,
        'by_rule': by_rule,
        'by_month': by_month,
        'by_status': by_status,
        'by_severity': by_severity,
    }


def get_anomaly_annotations():
    """
    获取带异常标记的性能数据点（用于 Cl-α 图表标注）
    返回 [{airfoil_code, alpha_deg, reynolds_number, cl, cd, rule_code, severity}]
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT a.airfoil_code,
                   ec.alpha_deg, ec.reynolds_number,
                   pr.cl, pr.cd, r.rule_code, r.severity, ar.details
            FROM anomaly_record ar
            JOIN anomaly_rule r ON r.rule_id = ar.rule_id
            JOIN performance_record pr ON pr.record_id = ar.record_id
            JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
            JOIN airfoil_version av ON av.version_id = pr.version_id
            JOIN airfoil a ON a.airfoil_id = av.airfoil_id
            WHERE ar.status IN ('open', 'confirmed')
              AND pr.is_deleted = false
            ORDER BY a.airfoil_code, ec.alpha_deg
            LIMIT 200
        """)
        return dictfetchall(cursor)
