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


def audit_sql(sql: str, *, question: str) -> AuditDecision:
    if not sql or not sql.strip():
        return AuditDecision(audit_status="rejected", error_types=["empty_sql"], notes="empty sql", sql_to_execute=None)

    normalized = _normalize_sql(sql)
    lower = normalized.lower()

    if _has_disallowed_schema(normalized):
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="disallowed schema access",
            sql_to_execute=None,
        )

    if ";" in normalized:
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="multiple statements not allowed",
            sql_to_execute=None,
        )

    for kw in _FORBIDDEN:
        if re.search(rf"\b{re.escape(kw)}\b", lower):
            return AuditDecision(
                audit_status="rejected",
                error_types=["unsafe_sql"],
                notes=f"forbidden keyword: {kw}",
                sql_to_execute=None,
            )

    if not re.match(r"^\s*(with|select)\b", normalized, flags=re.IGNORECASE):
        return AuditDecision(
            audit_status="rejected",
            error_types=["unsafe_sql"],
            notes="only select/with is allowed",
            sql_to_execute=None,
        )

    if any(re.search(rf"\b{re.escape(t)}\b", lower) for t in _SENSITIVE):
        if not _requires_user_account(question):
            return AuditDecision(
                audit_status="rejected",
                error_types=["sensitive_data_request"],
                notes="sensitive table access",
                sql_to_execute=None,
            )

    if _mentions_version_table(normalized) and not _is_cross_version_question(question):
        if not _mentions_current_view(normalized) and not _has_current_filters(normalized):
            return AuditDecision(
                audit_status="needs_fix",
                error_types=["version_semantics_error"],
                notes="missing current-valid-version constraint",
                sql_to_execute=None,
            )

    limited = _ensure_limit(normalized)
    return AuditDecision(audit_status="approved", error_types=[], notes="ok", sql_to_execute=limited)

