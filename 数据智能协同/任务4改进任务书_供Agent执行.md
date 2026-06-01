# 任务4（数据智能协同）改进任务书

> **目标读者**：AI 编程 Agent  
> **执行方式**：逐项顺序执行，每项完成后确认  
> **项目根目录**：`Airfoil-Engineering-Database-System/`  
> **Python 包路径**：`Airfoil-Engineering-Database-System/airfoil_collab/`

---

## 改进项 1（P0）：修复结果解释审计占位代码

### 问题定位
文件 `airfoil_collab/collab.py`，函数 `run_once()`，约第374行。`_insert_result_explain_audit()` 被调用时 `judgement` 被硬编码为 `"unsupported"`，`issues` 被硬编码为 `[]`。这意味着必做二"查询结果的智能解释与审计"的审计部分完全没有实现。

### 要做什么
在 `collab.py` 中新增一个 `audit_explanation()` 函数，对 LLM 返回的解释文本进行程序化审计，返回 `judgement` 和 `issues` 列表。

### 具体实现步骤

#### 步骤 1：在 `collab.py` 顶部新增函数 `audit_explanation()`

```python
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
    #    从 CSV 中提取所有浮点数/整数以及翼型编号等关键字符串
    csv_numbers: set[str] = set()
    csv_codes: set[str] = set()
    csv_columns_raw = csv_text.splitlines()[0] if csv_text else ""
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
    fabricated_codes = explained_codes - csv_codes - {code.upper() for code in re.findall(r"NACA\d{4}", question, re.IGNORECASE)}
    if fabricated_codes:
        issues.append("fabricated_missing_info")
    
    # 4. 检查解释是否引用了结果中的具体数值
    #    如果解释完全不包含 CSV 中出现的任何数值，可能未基于结果
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
        # 结果为空
        if any(kw in explanation for kw in ["发现", "表明", "显示", "可以看出", "数值为"]):
            issues.append("fabricated_missing_info")
        # 检查是否明确说"无法判断"或"无数据"
        if not any(kw in explanation for kw in ["无法判断", "无数据", "没有", "为空", "未找到"]):
            issues.append("not_grounded_in_result")
    else:
        # 有数据但解释看起来像泛化叙述
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
```

#### 步骤 2：修改 `run_once()` 中调用 `_insert_result_explain_audit()` 的位置

将原来（约第370-384行）的：
```python
    if do_explain:
        try:
            explanation_text = explain_result(cfg, question=question, sql=exec_sql, csv_text=csv_out)
            _insert_result_explain_audit(
                cfg,
                query_id=query_id,
                reviewer_id=user_id,
                snapshot_ref=str(snapshot_path),
                explanation=explanation_text,
                judgement="unsupported",
                issues=[],
            )
        except DeepSeekError:
            explanation_text = None
```

替换为：
```python
    if do_explain:
        try:
            explanation_text = explain_result(cfg, question=question, sql=exec_sql, csv_text=csv_out)
            exp_judgement, exp_issues = audit_explanation(
                explanation=explanation_text,
                csv_text=csv_out,
                question=question,
            )
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
```

### 验收标准
- `airfoil-collab run --question "..." --print-explain` 执行后，数据库中 `result_explain_audit.judgement` 不再是固定的 `"unsupported"`
- 空结果时解释如果虚构内容，`judgement` 应判为 `"incorrect"` 且 `issues_json` 含 `"fabricated_missing_info"`

---

## 改进项 2（P0）：实现 Schema 强弱提示自动对比

### 问题定位
`eval.py` 的 `run_eval()` 函数只按 `test_cases.json` 中指定的单一 `schema_mode` 执行，未做 weak/strong 对照。PDF 明确要求分析"加入 schema 提示后是否有改进"。

### 要做什么
修改 `eval.py`，对每条标记了需要对比的正例，自动用 `weak` 和 `strong` 两种模式各跑一遍，输出对比结果。

### 具体实现步骤

#### 步骤 1：修改 `run_eval()` 函数

在现有 `run_eval()` 的循环中，对每个 `kind == "positive"` 的 case，在 strong 模式执行完后，增加一次 weak 模式执行：

```python
def run_eval(cfg: AppConfig, cases_path: Path) -> dict:
    obj = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases") or []

    results: list[dict] = []  # 改为 dict 以容纳更多字段
    passed = 0

    for c in cases:
        case_id = str(c.get("id"))
        kind = str(c.get("kind") or "positive")
        schema_mode = str(c.get("schema_mode") or "strong")
        question = str(c.get("question") or "")
        expected_status = str(c.get("expected_audit_status") or "")
        gold_sql = c.get("gold_sql")
        do_compare = bool(c.get("schema_compare", kind == "positive"))

        # --- 主模式执行 ---
        out: RunOutcome = run_once(
            cfg, question=question, schema_mode=schema_mode,
            username="eval", do_explain=False,
        )
        ok, note = _check_case(out, kind, expected_status, gold_sql, cfg)

        case_result = {
            "case_id": case_id, "kind": kind,
            "schema_mode": schema_mode,
            "expected_audit_status": expected_status,
            "actual_audit_status": out.audit.audit_status,
            "passed": ok, "notes": note or out.audit.notes,
            "query_id": out.query_id,
            "generated_sql": out.generated.obj.get("sql") if out.generated else None,
            "error_types": out.audit.error_types,
        }

        # --- Weak 模式对比（仅正例） ---
        if do_compare and kind == "positive":
            out_weak: RunOutcome = run_once(
                cfg, question=question, schema_mode="weak",
                username="eval", do_explain=False,
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
            case_result["schema_improvement"] = (
                "improved" if (not ok_weak and ok) else
                "degraded" if (ok_weak and not ok) else
                "same_both_pass" if (ok_weak and ok) else
                "same_both_fail"
            )

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
```

#### 步骤 2：新增辅助函数

```python
def _check_case(
    out: RunOutcome, kind: str, expected_status: str,
    gold_sql: str | None, cfg: AppConfig,
) -> tuple[bool, str]:
    """复用原有逻辑，返回 (ok, note)"""
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


def _summarize_schema_compare(results: list[dict]) -> dict:
    """汇总 schema 对比统计"""
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


def _summarize_error_types(results: list[dict]) -> dict:
    """汇总所有用例中出现的错误类型频次"""
    from collections import Counter
    error_counter: Counter = Counter()
    for r in results:
        for et in r.get("error_types", []):
            error_counter[et] += 1
        if "weak" in r:
            for et in r["weak"].get("error_types", []):
                error_counter[f"weak_{et}"] += 1
    return dict(error_counter.most_common())
```

#### 步骤 3：更新 `test_cases.json`

给每条正例增加 `"schema_compare": true` 字段（可选，代码中已默认对 positive 做对比）：

```json
{
  "id": "P01",
  "kind": "positive",
  "schema_mode": "strong",
  "schema_compare": true,
  ...
}
```

### 验收标准
- `airfoil-collab eval` 输出 JSON 中每条正例包含 `weak` 对比结果和 `schema_improvement` 字段
- 汇总中包含 `schema_compare` 统计

---

## 改进项 3（P1）：补充结果解释测试用例

### 要做什么
新建 `数据智能协同/explain_test_cases.json`，定义 5-8 条结果解释审计用例。在 `eval.py` 中新增 `run_explain_eval()` 函数，在 `cli.py` 中新增 `explain-eval` 子命令。

### 文件：`explain_test_cases.json`

```json
{
  "version": 1,
  "cases": [
    {
      "id": "E01",
      "source_case": "P03",
      "description": "升阻比Top10结果解释——应引用具体数值",
      "question": "在 Re=3000000、攻角 α=2 条件下，列出升阻比最高的前 10 个翼型（只看当前有效版本）。",
      "schema_mode": "strong",
      "check_grounded": true,
      "check_no_fabrication": true
    },
    {
      "id": "E02",
      "source_case": "P08",
      "description": "分组统计结果解释——应引用具体计数",
      "question": "统计每个性能记录来源类型（source_type）下的记录数量与异常数量。",
      "schema_mode": "strong",
      "check_grounded": true,
      "check_no_fabrication": true
    },
    {
      "id": "E03",
      "source_case": "P09",
      "description": "异常翼型列表解释——应符合工程常识",
      "question": "列出存在异常提示的翼型（异常记录/性能异常/负 Cd 任一命中），只看当前有效版本，并按异常提示数降序。",
      "schema_mode": "strong",
      "check_engineering_sense": true,
      "check_grounded": true
    },
    {
      "id": "E04",
      "source_case": "P04",
      "description": "单翼型曲线数据解释——应描述趋势而非虚构",
      "question": "查询翼型编号为 NACA2412 在 Re=3000000 下不同攻角的 Cl、Cd 曲线点，按攻角升序。",
      "schema_mode": "strong",
      "check_grounded": true,
      "check_no_fabrication": true
    },
    {
      "id": "E05",
      "source_case": "P07",
      "description": "版本差异解释——应引用delta值",
      "question": "对比翼型编号为 NACA0012 的版本 1 与版本 2 在 Re=3000000、α=2 条件下的 Cd 差异（delta_cd）。",
      "schema_mode": "strong",
      "check_grounded": true,
      "check_no_fabrication": true
    },
    {
      "id": "E06",
      "source_case": "none",
      "description": "空结果对抗测试——不应虚构信息",
      "question": "查询翼型编号为 NACA9999 的当前有效版本信息。",
      "schema_mode": "strong",
      "check_empty_result": true,
      "check_no_fabrication": true
    },
    {
      "id": "E07",
      "source_case": "none",
      "description": "模糊问题降级测试——应说明无法判断",
      "question": "帮我找一个最好的翼型。",
      "schema_mode": "strong",
      "check_ambiguous": true
    }
  ]
}
```

### 步骤：在 `eval.py` 中新增 `run_explain_eval()`

```python
def run_explain_eval(cfg: AppConfig, cases_path: Path) -> dict:
    """对结果解释进行审计评测。"""
    import json as _json
    obj = _json.loads(cases_path.read_text(encoding="utf-8"))
    cases = obj.get("cases") or []
    results: list[dict] = []
    
    for c in cases:
        case_id = str(c.get("id"))
        question = str(c.get("question") or "")
        schema_mode = str(c.get("schema_mode") or "strong")
        
        out = run_once(
            cfg, question=question, schema_mode=schema_mode,
            username="eval", do_explain=True,
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
```

### 步骤：在 `cli.py` 中新增 `explain-eval` 子命令

```python
p_explain_eval = sub.add_parser("explain-eval", help="evaluate result explanation audit")
p_explain_eval.add_argument(
    "--cases",
    default=str(Path("数据智能协同") / "explain_test_cases.json"),
    help="path to explain test cases json",
)
p_explain_eval.set_defaults(func=_cmd_explain_eval)

# ...

def _cmd_explain_eval(args: argparse.Namespace) -> int:
    from .eval import run_explain_eval
    cfg = load_app_config()
    summary = run_explain_eval(cfg, Path(args.cases))
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0
```

### 验收标准
- `airfoil-collab explain-eval` 可执行并输出每条用例的解释审计结果
- 空结果用例（E06）的 `explanation` 不应包含虚构的具体数据

---

## 改进项 4（P1）：增强静态 SQL 审计规则

### 要做什么
在 `audit.py` 的 `audit_sql()` 函数中，在现有检查之后、`_ensure_limit()` 之前，增加两项新的静态检查规则。

### 具体修改

#### 新增函数 1：检测聚合语法误用

```python
def _check_group_by_consistency(sql: str) -> list[str]:
    """检查 GROUP BY 与 SELECT 列的一致性。
    
    简化策略：如果存在 GROUP BY，检查 SELECT 中的非聚合列是否都在 GROUP BY 中。
    """
    import re
    s = re.sub(r"\s+", " ", sql)
    
    # 检测是否有 GROUP BY
    if not re.search(r"\bGROUP\s+BY\b", s, re.IGNORECASE):
        return []
    
    # 提取 SELECT ... FROM 之间的列表达式
    select_match = re.search(r"\bSELECT\b(.+?)\bFROM\b", s, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []
    
    select_part = select_match.group(1)
    # 分割各个列表达式（简单按逗号分割，不处理嵌套函数内的逗号——简化版）
    columns = [col.strip() for col in select_part.split(",")]
    
    # 提取 GROUP BY 后的列
    group_match = re.search(r"\bGROUP\s+BY\b(.+?)(?:\bORDER\b|\bLIMIT\b|\bHAVING\b|$)", s, re.IGNORECASE | re.DOTALL)
    if not group_match:
        return []
    group_part = group_match.group(1)
    group_cols = {col.strip().lower() for col in group_part.split(",")}
    
    # 聚合函数模式
    agg_pattern = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|ARRAY_AGG|STRING_AGG|JSON_AGG|JSONB_AGG)\s*\(|\bCAST\s*\(|\bCOALESCE\s*\(|\bNULLIF\s*\(", re.IGNORECASE)
    
    issues = []
    for col in columns:
        col_clean = col.strip().lower()
        # 跳过常量、*、包含聚合函数的表达式
        if col_clean in ("*", "1", "true", "false") or col_clean.isdigit():
            continue
        if agg_pattern.search(col):
            continue
        # 提取列别名前的真实列名
        if " AS " in col.upper():
            col_clean = col.upper().split(" AS ")[0].strip().lower()
        # 简单的表.列形式匹配
        if "." in col_clean:
            col_clean = col_clean.split(".")[-1]
        if col_clean not in group_cols:
            issues.append("aggregate_misuse")
            break
    
    return issues
```

#### 新增函数 2：检测可能的连接条件遗漏

```python
def _check_missing_join_condition(sql: str) -> list[str]:
    """如果 SQL 涉及多表连接（显式 JOIN 或 FROM 多表），检查是否遗漏连接条件。
    
    简化策略：统计 FROM/JOIN 中涉及的表数量，如果 ≥2 且 WHERE/ON 中没有 `=` 连接条件，标记。
    """
    import re
    s = sql
    
    # 统计表（简化：匹配 FROM 和 JOIN 后的标识符，排除子查询）
    table_pattern = re.compile(
        r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)',
        re.IGNORECASE
    )
    tables = table_pattern.findall(s)
    # 去重
    unique_tables = set(t.lower() for t in tables)
    
    if len(unique_tables) < 2:
        return []
    
    # 检查是否有至少一个连接条件（table1.col = table2.col 模式）
    join_cond_pattern = re.compile(r'\w+\.\w+\s*=\s*\w+\.\w+')
    if not join_cond_pattern.search(s):
        return ["missing_join_condition"]
    
    return []
```

#### 步骤：在 `audit_sql()` 中集成新规则

在 `audit_sql()` 中，在版本语义检查之后、`_ensure_limit()` 之前，新增：

```python
    # 新增：聚合语法检查
    agg_issues = _check_group_by_consistency(normalized)
    if agg_issues:
        error_types = list(set(audit.audit_status_error_types + agg_issues))  # 需要重构
        # 简化处理：将 aggregate_misuse 作为 needs_fix 的附加错误类型
        ...
    
    # 新增：连接条件检查
    join_issues = _check_missing_join_condition(normalized)
    ...
```

> **注意**：由于当前 `audit_sql()` 是单路径返回的，要同时附加多个错误类型，建议重构为累积式：
> 1. 先收集所有 `error_types` 和 `notes`
> 2. 最后统一根据最严重的类型决定 `audit_status`
> 3. 优先级：`rejected` > `needs_fix` > `approved`

### 验收标准
- 提交一个 SELECT 有 GROUP BY 但 SELECT 列不在 GROUP BY 中的 SQL，审计结果应含 `aggregate_misuse`
- 提交一个 FROM 两表但无 ON/USING/WHERE 连接条件的 SQL，审计结果应含 `missing_join_condition`

---

## 改进项 5（P2）：选做三——异常检测对比实验框架

### 要做什么
新增一个 Python 模块 `airfoil_collab/anomaly_compare.py`，实现规则法 vs LLM 法的异常检测对比实验。

### 具体实现

#### 新建文件：`airfoil_collab/anomaly_compare.py`

```python
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
            cases.append(AnomalyCase(
                record_id=parts[0],
                cl=float(parts[1]),
                cd=float(parts[2]),
                alpha_deg=float(parts[3]),
                reynolds_number=float(parts[4]),
                l_over_d=float(parts[5]) if parts[5] else None,
                is_true_anomaly=parts[6].strip().lower() in ("true", "t", "1", "yes"),
            ))
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
        results.append({
            "record_id": c.record_id,
            "predicted_anomaly": predicted,
            "true_anomaly": c.is_true_anomaly,
            "method": "rule",
            "flags": flags,
        })
    return results


def llm_based_detect(
    cfg: DeepSeekConfig,
    cases: list[AnomalyCase],
    batch_size: int = 20,
) -> list[dict]:
    """大模型法异常检测。将数据以表格形式发给 LLM 判断。"""
    results: list[dict] = []
    
    for batch_start in range(0, len(cases), batch_size):
        batch = cases[batch_start:batch_start + batch_size]
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
                cfg, system_prompt=system_prompt, user_prompt=user_prompt,
                timeout_s=30, max_format_retries=2,
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
            results.append({
                "record_id": c.record_id,
                "predicted_anomaly": bool(pred.get("is_anomaly", False)),
                "true_anomaly": c.is_true_anomaly,
                "method": "llm",
                "llm_reason": str(pred.get("reason", "")),
            })
    
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
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
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
    llm_only_caught = []   # LLM发现但规则漏掉的真异常
    for c in cases:
        r = rule_map.get(c.record_id, {})
        l = llm_map.get(c.record_id, {})
        if r.get("predicted_anomaly") and not l.get("predicted_anomaly") and c.is_true_anomaly:
            rule_only_caught.append(c.record_id)
        if l.get("predicted_anomaly") and not r.get("predicted_anomaly") and c.is_true_anomaly:
            llm_only_caught.append({"record_id": c.record_id, "reason": l.get("llm_reason", "")})
    
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
```

#### 步骤：在 `cli.py` 中新增 `anomaly-compare` 子命令

```python
p_anomaly = sub.add_parser("anomaly-compare", help="rule vs llm anomaly detection comparison")
p_anomaly.add_argument("--sample-size", type=int, default=100, help="number of records to sample")
p_anomaly.set_defaults(func=_cmd_anomaly_compare)

# ...

def _cmd_anomaly_compare(args: argparse.Namespace) -> int:
    from .anomaly_compare import run_anomaly_compare
    cfg = load_app_config()
    result = run_anomaly_compare(cfg, sample_size=args.sample_size)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0
```

### 验收标准
- `airfoil-collab anomaly-compare --sample-size 50` 可执行并输出规则法 vs LLM法的 precision/recall/f1 对比
- 能识别出"规则独有发现"和"LLM独有发现"的分歧案例

---

## 附录：执行顺序建议

```
改进项 1（P0）→ 改进项 2（P0）→ 改进项 4（P1）→ 改进项 3（P1）→ 改进项 5（P2）
```

- 先做 1 和 2，因为它们是必做内容的缺陷修复
- 再做 4，因为增强审计规则会影响后续测试的审计结果
- 再做 3，它依赖改进项 1 的 `audit_explanation()` 函数
- 最后做 5，因为它是选做加分项

---

## 关键文件索引

| 文件 | 涉及改进项 |
|------|-----------|
| `airfoil_collab/collab.py` | 改进项 1 |
| `airfoil_collab/eval.py` | 改进项 2, 3 |
| `airfoil_collab/cli.py` | 改进项 3, 5 |
| `airfoil_collab/audit.py` | 改进项 4 |
| `数据智能协同/test_cases.json` | 改进项 2 |
| `数据智能协同/explain_test_cases.json` | 改进项 3（新建） |
| `airfoil_collab/anomaly_compare.py` | 改进项 5（新建） |
