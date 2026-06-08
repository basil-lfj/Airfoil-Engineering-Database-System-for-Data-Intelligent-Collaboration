"""
NL2SQL 协同服务：封装 airfoil_collab 调用，供 Django View 使用
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# ── 延迟加载 airfoil_collab（避免启动时解析环境失败） ──
_collab = None
_cfg = None


def _ensure_loaded():
    global _collab, _cfg
    if _collab is not None and _cfg is not None:
        return

    try:
        from airfoil_collab import collab
        from airfoil_collab.config import load_app_config

        _collab = collab

        # 显式传递 project_root，确保 load_app_config 正确解析 .env 和 pg_service.conf
        _cfg = load_app_config(project_root=settings.AEDS_ROOT)
        logger.info("airfoil_collab 加载成功，AEDS_ROOT=%s", settings.AEDS_ROOT)
    except Exception as e:
        logger.error("airfoil_collab 加载失败: %s", e)
        _collab = None
        _cfg = None
        raise


def nl2sql_query(
    question: str,
    schema_mode: str = "strong",
    username: str = "web_user",
    do_explain: bool = True,
) -> dict[str, Any]:
    """执行一次 NL2SQL 完整闭环，返回前端可用的字典。"""
    _ensure_loaded()
    out = _collab.run_once(
        _cfg,
        question=question,
        schema_mode=schema_mode,
        username=username,
        do_explain=do_explain,
    )

    # 解析 CSV 为列表字典，方便前端渲染
    rows: list[dict[str, str]] = []
    columns: list[str] = []
    if out.result_csv:
        reader = csv.DictReader(io.StringIO(out.result_csv))
        columns = reader.fieldnames or []
        for i, row in enumerate(reader):
            if i >= 200:  # 防止超大结果集
                break
            rows.append(row)

    return {
        "query_id": out.query_id,
        "audit_status": out.audit.audit_status,
        "error_types": out.audit.error_types,
        "notes": out.audit.notes,
        "executed_sql": out.executed_sql,
        "generated_sql": out.executed_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "result_csv": out.result_csv,
        "explanation_text": out.explanation_text,
    }