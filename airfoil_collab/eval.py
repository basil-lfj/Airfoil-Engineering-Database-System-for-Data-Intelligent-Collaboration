from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .collab import RunOutcome, run_once
from .config import AppConfig
from .psql import PsqlError, export_select_to_csv


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    kind: str
    expected_audit_status: str
    actual_audit_status: str
    passed: bool
    notes: str
    query_id: str | None


def _norm_csv(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


# ── 抽取的判定逻辑 ──────────────────────────────────────────────────

def _check_case(
    out: RunOutcome,
    kind: str,
    expected_status: str,
    gold_sql: str | None,
    cfg: AppConfig,
) -> tuple[bool, str]:
    """复用原有逻辑，返回 (ok, note)。"""
    ok = out.audit.audit_status == expected_status if expected_status else True
    note = ""
    if kind == "positive" and ok and gold_sql and out.executed_sql and out.result_csv is not None:
        try:
            gold_csv = export_select_to_csv(cfg.postgres, str(gold_sql), statement_timeout_ms=5000)
            ok = _norm_csv(gold_csv) == _norm_csv(out.result_csv)
            if not ok:
                note = "result_mismatch"
        except PsqlError as e:
            ok = False
            note = f"gold_sql_failed: {str(e)[:200]}"
    return ok, note


# ── Schema 对比汇总 ─────────────────────────────────────────────────

def _summarize_schema_compare(results: list[dict]) -> dict:
    """汇总 schema 对比统计。"""
    improved = sum(1 for r in results if r.get("schema_improvement") == "improved")
    degraded = sum(1 for r in results if r.get("schema_improvement") == "degraded")
    both_pass = sum(1 for r in results if r.get("schema_improvement") == "same_both_pass")
    both_fail = sum(1 for r in results if r.get("schema_improvement") == "same_both_fail")
    total = improved + degraded + both_pass + both_fail
    return {
        "total_compared": total,
        "improved_with_strong": improved,
        "degraded_with_strong": degraded,
        "both_pass": both_pass,
        "both_fail": both_fail,
        "conclusion": (
            f"Strong schema 提示在 {improved}/{total} 条用例中带来了改进，"
            f"{degraded}/{total} 条退化，{both_pass}/{total} 条无差异。"
        ) if total else "未执行对比",
    }


# ── 错误类型汇总 ────────────────────────────────────────────────────

def _summarize_error_types(results: list[dict]) -> dict:
    """汇总所有用例中出现的错误类型频次。"""
    error_counter: Counter = Counter()
    for r in results:
        for et in r.get("error_types", []):
            error_counter[et] += 1
        if "weak" in r:
            for et in r["weak"].get("error_types", []):
                error_counter[f"weak_{et}"] += 1
    return dict(error_counter.most_common())


# ── 主评测函数（重构版）─────────────────────────────────────────────

def run_eval(cfg: AppConfig, cases_path: Path) -> dict:
    obj = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases") or []

    results: list[dict] = []
    passed = 0

    for c in cases:
        case_id = str(c.get("id"))
        kind = str(c.get("kind") or "positive")
        schema_mode = str(c.get("schema_mode") or "strong")
        question = str(c.get("question") or "")
        expected_status = str(c.get("expected_audit_status") or "")
        gold_sql = c.get("gold_sql")
        do_compare = bool(c.get("schema_compare", kind == "positive"))

        # ── 主模式执行 ──
        out: RunOutcome = run_once(
            cfg,
            question=question,
            schema_mode=schema_mode,
            username="eval",
            do_explain=False,
        )
        ok, note = _check_case(out, kind, expected_status, gold_sql, cfg)

        case_result = {
            "case_id": case_id,
            "kind": kind,
            "schema_mode": schema_mode,
            "expected_audit_status": expected_status,
            "actual_audit_status": out.audit.audit_status,
            "passed": ok,
            "notes": note or out.audit.notes,
            "query_id": out.query_id,
            "generated_sql": out.generated.obj.get("sql") if out.generated else None,
            "error_types": out.audit.error_types,
        }

        # ── Weak 模式对比（仅正例）──
        if do_compare and kind == "positive":
            out_weak: RunOutcome = run_once(
                cfg,
                question=question,
                schema_mode="weak",
                username="eval",
                do_explain=False,
            )
            ok_weak, note_weak = _check_case(out_weak, kind, expected_status, gold_sql, cfg)
            case_result["weak"] = {
                "schema_mode": "weak",
                "actual_audit_status": out_weak.audit.audit_status,
                "passed": ok_weak,
                "notes": note_weak or out_weak.audit.notes,
                "generated_sql": out_weak.generated.obj.get("sql") if out_weak.generated else None,
                "error_types": out_weak.audit.error_types,
            }
            if not ok_weak and ok:
                case_result["schema_improvement"] = "improved"
            elif ok_weak and not ok:
                case_result["schema_improvement"] = "degraded"
            elif ok_weak and ok:
                case_result["schema_improvement"] = "same_both_pass"
            else:
                case_result["schema_improvement"] = "same_both_fail"

        if ok:
            passed += 1
        results.append(case_result)

    summary = {
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "schema_compare": _summarize_schema_compare(results),
        "error_type_summary": _summarize_error_types(results),
        "items": results,
    }
    return summary


# ── 结果解释评测 ────────────────────────────────────────────────────

def run_explain_eval(cfg: AppConfig, cases_path: Path) -> dict:
    """对结果解释进行审计评测。"""
    obj = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases") or []
    results: list[dict] = []

    for c in cases:
        case_id = str(c.get("id"))
        question = str(c.get("question") or "")
        schema_mode = str(c.get("schema_mode") or "strong")

        out = run_once(
            cfg,
            question=question,
            schema_mode=schema_mode,
            username="eval",
            do_explain=True,
        )

        results.append({
            "case_id": case_id,
            "description": c.get("description", ""),
            "audit_status": out.audit.audit_status,
            "has_result": out.result_csv is not None,
            "has_explanation": out.explanation_text is not None,
            "explanation_preview": (out.explanation_text or "")[:300],
            "error_types": out.audit.error_types,
        })

    return {"cases": len(results), "items": results}
