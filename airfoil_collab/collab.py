from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .audit import AuditDecision, audit_sql
from .config import AppConfig
from .deepseek import DeepSeekError, JsonCallResult, call_json_with_retries
from .psql import PsqlError, export_select_to_csv, run_psql, run_psql_file
from .schema_prompt import SchemaSnapshot, build_schema_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunOutcome:
    query_id: str | None
    audit: AuditDecision
    generated: JsonCallResult | None
    executed_sql: str | None
    result_csv: str | None
    explanation_text: str | None
    explanation_judgement: str | None
    explanation_issues: list[str] | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_nullable(value: str | None) -> str:
    return "NULL" if value is None else _sql_quote(value)


def _sql_bool(value: bool) -> str:
    return "true" if value else "false"


def _detect_airfoil_codes(text: str) -> list[str]:
    found = re.findall(r"\bNACA\s*([0-9]{4})\b", text, flags=re.IGNORECASE)
    codes = [f"NACA{n}" for n in found]
    unique: list[str] = []
    for c in codes:
        if c not in unique:
            unique.append(c)
    return unique


def _classify_query_type(sql: str) -> str:
    s = sql.lower()
    if "coordinate_point" in s or "get_airfoil_geometry" in s:
        return "geom"
    if "anomaly" in s:
        return "anomaly"
    if "compare" in s or "version" in s:
        return "version_diff" if "version" in s else "compare"
    if "performance" in s or "find_airfoils_by_condition" in s:
        return "perf"
    return "perf"


def _get_or_create_user_id(cfg: AppConfig, username: str) -> str:
    sql = (
        "INSERT INTO public.user_account(username, role, is_active)\n"
        f"VALUES ({_sql_quote(username)}, 'operator', true)\n"
        "ON CONFLICT (username) DO UPDATE SET is_active = true\n"
        "RETURNING user_id;"
    )
    res = run_psql(cfg.postgres, sql, csv=False, tuples_only=True, no_align=True, quiet=True)
    return res.stdout.strip()


def _maybe_airfoil_id(cfg: AppConfig, airfoil_code: str) -> str | None:
    sql = (
        "SELECT airfoil_id\n"
        "FROM public.airfoil\n"
        f"WHERE airfoil_code = {_sql_quote(airfoil_code)} AND is_deleted = false\n"
        "LIMIT 1;"
    )
    try:
        res = run_psql(cfg.postgres, sql, csv=False, tuples_only=True, no_align=True, quiet=True)
        v = res.stdout.strip()
        return v or None
    except PsqlError:
        return None


def _insert_query_log(
    cfg: AppConfig,
    *,
    user_id: str,
    airfoil_id: str | None,
    query_type: str,
    parameters_json: str,
    sql_text: str | None,
    is_success: bool,
    error_message: str | None,
) -> str:
    sql = (
        "INSERT INTO public.query_log(user_id, airfoil_id, query_type, parameters_json, sql_text, is_success, error_message)\n"
        f"VALUES ({_sql_quote(user_id)}, {_sql_nullable(airfoil_id)}, {_sql_quote(query_type)}, {_sql_quote(parameters_json)}, {_sql_nullable(sql_text)}, {_sql_bool(is_success)}, {_sql_nullable(error_message)})\n"
        "RETURNING query_id;"
    )
    res = run_psql(cfg.postgres, sql, csv=False, tuples_only=True, no_align=True, quiet=True)
    return res.stdout.strip()


def _insert_nl2sql_audit(
    cfg: AppConfig,
    *,
    query_id: str,
    auditor_id: str,
    nl_question: str,
    generated_sql: str | None,
    audited_sql: str | None,
    audit_status: str,
    error_types: list[str],
    notes: str,
) -> None:
    error_types_json = json.dumps(error_types, ensure_ascii=False)
    sql = (
        "INSERT INTO public.nl2sql_audit(query_id, auditor_id, nl_question, generated_sql, audited_sql, audit_status, error_types_json, notes)\n"
        f"VALUES ({_sql_quote(query_id)}, {_sql_quote(auditor_id)}, {_sql_quote(nl_question)}, {_sql_quote(generated_sql or '')}, {_sql_nullable(audited_sql)}, {_sql_quote(audit_status)}, {_sql_quote(error_types_json)}, {_sql_quote(notes)})"
        ";"
    )
    run_psql(cfg.postgres, sql, csv=False, tuples_only=False, no_align=False, quiet=True)


def _insert_result_explain_audit(
    cfg: AppConfig,
    *,
    query_id: str,
    reviewer_id: str,
    snapshot_ref: str,
    explanation: str,
    judgement: str,
    issues: list[str],
) -> None:
    issues_json = json.dumps(issues, ensure_ascii=False)
    sql = (
        "INSERT INTO public.result_explain_audit(query_id, reviewer_id, result_snapshot_ref, llm_explanation, judgement, issues_json)\n"
        f"VALUES ({_sql_quote(query_id)}, {_sql_quote(reviewer_id)}, {_sql_quote(snapshot_ref)}, {_sql_quote(explanation)}, {_sql_quote(judgement)}, {_sql_quote(issues_json)});"
    )
    run_psql(cfg.postgres, sql, csv=False, tuples_only=False, no_align=False, quiet=True)


def bootstrap_db(cfg: AppConfig) -> None:
    design_dir = cfg.project_root / "数据库设计" / "sql"
    for name in ["01_tables.sql", "02_constraints.sql", "05_core_queries.sql", "11_advanced_mechanisms.sql"]:
        p = design_dir / name
        if p.exists():
            run_psql_file(cfg.postgres, p)


def generate_sql(cfg: AppConfig, *, question: str, schema: SchemaSnapshot) -> JsonCallResult:
    system_prompt = "\n".join(
        [
            "你是一个严格的 NL2SQL 引擎。",
            "只允许生成只读 SQL（SELECT/WITH）。",
            "禁止生成多语句；最终 SQL 不要包含分号。",
            "若问题无法在给定数据库中回答，请输出 sql 为空字符串，并在 assumptions 中说明原因。",
            "输出必须是单个 JSON 对象，字段：sql(string), assumptions(array of string), risk_flags(array of string)。",
            "版本化约束：凡语义涉及“当前有效版本”，必须通过 api.v_current_airfoil_version 选取 version_id，再做连接/查询。",
            "敏感对象默认拒绝：user_account 仅在问题明确要求创建者/用户名或查询日志统计时允许，且必须有过滤条件与 LIMIT。",
        ]
    )

    user_prompt = "\n".join(
        [
            f"问题：{question}",
            "",
            schema.text,
            "",
            "请输出 JSON：",
            '{"sql":"","assumptions":[],"risk_flags":[]}',
        ]
    )

    return call_json_with_retries(cfg.deepseek, system_prompt=system_prompt, user_prompt=user_prompt)


def explain_result(cfg: AppConfig, *, question: str, sql: str, csv_text: str) -> str:
    head_lines = csv_text.splitlines()[:25]
    snippet = "\n".join(head_lines)
    system_prompt = "\n".join(
        [
            "你是一个严格的数据库结果解释器。",
            "必须基于给定结果表格进行解释，必须引用具体列名与数值或行数。",
            "如果结果不足以支撑结论，必须明确说明无法判断并列出缺失信息。",
            "禁止补充结果中不存在的具体事实。",
            "输出必须是单个 JSON 对象，字段：explanation(string), issues(array of string)。",
            "issues 可选值：not_grounded_in_result, engineering_common_sense_violation, hallucination_plausible_but_wrong, fabricated_missing_info。",
        ]
    )
    user_prompt = "\n".join(
        [
            f"原问题：{question}",
            f"SQL：{sql}",
            "",
            "结果（CSV 前若干行，可能被截断）：",
            snippet,
            "",
            '请输出 JSON：{"explanation":"","issues":[]}',
        ]
    )
    res = call_json_with_retries(cfg.deepseek, system_prompt=system_prompt, user_prompt=user_prompt)
    explanation = str(res.obj.get("explanation") or "").strip()
    return explanation


def audit_explanation(
    explanation: str,
    csv_text: str,
    question: str,
) -> tuple[str, list[str]]:
    """对结果解释进行程序化审计，返回 (judgement, issues)。"""
    import re

    judgement: str = "correct"
    issues: list[str] = []

    # 1. 解释是否空白/过于简短（明显未基于结果）
    if not explanation or len(explanation.strip()) < 10:
        return ("unsupported", ["not_grounded_in_result"])

    # 2. 提取结果中的数值集合（含列名中的数字），用于检测幻觉
    csv_numbers: set[str] = set()
    csv_codes: set[str] = set()
    for line in csv_text.splitlines():
        # 提取翼型编号 (NACAxxxx)
        for m in re.finditer(r"NACA\d{4}", line, re.IGNORECASE):
            csv_codes.add(m.group().upper())
        # 提取浮点数（保留 4 位以内精度用于匹配）
        for m in re.finditer(r"\d+\.\d+", line):
            csv_numbers.add(m.group())
        for m in re.finditer(r"\b\d+\b", line):
            csv_numbers.add(m.group())

    # 3. 提取解释中的翼型编号
    explained_codes = set(re.findall(r"NACA\d{4}", explanation, re.IGNORECASE))
    question_codes = set(re.findall(r"NACA\d{4}", question, re.IGNORECASE))
    fabricated_codes = explained_codes - csv_codes - {c.upper() for c in question_codes}
    if fabricated_codes:
        issues.append("fabricated_missing_info")

    # 4. 检查解释是否引用了结果中的具体数值
    has_grounded_number = any(num in explanation for num in csv_numbers if len(num) >= 3)

    # 5. 检查严重工程常识违规关键词
    suspicious_phrases = [
        ("负阻力", "engineering_common_sense_violation"),
        ("升力系数为零", "hallucination_plausible_but_wrong"),
        ("无限升阻比", "engineering_common_sense_violation"),
    ]
    for phrase, issue_type in suspicious_phrases:
        if phrase in explanation:
            if issue_type not in issues:
                issues.append(issue_type)

    # 6. 如果 CSV 为空（只有 header），解释却说有具体发现
    csv_data_lines = [l for l in csv_text.splitlines()[1:] if l.strip()]
    if not csv_data_lines:
        if any(kw in explanation for kw in ["发现", "表明", "显示", "可以看出", "数值为"]):
            issues.append("fabricated_missing_info")
        if not any(kw in explanation for kw in ["无法判断", "无数据", "没有", "为空", "未找到"]):
            issues.append("not_grounded_in_result")
    else:
        if not has_grounded_number:
            issues.append("not_grounded_in_result")

    # 7. 综合判定
    if "fabricated_missing_info" in issues:
        judgement = "incorrect"
    elif "engineering_common_sense_violation" in issues:
        judgement = "incorrect"
    elif "not_grounded_in_result" in issues and "hallucination_plausible_but_wrong" in issues:
        judgement = "incorrect"
    elif issues:
        judgement = "unsupported"

    return (judgement, issues)


def run_once(
    cfg: AppConfig,
    *,
    question: str,
    schema_mode: str = "strong",
    username: str = "system",
    do_explain: bool = True,
    statement_timeout_ms: int = 3000,
    result_dir: Path | None = None,
) -> RunOutcome:
    schema = build_schema_prompt(cfg.postgres, mode=schema_mode)

    user_id = _get_or_create_user_id(cfg, username)
    airfoil_codes = _detect_airfoil_codes(question)
    airfoil_id = _maybe_airfoil_id(cfg, airfoil_codes[0]) if len(airfoil_codes) == 1 else None

    parameters = {
        "schema_mode": schema.mode,
        "schema_meta": json.loads(schema.meta_json),
        "model": cfg.deepseek.model,
        "model_params": {
            "temperature": cfg.deepseek.temperature,
            "top_p": cfg.deepseek.top_p,
            "max_tokens": cfg.deepseek.max_tokens,
        },
        "entity_binding": {"airfoil_codes": airfoil_codes},
        "at": _now_iso(),
    }

    query_id: str | None = None
    generated: JsonCallResult | None = None
    try:
        generated = generate_sql(cfg, question=question, schema=schema)
        logger.info("LLM generated object: %s", generated.obj) # 添加日志
        model_sql = str(generated.obj.get("sql") or "")
        query_type = _classify_query_type(model_sql)
        query_id = _insert_query_log(
            cfg,
            user_id=user_id,
            airfoil_id=airfoil_id,
            query_type=query_type,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            sql_text=model_sql,
            is_success=False,
            error_message=None,
        )
    except DeepSeekError as e:
        query_id = _insert_query_log(
            cfg,
            user_id=user_id,
            airfoil_id=airfoil_id,
            query_type="perf",
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            sql_text=None,
            is_success=False,
            error_message="LLM_CALL_FAILED",
        )
        _insert_nl2sql_audit(
            cfg,
            query_id=query_id,
            auditor_id=user_id,
            nl_question=question,
            generated_sql=None,
            audited_sql=None,
            audit_status="rejected",
            error_types=["llm_call_failed"],
            notes=str(e),
        )
        return RunOutcome(
            query_id=query_id,
            audit=AuditDecision("rejected", ["llm_call_failed"], str(e), None),
            generated=None,
            executed_sql=None,
            result_csv=None,
            explanation_text=None,
            explanation_judgement=None,
            explanation_issues=None,
        )

    model_sql = str(generated.obj.get("sql") or "")
    audit = audit_sql(model_sql, question=question)
    logger.info("审计结果: status=%s, errors=%s, sql_to_execute=%s", audit.audit_status, audit.error_types, audit.sql_to_execute)
    _insert_nl2sql_audit(
        cfg,
        query_id=query_id,
        auditor_id=user_id,
        nl_question=question,
        generated_sql=model_sql or None,
        audited_sql=audit.sql_to_execute,
        audit_status=audit.audit_status,
        error_types=audit.error_types,
        notes=audit.notes,
    )

    if audit.audit_status != "approved" or audit.sql_to_execute is None:
        run_psql(
            cfg.postgres,
            "UPDATE public.query_log SET is_success=false, error_message='AUDIT_BLOCKED' WHERE query_id = "
            + _sql_quote(query_id)
            + ";",
            csv=False,
            tuples_only=False,
            no_align=False,
            quiet=True,
        )
        return RunOutcome(
            query_id=query_id,
            audit=audit,
            generated=generated,
            executed_sql=None,
            result_csv=None,
            explanation_text=None,
            explanation_judgement=None,
            explanation_issues=None,
        )

    exec_sql = audit.sql_to_execute
    csv_out: str | None = None
    try:
        csv_out = export_select_to_csv(cfg.postgres, exec_sql, statement_timeout_ms=statement_timeout_ms)
        run_psql(
            cfg.postgres,
            "UPDATE public.query_log SET is_success=true, error_message=NULL, sql_text="
            + _sql_quote(exec_sql)
            + " WHERE query_id = "
            + _sql_quote(query_id)
            + ";",
            csv=False,
            tuples_only=False,
            no_align=False,
            quiet=True,
        )
    except PsqlError as e:
        logger.error("SQL 执行失败: %s\nSQL: %s", e, exec_sql)
        run_psql(
            cfg.postgres,
            "UPDATE public.query_log SET is_success=false, error_message="
            + _sql_quote(str(e)[:500])
            + " WHERE query_id = "
            + _sql_quote(query_id)
            + ";",
            csv=False,
            tuples_only=False,
            no_align=False,
            quiet=True,
        )
        return RunOutcome(
            query_id=query_id,
            audit=audit,
            generated=generated,
            executed_sql=exec_sql,
            result_csv=None,
            explanation_text=None,
            explanation_judgement=None,
            explanation_issues=None,
        )

    result_root = result_dir or (cfg.project_root / "数据智能协同" / "runs")
    result_root.mkdir(parents=True, exist_ok=True)
    run_folder = result_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder.mkdir(parents=True, exist_ok=True)
    snapshot_path = run_folder / f"{query_id}.csv"
    snapshot_path.write_text(csv_out, encoding="utf-8", errors="ignore")

    explanation_text: str | None = None
    explanation_judgement: str | None = None
    explanation_issues: list[str] | None = None
    if do_explain:
        try:
            explanation_text = explain_result(cfg, question=question, sql=exec_sql, csv_text=csv_out)
            exp_judgement, exp_issues = audit_explanation(
                explanation=explanation_text,
                csv_text=csv_out,
                question=question,
            )
            explanation_judgement = exp_judgement
            explanation_issues = exp_issues
            _insert_result_explain_audit(
                cfg,
                query_id=query_id,
                reviewer_id=user_id,
                snapshot_ref=str(snapshot_path),
                explanation=explanation_text,
                judgement=exp_judgement,
                issues=exp_issues,
            )
        except DeepSeekError:
            explanation_text = None

    return RunOutcome(
        query_id=query_id,
        audit=audit,
        generated=generated,
        executed_sql=exec_sql,
        result_csv=csv_out,
        explanation_text=explanation_text,
        explanation_judgement=explanation_judgement,
        explanation_issues=explanation_issues,
    )
