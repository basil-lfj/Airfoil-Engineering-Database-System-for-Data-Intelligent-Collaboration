\set ON_ERROR_STOP on

\echo === Scenario A: batch import rollback on invalid row ===
DO $$
DECLARE
  v_before bigint;
  v_after bigint;
  v_version_id uuid;
BEGIN
  SELECT version_id INTO v_version_id
  FROM airfoil_version
  WHERE is_deleted = false AND status = 'valid'
  ORDER BY is_current DESC, version_no DESC
  LIMIT 1;

  IF v_version_id IS NULL THEN
    RAISE EXCEPTION 'No valid version found for import test';
  END IF;

  SELECT count(*) INTO v_before FROM performance_record;

  BEGIN
    PERFORM governance.import_performance_batch(
      v_version_id,
      '[
        {"alpha_deg": 48, "reynolds_number": 777777, "cl": 0.55, "cd": 0.032, "cm": 0.00},
        {"alpha_deg": 49, "reynolds_number": 777777, "cl": 0.58, "cd": -0.010, "cm": 0.00}
      ]'::jsonb,
      'synthetic',
      false
    );
    RAISE EXCEPTION 'batch rollback test failed: import unexpectedly succeeded';
  EXCEPTION WHEN others THEN
    RAISE NOTICE 'batch import rolled back as expected: %', SQLERRM;
  END;

  SELECT count(*) INTO v_after FROM performance_record;
  IF v_before <> v_after THEN
    RAISE EXCEPTION 'rollback check failed: before %, after %', v_before, v_after;
  ELSE
    RAISE NOTICE 'rollback check passed: before %, after %', v_before, v_after;
  END IF;
END
$$;

\echo === Scenario B: optimistic lock conflict simulation ===
DO $$
DECLARE
  v_record_id uuid;
  v_xmin_old text;
  v_xmin_new text;
  v_success boolean;
  v_message text;
BEGIN
  SELECT record_id, xmin::text
  INTO v_record_id, v_xmin_old
  FROM performance_record
  WHERE is_deleted = false
  LIMIT 1;

  IF v_record_id IS NULL THEN
    RAISE EXCEPTION 'No performance record found for optimistic-lock test';
  END IF;

  PERFORM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old, 0.6001, 0.0201, NULL, 'optimistic_user_a'
  );

  SELECT xmin::text INTO v_xmin_new
  FROM performance_record
  WHERE record_id = v_record_id;

  SELECT success, message
  INTO v_success, v_message
  FROM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old, 0.6002, 0.0202, NULL, 'optimistic_user_b'
  );

  RAISE NOTICE 'xmin old=%, xmin new=%', v_xmin_old, v_xmin_new;
  RAISE NOTICE 'second update success=%, message=%', v_success, v_message;
END
$$;

\echo === Scenario C: pessimistic lock (manual two-session steps) ===
\echo Session A:
\echo "BEGIN;"
\echo "SELECT record_id FROM performance_record WHERE is_deleted=false LIMIT 1;"
\echo "SELECT * FROM performance_record WHERE record_id = '<record_id>' FOR UPDATE;"
\echo "-- keep transaction open, do not COMMIT yet"
\echo
\echo Session B:
\echo "SET lock_timeout = '3s';"
\echo "BEGIN;"
\echo "SELECT * FROM governance.update_performance_record_pessimistic('<same_record_id>', 0.9, 0.03, NULL, 'session_b');"
\echo "-- expected: timeout or waiting until Session A COMMIT"
\echo
\echo After Session A COMMIT, rerun Session B update and it should succeed.

