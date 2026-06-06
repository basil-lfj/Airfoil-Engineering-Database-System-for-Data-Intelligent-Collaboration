from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .envparse import load_loose_env
from .pgservice import read_pg_service_conf


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str | None
    psql_path: str = "psql"


@dataclass(frozen=True)
class DeepSeekConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    timeout_s: float
    max_retries: int


@dataclass(frozen=True)
class AppConfig:
    postgres: PostgresConfig
    deepseek: DeepSeekConfig
    project_root: Path
    psql_path: str


def load_app_config(project_root: Path | None = None) -> AppConfig:
    root = project_root or Path(__file__).resolve().parents[1]

    env_path = root / ".env"
    env = load_loose_env(env_path) if env_path.exists() else {}

    pg_service_path = root / "数据库设计" / "sql" / "pg_service.conf"
    pg_service = read_pg_service_conf(pg_service_path, preferred_section="数据库大作业") if pg_service_path.exists() else {}

    host = (
        (env.get("PGHOST") or env.get("host") or env.get("HOST") or pg_service.get("host") or "localhost").strip()
    )
    port_raw = env.get("PGPORT") or env.get("port") or env.get("PORT") or pg_service.get("port") or "5432"
    try:
        port = int(str(port_raw).strip())
    except ValueError:
        port = 5432

    dbname = (env.get("PGDATABASE") or env.get("dbname") or pg_service.get("dbname") or "翼型工程").strip()
    user = (env.get("PGUSER") or env.get("user") or pg_service.get("user") or "postgres").strip()
    password = env.get("PGPASSWORD") or env.get("password") or env.get("PASSWORD")
    if password is not None:
        password = str(password).strip()

    base_url = (env.get("DEEPSEEK_BASE_URL") or env.get("BASE_URL") or "").strip()
    api_key = (env.get("DEEPSEEK_API_KEY") or env.get("API_KEY") or "").strip()
    model = (env.get("DEEPSEEK_MODEL") or "deepseek-v3.2").strip()
    psql_path = (env.get("PSQL_PATH") or "psql").strip()

    postgres = PostgresConfig(host=host, port=port, dbname=dbname, user=user, password=password or None, psql_path=psql_path)
    deepseek = DeepSeekConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=float(env.get("DEEPSEEK_TEMPERATURE") or 0),
        top_p=float(env.get("DEEPSEEK_TOP_P") or 1),
        max_tokens=int(env.get("DEEPSEEK_MAX_TOKENS") or 1024),
        timeout_s=float(env.get("DEEPSEEK_TIMEOUT_S") or 20),
        max_retries=int(env.get("DEEPSEEK_MAX_RETRIES") or 2),
    )

    return AppConfig(postgres=postgres, deepseek=deepseek, project_root=root, psql_path=psql_path)

