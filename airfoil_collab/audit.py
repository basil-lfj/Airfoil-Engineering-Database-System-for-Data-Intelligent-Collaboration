from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditDecision:
    audit_status: str
    error_types: list[str]
    notes: str
    sql_to_execute: str | None


_FORBIDDEN = [
    "insert",
    "update",
    "delete",
    "alter",
    "drop",
    "truncate",
    "copy",
    "create",
    "grant",
    "revoke",
    "vacuum",
    "analyze",
    "call",
]

_SENSITIVE = [
    "user_account",
]

_DISALLOWED_SCHEMAS = [
    "pg_catalog",
    "information_schema",
]


def _normalize_sql(sql: str) -> str:
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    return s


def _has_disallowed_schema(sql: str) -> bool:
    s = sql.lower()
    return any(f"{schema}." in s for schema in _DISALLOWED_SCHEMAS)


def _mentions_version_table(sql: str) -> bool:
    return bool(re.search(r"\bairfoil_version\b", sql, flags=re.IGNORECASE))


def _mentions_current_view(sql: str) -> bool:
    return bool(re.search(r"\bv_current_airfoil_version\b", sql, flags=re.IGNORECASE))


def _has_current_filters(sql: str) -> bool:
    s = re.sub(r"\s+", " ", sql.lower())
    return (
        ("is_current" in s and "true" in s)
        and ("status" in s and "valid" in s)
        and ("is_deleted" in s and "false" in s)
    )


def _is_cross_version_question(question: str) -> bool:
    q = question
    keys = [
        "不同版本",
        "跨版本",
        "历史版本",
        "版本对比",
        "版本差异",
        "版本 1",
        "版本1",
        "版本 2",
        "版本2",
        "version_no_a",
        "version_no_b",
    ]
    return any(k in q for k in keys)


def _requires_user_account(question: str) -> bool:
    keys = ["创建者", "用户名", "username", "用户", "查询日志"]
    return any(k in question for k in keys)


def _ensure_limit(sql: str, *, max_limit: int = 200) -> str:
    s = sql.strip()
    if not re.search(r"\blimit\b", s, flags=re.IGNORECASE):
        return s + f"\nLIMIT {max_limit}"

    m = re.search(r"\blimit\s+(\d+)\b", s, flags=re.IGNORECASE)
    if not m:
        return s
    try:
        n = int(m.group(1))
    except ValueError:
        return s
    if n <= max_limit:
        return s
    return re.sub(r"\blimit\s+\d+\b", f"LIMIT {max_limit}", s, count=1, flags=re.IGNORECASE)


# ── 新增：聚合语法误用检查 ──────────────────────────────────────────

def _check_group_by_consistency(sql: str) -> list[str]:
    """检查 GROUP BY 与 SELECT 列的一致性。

    简化策略：如果存在 GROUP BY，检查 SELECT 中的非聚合列是否都在 GROUP BY 中。
    """
    s = re.sub(r"\s+", " ", sql)

    # 检测是否有 GROUP BY
    if not re.search(r"\bGROUP\s+BY\b", s, re.IGNORECASE):
        return []

    # 提取 SELECT ... FROM 之间的列表达式
    select_match = re.search(r"\bSELECT\b(.+?)\bFROM\b", s, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []

    select_part = select_match.group(1)
    columns = [col.strip() for col in select_part.split(",")]

    # 提取 GROUP BY 后的列
    group_match = re.search(
        r"\bGROUP\s+BY\b(.+?)(?:\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
        s,
        re.IGNORECASE | re.DOTALL,
    )
    if not group_match:
        return []
    group_part = group_match.group(1)
    group_cols = {col.strip().lower() for col in group_part.split(",")}

    # 聚合函数模式
    agg_pattern = re.compile(
        r"\b(COUNT|SUM|AVG|MIN|MAX|ARRAY_AGG|STRING_AGG|JSON_AGG|JSONB_AGG)\s*\(|\bCAST\s*\(|\bCOALESCE\s*\(|\bNULLIF\s*\(",
        re.IGNORECASE,
    )

    issues = []
    for col in columns:
        col_clean = col.strip().lower()
        # 跳过常量、*、包含聚合函数的表达式
        if col_clean in ("*", "1", "true", "false") or col_clean.isdigit():
            continue
        if agg_pattern.search(col):
            continue
        # 提取列别名前的真实列名
        if " AS " in col.upper():
            col_clean = col.upper().split(" AS ")[0].strip().lower()
        # 简单的表.列形式匹配
        if "." in col_clean:
            col_clean = col_clean.split(".")[-1]
        if col_clean not in group_cols:
            issues.append("aggregate_misuse")
            break

    return issues


# ── 新增：连接条件遗漏检查 ──────────────────────────────────────────

def _check_missing_join_condition(sql: str) -> list[str]:
    """如果 SQL 涉及多表连接，检查是否遗漏连接条件。

    简化策略：统计 FROM/JOIN 中涉及的表数量，如果 ≥2 且 WHERE/ON 中没有 `=` 连接条件，标记。
    """
    s = sql

    table_pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
        re.IGNORECASE,
    )
    tables = table_pattern.findall(s)
    unique_tables = set(t.lower() for t in tables)

    if len(unique_tables) < 2:
        return []

    # 检查是否有至少一个连接条件（table1.col = table2.col 模式）
    join_cond_pattern = re.compile(r"\w+\.\w+\s*=\s*\w+\.\w+")
    if not join_cond_pattern.search(s):
        return ["missing_join_condition"]

    return []


# ── 重构后的审计主函数（累积式错误收集）───────────────────────────

def audit_sql(sql: str, *, question: str) -> AuditDecision:
    """对生成的 SQL 进行静态审计。

    采用累积式策略：先收集所有错误类型与备注，最后统一根据
    优先级（rejected > needs_fix > approved）决定 audit_status。
    """
    if not sql or not sql.strip():
        return AuditDecision(
            audit_status="rejected",
            error_types=["empty_sql"],
            notes="empty sql",
            sql_to_execute=None,
        )

    normalized = _normalize_sql(sql)
    lower = normalized.lower()

    error_types: list[str] = []
    notes_parts: list[str] = []

    # ── 1. 硬拦截：禁止的 schema ──
    if _has_disallowed_schema(normalized):
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="disallowed schema access",
            sql_to_execute=None,
        )

    # ── 2. 多语句 ──
    if ";" in normalized:
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="multiple statements not allowed",
            sql_to_execute=None,
        )

    # ── 3. 禁止关键词 ──
    for kw in _FORBIDDEN:
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            return AuditDecision(
                audit_status="rejected",
                error_types=["unsafe_sql"],
                notes=f"forbidden keyword: {kw}",
                sql_to_execute=None,
            )

    # ── 4. 非 SELECT/WITH ──
    if not re.match(r"^\s*(with|select)\b", normalized, flags=re.IGNORECASE):
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="only select/with is allowed",
            sql_to_execute=None,
        )

    # ── 5. 敏感表访问（可降级但不能执行）──
    if any(re.search(rf"\b{re.escape(t)}\b", lower) for t in _SENSITIVE):
        if not _requires_user_account(question):
            return AuditDecision(
                audit_status="rejected",
                error_types=["sensitive_data_request"],
                notes="sensitive table access",
                sql_to_execute=None,
            )

    # ── 6. 版本语义检查 ──
    if _mentions_version_table(normalized) and not _is_cross_version_question(question):
        if not _mentions_current_view(normalized) and not _has_current_filters(normalized):
            error_types.append("version_semantics_error")
            notes_parts.append("missing current-valid-version constraint")

    # ── 7. 新增：聚合语法检查 ──
    agg_issues = _check_group_by_consistency(normalized)
    if agg_issues:
        error_types.extend(agg_issues)
        notes_parts.append("possible GROUP BY inconsistency")

    # ── 8. 新增：连接条件检查 ──
    join_issues = _check_missing_join_condition(normalized)
    if join_issues:
        error_types.extend(join_issues)
        notes_parts.append("possible missing join condition")

    # ── 9. 综合判定优先级 ──
    notes = "; ".join(notes_parts) if notes_parts else "ok"

    if not error_types:
        # 全部通过
        limited = _ensure_limit(normalized)
        return AuditDecision(
            audit_status="approved",
            error_types=[],
            notes=notes,
            sql_to_execute=limited,
        )

    # 有错误：按优先级判定
    # rejected 级错误：unsafe_sql, sensitive_data_request
    rejected_types = {"unsafe_sql", "sensitive_data_request"}
    if any(et in rejected_types for et in error_types):
        return AuditDecision(
            audit_status="rejected",
            error_types=error_types,
            notes=notes,
            sql_to_execute=None,
        )

    # needs_fix 级错误：version_semantics_error, aggregate_misuse, missing_join_condition
    return AuditDecision(
        audit_status="needs_fix",
        error_types=error_types,
        notes=notes,
        sql_to_execute=None,
    )
