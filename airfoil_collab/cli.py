from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collab import bootstrap_db, run_once
from .config import load_app_config
from .eval import run_eval


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

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return int(ns.func(ns))


def _cmd_eval(args: argparse.Namespace) -> int:
    cfg = load_app_config()
    summary = run_eval(cfg, Path(args.cases))
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0 if summary.get("failed") == 0 else 2
