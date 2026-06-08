# Webfront 前端升级更新日志

> 更新时间：2026-06-08  
> 更新范围：前端页面 + Schema Prompt  
> 相关分支/提交：Webfront 项目本地修改

---

## 更新概览

| # | 修改项 | 影响文件 | 类型 |
|:-|:-------|:--------|:----|
| 1 | 执行过程步骤进度展示 | `nl2sql.html` + `base.html` | ✨ 新功能 |
| 2 | 统一空状态展示组件 | `nl2sql.html` + `base.html` | ✨ 新功能 |
| 3 | 响应式布局适配 | `base.html` | 🎨 样式优化 |
| 4 | Schema Prompt 改进 | `schema_prompt.py` | 🐛 数据准确性修复 |
| 5 | 前端字段名匹配修复 | `collab_service.py` | 🐛 Bug 修复 |
| 6 | 快速示例按钮修正 | `nl2sql.html` | 🐛 数据准确性修复 |

---

## 详细变更

### 1. 执行过程步骤进度展示

**文件：** `templates/webfront/nl2sql.html` + `templates/webfront/base.html`

在 NL2SQL 查询执行期间，新增 4 步进度展示组件，取代原先简单的加载旋转图标：

```
🤖 AI 分析问题并生成 SQL   → 进行中… / 已完成 ✓ / 失败 ✗
🔍 静态审计检查 SQL 安全性  → 进行中… / 已完成 ✓ / 失败 ✗
⚡ 执行 SQL 并获取结果      → 进行中… / 已完成 ✓ / 失败 ✗
📊 AI 解读查询结果          → 进行中… / 已完成 ✓ / 失败 ✗
```

**设计规格：**
- 每步独立显示状态标记（圆点颜色 + 标签文字）
- 进行中状态：橙色圆点 + 脉冲动画（`pulse-dot`）
- 已完成状态：绿色圆点
- 失败状态：红色圆点
- 未激活步骤：半透明（opacity: 0.5）
- 等待中 → 进行中 → 完成/失败 自动过渡

**新增 CSS 类（base.html）：**
| 类名 | 用途 |
|:-----|:-----|
| `.step-progress` | 进度容器，卡片样式上下排列 |
| `.step-item` | 单步条目，flex 布局 |
| `.step-item.active` | 进行中高亮 |
| `.step-item.done` | 已完成样式 |
| `.step-item.failed` | 失败样式 |
| `.step-dot` | 状态圆点 |
| `.step-label` | 步骤标签 |
| `.step-status` | 右侧状态文字 |
| `@keyframes pulse-dot` | 圆点脉冲动画 |
| `@keyframes spin` | 旋转加载动画（全局可用） |

---

### 2. 统一空状态展示组件

**文件：** `templates/webfront/base.html` + `templates/webfront/nl2sql.html`

新增通用空状态组件，替换原先简单的「无结果」文字提示。

**设计规格：**
- SVG 图标（56×56，表格/搜索图标）
- 标题文案（根据场景自动切换）
- 描述文案（根据场景自动切换）
- 操作引导按钮（如「重新输入」）

**状态与文案映射：**

| 场景 | 标题 | 描述 |
|:----|:----|:-----|
| SQL 已执行但无数据 | 暂无数据 | 当前查询条件未返回任何数据，请尝试调整条件或使用其他问题。 |
| 审计标记 needs_fix | 未找到相关结果 | SQL 已执行但未返回数据。可能是查询条件太严格或数据库暂无匹配记录。 |
| 审计标记 rejected |（隐藏空状态） | - |

**新增 CSS 类（base.html）：**
| 类名 | 用途 |
|:-----|:-----|
| `.empty-state` | 空状态 flex 容器（纵向居中对齐） |
| `.empty-state-icon` | 56×56 SVG 图标容器 |
| `.empty-state-title` | 标题 |
| `.empty-state-desc` | 描述文案（max-width: 360px） |

---

### 3. 响应式布局适配

**文件：** `templates/webfront/base.html`

新增两档响应式断点，覆盖所有页面。

**768px 断点（平板/小屏）：**
- 字号：`html` 由 15px → 14px
- 容器边距：由 2rem → 1.25rem
- 导航栏：水平滚动，字号缩小，间距收窄
- 统计网格：最小列宽由 180px → 120px
- 页面标题：由 1.25rem → 1.1rem
- 结果双列布局：自动变为单列（`.result-grid { grid-template-columns: 1fr !important }`）

**480px 断点（手机）：**
- 字号：`html` 由 14px → 13px
- 容器边距：进一步收窄
- 导航栏链接进一步缩小

---

### 4. Schema Prompt 改进

**文件：** `airfoil_collab/schema_prompt.py`

**weak 模式新增内容：**
```
【数据约束提示】
- 翼型编码（airfoil_code）格式为 NACA_xxxx（注意带下划线）
- experiment_condition 表中可用的雷诺数仅为：50000、100000、300000、500000、1000000
- 攻角（alpha_deg）范围：-90° ~ +90°
- 基础表字段信息

【可用示例提问】
- "查询 NACA_2412 的当前有效版本"
- "在 Re=300000、攻角 α=2 条件下，列出升阻比最高的前 10 个翼型"
- "查询 NACA_0012 的上表面坐标点"
- "列出存在异常提示的翼型"
- "统计每个版本类型下的翼型数量"
- "查询翼型 NACA_0012 在 Re=500000 下不同攻角的 Cl、Cd 性能数据"
- "对比翼型 NACA_0012 和 NACA_2412 在 Re=300000 下的升阻比"
```

**strong 模式新增（在原有 JSON Schema 后追加）：**
- 翼型编码格式约束
- 可用雷诺数列举
- 敏感表访问规则
- 同样 7 条可用示例提问

---

### 5. 前端字段名匹配修复

**文件：** `webfront/services/collab_service.py`

**问题：** 后端返回 `generated_sql` 字段，但前端 JS 读取 `data.executed_sql`，导致 SQL 始终显示「(无 SQL 生成)」。

**修复：** 后端返回字典中同时包含 `generated_sql` 和 `executed_sql` 两个字段。

---

### 6. 快速示例按钮修正

**文件：** `templates/webfront/nl2sql.html`

**修正前（不可用/数据不匹配）：**
```
- "查询 NACA2412 的当前有效版本"   ← 编码格式错误（无下划线）
- "Re=3000000 升阻比最高的前 10 个翼型"  ← 雷诺数不存在
```

**修正后：**
```
- "查询 NACA_2412 的当前有效版本"   ← 正确带下划线
- "在 Re=300000、攻角 α=2 条件下，列出升阻比最高的前 10 个翼型"  ← 使用有效雷诺数
- "对比 NACA_0012 和 NACA_2412 在 Re=500000 下的升阻比"  ← 新增可用示例
```

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|:----|:--------|:-----|
| `Webfront/templates/webfront/base.html` | 修改 | 新增 step-progress, empty-state, responsive CSS + spin 动画 |
| `Webfront/templates/webfront/nl2sql.html` | 重写 | 步骤进度组件、空状态组件、快速示例修正 |
| `Webfront/webfront/services/collab_service.py` | 修改 | 增加 `executed_sql` 后端字段 |
| `airfoil_collab/schema_prompt.py` | 修改 | weak/strong 模式新增数据约束提示和示例提问 |

---

## 后续建议

| 优先级 | 建议 |
|:-----|:-----|
| P0 | 数据导入脚本需为每个翼型至少设置一条 `is_current=true, status='valid'` 的记录 |
| P1 | 更多雷诺数（如 3,000,000）的 Polar 数据生成 |
| P2 | NL2SQL 服务端结果缓存，优化多次相同查询的响应速度 |
