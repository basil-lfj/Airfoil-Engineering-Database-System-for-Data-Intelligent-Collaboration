-- ============================================================================
-- §7.3 视图/触发器/存储过程验证 — Navicat 兼容版
-- Navicat 中：选中整个文件 → 运行
-- ============================================================================

-- ============================================================================
-- 1. 视图：v_current_airfoil_version — 展示当前有效版本
-- ============================================================================
SELECT pg_get_viewdef('public.v_current_airfoil_version', true) AS view_definition;

SELECT airfoil_code, name, version_no, version_type, status, created_at
FROM public.v_current_airfoil_version
ORDER BY airfoil_code
LIMIT 10;

SELECT count(*) AS current_versions FROM public.v_current_airfoil_version;

-- ============================================================================
-- 2. 触发器列表
-- ============================================================================
SELECT tgname AS trigger_name, tgrelid::regclass::text AS table_name
FROM pg_trigger
WHERE tgname LIKE 'trg_log_change%'
ORDER BY tgname;

SELECT version_id, action, entity_name, at, detail
FROM change_log
ORDER BY at DESC
LIMIT 10;

-- ============================================================================
-- 3. 视图：数据来源统计
-- ============================================================================
SELECT * FROM governance.v_data_source_summary ORDER BY source_type, provider;

-- ============================================================================
-- 4. 视图：性能数据版本追溯
-- ============================================================================
SELECT airfoil_code, version_no, source_type, cl, cd, version_created_at
FROM governance.v_performance_version_trace
ORDER BY airfoil_code, version_no
LIMIT 15;

-- ============================================================================
-- 5. governance 模式下的函数列表
-- ============================================================================
SELECT routine_name, routine_type, data_type AS return_type
FROM information_schema.routines
WHERE specific_schema = 'governance'
ORDER BY routine_name;

-- ============================================================================
-- 6. api 模式下的函数列表
-- ============================================================================
SELECT routine_name, routine_type, data_type AS return_type
FROM information_schema.routines
WHERE specific_schema = 'api'
ORDER BY routine_name;

-- ============================================================================
-- 7. prevent_core_delete 触发器
-- ============================================================================
SELECT tgname AS trigger_name, tgrelid::regclass::text AS table_name
FROM pg_trigger
WHERE tgname = 'trg_prevent_core_delete'
   OR tgname LIKE '%prevent%';