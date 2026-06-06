"""异常检测对比实验：规则法 vs 大模型法"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .psql import run_psql, PsqlError
from .deepseek import DeepSeekConfig, call_json_with_retries


@dataclass(frozen=True)
class AnomalyCase:
    record_id: str
    cl: float
    cd: float
    alpha_deg: float
    reynolds_number: float
    l_over_d: float | None
    is_true_anomaly: bool  # ground truth


def fetch_performance_sample(cfg: AppConfig, limit: int = 100) -> list[AnomalyCase]:
    """从数据库获取性能记录样本（包含已知异常）。"""
    sql = f"""
        SELECT record_id::text, cl, cd, alpha_deg, reynolds_number,
               l_over_d, COALESCE(is_anomaly, false) AS is_anomaly
        FROM public.performance_record
        WHERE is_deleted = false
        ORDER BY RANDOM()
        LIMIT {limit};
    """
    try:
        res = run_psql(cfg.postgres, sql, csv=True, tuples_only=True, quiet=True)
    except PsqlError:
        return []

    lines = res.stdout.strip().splitlines()
    if len(lines) < 2:
        return []

    cases: list[AnomalyCase] = []
    for line in lines[1:]:  # 跳过 header
        parts = line.split(",")
        if len(parts) < 7:
            continue
        try:
            cases.append(
                AnomalyCase(
                    record_id=parts[0],
                    cl=float(parts[1]),
                    cd=float(parts[2]),
                    alpha_deg=float(parts[3]),
                    reynolds_number=float(parts[4]),
                    l_over_d=float(parts[5]) if parts[5] else None,
                    is_true_anomaly=parts[6].strip().lower() in ("true", "t", "1", "yes"),
                )
            )
        except (ValueError, IndexError):
            continue
    return cases


def rule_based_detect(cases: list[AnomalyCase]) -> list[dict]:
    """规则法异常检测。规则：cd < 0, cl 超出合理范围, l_over_d 异常。"""
    results: list[dict] = []
    for c in cases:
        flags = []
        if c.cd < 0:
            flags.append("negative_cd")
        if abs(c.cl) > 5:
            flags.append("extreme_cl")
        if c.l_over_d is not None and c.l_over_d > 500:
            flags.append("extreme_l_over_d")
        if c.l_over_d is not None and c.l_over_d < -10:
            flags.append("negative_l_over_d")
        predicted = len(flags) > 0
        results.append(
            {
                "record_id": c.record_id,
                "predicted_anomaly": predicted,
                "true_anomaly": c.is_true_anomaly,
                "method": "rule",
                "flags": flags,
            }
        )
    return results


def llm_based_detect(
    cfg: DeepSeekConfig,
    cases: list[AnomalyCase],
    batch_size: int = 20,
) -> list[dict]:
    """大模型法异常检测。将数据以表格形式发给 LLM 判断。"""
    results: list[dict] = []

    for batch_start in range(0, len(cases), batch_size):
        batch = cases[batch_start : batch_start + batch_size]
        rows = "\n".join(
            f"{c.record_id}: α={c.alpha_deg}°, Re={c.reynolds_number:.0f}, "
            f"Cl={c.cl:.4f}, Cd={c.cd:.4f}, L/D={c.l_over_d or 'N/A'}"
            for c in batch
        )

        system_prompt = (
            "你是一个翼型气动数据分析专家。"
            "对每条记录判断是否为异常数据，基于：Cd<0 为异常、Cl 超出常见范围(±3)为可疑、"
            "升阻比异常(>300 或 <0)为可疑。"
            "输出必须是 JSON 数组，每个元素："
            '{"record_id":"...","is_anomaly":true/false,"reason":"简短理由"}'
        )
        user_prompt = f"分析以下性能记录：\n{rows}\n\n请输出 JSON 数组。"

        try:
            res = call_json_with_retries(
                cfg,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_s=30,
                max_format_retries=2,
            )
            predictions = res.obj if isinstance(res.obj, list) else []
        except Exception:
            predictions = [
                {"record_id": c.record_id, "is_anomaly": False, "reason": "llm_call_failed"}
                for c in batch
            ]

        pred_map = {p["record_id"]: p for p in predictions if isinstance(p, dict)}
        for c in batch:
            pred = pred_map.get(c.record_id, {"is_anomaly": False, "reason": "no_prediction"})
            results.append(
                {
                    "record_id": c.record_id,
                    "predicted_anomaly": bool(pred.get("is_anomaly", False)),
                    "true_anomaly": c.is_true_anomaly,
                    "method": "llm",
                    "llm_reason": str(pred.get("reason", "")),
                }
            )

    return results


def compute_metrics(results: list[dict]) -> dict:
    """计算精确率、召回率、F1。"""
    tp = sum(1 for r in results if r["predicted_anomaly"] and r["true_anomaly"])
    fp = sum(1 for r in results if r["predicted_anomaly"] and not r["true_anomaly"])
    fn = sum(1 for r in results if not r["predicted_anomaly"] and r["true_anomaly"])
    tn = sum(1 for r in results if not r["predicted_anomaly"] and not r["true_anomaly"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_anomaly_compare(cfg: AppConfig, sample_size: int = 100) -> dict:
    """执行完整的异常检测对比实验。"""
    cases = fetch_performance_sample(cfg, limit=sample_size)
    if not cases:
        return {"error": "no data fetched"}

    rule_results = rule_based_detect(cases)
    llm_results = llm_based_detect(cfg.deepseek, cases)

    rule_metrics = compute_metrics(rule_results)
    llm_metrics = compute_metrics(llm_results)

    # 找出分歧案例
    rule_map = {r["record_id"]: r for r in rule_results}
    llm_map = {r["record_id"]: r for r in llm_results}

    rule_only_caught = []  # 规则发现但LLM漏掉的真异常
    llm_only_caught = []  # LLM发现但规则漏掉的真异常
    for c in cases:
        r = rule_map.get(c.record_id, {})
        l = llm_map.get(c.record_id, {})
        if r.get("predicted_anomaly") and not l.get("predicted_anomaly") and c.is_true_anomaly:
            rule_only_caught.append(c.record_id)
        if l.get("predicted_anomaly") and not r.get("predicted_anomaly") and c.is_true_anomaly:
            llm_only_caught.append(
                {"record_id": c.record_id, "reason": l.get("llm_reason", "")}
            )

    return {
        "sample_size": len(cases),
        "true_anomaly_count": sum(1 for c in cases if c.is_true_anomaly),
        "rule_based": rule_metrics,
        "llm_based": llm_metrics,
        "rule_only_caught": rule_only_caught,
        "llm_only_caught": llm_only_caught,
        "discussion_points": [
            "大模型是否真的提高了异常识别效果：比较 F1 值",
            "规则方法更稳的场景：强物理约束（如 Cd<0）不会漏",
            "大模型有辅助价值的场景：边界模糊、非典型异常模式",
        ],
    }
