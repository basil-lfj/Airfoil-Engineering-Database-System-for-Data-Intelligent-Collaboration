-- ============================================================================
-- §7.3 视图/触发器/存储过程验证
-- 验证现有实现是否满足文档要求的 "三者至少其一"
-- ============================================================================


-- ============================================================================
-- 1. 视图：v_current_airfoil_version — 展示当前有效版本
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3a 视图 — v_current_airfoil_version
-- ╚════════════════════════════════════════════════════════════

-- === View definition ===
SELECT pg_get_viewdef('public.v_current_airfoil_version', true);

-- === Sample data (top 10) ===
SELECT airfoil_code, name, version_no, version_type, status, created_at
FROM public.v_current_airfoil_version
ORDER BY airfoil_code
LIMIT 10;

-- === Count of current versions ===
SELECT count(*) AS current_versions FROM public.v_current_airfoil_version;

-- ============================================================================
-- 2. 触发器：tables with change log triggers
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3b 触发器 — trg_log_change_*
-- ╚════════════════════════════════════════════════════════════

-- === Registered triggers ===
SELECT tgname, tgrelid::regclass AS table_name
FROM pg_trigger
WHERE tgname LIKE 'trg_log_change%'
ORDER BY tgname;

-- === Change log sample ===
SELECT version_id, action, entity_name, at, detail
FROM change_log
ORDER BY at DESC
LIMIT 10;

-- ============================================================================
-- 3. 视图：v_data_source_summary — 数据来源统计
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3b 视图 — governance.v_data_source_summary
-- ╚════════════════════════════════════════════════════════════

SELECT * FROM governance.v_data_source_summary ORDER BY source_type, provider;

-- ============================================================================
-- 4. 视图：v_performance_version_trace — 性能数据版本追溯
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3b 视图 — governance.v_performance_version_trace
-- ╚════════════════════════════════════════════════════════════

SELECT airfoil_code, version_no, source_type, cl, cd, version_created_at
FROM governance.v_performance_version_trace
ORDER BY airfoil_code, version_no
LIMIT 15;

-- ============================================================================
-- 5. 存储过程：governance 模式函数列表
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3c 存储过程 — governance 模式函数
-- ╚════════════════════════════════════════════════════════════

-- === Functions in governance schema ===
SELECT routine_name, routine_type, data_type AS return_type
FROM information_schema.routines
WHERE specific_schema = 'governance'
ORDER BY routine_name;

-- === Functions in api schema ===
SELECT routine_name, routine_type, data_type AS return_type
FROM information_schema.routines
WHERE specific_schema = 'api'
ORDER BY routine_name;

-- ============================================================================
-- 6. 完整性：prevent_core_delete 触发器验证
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ §7.3b 触发器 — governance.prevent_core_delete
-- ╚════════════════════════════════════════════════════════════

SELECT tgname, tgrelid::regclass AS table_name
FROM pg_trigger
WHERE tgname = 'trg_prevent_core_delete'
   OR tgname LIKE '%prevent%';

-- === [DONE] Advanced mechanisms verification complete ===