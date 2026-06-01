\set ON_ERROR_STOP on

\echo === Candidate query timing (EXPLAIN ANALYZE) ===
\echo Q1: Geometry by airfoil_code (current)
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM api.get_airfoil_geometry('ag17', true, NULL);

\echo Q2: Filter airfoils by condition with ORDER BY (current)
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

\echo Q5: Airfoils with anomalies (current)
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, total_anomaly_hint
FROM api.list_airfoils_with_anomalies(true)
LIMIT 50;

\echo === Index optimization experiment for Q2 ===
\echo Phase 0: Drop related non-constraint indexes (no-index baseline)
DROP INDEX IF EXISTS idx_performance_record_condition_lod;
DROP INDEX IF EXISTS idx_performance_record_condition_cd_cl;
DROP INDEX IF EXISTS idx_performance_record_version;
DROP INDEX IF EXISTS idx_experiment_condition_alpha_re;
DROP INDEX IF EXISTS idx_airfoil_version_airfoil_current;

\echo Phase 0: EXPLAIN (ANALYZE, BUFFERS) - baseline
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

\echo Phase 1: Create single-column indexes
CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_only ON experiment_condition(alpha_deg);
CREATE INDEX IF NOT EXISTS idx_experiment_condition_re_only ON experiment_condition(reynolds_number);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_only ON performance_record(condition_id);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_is_current_only ON airfoil_version(is_current) WHERE is_current;

\echo Phase 1: EXPLAIN (ANALYZE, BUFFERS) - single-column indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

\echo Phase 2: Create composite indexes aligned with predicates and ordering
DROP INDEX IF EXISTS idx_experiment_condition_alpha_only;
DROP INDEX IF EXISTS idx_experiment_condition_re_only;
DROP INDEX IF EXISTS idx_performance_record_condition_only;
DROP INDEX IF EXISTS idx_airfoil_version_is_current_only;

CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_re ON experiment_condition(alpha_deg, reynolds_number);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_lod ON performance_record(condition_id, l_over_d DESC);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_current ON airfoil_version(airfoil_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_performance_record_version ON performance_record(version_id);

\echo Phase 2: EXPLAIN (ANALYZE, BUFFERS) - composite indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT airfoil_code, name, version_no, cl, cd, l_over_d
FROM api.find_airfoils_by_condition(0, 100000, NULL, 0.02, NULL, true)
LIMIT 50;

