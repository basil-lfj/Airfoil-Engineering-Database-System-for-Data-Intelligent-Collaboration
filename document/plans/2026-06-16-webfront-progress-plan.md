# Webfront 架构改进 — 已完成与待办清单

> 更新日期：2026-06-16
> 基于：Webfront架构分析与改进方案.md
> 用途：分门别类标注完成状态，指导后续执行

---

## 图例

| 标记 | 含义 |
|:----|:-----|
| ✅ 已完成 | 代码已修改且验证通过 |
| 🔄 部分完成 | 有进展但未完全达标 |
| ❌ 未开始 | 尚未涉及 |

---

## Phase 0：数据库综合优化（P0-4）

### A：覆盖索引 + pg_trgm（必做）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | 创建 SQL 迁移脚本（含 pg_trgm 扩展、5 个索引、1 个物化视图） | `scripts/migration/v1.0_indexes.sql` |
| ✅ | **在 PostgreSQL 数据库中执行该迁移脚本** | 已执行 via `run_migration.py`

### B：连接池 + 查询缓存（必做）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | settings.py 增加 `CONN_MAX_AGE=300` | `Webfront/config/settings.py` |
| ✅ | settings.py 增加 CACHES 配置（LocMemCache） | `Webfront/config/settings.py` |
| ✅ | statistics_dao.py 中 get_statistics() 使用物化视图 + 缓存，含 ProgrammingError fallback | `Webfront/webfront/services/dao/statistics_dao.py` |
| ✅ | airfoil_service.py facade 委托到 DAO | `Webfront/webfront/services/airfoil_service.py` |

### D：超时参数调优（推荐）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | psql.py 已有 statement_timeout 默认 3000ms | `airfoil_collab/psql.py:155` |
| ✅ | **从环境变量读取 `STATEMENT_TIMEOUT_MS`** | `airfoil_collab/psql.py:155` |

---

## Phase 1：P0 功能重构

### P0-1：Service 层解耦（3天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | 创建 `services/dao/` 包 | `Webfront/webfront/services/dao/` |
| ✅ | statistics_dao.py（get_statistics + get_top_performers） | `Webfront/webfront/services/dao/statistics_dao.py` |
| ✅ | airfoil_dao.py（列表/详情/搜索/对比） | `Webfront/webfront/services/dao/airfoil_dao.py` |
| ✅ | anomaly_dao.py（异常统计/列表） | `Webfront/webfront/services/dao/anomaly_dao.py` |
| ✅ | dao/__init__.py 统一导出 | `Webfront/webfront/services/dao/__init__.py` |
| ✅ | airfoil_service.py 改为 Facade | `Webfront/webfront/services/airfoil_service.py` |
| ✅ | 导入验证通过 | 运行 `python -c "from webfront.services.airfoil_service import *"` |

### P0-2：可视化实时化（3天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | 新增 6 个 JSON API View | `Webfront/webfront/views.py`（6个 visualize_api_* 函数） |
| ✅ | 注册 6 个可视化 API 路由 | `Webfront/webfront/urls.py` |
| ✅ | visualize.html 全部 ECharts + AJAX 动态渲染 | `Webfront/templates/webfront/visualize.html` |
| ✅ | 数据筛选器卡片支持交互 | `Webfront/templates/webfront/visualize.html` |
| ✅ | 移除了所有静态 `<img>` 引用 | `Webfront/templates/webfront/visualize.html` |

### P0-3：对比与可视化融合（1.5天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | compare.html 表格每行增加「查看可视化」按钮 | `Webfront/templates/webfront/compare.html` |
| ✅ | visualize View 解析 codes/reynolds 参数 | `Webfront/webfront/views.py` |
| ✅ | visualize.html 页面加载时读取 URL 参数并应用 | `Webfront/templates/webfront/visualize.html` |
| ✅ | 数据筛选器卡片与对比功能共享参数 | `Webfront/templates/webfront/visualize.html` |

---

## Phase 2：P1 体验优化

### P1-1：审计入口集成（1天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | 导航栏「智能查询 ✦」增加下拉菜单含审计入口 | `Webfront/templates/webfront/base.html` |
| ✅ | nl2sql.html 审计横幅增加「查看审计详情」链接 | `Webfront/templates/webfront/nl2sql.html` |
| ✅ | nl2sql_audit_list.html 使用统一设计 Token | `Webfront/templates/webfront/nl2sql_audit_list.html` |

### P1-2：审计页面 UI 统一（0.5天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | nl2sql_audit_detail.html 使用 detail-grid + form-input + code-block | `Webfront/templates/webfront/nl2sql_audit_detail.html` |
| ✅ | explain_audit_detail.html 统一风格 | `Webfront/templates/webfront/explain_audit_detail.html` |
| ✅ | explain_audit_list.html 使用 table-wrap | `Webfront/templates/webfront/explain_audit_list.html` |

### P1-3：NL2SQL 历史查询记录（1天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | 新增 nl2sql_history View（最近 50 条） | `Webfront/webfront/views.py` |
| ✅ | 注册 /nl2sql/history/ 路由 | `Webfront/webfront/urls.py` |
| ✅ | nl2sql.html 增加可折叠历史记录面板 | `Webfront/templates/webfront/nl2sql.html` |
| ✅ | 点击历史记录自动填充并触发查询 | `Webfront/templates/webfront/nl2sql.html` |

### P1-4：搜索功能交互优化（0.5天 → 已完成）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | search.html 增加 tab-nav Tab 切换 | `Webfront/templates/webfront/search.html` |
| ✅ | views.py search_airfoils 支持 mode 参数 | `Webfront/webfront/views.py` |
| ✅ | 两种搜索模式互斥且清晰区分 | `Webfront/templates/webfront/search.html` |

---

## Phase 3：P2 进阶增强

### P2-1：图表交互升级（1天）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | visualize.html 使用 ECharts（含 tooltip） | `Webfront/templates/webfront/visualize.html` |
| ✅ | index.html 使用 ECharts（含 tooltip） | `Webfront/templates/webfront/index.html` |
| ✅ | **图表增加 dataZoom 缩放能力** | index.html + visualize.html |
| ✅ | **图表增加「导出为 PNG」按钮** | index.html + visualize.html |

### P2-2：数据导出功能（0.5天）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | airfoil_list.html 导出 CSV | `Webfront/templates/webfront/airfoil_list.html` |
| ✅ | compare.html 导出 CSV | `Webfront/templates/webfront/compare.html` |
| ✅ | anomaly_list.html 导出 CSV | `Webfront/templates/webfront/anomaly_list.html` |
| ✅ | **search.html 增加导出 CSV** | `Webfront/templates/webfront/search.html` |
| ✅ | **NL2SQL 查询结果增加导出 CSV** | `Webfront/templates/webfront/nl2sql.html` |

### P2-3：移动端适配（1天）
| 状态 | 条目 | 文件 |
|:----|:-----|:-----|
| ✅ | base.css 增加 `@media (max-width: 768px)` 和 `(max-width: 480px)` 响应式规则 | `Webfront/templates/webfront/base.html` |
| ✅ | `.result-grid`、`.detail-grid` 在 768px 下单列 | `Webfront/templates/webfront/base.html` |
| ✅ | compare.html 表格已用 table-wrap 支持横向滚动 | `Webfront/templates/webfront/compare.html` |
| ✅ | **visualize.html 双列网格在 480px 下改为单列** | `Webfront/templates/webfront/base.html` |
| ✅ | **nl2sql.html 的 SQL/解读双列在小屏下切换为单列** | `Webfront/templates/webfront/nl2sql.html` |

---

## 技术债务（文档中列出）

| 状态 | 项目 | 影响 | 参考文件 |
|:----|:-----|:-----|:---------|
| ❌ | collab_service.py 模块加载缓存 | 每次请求可能重复加载 | `Webfront/webfront/services/collab_service.py` |
| ❌ | 无单元测试覆盖 | 重构风险高 | `Webfront/webfront/tests.py` |
| ❌ | 未使用静态文件打包 | 生产部署需手动处理 | `Webfront/config/settings.py` |
| ✅ | **P0-4 迁移脚本已执行** | 5 个索引 + 1 个物化视图已创建 via `run_migration.py` |

---

## 汇总

| 类别 | 总计项 | 已完成 | 部分完成 | 未开始 |
|:-----|:------|:------|:--------|:------|
| P0 数据库优化 | 8 | 8 | 0 | 0 |
| P1 功能重构 | 14 | 14 | 0 | 0 |
| P2 体验优化 | 10 | 10 | 0 | 0 |
| P3 进阶增强 | 12 | 12 | 0 | 0 |
| 技术债务 | 4 | 0 | 0 | 4 |
| **总计** | **48** | **44** | **0** | **4** |

---

## 推荐下一步执行顺序

### 中优先级（后续可选）
```
1. 技术债务 → collab_service.py 模块加载缓存优化
```

### 低优先级（持续改进）
```
2. 技术债务 → tests.py 单元测试覆盖率
3. 技术债务 → 静态文件打包配置
```
