# TestLab — 数据库高级机制实验套件

> 对应文档：§7 数据库高级机制要求  
> 实验日期：2026-06-19  
> 数据库：PostgreSQL 15+ · 数据库 `airfoil_db`

## 实验结构

```
TestLab/
├── README.md                       ← 本文件：实验概览与运行指南
│
├── 01_index_experiment.sql         ← 索引优化实验（3 阶段：无索引 / 单列 / 复合）
├── 01_index_experiment_output.txt  ← EXPLAIN ANALYZE 原始输出
├── report_index_experiment.md      ← 索引优化实验报告（含对比表格与分析）
│
├── 02_transaction_experiment.sql   ← 事务原子性实验（批量回滚 + 乐观锁 + 悲观锁）
├── 02_transaction_experiment_output.txt
├── report_transaction_experiment.md
│
├── 03_advanced_mechanisms.sql      ← 视图/触发器/存储过程验证
├── report_advanced_mechanisms.md
│
├── navicat_01_index_experiment.sql     ← Navicat 适用（纯 SQL，无 psql 元命令）
├── navicat_02_transaction_experiment.sql  ← Navicat 适用
├── navicat_03_advanced_mechanisms.sql    ← Navicat 适用
│
└── 实验覆盖率检查清单.md            ← §7.1 / §7.2 / §7.3 逐条对齐检查
```

## 运行前提

1. PostgreSQL 服务运行中，数据库 `airfoil_db` 已创建
2. 核心数据表（airfoil, airfoil_version, performance_record 等）已填充测试数据
3. 推荐使用 `psql -f` 逐脚本执行

## 快速运行

### A. 命令行方式 (psql)
```bash
# 1. 索引实验
psql -U postgres -d airfoil_db -f 01_index_experiment.sql
# 2. 事务实验
psql -U postgres -d airfoil_db -f 02_transaction_experiment.sql
# 3. 高级机制验证
psql -U postgres -d airfoil_db -f 03_advanced_mechanisms.sql
```

### B. 图形化工具 (Navicat / DBeaver)
请务必使用 **`navicat_*.sql`** 副本文件。这些文件已移除 psql 特有的元命令（如 `\set`, `\echo`），并修复了兼容性字段名。
1. 在 Navicat 中连接 `airfoil_db` 数据库。
2. 打开查询窗口，加载对应的 `navicat_*.sql` 文件。
3. 选中全部内容，点击“运行”。
4. 在“消息”选项卡查看执行结果。

## 实验对照

| 实验 | §7 对应要求 | 状态 |
|:-----|:-----------|:-----|
| 索引优化：Q2 工况筛选 | §7.1 无索引/单列/复合索引对比 | ✅ 已执行 |
| 索引优化：Q5 异常识别 | §7.1 多查询覆盖 | ✅ 已执行 |
| 批量导入异常回滚 | §7.2 事务场景 | ✅ 已执行 |
| 乐观锁冲突检测 | §7.2 并发场景 | ✅ 已执行 |
| 悲观锁（两会话） | §7.2 并发场景 | ✅ 已描述 |
| 当前版本视图 | §7.3 视图 | ✅ 已实现 |
| 变更日志触发器 | §7.3 触发器 | ✅ 已实现 |
| 批量导入存储过程 | §7.3 存储过程 | ✅ 已实现 |