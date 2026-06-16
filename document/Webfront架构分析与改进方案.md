# Webfront 项目架构分析与改进方案

> 分析日期：2026-06-08  
> 分析范围：AEDS/Webfront 全模块  
> 分析目标：架构问题识别 + 优先级排序 + 可落地方案

---

## 一、项目技术架构总览

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                   Webfront (Django 6.0.5)                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Config Layer (config/)                             │ │
│  │  settings.py / urls.py / wsgi.py / asgi.py         │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼──────────────────────────────┐ │
│  │  View Layer (webfront/views.py)                     │ │
│  │  10 个页面 View + 1 个 API View + 4 个审计 View     │ │
│  └──────┬────────────────────┬──────────────────┬──────┘ │
│         │                    │                  │        │
│  ┌──────▼──────┐  ┌─────────▼────────┐  ┌─────▼──────┐  │
│  │ Service     │  │  Templates       │  │ Models     │  │
│  │ airfoil_svc │  │  base.html +     │  │ 13 个 DB   │  │
│  │ collab_svc  │  │  10 个页面模板   │  │ 映射模型   │  │
│  └─────────────┘  └──────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              airfoil_collab (外部 Python 模块)           │
│  collab.py / audit.py / psql.py / deepseek.py           │
│  schema_prompt.py / eval.py / cli.py                    │
└─────────────────────────────────────────────────────────┘
```

### 1.2 页面路由与职责

| 路由 | View 函数 | 模板 | 职责 |
|:-----|:----------|:-----|:-----|
| `/` | `index` | `index.html` | 系统总览仪表盘 |
| `/airfoils/` | `airfoil_list` | `airfoil_list.html` | 翼型列表 |
| `/airfoils/<code>/` | `airfoil_detail` | `airfoil_detail.html` | 翼型详情 |
| `/search/` | `search_airfoils` | `search.html` | 工况条件查询 |
| `/compare/` | `compare_airfoils` | `compare.html` | 翼型性能对比 |
| `/anomalies/` | `anomaly_list` | `anomaly_list.html` | 异常数据列表 |
| `/visualize/` | `visualize` | `visualize.html` | 静态图片可视化 |
| `/nl2sql/` | `nl2sql` | `nl2sql.html` | NL2SQL 智能查询 |
| `/nl2sql/api/` | `nl2sql_api` | - | NL2SQL AJAX API |
| `/nl2sql/audits/` | `nl2sql_audit_list` | `nl2sql_audit_list.html` | SQL 审计列表 |
| `/nl2sql/audits/<id>/` | `nl2sql_audit_detail` | `nl2sql_audit_detail.html` | SQL 审计详情 |
| `/nl2sql/explain-audits/` | `explain_audit_list` | `explain_audit_list.html` | 解释审计列表 |
| `/nl2sql/explain-audits/<id>/` | `explain_audit_detail` | `explain_audit_detail.html` | 解释审计详情 |

### 1.3 数据流模式

```
用户请求 → URL 路由 → View 函数 → Service 层(原始 SQL) → PostgreSQL
                                              ↓
                                       Django Template ← 返回渲染
```

---

## 二、问题排查与改进方案

### 🔴 高优先级（P0）

#### P0-1：Service 层原始 SQL 耦合，无 ORM 抽象

**问题描述：**  
`airfoil_service.py` 全部使用 `connection.cursor()` + 手写 SQL，与数据库高度耦合。加字段/改表结构时需逐条修改 SQL 语句，维护成本极高。

**示例代码：**
```python
# airfoil_service.py 全部使用 raw SQL
cursor.execute("SELECT count(*) FROM airfoil WHERE is_deleted = false")
```

**影响范围：** 全部 7 个页面 View 的后端查询。

**改进方案：**  
**方案 A**（推荐，3 天工作量）：引入原生 `Model.objects` 查询，对有复杂业务的视图函数保留原始 SQL 但抽取为独立 DAO 函数。

**实施步骤：**
1. 新增 `webfront/services/dao/` 包，将 `airfoil_service.py` 按业务拆分为 `statistics_dao.py`、`airfoil_dao.py`、`anomaly_dao.py`
2. 对简单 COUNT 查询改用 `Model.objects.filter(is_deleted=False).count()`  
3. 对复杂 JOIN 查询抽取为命名 DAO 方法并添加文档注释
4. 完成后运行全部页面回归测试

**技术依赖：** 无  
**验收标准：** 所有页面功能不变，Service 层代码量减少 40%，DAO 方法覆盖度 100%

---

#### P0-2：可视化模块完全静态化，数据无法实时更新

**问题描述：**  
`visualize.html` 直接引用预生成的 PNG 静态图片（`01_foil_profiles.png` 等 6 张），页面内容与数据库状态完全脱节。新数据导入后需手动运行 `scripts/data_visualization.py` 重新生成。

**影响范围：** 可视化页面无法反映最新数据状态。

**改进方案：**  
采用 **ECharts + AJAX** 替代静态图片，服务端按需生成数据 JSON。

**实施步骤：**
1. 在 `views.py` 新增 6 个 JSON API View（`/visualize/api/foil-profiles/` 等）
2. 每个 API 调用对应的 DAO 方法，返回 ECharts 兼容的 JSON
3. 在 `visualize.html` 引入 ECharts CDN，删除静态 `<img>` 标签
4. 替换为 ECharts 初始化脚本，调用 API 获取数据并渲染

**技术依赖：** `pip install pyecharts`（或直接使用 ECharts JS）  
**验收标准：**
- 页面打开时自动加载最新数据
- 新增数据后刷新页面即更新图表
- 所有 6 张图表可交互（缩放/悬停/筛选）
- 响应式适配移动端

---

#### P0-3：数据对比与可视化模块完全脱节

**问题描述：**  
`compare.html`（翼型性能对比）和 `visualize.html`（可视化分析）是两个独立页面。用户在对比页面筛选翼型后，无法一键跳转到可视化页面查看该翼型的详细图表。

**影响范围：** 跨页面数据流转断裂，用户体验割裂。

**改进方案：**  
在对比页面新增「发送到可视化」功能，携带筛选参数跳转。

**实施步骤：**
1. 在 `compare.html` 每个翼型行末添加「查看可视化」按钮
2. 按钮链接格式：`/visualize/?codes=NACA_2412,NACA_0012&re=300000`
3. 在 `visualize.py` 的 View 中解析 `codes` 和 `re` 参数
4. 可视化页面加载时根据 URL 参数自动筛选并高亮对应数据
5. 在可视化页面顶部添加「数据筛选器」卡片，与对比功能共享参数

**技术依赖：** 需配合 P0-2 的动态图表方案  
**验收标准：**
- 对比页面点击翼型可跳转到可视化页面并自动筛选
- 可视化页面顶部显示当前筛选条件
- 筛选条件变更时图表实时刷新

---

### 🟡 中优先级（P1）

#### P1-1：NL2SQL 审计流程未与前端用户界面集成

**问题描述：**  
目前已实现 `nl2sql_audit_list`、`nl2sql_audit_detail` 等审计页面，但它们**仅暴露在 URL 路由层**，在导航栏、NL2SQL 页面、系统总览中均无任何入口链接。普通用户完全不知道审计功能的存在。

**影响范围：** NL2SQL 审计功能形同虚设。

**改进方案：**  
在 NL2SQL 页面和导航栏增加审计入口。

**实施步骤：**
1. 在 `nl2sql.html` 结果区域的审计状态横幅中，增加「查看审计详情」链接
2. 在导航栏「智能查询 ✦」下拉或二级菜单中增加「审计列表」
3. 在 `nl2sql_audit_list.html` 顶部增加返回 NL2SQL 的链接
4. 审计详情页面增加「重新审核」确认弹窗

**技术依赖：** 无  
**验收标准：**
- NL2SQL 执行结果后可直接点击查看审计详情
- 导航栏有审计入口
- 审计列表/详情页面 UI 风格与主站一致

---

#### P1-2：页面 UI 风格不一致——双模式审计页面风格突兀

**问题描述：**  
`nl2sql_audit_detail.html` 和 `explain_audit_detail.html` 页面包含表单输入、POST 提交、编辑能力，但 UI 风格与 `base.html` 的设计系统不一致（无统一卡片、按钮风格混用）。

**影响范围：** 管理审计页面用户体验差。

**改进方案：**  
统一应用 `base.html` 中的设计 Token。

**实施步骤：**
1. 检查 `nl2sql_audit_detail.html` 和 `explain_audit_detail.html` 的内联样式
2. 移除所有不兼容的内联样式，替换为 `base.html` 中的 CSS 类（`.card`、`.btn`、`.tag`、`.alert`）
3. 表单控件统一使用 `.search-row input` 样式
4. 添加表单验证的前端提示

**技术依赖：** 无  
**验收标准：** 审计页面视觉风格与其他页面完全一致。

---

#### P1-3：NL2SQL 功能无历史查询记录

**问题描述：**  
用户执行 NL2SQL 查询后，结果展示在页面中。关闭或刷新页面后查询记录消失。数据库中的 `query_log` 表记录了历史查询，但前端没有任何展示入口。

**影响范围：** 用户无法回溯历史查询。

**改进方案：**  
在 NL2SQL 页面增加历史记录侧边栏。

**实施步骤：**
1. 新增 `/nl2sql/history/` API（查询 `query_log` 表，返回最近 50 条记录）
2. 在 `nl2sql.html` 左侧或底部增加可折叠的历史记录面板
3. 历史记录展示：问题摘要、审计状态、时间
4. 点击历史记录自动填充问题并触发查询

**技术依赖：** 无  
**验收标准：**
- 页面刷新后历史记录仍可查看
- 点击历史记录可重新执行查询

---

#### P1-4：搜索功能交互不流畅——需手动选择搜索方式

**问题描述：**  
`search.html` 中按名称搜索和按工况搜索是互斥的（用户只能填 query 或 alpha+reynolds），但 UI 上没有明确提示，用户可能同时填写却只有一种生效。

**影响范围：** 搜索功能使用门槛高。

**改进方案：**  
增加 Tab 切换明确区分两种搜索模式。

**实施步骤：**
1. 在 `search.html` 添加 Tab 切换「按名称搜索」/「按工况搜索」
2. 切换 Tab 时显隐对应的输入字段
3. 按工况搜索增加可用雷诺数下拉选择（从 `experiment_condition` 表查询）

**技术依赖：** 无需新 API，前端 JS 控制  
**验收标准：** 两种搜索模式互斥且清晰区分，可用雷诺数以下拉形式展示。

---

### 🟢 低优先级（P2）

#### P2-1：Chart.js 图表无交互能力

**问题描述：**  
`index.html` 和 `visualize.html` 中的 `#chart-performers` 和 `#chart-anomalies` 虽然使用了 Chart.js，但仅用于展示简单排行，缺少筛选、缩放、数据导出能力。

**影响范围：** 数据探索深度不足。

**改进方案：**  
升级为 ECharts 并增加交互配置。

**实施步骤：**
1. 将 Chart.js 替换为 ECharts（统一可视化技术栈）
2. 增加 tooltip/zoom/legend 交互
3. 增加「导出为 PNG」按钮

**技术依赖：** `pip install pyecharts`  
**验收标准：** 图表可缩放、悬停显示详情、可导出图片。

---

#### P2-2：缺失数据导出功能

**问题描述：**  
所有查询结果/对比结果/异常列表均无法导出为 CSV/Excel。

**影响范围：** 用户无法将数据结果本地化保存。

**改进方案：**  
为每个数据表格页面增加导出按钮。

**实施步骤：**
1. 在 `airfoil_list.html`、`search.html`、`compare.html`、`anomaly_list.html` 的表格区域增加「导出 CSV」按钮
2. 前端 JS 实现：将表格数据转换为 CSV Blob 下载
3. 对 NL2SQL 结果也增加导出功能

**技术依赖：** 纯前端实现，无后端依赖  
**验收标准：** 所有数据表格页面均可一键导出 CSV。

---

#### P0-4：数据库查询未使用覆盖索引——`performance_record` 全表扫描

**问题描述：**  
通过 `EXPLAIN ANALYZE` 实测（当前数据量：`performance_record` 22,907 行，`coordinate_point` 50,045 行），高频查询存在以下性能问题：

| 问题 | 说明 | 实测数据 |
|:----|:-----|:---------|
| 全表扫描 | `performance_record` 每次查询都扫描全部行 | 22,907 行顺序扫描，消耗 353 buffers |
| 缺少过滤索引 | `is_deleted = false` 最为常用但无对应索引 | 每次扫描需逐行过滤 |
| 覆盖索引缺失 | 查询列分散在多个表，无法索引覆盖 | - |
| 版本过滤低效 | `airfoil_version.is_current` 过滤 400/500 行 | 大部分行不符合条件 |
| GIN 索引缺失 | `airfoil_code ILIKE '%query%'` 无法使用普通 B-tree | 搜索功能低效 |

当前查询执行时间约 **7ms**（数据量 2.3 万行），但按对数增长预估，数据量到 10 万行时可能劣化到 **30-50ms**，到 50 万行时可能 >200ms。

**影响范围：** 首页指标统计、翼型详情页、搜索功能、性能排行查询。

**改进方案：三管齐下综合方案（1.5 天）**

三个子方案完全互补，可同时执行：

| 子方案 | 解决 | 优先级 |
|:-------|:-----|:-------|
| A：覆盖索引 + pg_trgm | 消除全表扫描，加速搜索 | 必做 |
| B：物化视图 | 首页/可视化聚合查询零成本 | 推荐 |
| C：连接池 + 查询缓存 | 减少连接开销，避免重复查询 | 必做 |
| D：超时参数调优 | 复杂查询不超时，快速查询快速失败 | 推荐 |

**综合实施步骤：**

**Day 1 上午 — 索引（A）+ 物化视图（B）**

```sql
-- 步骤 1：创建扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 步骤 2：覆盖索引 + 部分索引（不锁表）
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_performance_record_active
  ON performance_record(version_id, is_deleted)
  INCLUDE (cl, cd, l_over_d);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_version_current_active
  ON airfoil_version(airfoil_id, version_id)
  WHERE is_current = true AND is_deleted = false;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_code_name
  ON airfoil(airfoil_code, name);

-- 步骤 3：模糊搜索 GIN 索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_code_trgm
  ON airfoil USING gin (airfoil_code gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_airfoil_name_trgm
  ON airfoil USING gin (name gin_trgm_ops);

-- 步骤 4：物化视图
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_airfoil_stats AS
SELECT
  (SELECT count(*) FROM airfoil WHERE is_deleted = false) AS airfoil_count,
  (SELECT count(*) FROM airfoil_version WHERE is_deleted = false) AS version_count,
  (SELECT count(*) FROM coordinate_point WHERE is_deleted = false) AS coord_count,
  (SELECT count(*) FROM performance_record WHERE is_deleted = false) AS perf_count,
  (SELECT count(*) FROM anomaly_record WHERE status = 'open') AS anomaly_count;
```

**Day 1 下午 — 连接池 + 缓存（C）+ 超时调优（D）**

修改 `settings.py`：
```python
DATABASES['default']['CONN_MAX_AGE'] = 300  # 连接复用 5 分钟
```

修改 `airfoil_service.py`，给 `get_statistics()` 增加缓存：
```python
from django.core.cache import cache
def get_statistics():
    cached = cache.get('dashboard_stats')
    if cached:
        return cached
    # ... 原有查询逻辑
    cache.set('dashboard_stats', result, 60)
    return result
```

修改 `airfoil_service.py`，让 `get_statistics()` 优先查物化视图：
```python
def get_statistics():
    cached = cache.get('dashboard_stats')
    if cached:
        return cached
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM mv_airfoil_stats")
        result = dictfetchall(cursor)[0]
    cache.set('dashboard_stats', result, 60)
    return result
```

修改 `psql.py`，从配置读取超时值：
```python
# 在 export_select_to_csv 中
timeout_ms = int(os.environ.get('STATEMENT_TIMEOUT_MS', '10000'))
```

**技术依赖：** PostgreSQL（pg_trgm 扩展）、Django cache framework  
**验收标准：**
- `get_top_performers` 查询从 7ms 降至 <2ms
- 搜索功能性能提升 10x 以上（`ILIKE` 走 GIN 索引）
- 首页加载时间降低 50% 以上
- 数据库连接数减少 80%
- `EXPLAIN ANALYZE` 确认无全表扫描
- NL2SQL 复杂查询不再因 3s 超时报错

---

> **注：P0-5 的「连接池 + 查询缓存」已整合进 P0-4 的综合方案 Day 1 下午部分，不再单独列项。以下保留原问题描述供参考。**

**问题描述：**  
首页每次刷新执行 5 次独立 COUNT 查询、1 次排行查询、1 次异常统计查询，全部串行执行且每次打开新数据库连接（Django 默认 CONN_MAX_AGE=0），对 22,907 行 `performance_record` 重复全表扫描。

**影响范围：** 首页加载速度。

**改进方案：** 已合并至 P0-4 综合方案，参见上方 Day 1 下午。

---

#### P2-3：移动端适配不完整

**问题描述：**  
`base.html` 已有 768px/480px 两档响应式适配，但部分页面（如 `compare.html` 的多翼型对比表格、`visualize.html` 的双列图片网格）在小屏下布局错乱。

**影响范围：** 移动端用户体验差。

**改进方案：**  
逐模板排查并增加响应式规则。

**实施步骤：**
1. 检查 `compare.html` 表格在小屏下的横向滚动
2. 检查 `visualize.html` 双列网格在 480px 下改为单列
3. 检查 `nl2sql.html` 的 SQL/解读双列在小屏下切换为单列
4. 统一使用 `base.html` 中已定义的 `.result-grid` 类

**技术依赖：** 无  
**验收标准：** 所有页面在 480px/768px/1280px 三种宽度下布局正常。

---

## 三、执行清单汇总

### 3.1 按优先级排序

| 优先级 | ID | 问题 | 工作量 | 依赖 | 当前状态 |
|:------|:---|:-----|:------|:-----|:--------|
| 🔴 P0 | 1 | Service 层原始 SQL 耦合 | 3 天 | 无 | 待开始 |
| 🔴 P0 | 2 | 可视化静态图片无法实时更新 | 3 天 | ECharts | 待开始 |
| 🔴 P0 | 3 | 对比与可视化模块脱节 | 1.5 天 | P0-2 | 待开始 |
| 🔴 **P0** | **4** | **数据库综合优化：覆盖索引 + 物化视图 + 连接池 + 缓存 + 超时调优** | **1.5 天** | **pg_trgm** | **待开始** |
| � P1 | 5 | 审计流程无前端入口 | 1 天 | 无 | 待开始 |
| 🟡 P1 | 6 | 审计页面 UI 风格不一致 | 0.5 天 | 无 | 待开始 |
| 🟡 P1 | 7 | NL2SQL 无历史查询记录 | 1 天 | 无 | 待开始 |
| 🟡 P1 | 8 | 搜索功能交互不流畅 | 0.5 天 | 无 | 待开始 |
| 🟢 P2 | 9 | Chart.js 无交互能力 | 1 天 | ECharts | 待开始 |
| 🟢 P2 | 10 | 缺失数据导出功能 | 0.5 天 | 无 | 待开始 |
| 🟢 P2 | 11 | 移动端适配不完整 | 1 天 | 无 | 待开始 |

### 3.2 推荐执行顺序

```
Phase 0（P0 数据库优化，Week 0 — 建议最先做）
  ├── P0-4 综合方案 Day 1 上午：索引 + 物化视图
  ├── P0-4 综合方案 Day 1 下午：连接池 + 缓存 + 超时调优
  └── 验证：`EXPLAIN ANALYZE` 全表扫描消除

Phase 1（P0 功能重构，Week 1）
  ├── P0-2 可视化实时化（核心体验升级）
  ├── P0-3 对比+可视化融合（趁 P0-2 热修复）
  └── P0-1 Service 层解耦（长期维护收益）

Phase 2（P1 体验优化，Week 2）
  ├── P1-8 搜索功能优化
  ├── P1-5 审计入口集成
  ├── P1-7 历史查询记录
  └── P1-6 审计页面 UI 统一

Phase 3（P2 进阶增强，Week 3）
  ├── P2-9 图表交互升级
  ├── P2-11 移动端适配
  └── P2-10 数据导出功能
```

### 3.3 技术债务清单

| 项目 | 影响 | 建议处理时机 |
|:----|:-----|:------------|
| `airfoil_service.py` 全部使用 raw SQL | 维护成本高，改字段风险大 | Phase 1 |
| 可视化数据与数据库脱节 | 展示信息过时 | Phase 1 |
| `performance_record` 全表扫描 | 数据量大时性能劣化 | **Phase 0** |
| 缺失 `pg_trgm` 模糊搜索索引 | 搜索功能低效 | **Phase 0** |
| 首页无查询缓存 | 重复 COUNT 查询浪费资源 | **Phase 0** |
| 审计功能无入口 | 功能浪费 | Phase 2 |
| 图表无交互能力 | 数据探索体验差 | Phase 3 |
| 未使用静态文件打包 | 生产部署需手动处理 | 上线前 |
| `collab_service.py` 的模块加载无服务端缓存 | 每次请求可能重复加载 | Phase 2 |
| 无单元测试覆盖 | 重构风险高 | 持续 |
