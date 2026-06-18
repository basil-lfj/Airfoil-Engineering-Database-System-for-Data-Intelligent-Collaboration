# 面向数据智能协同的翼型工程数据库系统 (AEDS)

**Airfoil Engineering Database System for Data-Intelligent Collaboration**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-lightgrey.svg)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5.0-orange.svg)](https://echarts.apache.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 项目总览

本项目以翼型工程数据为对象，设计并实现一个**以数据库为核心的完整数据工程系统**。系统覆盖**数据获取 → 清洗 → 存储 → 智能查询 → 可视化分析**全链路，包含以下 4 个核心模块：

| 模块 | 说明 |
|:-----|:------|
| `airfoil_collab/` | **AI 智能查询引擎** — CLI 工具，基于 DeepSeek 大模型，NL2SQL + 多重审计 + 结果解释 |
| `Webfront/` | **Django Web 前端** — 数据浏览、查询对比、实时可视化、审计工作流 |
| `scripts/` | **数据管线** — NACA/UIUC 数据抓取、翼型生成、异常注入、可视化生成、数据库迁移 |
| `project_data/` | **数据仓库** — 原始 UIUC 翼型 `.dat` 文件 + 经管线处理的 CSV 数据集 |

**系统核心是数据库设计** — 从概念建模、逻辑设计到物理优化（覆盖索引 + pg_trgm + 物化视图），覆盖数据库工程完整生命周期。

---

## 🏛️ 数据库设计（核心章节）

### 一、概念模型 — ER 图

7 个核心实体 + 3 个审计辅助实体：

```
┌─────────────┐       ┌──────────────────┐
│  DataSource  │       │   UserAccount    │
│  (数据来源)   │       │   (用户账户)      │
└──────┬───────┘       └────────┬─────────┘
       │                        │
       ▼                        ▼
┌──────────────────────────────────────────┐
│               Airfoil                    │
│  airfoil_id (PK) · airfoil_code (UQ)    │
│  name · category · family · source (FK) │
│  is_generated · is_deleted · created_at │
└──────────────┬───────────────────────────┘
               │ 1:N
               ▼
┌──────────────────────────────────────────┐
│           AirfoilVersion                 │
│  version_id (PK) · airfoil_id (FK)      │
│  version_no · version_type · status     │
│  is_current · created_by (FK) · is_deleted│
└──────┬──────────────────────────┬────────┘
       │ 1:N                      │ 1:N
       ▼                          ▼
┌─────────────────┐   ┌──────────────────────┐
│ CoordinatePoint  │   │  PerformanceRecord   │
│  point_id (PK)   │   │  record_id (PK)      │
│  surface(upper/  │   │  condition_id (FK)   │
│         lower)   │   │  cl · cd · l_over_d  │
│  point_order·x·y │   │  source_type         │
│  is_deleted      │   │  is_anomaly·is_deleted│
└──────────────────┘   └──────┬───────────────┘
                               │ N:1
                               ▼
                     ┌────────────────────┐
                     │ ExperimentCondition │
                     │  (alpha_deg,        │
                     │   reynolds_number)  │
                     └────────────────────┘

┌───────────────────┐   ┌────────────────────┐
│   AnomalyRule     │   │   AnomalyRecord    │
│  rule_id (PK)     │──1:N│  anomaly_id (PK)  │
│  rule_code (UQ)   │   │  version_id (FK)   │
│  description      │   │  record_id (FK)    │
│  severity         │   │  rule_id (FK)      │
│  is_enabled       │   │  status · details  │
└───────────────────┘   └────────────────────┘

审计辅助实体：QueryLog ──1:1── NL2SQLAudit
                                ──1:1── ResultExplainAudit
```

### 二、逻辑设计 — 7 张核心表

| 表名 | 行数 | 主键 | 关键外键 | 说明 |
|:-----|:-----|:-----|:---------|:-----|
| `airfoil` | 100 | `airfoil_id` (UUID) | `source → DataSource` | 翼型主表，唯一编码 `airfoil_code` |
| `airfoil_version` | 500 | `version_id` (UUID) | `airfoil_id → Airfoil` | 每翼型平均 5 个版本，`is_current` 标记当前版 |
| `coordinate_point` | 50,045 | `point_id` (UUID) | `version_id → AirfoilVersion` | 轮廓坐标点，`surface` 区分上下表面 |
| `performance_record` | 22,907 | `record_id` (UUID) | `version_id + condition_id` | 气动性能：Cl、Cd、L/D |
| `experiment_condition` | — | `condition_id` (UUID) | — | 工况组合：攻角 α + 雷诺数 Re |
| `anomaly_record` | 206 | `anomaly_id` (UUID) | `version_id + record_id + rule_id` | 异常检测结果 |
| `anomaly_rule` | — | `rule_id` (UUID) | — | 规则定义：`rule_code` 唯一 |

**版本控制机制**：`airfoil_version.is_current` + `is_deleted` 软删除，部分索引 `WHERE is_current = true AND is_deleted = false` 加速过滤 80% 的历史版本数据。

### 三、物理设计 — 数据类型策略

| 类型 | 用途 | 设计理由 |
|:-----|:------|:---------|
| `UUID` | 全部主键与外键 | 避免自增 ID 暴露数据量，便于分布式合并 |
| `TEXT` | 编码、名称、描述 | 数据来源多样，不预先截断 |
| `DECIMAL`（无精度限制） | Cl、Cd、x、y | 气动参数精度随场景变化，不预截断 |
| `BOOLEAN` | `is_deleted`, `is_current`, `is_anomaly` | 状态标记 |
| `JSON/TEXT` | 审计结果存储 | 灵活存储结构化审计信息 |

### 四、四层性能优化体系

#### 第 1 层：覆盖索引

```sql
-- 覆盖 cl, cd, l_over_d，消除回表查询 22,907 行
CREATE INDEX CONCURRENTLY idx_performance_record_active
  ON performance_record(version_id, is_deleted)
  INCLUDE (cl, cd, l_over_d);

-- 部分索引：仅索引当前有效版本，过滤 80% 历史数据
CREATE INDEX CONCURRENTLY idx_airfoil_version_current_active
  ON airfoil_version(airfoil_id, version_id)
  WHERE is_current = true AND is_deleted = false;
```

#### 第 2 层：pg_trgm GIN 模糊搜索

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_airfoil_code_trgm
  ON airfoil USING gin (airfoil_code gin_trgm_ops);
CREATE INDEX CONCURRENTLY idx_airfoil_name_trgm
  ON airfoil USING gin (name gin_trgm_ops);
```

效果：`ILIKE '%query%'` 从顺序扫描 O(n) → GIN 索引扫描 O(log n)，性能提升 ~100x。

#### 第 3 层：物化视图 + 三层缓存兜底

```sql
CREATE MATERIALIZED VIEW mv_airfoil_stats AS
SELECT
  (SELECT count(*) FROM airfoil WHERE is_deleted = false),
  (SELECT count(*) FROM airfoil_version WHERE is_deleted = false),
  (SELECT count(*) FROM coordinate_point WHERE is_deleted = false),
  (SELECT count(*) FROM performance_record WHERE is_deleted = false),
  (SELECT count(*) FROM anomaly_record WHERE status = 'open');
```

应用层三层策略：**内存缓存 (60s) → 物化视图 (1次查询) → ProgrammingError 回退 (5次COUNT)**

#### 第 4 层：连接池 + 超时控制

```python
CONN_MAX_AGE = 300         # 连接复用 5 分钟
LocMemCache TTL = 60       # 首页缓存 60 秒
STATEMENT_TIMEOUT_MS       # 环境变量控制（默认 3000ms）
```

### 五、优化效果

| 指标 | 优化前 | 优化后 | 提升 |
|:-----|:-------|:-------|:-----|
| 首页统计查询 | 5 次独立 COUNT | 1 次物化视图 | **5x** |
| performance_record 扫描 | 全表扫描 22,907 行 | 索引覆盖扫描 | **消除回表** |
| 模糊搜索 | 顺序扫描 O(n) | GIN 索引 O(log n) | **~100x** |
| 数据库连接数/首页刷新 | 7 次新建连接 | 复用已有连接 | **减少 80%** |
| 首页加载缓存 | 无 | 60s 内存缓存 | **重复请求 0ms** |

---

## 🤖 NL2SQL 智能查询引擎 — `airfoil_collab/`

一个独立的 Python CLI 模块，通过 DeepSeek 大模型将自然语言转为 SQL，自动执行并解读结果。

### 模块架构

```
airfoil_collab/
├── cli.py            # CLI 入口（bootstrap/run/eval/explain-eval/psql）
├── collab.py         # 核心编排：SQL 生成 → 审计 → 执行 → 解读
├── audit.py          # SQL 审计引擎（禁止 DDL/DML，检测敏感表、跨 schema）
├── deepseek.py       # DeepSeek API 调用（含 JSON 提取、重试）
├── schema_prompt.py  # 数据库 Schema 提示构建（strong/weak 模式）
├── psql.py           # PostgreSQL 查询执行器（CSV 导出，超时控制）
├── config.py         # 配置加载（.env / pg_service.conf）
├── eval.py           # NL2SQL 质量评估
├── anomaly_compare.py# 异常对比分析
├── envparse.py       # .env 文件解析
└── pgservice.py      # pg_service.conf 解析
```

### 工作流程

```
用户自然语言 → DeepSeek 生成 SQL → 静态审计(禁止DDL/DML)
    → 通过 ✓ → 执行 SQL → DeepSeek 解读结果 → 输出
    → 拒绝 ✗ → 返回错误类型 + 建议修正
```

### 安全审计规则

- 禁止：`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` 等
- 禁止访问系统 schema（`pg_catalog`, `information_schema`）
- 敏感表保护（`user_account`）
- 三种审计状态：`approved` / `needs_fix` / `rejected`
- 支持 `strong`（精确模式）和 `weak`（宽松模式）两种 Schema 提示

### 可用命令

```bash
# 初始化数据库
python -m airfoil_collab bootstrap

# 单次 NL2SQL 查询
python -m airfoil_collab run --question "查询 NACA_2412 的当前有效版本"

# 批量评估
python -m airfoil_collab eval --cases test_cases.json

# 结果解读审计评估
python -m airfoil_collab explain-eval --cases explain_cases.json
```

---

## 🌐 Web 前端 — `Webfront/`

Django 6.0.5 构建的数据管理与可视化平台。

### 页面路由

| 路由 | 模板 | 功能 |
|:-----|:------|:------|
| `/` | `index.html` | 系统总览仪表盘（ECharts 排行 + 异常统计） |
| `/airfoils/` | `airfoil_list.html` | 翼型列表 + CSV 导出 |
| `/airfoils/<code>/` | `airfoil_detail.html` | 翼型详情（几何/版本/性能） |
| `/search/` | `search.html` | 按名称/工况 Tab 切换搜索 |
| `/compare/` | `compare.html` | 多翼型性能对比 + ECharts + CSV 导出 |
| `/visualize/` | `visualize.html` | 6 张 ECharts 实时图表 + 数据筛选器 |
| `/anomalies/` | `anomaly_list.html` | 异常数据列表 + CSV 导出 |
| `/nl2sql/` | `nl2sql.html` | NL2SQL 前端界面 + 历史记录 + CSV 导出 |
| `/nl2sql/audits/` | `nl2sql_audit_list.html` | SQL 审计列表 |
| `/nl2sql/explain-audits/` | `explain_audit_list.html` | 解释审计列表 |

### UI 设计系统

- **品牌色**: 深海军蓝 `#0f1d32` + Warm Amber `#d97706`
- **背景/卡片**: 冷灰白 `#eef2f6` / 纯白 `#ffffff`
- **字体**: Inter（正文）+ JetBrains Mono（代码）
- **布局**: 1680px widescreen 容器，56px 粘性导航栏
- **响应式**: 480px / 768px / 1280px 三档断点
- **动效**: fade-up 进入动画，卡片 hover 抬升阴影

### ECharts 可视化

7 张实时图表（AJAX 数据加载），全部支持 `dataZoom` 缩放 + 导出 PNG：

| 图表 | 位置 |
|:-----|:------|
| 翼型性能排行（柱状图） | 总览 / 可视化 |
| 异常规则统计（饼图） | 总览 / 可视化 |
| 翼型轮廓对比 | 可视化 |
| Cl-α 曲线（折线图） | 可视化 |
| Cd/L-D 曲线（折线图） | 可视化 |
| 多翼型性能对比（折线图） | 可视化 |
| 数据规模总览（饼图） | 可视化 |

### 架构设计

- **DAO 层**: `services/dao/` 按月业务拆分（statistics / airfoil / anomaly）
- **Service 层**: `airfoil_service.py` 作为 Facade，向后兼容
- **View 层**: 页面 View + 6 个可视化 JSON API

---

## 🧪 数据处理管线 — `scripts/`

从数据抓取到可视化生成的完整 ETL 管线：

### 数据获取
```bash
scripts/fetch_naca_airfoils.py   # 从 NACA 官方数据源抓取翼型数据
project_data/scripts/download_uiuc.py  # 从 UIUC 仓库下载翼型坐标
```

### 数据处理
```bash
scripts/generate_polar.py         # 生成极曲线性能数据
scripts/generate_variants.py      # 生成翼型变体
scripts/interpolate_airfoils.py   # 翼型插值生成
scripts/inject_anomalies.py       # 注入异常数据用于测试检测规则
scripts/cleanup_foils.py          # 数据清理与去重
scripts/validate_data.py          # 数据完整性验证
scripts/data_visualization.py     # 生成 Matplotlib 静态分析图（6 张）
```

### 性能迁移
```bash
scripts/migration/run_migration.py     # 执行性能优化迁移（索引+物化视图）
scripts/migration/verify_migration.py  # 验证迁移结果
```

### 数据分析

```bash
analyze_data.py      # NACA 翼型数据分析报告（厚度分布、弯度分类、性能统计）
_generate_data.py    # 根级别数据生成器，产出 CSV 数据集至 project_data/output/
```

---

## 📁 项目结构

```
AEDS/
│
├── airfoil_collab/              # [AI 智能查询引擎] NLP → SQL → 审计 → 执行 → 解读
│   ├── cli.py                   # CLI 入口（4 子命令）
│   ├── collab.py                # 核心编排逻辑
│   ├── audit.py                 # SQL 安全审计引擎
│   ├── deepseek.py              # DeepSeek API 调用
│   ├── schema_prompt.py         # Schema 提示构建
│   ├── psql.py                  # PostgreSQL 查询执行器
│   ├── config.py                # 配置加载（.env / pg_service）
│   ├── eval.py                  # NL2SQL 质量评估
│   └── __main__.py              # python -m airfoil_collab 入口
│
├── Webfront/                    # [Django Web 前端]
│   ├── config/settings.py       # Django 配置（CONN_MAX_AGE=300, LocMemCache）
│   ├── webfront/
│   │   ├── services/dao/        # DAO 层（statistics / airfoil / anomaly）
│   │   ├── views.py             # 页面 View + 6 可视化 JSON API
│   │   ├── models.py            # 13 个 Django Model（managed=False）
│   │   └── urls.py              # 全部路由注册
│   ├── templates/webfront/      # 11 个 HTML 模板
│   └── static/visualization/    # 静态可视化图片
│
├── scripts/                     # [数据处理管线]
│   ├── migration/               # 数据库迁移（DDL 脚本 + 自动执行工具）
│   ├── fetch_naca_airfoils.py   # NACA 数据抓取
│   ├── generate_polar.py        # 极曲线生成
│   ├── generate_variants.py     # 翼型变体生成
│   ├── inject_anomalies.py      # 异常数据注入
│   ├── data_visualization.py    # Matplotlib 静态图表
│   ├── cleanup_foils.py         # 数据清理
│   ├── validate_data.py         # 数据验证
│   ├── interpolate_airfoils.py  # 翼型插值
│   └── _download/               # 原始下载数据缓存
│
├── project_data/                # [数据仓库]
│   ├── output/                  # 管线生成的 CSV 数据集
│   ├── raw_uiuc/                # UIUC 原始 .dat 翼型数据（160+ 个翼型）
│   └── scripts/                 # 数据下载工具
│
├── document/                    # [文档]
│   ├── Webfront架构分析与改进方案.md
│   ├── Webfront前端升级更新日志.md
│   ├── 项目2-面向数据智能协同的翼型工程数据库系统设计与实现.pdf
│   └── plans/
│
├── source-data/NACAdata/        # NACA 原始数据（foil 坐标 + polar 性能）
│
├── _generate_data.py            # 根级数据生成器
├── analyze_data.py              # 翼型数据分析报告
└── README.md
```

---

## 🚀 安装部署指南

### 环境要求
- Python 3.11+ · PostgreSQL 15+ · Conda（推荐）

### 快速安装

```bash
# 1. 创建环境
conda create -n web-front python=3.11 && conda activate web-front

# 2. 安装依赖
cd Webfront && pip install django psycopg2-binary pandas numpy matplotlib

# 3. 创建数据库
psql -U postgres -c "CREATE DATABASE airfoil_db;"

# 4. 配置 settings.py 中的数据库密码，初始化
python manage.py migrate

# 5. 执行数据库性能优化迁移
cd ../scripts/migration && python run_migration.py
# 创建：pg_trgm 扩展 · 5 个覆盖索引 · 1 个物化视图

# 6.（可选）设置查询超时
$env:STATEMENT_TIMEOUT_MS = '5000'

# 7. 导入数据
cd ../scripts
python fetch_naca_airfoils.py   # 导入 NACA 翼型
python generate_polar.py        # 生成性能数据
python inject_anomalies.py      # 注入异常测试数据

# 8.（可选）生成可视化图片
python data_visualization.py

# 9. 启动 Web 服务器
cd ../Webfront && python manage.py runserver
# 访问 http://127.0.0.1:8000/

# 10.（可选）使用 NL2SQL CLI
cd .. && python -m airfoil_collab run --question "查询 NACA_2412 的当前有效版本"
```

---

## � 数据规模

| 指标 | 数量 |
|:-----|:-----|
| NACA 翼型型号 | 100+ |
| UIUC 翼型数据 | 160+ |
| 总数据版本 | 500 |
| 几何坐标点 | 50,045 |
| 性能记录 | 22,907 |
| 异常标记 | 206 |
| Web 页面 | 11 个模板 |
| 可视化图表 | 7 张 ECharts + 6 张 Matplotlib |

---

## 🧠 AI 集成能力

| 能力 | 说明 |
|:-----|:------|
| **NL2SQL** | 自然语言 → SQL 自动生成 |
| **SQL 安全审计** | 静态规则检测 DDL/DML/敏感操作 |
| **结果智能解读** | AI 分析查询结果并给出解释 |
| **审计工作流** | NL2SQL 审计 + 结果解释审计双通道 |
| **质量评估** | 批量评估 NL2SQL 准确率 |

---

## 👥 团队协作

- **数据库设计**: ER 建模、物理设计、性能优化
- **数据工程**: 数据抓取、清洗、生成管线
- **后端开发**: Django、DAO 层、可视化 API
- **前端开发**: Web 模板、ECharts 可视化、响应式 UI
- **AI 集成**: DeepSeek 大模型、NL2SQL 审计、Schema Prompt

---

**注**: 本项目为数据库课程大作业，覆盖数据库设计、数据管理、Web 应用开发及 AI 集成的完整工程实践。
