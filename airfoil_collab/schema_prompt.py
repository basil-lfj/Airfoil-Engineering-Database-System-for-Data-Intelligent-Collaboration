from __future__ import annotations

import json
from dataclasses import dataclass

from .config import PostgresConfig
from .psql import run_psql


@dataclass(frozen=True)
class SchemaSnapshot:
    mode: str
    text: str
    meta_json: str


def build_schema_prompt(pg: PostgresConfig, *, mode: str) -> SchemaSnapshot:
    mode_norm = (mode or "weak").strip().lower()
    if mode_norm not in {"weak", "strong"}:
        mode_norm = "weak"

    if mode_norm == "weak":
        text = "\n".join(
            [
                "数据库对象（弱提示，仅列出允许使用的对象名称）：",
                "- api.v_current_airfoil_version",
                "- api.get_airfoil_geometry(p_airfoil_code, p_only_current, p_version_no)",
                "- api.find_airfoils_by_condition(p_alpha_deg, p_reynolds_number, p_min_cl, p_max_cd, p_min_l_over_d, p_only_current)",
                "- api.compare_airfoils_at_reynolds(p_airfoil_codes[], p_reynolds_number, p_only_current)",
                "- api.get_airfoil_performance_across_versions(p_airfoil_code, p_alpha_deg, p_reynolds_number)",
                "- api.compare_airfoil_versions(p_airfoil_code, p_alpha_deg, p_reynolds_number, p_version_no_a, p_version_no_b)",
                "- api.list_airfoils_with_anomalies(p_only_current)",
                "基础表（只读）：airfoil, airfoil_version, coordinate_point, experiment_condition, performance_record, anomaly_rule, anomaly_record",
                "审计留痕表（只读/写入由应用层完成）：query_log, nl2sql_audit, result_explain_audit",
                "",
                "【数据约束提示】",
                "- 翼型编码（airfoil_code）格式为 NACA_xxxx（注意带下划线），如 NACA_2412、NACA_0012、NACA_23012__12%",
                "- experiment_condition 表中可用的雷诺数（reynolds_number）仅为：50000、100000、300000、500000、1000000",
                "- 攻角（alpha_deg）范围：-90° ~ +90°",
                "- 查询雷诺数条件时应使用上述可用值，否则结果为空",
                "- 基础表字段：airfoil(airfoil_code, name), performance_record(cl, cd, l_over_d), coordinate_point(x, y, surface)",
                "",
                "【可用示例提问】",
                '- "查询 NACA_2412 的当前有效版本"',
                '- "在 Re=300000、攻角 α=2 条件下，列出升阻比最高的前 10 个翼型"',
                '- "查询 NACA_0012 的上表面坐标点"',
                '- "列出存在异常提示的翼型"',
                '- "统计每个版本类型下的翼型数量"',
                '- "查询翼型 NACA_0012 在 Re=500000 下不同攻角的 Cl、Cd 性能数据"',
                '- "对比翼型 NACA_0012 和 NACA_2412 在 Re=300000 下的升阻比"',
            ]
        )
        meta_json = json.dumps({"mode": "weak"}, ensure_ascii=False)
        return SchemaSnapshot(mode="weak", text=text, meta_json=meta_json)

    cols_sql = r"""
WITH objs AS (
  SELECT table_schema, table_name, column_name, data_type
  FROM information_schema.columns
  WHERE table_schema IN ('api', 'public', 'airfoil_db')
    AND table_name NOT LIKE 'pg_%'
),
t AS (
  SELECT table_schema, table_name,
         json_agg(json_build_object('column', column_name, 'type', data_type) ORDER BY ordinal_position) AS cols
  FROM information_schema.columns
  WHERE table_schema IN ('api', 'public', 'airfoil_db')
    AND table_name NOT LIKE 'pg_%'
  GROUP BY table_schema, table_name
)
SELECT coalesce(json_agg(json_build_object('schema', table_schema, 'name', table_name, 'columns', cols)
                         ORDER BY table_schema, table_name), '[]'::json)
FROM t;
"""

    funcs_sql = r"""
SELECT coalesce(json_agg(json_build_object(
  'schema', n.nspname,
  'name', p.proname,
  'args', pg_get_function_identity_arguments(p.oid),
  'returns', pg_get_function_result(p.oid)
) ORDER BY n.nspname, p.proname), '[]'::json)
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('api')
  AND p.prokind = 'f';
"""

    tables_json = run_psql(pg, cols_sql, csv=False, tuples_only=True, no_align=True, quiet=True).stdout.strip()
    funcs_json = run_psql(pg, funcs_sql, csv=False, tuples_only=True, no_align=True, quiet=True).stdout.strip()

    meta = {"mode": "strong", "tables": json.loads(tables_json or "[]"), "functions": json.loads(funcs_json or "[]")}
    meta_json = json.dumps(meta, ensure_ascii=False)
    text = (
        "数据库 Schema（强提示，JSON 结构化）：\n"
        + meta_json
        + "\n"
        + "约束要求：\n"
        + "1. 涉及当前有效版本的查询必须使用 api.v_current_airfoil_version 选取 version_id，禁止自行推断当前版本。\n"
        + "2. 翼型编码（airfoil_code）格式为 NACA_xxxx（带下划线），如 NACA_2412、NACA_0012\n"
        + "3. experiment_condition 表中可用的雷诺数（reynolds_number）仅为：50000、100000、300000、500000、1000000\n"
        + "4. 查询雷诺数条件时应使用上述可用值，否则结果为空\n"
        + "5. 敏感表 user_account 仅在问题明确要求创建者/用户名或查询日志统计时允许，且必须有过滤条件与 LIMIT\n"
        + "\n"
        + "【可用示例提问】\n"
        + '- "查询 NACA_2412 的当前有效版本"\n'
        + '- "在 Re=300000、攻角 α=2 条件下，列出升阻比最高的前 10 个翼型"\n'
        + '- "查询 NACA_0012 的上表面坐标点"\n'
        + '- "列出存在异常提示的翼型"\n'
        + '- "统计每个版本类型下的翼型数量"\n'
        + '- "查询翼型 NACA_0012 在 Re=500000 下不同攻角的 Cl、Cd 性能数据"\n'
        + '- "对比翼型 NACA_0012 和 NACA_2412 在 Re=300000 下的升阻比"'
    )
    return SchemaSnapshot(mode="strong", text=text, meta_json=meta_json)

