-- v1.0_indexes.sql
-- 数据库优化：覆盖索引 + pg_trgm + 物化视图
-- 对应 Webfront 架构改进 P0-4

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
