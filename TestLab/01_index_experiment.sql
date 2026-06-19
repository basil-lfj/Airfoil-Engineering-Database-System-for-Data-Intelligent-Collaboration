-- ============================================================================
-- §7.1 索引优化实验
-- 核心查询：Q2 — 工况条件筛选（api.find_airfoils_by_condition）
--           Q5 — 异常翼型识别（api.list_airfoils_with_anomalies）
-- 实验阶段：Phase 0（无索引基准）→ Phase 1（单列索引）→ Phase 2（复合索引）
-- 输出：EXPLAIN (ANALYZE, BUFFERS)
-- ============================================================================

-- ============================================================================
-- 实验前准备：确保测试数据存在
-- ============================================================================
SELECT count(*) AS perf_records FROM performance_record WHERE is_deleted = false;
SELECT count(*) AS valid_versions FROM airfoil_version WHERE is_deleted = false AND status = 'valid';
SELECT count(*) AS condition_count FROM experiment_condition;

-- ============================================================================
-- 实验 A：Q2 — 工况条件筛选（find_airfoils_by_condition）
-- SQL：SELECT airfoil_code, name, version_no, cl, cd, l_over_d
--      FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
--      LIMIT 50;
-- ============================================================================

-- ════════════════════════════════════════════════════════════
-- ║ 实验 A：工况条件筛选（Q2）
-- ╚════════════════════════════════════════════════════════════

-- ── Phase 0：无索引基准 ──
-- === [A/Phase 0] Drop all non-constraint indexes (no-index baseline) ===
DROP INDEX IF EXISTS idx_experiment_condition_alpha_re;
DROP INDEX IF EXISTS idx_experiment_condition_re_alpha;
DROP INDEX IF EXISTS idx_experiment_condition_alpha_only;
DROP INDEX IF EXISTS idx_experiment_condition_re_only;
DROP INDEX IF EXISTS idx_performance_record_condition_lod;
DROP INDEX IF EXISTS idx_performance_record_condition_cd_cl;
DROP INDEX IF EXISTS idx_performance_record_condition_only;
DROP INDEX IF EXISTS idx_performance_record_version;
DROP INDEX IF EXISTS idx_airfoil_version_airfoil_current;
DROP INDEX IF EXISTS idx_airfoil_version_airfoil_id;

-- === [A/Phase 0] EXPLAIN (ANALYZE, BUFFERS) - baseline ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

-- ── Phase 1：单列索引 ──
-- === [A/Phase 1] Create single-column indexes ===
CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_only ON experiment_condition(alpha_deg);
CREATE INDEX IF NOT EXISTS idx_experiment_condition_re_only ON experiment_condition(reynolds_number);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_only ON performance_record(condition_id);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_is_current_only ON airfoil_version(is_current) WHERE is_current;

-- === [A/Phase 1] EXPLAIN (ANALYZE, BUFFERS) - single-column indexes ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

-- ── Phase 2：复合索引（对齐谓词与排序需求） ──
-- === [A/Phase 2] Drop single-column, create composite indexes ===
DROP INDEX IF EXISTS idx_experiment_condition_alpha_only;
DROP INDEX IF EXISTS idx_experiment_condition_re_only;
DROP INDEX IF EXISTS idx_performance_record_condition_only;
DROP INDEX IF EXISTS idx_airfoil_version_is_current_only;

CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_re
  ON experiment_condition(alpha_deg, reynolds_number);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_lod
  ON performance_record(condition_id, l_over_d DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_current
  ON airfoil_version(airfoil_id) WHERE is_current AND is_deleted = false AND status = 'valid';
CREATE INDEX IF NOT EXISTS idx_performance_record_version
  ON performance_record(version_id);

-- === [A/Phase 2] EXPLAIN (ANALYZE, BUFFERS) - composite indexes ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

-- ============================================================================
-- 实验 B：Q5 — 异常翼型识别（list_airfoils_with_anomalies）
-- 查询含异常记录的翼型（异常表记录 + is_anomaly 标记 + Cd<0 记录）
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ 实验 B：异常翼型识别（Q5）
-- ╚════════════════════════════════════════════════════════════

-- ── Phase 0：无索引基准 ──
-- === [B/Phase 0] Drop anomaly-related indexes (no-index baseline) ===
DROP INDEX IF EXISTS idx_performance_record_anomaly_version;
DROP INDEX IF EXISTS idx_performance_record_negative_cd_version;
DROP INDEX IF EXISTS idx_anomaly_record_version;
DROP INDEX IF EXISTS idx_anomaly_record_rule;
DROP INDEX IF EXISTS idx_anomaly_record_status;

-- === [B/Phase 0] EXPLAIN (ANALYZE, BUFFERS) - baseline ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

-- ── Phase 1：单列索引 ──
-- === [B/Phase 1] Create single-column indexes ===
CREATE INDEX IF NOT EXISTS idx_performance_record_version_only ON performance_record(version_id);
CREATE INDEX IF NOT EXISTS idx_performance_record_cd_only ON performance_record(cd);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_version_only ON anomaly_record(version_id);

-- === [B/Phase 1] EXPLAIN (ANALYZE, BUFFERS) - single-column indexes ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

-- ── Phase 2：部分索引（Partial Indexes） ──
-- === [B/Phase 2] Drop single-column, create partial indexes ===
DROP INDEX IF EXISTS idx_performance_record_version_only;
DROP INDEX IF EXISTS idx_performance_record_cd_only;
DROP INDEX IF EXISTS idx_anomaly_record_version_only;

CREATE INDEX IF NOT EXISTS idx_anomaly_record_version ON anomaly_record(version_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_rule ON anomaly_record(rule_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_status ON anomaly_record(status);
CREATE INDEX IF NOT EXISTS idx_performance_record_anomaly_version
  ON performance_record(version_id) WHERE is_anomaly;
CREATE INDEX IF NOT EXISTS idx_performance_record_negative_cd_version
  ON performance_record(version_id) WHERE cd < 0;

-- === [B/Phase 2] EXPLAIN (ANALYZE, BUFFERS) - partial indexes ===
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

-- ============================================================================
-- 恢复生产环境索引
-- ============================================================================
-- === [RESTORE] Recreate production indexes ===

DROP INDEX IF EXISTS idx_experiment_condition_alpha_only;
DROP INDEX IF EXISTS idx_experiment_condition_re_only;
DROP INDEX IF EXISTS idx_performance_record_condition_only;
DROP INDEX IF EXISTS idx_airfoil_version_is_current_only;

CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_id ON airfoil_version(airfoil_id);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_current ON airfoil_version(airfoil_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_coordinate_point_version_surface_order ON coordinate_point(version_id, surface, point_order);
CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_re ON experiment_condition(alpha_deg, reynolds_number);
CREATE INDEX IF NOT EXISTS idx_experiment_condition_re_alpha ON experiment_condition(reynolds_number, alpha_deg);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_lod ON performance_record(condition_id, l_over_d DESC);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_cd_cl ON performance_record(condition_id, cd, cl);
CREATE INDEX IF NOT EXISTS idx_performance_record_version ON performance_record(version_id);
CREATE INDEX IF NOT EXISTS idx_performance_record_anomaly_version ON performance_record(version_id) WHERE is_anomaly;
CREATE INDEX IF NOT EXISTS idx_anomaly_record_version ON anomaly_record(version_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_rule ON anomaly_record(rule_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_status ON anomaly_record(status);

-- === [DONE] Index experiment complete ===