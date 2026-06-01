from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import PostgresConfig


class PsqlError(RuntimeError):
    pass


@dataclass(frozen=True)
class PsqlResult:
    returncode: int
    stdout: str
    stderr: str


def run_psql(
    pg: PostgresConfig,
    sql: str,
    *,
    csv: bool = False,
    tuples_only: bool = False,
    no_align: bool = False,
    quiet: bool = True,
    timeout_s: float | None = None,
) -> PsqlResult:
    env = os.environ.copy()
    if pg.password:
        env["PGPASSWORD"] = pg.password

    args: list[str] = [
        "psql",
        "-h",
        pg.host,
        "-p",
        str(pg.port),
        "-U",
        pg.user,
        "-d",
        pg.dbname,
        "-v",
        "ON_ERROR_STOP=1",
        "-X",
    ]
    if quiet:
        args.append("-q")
    if csv:
        args.append("--csv")
    if tuples_only:
        args.append("-t")
    if no_align:
        args.append("-A")

    args.extend(["-c", sql])

    try:
        proc = subprocess.run(
            args,
            input="",
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout_s,
            cwd=str(Path.cwd()),
        )
    except subprocess.TimeoutExpired as e:
        raise PsqlError(f"psql timeout after {timeout_s}s") from e

    res = PsqlResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    if res.returncode != 0:
        raise PsqlError(res.stderr.strip() or "psql failed")
    return res


def run_psql_file(
    pg: PostgresConfig,
    sql_file: Path,
    *,
    quiet: bool = False,
    timeout_s: float | None = None,
) -> PsqlResult:
    env = os.environ.copy()
    if pg.password:
        env["PGPASSWORD"] = pg.password

    args: list[str] = [
        "psql",
        "-h",
        pg.host,
        "-p",
        str(pg.port),
        "-U",
        pg.user,
        "-d",
        pg.dbname,
        "-v",
        "ON_ERROR_STOP=1",
        "-X",
    ]
    if quiet:
        args.append("-q")
    args.extend(
        [
            "-f",
            str(sql_file),
        ]
    )

    try:
        proc = subprocess.run(
            args,
            input="",
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout_s,
            cwd=str(Path.cwd()),
        )
    except subprocess.TimeoutExpired as e:
        raise PsqlError(f"psql timeout after {timeout_s}s") from e

    res = PsqlResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    if res.returncode != 0:
        raise PsqlError(res.stderr.strip() or "psql failed")
    return res


def export_select_to_csv(
    pg: PostgresConfig,
    select_sql: str,
    *,
    statement_timeout_ms: int = 3000,
    timeout_s: float | None = None,
) -> str:
    s = select_sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()

    script = "\n".join(
        [
            r"\set ON_ERROR_STOP on",
            r"\pset footer off",
            f"SET statement_timeout = '{int(statement_timeout_ms)}ms';",
            rf"\copy ({s}) TO STDOUT WITH CSV HEADER",
        ]
    )

    with NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(script)
        temp_path = Path(f.name)

    try:
        res = run_psql_file(pg, temp_path, quiet=True, timeout_s=timeout_s)
        return res.stdout
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
