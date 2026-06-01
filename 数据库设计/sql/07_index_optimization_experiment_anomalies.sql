\set ON_ERROR_STOP on

\echo === Index optimization experiment for Q5 (airfoils with anomalies) ===
\echo Phase 0: Drop related non-constraint indexes (no-index baseline)
DROP INDEX IF EXISTS idx_performance_record_anomaly_version;
DROP INDEX IF EXISTS idx_anomaly_record_version;
DROP INDEX IF EXISTS idx_anomaly_record_rule;
DROP INDEX IF EXISTS idx_anomaly_record_status;

\echo Phase 0: EXPLAIN (ANALYZE, BUFFERS) - baseline
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

\echo Phase 1: Create single-column indexes
CREATE INDEX IF NOT EXISTS idx_performance_record_version_only ON performance_record(version_id);
CREATE INDEX IF NOT EXISTS idx_performance_record_cd_only ON performance_record(cd);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_version_only ON anomaly_record(version_id);

\echo Phase 1: EXPLAIN (ANALYZE, BUFFERS) - single-column indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

\echo Phase 2: Create partial indexes aligned with filters
DROP INDEX IF EXISTS idx_performance_record_version_only;
DROP INDEX IF EXISTS idx_performance_record_cd_only;
DROP INDEX IF EXISTS idx_anomaly_record_version_only;

CREATE INDEX IF NOT EXISTS idx_anomaly_record_version ON anomaly_record(version_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_rule ON anomaly_record(rule_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_status ON anomaly_record(status);

CREATE INDEX IF NOT EXISTS idx_performance_record_anomaly_version ON performance_record(version_id) WHERE is_anomaly;
CREATE INDEX IF NOT EXISTS idx_performance_record_negative_cd_version ON performance_record(version_id) WHERE cd < 0;

\echo Phase 2: EXPLAIN (ANALYZE, BUFFERS) - partial indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

