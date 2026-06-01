from __future__ import annotations

import json
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


def run_eval(cfg: AppConfig, cases_path: Path) -> dict:
    obj = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases") or []

    results: list[CaseResult] = []
    passed = 0

    for c in cases:
        case_id = str(c.get("id"))
        kind = str(c.get("kind") or "positive")
        schema_mode = str(c.get("schema_mode") or "strong")
        question = str(c.get("question") or "")
        expected_status = str(c.get("expected_audit_status") or "")
        gold_sql = c.get("gold_sql")

        out: RunOutcome = run_once(
            cfg,
            question=question,
            schema_mode=schema_mode,
            username="eval",
            do_explain=False,
        )

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

        if ok:
            passed += 1
        results.append(
            CaseResult(
                case_id=case_id,
                kind=kind,
                expected_audit_status=expected_status,
                actual_audit_status=out.audit.audit_status,
                passed=ok,
                notes=note or out.audit.notes,
                query_id=out.query_id,
            )
        )

    summary = {
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "items": [r.__dict__ for r in results],
    }
    return summary

