\set ON_ERROR_STOP on

\echo === airfoil_db index experiment ===
\echo Q: find_airfoils_by_condition (latest) at a common condition

\echo Phase 0: baseline with existing indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM airfoil_db.find_airfoils_by_condition(500000, NULL, -2, NULL, 0.05, NULL, true)
LIMIT 50;

\echo Phase 1: drop related indexes (no-index baseline)
DROP INDEX IF EXISTS airfoil_db.idx_perf_threshold;
DROP INDEX IF EXISTS airfoil_db.idx_perf_condition;
DROP INDEX IF EXISTS airfoil_db.idx_perf_version;
DROP INDEX IF EXISTS airfoil_db.idx_airfoil_version_airfoil;

\echo Phase 1: EXPLAIN (ANALYZE, BUFFERS) after drop
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM airfoil_db.find_airfoils_by_condition(500000, NULL, -2, NULL, 0.05, NULL, true)
LIMIT 50;

\echo Phase 2: create single-column indexes
CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_only
  ON airfoil_db.airfoil_version(airfoil_id);
CREATE INDEX IF NOT EXISTS idx_perf_reynolds_only
  ON airfoil_db.airfoil_performance(reynolds);
CREATE INDEX IF NOT EXISTS idx_perf_aoa_only
  ON airfoil_db.airfoil_performance(aoa_deg);
CREATE INDEX IF NOT EXISTS idx_perf_mach_only
  ON airfoil_db.airfoil_performance(mach);

\echo Phase 2: EXPLAIN (ANALYZE, BUFFERS) with single-column indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM airfoil_db.find_airfoils_by_condition(500000, NULL, -2, NULL, 0.05, NULL, true)
LIMIT 50;

\echo Phase 3: create composite indexes aligned with predicates and ordering
DROP INDEX IF EXISTS airfoil_db.idx_airfoil_version_airfoil_only;
DROP INDEX IF EXISTS airfoil_db.idx_perf_reynolds_only;
DROP INDEX IF EXISTS airfoil_db.idx_perf_aoa_only;
DROP INDEX IF EXISTS airfoil_db.idx_perf_mach_only;

CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil
  ON airfoil_db.airfoil_version(airfoil_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_perf_condition
  ON airfoil_db.airfoil_performance(reynolds, mach, aoa_deg);
CREATE INDEX IF NOT EXISTS idx_perf_threshold
  ON airfoil_db.airfoil_performance(reynolds, mach, ldr);
CREATE INDEX IF NOT EXISTS idx_perf_version
  ON airfoil_db.airfoil_performance(version_id);

\echo Phase 3: EXPLAIN (ANALYZE, BUFFERS) with composite indexes
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM airfoil_db.find_airfoils_by_condition(500000, NULL, -2, NULL, 0.05, NULL, true)
LIMIT 50;

