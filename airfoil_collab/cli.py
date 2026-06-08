from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collab import bootstrap_db, run_once
from .config import load_app_config
from .eval import run_eval, run_explain_eval
from .psql import run_psql


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    bootstrap_db(cfg)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    out = run_once(
        cfg,
        question=args.question,
        schema_mode=args.schema_mode,
        username=args.username,
        do_explain=not args.no_explain,
        statement_timeout_ms=args.statement_timeout_ms,
        result_dir=Path(args.result_dir) if args.result_dir else None,
    )

    payload = {
        "query_id": out.query_id,
        "audit_status": out.audit.audit_status,
        "error_types": out.audit.error_types,
        "notes": out.audit.notes,
        "executed_sql": out.executed_sql,
        "has_result": out.result_csv is not None,
        "has_explanation": out.explanation_text is not None,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if out.result_csv is not None and args.print_result:
        sys.stdout.write("\n")
        sys.stdout.write(out.result_csv)
        if not out.result_csv.endswith("\n"):
            sys.stdout.write("\n")
    if out.explanation_text is not None and args.print_explain:
        sys.stdout.write("\n")
        sys.stdout.write(out.explanation_text + "\n")
    return 0 if out.audit.audit_status == "approved" else 2


def _cmd_eval(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    summary = run_eval(cfg, Path(args.cases))
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0 if summary.get("failed") == 0 else 2


def _cmd_explain_eval(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    summary = run_explain_eval(cfg, Path(args.cases))
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


def _cmd_anomaly_compare(args: argparse.Namespace) -> int:
    from .anomaly_compare import run_anomaly_compare

    cfg = load_app_config()
    result = run_anomaly_compare(cfg, sample_size=args.sample_size)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _cmd_review_nl2sql(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    sets: list[str] = []
    if args.audit_status:
        sets.append("audit_status=" + _sql_quote(args.audit_status))
    if args.audited_sql is not None:
        sets.append("audited_sql=" + (_sql_quote(args.audited_sql) if args.audited_sql != "" else "NULL"))
    if args.error_types_json is not None:
        sets.append(
            "error_types_json=" + (_sql_quote(args.error_types_json) if args.error_types_json != "" else "NULL")
        )
    if args.notes is not None:
        sets.append("notes=" + (_sql_quote(args.notes) if args.notes != "" else "NULL"))
    if not sets:
        return 0

    where = ""
    if args.audit_id:
        where = "audit_id=" + _sql_quote(str(args.audit_id))
    elif args.query_id:
        where = "query_id=" + _sql_quote(str(args.query_id))
    else:
        return 2

    sql = "UPDATE public.nl2sql_audit SET " + ", ".join(sets) + " WHERE " + where + " RETURNING audit_id::text;"
    res = run_psql(cfg.postgres, sql, tuples_only=True, no_align=True, quiet=True)
    sys.stdout.write(json.dumps({"updated_audit_id": res.stdout.strip()}, ensure_ascii=False) + "\n")
    return 0


def _cmd_review_explain(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    sets: list[str] = []
    if args.judgement:
        sets.append("judgement=" + _sql_quote(args.judgement))
    if args.issues_json is not None:
        sets.append("issues_json=" + (_sql_quote(args.issues_json) if args.issues_json != "" else "NULL"))
    if not sets:
        return 0

    where = ""
    if args.explain_id:
        where = "explain_id=" + _sql_quote(str(args.explain_id))
    elif args.query_id:
        where = "query_id=" + _sql_quote(str(args.query_id))
    else:
        return 2

    sql = (
        "UPDATE public.result_explain_audit SET "
        + ", ".join(sets)
        + " WHERE "
        + where
        + " RETURNING explain_id::text;"
    )
    res = run_psql(cfg.postgres, sql, tuples_only=True, no_align=True, quiet=True)
    sys.stdout.write(json.dumps({"updated_explain_id": res.stdout.strip()}, ensure_ascii=False) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="airfoil-collab", add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_boot = sub.add_parser("bootstrap", help="apply required database sql scripts")
    p_boot.set_defaults(func=_cmd_bootstrap)

    p_run = sub.add_parser("run", help="nl2sql + audit + execute + explain")
    p_run.add_argument("--question", required=True, help="natural language question")
    p_run.add_argument("--schema-mode", default="strong", choices=["weak", "strong"], help="schema prompt mode")
    p_run.add_argument("--username", default="system", help="audit actor username")
    p_run.add_argument("--statement-timeout-ms", type=int, default=3000, help="db statement timeout")
    p_run.add_argument("--result-dir", default="", help="result snapshot directory")
    p_run.add_argument("--no-explain", action="store_true", help="disable result explanation")
    p_run.add_argument("--print-result", action="store_true", help="print csv result to stdout")
    p_run.add_argument("--print-explain", action="store_true", help="print explanation to stdout")
    p_run.set_defaults(func=_cmd_run)

    p_eval = sub.add_parser("eval", help="run reproducible nl2sql evaluation cases")
    p_eval.add_argument(
        "--cases",
        default=str(Path("数据智能协同") / "test_cases.json"),
        help="path to test cases json",
    )
    p_eval.set_defaults(func=_cmd_eval)

    p_explain_eval = sub.add_parser("explain-eval", help="evaluate result explanation audit")
    p_explain_eval.add_argument(
        "--cases",
        default=str(Path("数据智能协同") / "explain_test_cases.json"),
        help="path to explain test cases json",
    )
    p_explain_eval.set_defaults(func=_cmd_explain_eval)

    p_anomaly = sub.add_parser("anomaly-compare", help="rule vs llm anomaly detection comparison")
    p_anomaly.add_argument("--sample-size", type=int, default=100, help="number of records to sample")
    p_anomaly.set_defaults(func=_cmd_anomaly_compare)

    p_review = sub.add_parser("review-nl2sql", help="manual review/update for nl2sql_audit")
    p_review.add_argument("--audit-id", default="", help="audit_id uuid")
    p_review.add_argument("--query-id", default="", help="query_id uuid")
    p_review.add_argument("--audit-status", default="", choices=["approved", "needs_fix", "rejected"], help="audit_status")
    p_review.add_argument("--audited-sql", default=None, help="audited_sql; use empty string to clear")
    p_review.add_argument("--error-types-json", default=None, help="error_types_json; use empty string to clear")
    p_review.add_argument("--notes", default=None, help="notes; use empty string to clear")
    p_review.set_defaults(func=_cmd_review_nl2sql)

    p_review_exp = sub.add_parser("review-explain", help="manual review/update for result_explain_audit")
    p_review_exp.add_argument("--explain-id", default="", help="explain_id uuid")
    p_review_exp.add_argument("--query-id", default="", help="query_id uuid")
    p_review_exp.add_argument("--judgement", default="", choices=["correct", "incorrect", "unsupported"], help="judgement")
    p_review_exp.add_argument("--issues-json", default=None, help="issues_json; use empty string to clear")
    p_review_exp.set_defaults(func=_cmd_review_explain)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return int(ns.func(ns))
