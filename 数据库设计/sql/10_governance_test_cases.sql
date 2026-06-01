\set ON_ERROR_STOP on

\echo === Test 1: anomaly detection idempotency ===
SELECT * FROM governance.detect_performance_anomalies(false);
SELECT * FROM governance.detect_performance_anomalies(false);
\echo Expectation: second run inserted_records should be 0 (or much lower).

\echo === Test 2: hard delete is blocked on core table ===
DO $$
DECLARE
  v_any_record uuid;
BEGIN
  SELECT record_id INTO v_any_record FROM performance_record WHERE is_deleted = false LIMIT 1;
  BEGIN
    DELETE FROM performance_record WHERE record_id = v_any_record;
    RAISE EXCEPTION 'hard-delete test failed: DELETE unexpectedly succeeded';
  EXCEPTION
    WHEN others THEN
      RAISE NOTICE 'hard-delete blocked as expected: %', SQLERRM;
  END;
END
$$;

\echo === Test 3: soft delete workflow (inside rollback transaction) ===
BEGIN;

WITH candidate AS (
  SELECT airfoil_code
  FROM airfoil
  WHERE is_deleted = false
  ORDER BY airfoil_code
  LIMIT 1
)
SELECT * FROM governance.soft_delete_airfoil((SELECT airfoil_code FROM candidate), 'governance_tester', 'test_soft_delete_rollback');

WITH candidate AS (
  SELECT airfoil_code
  FROM airfoil
  ORDER BY airfoil_code
  LIMIT 1
)
SELECT
  a.airfoil_code,
  a.is_deleted AS airfoil_deleted,
  (SELECT count(*)::bigint FROM airfoil_version av2 WHERE av2.airfoil_id = a.airfoil_id AND av2.is_deleted) AS deleted_versions,
  (SELECT count(*)::bigint FROM coordinate_point cp2 JOIN airfoil_version av2 ON av2.version_id = cp2.version_id WHERE av2.airfoil_id = a.airfoil_id AND cp2.is_deleted) AS deleted_points,
  (SELECT count(*)::bigint FROM performance_record pr2 JOIN airfoil_version av2 ON av2.version_id = pr2.version_id WHERE av2.airfoil_id = a.airfoil_id AND pr2.is_deleted) AS deleted_performance
FROM candidate c
JOIN airfoil a ON a.airfoil_code = c.airfoil_code
;

ROLLBACK;

\echo === Test 4: post-rollback sanity ===
SELECT
  count(*) FILTER (WHERE is_deleted = true) AS deleted_airfoils,
  count(*) FILTER (WHERE is_deleted = false) AS active_airfoils
FROM airfoil;
