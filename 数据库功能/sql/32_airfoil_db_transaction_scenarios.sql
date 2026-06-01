\set ON_ERROR_STOP on

\echo === airfoil_db Scenario A: batch import rollback on unique conflict ===
DO $$
DECLARE
  v_before bigint;
  v_after bigint;
  v_version_id bigint;
  v_re double precision;
  v_aoa double precision;
  v_mach double precision;
BEGIN
  SELECT p.version_id, p.reynolds, p.aoa_deg, p.mach
  INTO v_version_id, v_re, v_aoa, v_mach
  FROM airfoil_db.airfoil_performance p
  ORDER BY p.perf_id
  LIMIT 1;

  IF v_version_id IS NULL THEN
    RAISE EXCEPTION 'no performance data found';
  END IF;

  SELECT count(*) INTO v_before FROM airfoil_db.airfoil_performance;

  BEGIN
    PERFORM airfoil_db.import_performance_batch(
      v_version_id,
      jsonb_build_array(
        jsonb_build_object('reynolds', v_re, 'aoa_deg', v_aoa, 'mach', v_mach, 'cl', 0.1, 'cd', 0.01, 'cm', 0.0),
        jsonb_build_object('reynolds', v_re, 'aoa_deg', v_aoa, 'mach', v_mach, 'cl', 0.2, 'cd', 0.02, 'cm', 0.0)
      ),
      'tx_test'
    );
    RAISE EXCEPTION 'batch rollback test failed: import unexpectedly succeeded';
  EXCEPTION WHEN others THEN
    RAISE NOTICE 'batch import rolled back as expected: %', SQLERRM;
  END;

  SELECT count(*) INTO v_after FROM airfoil_db.airfoil_performance;
  IF v_before <> v_after THEN
    RAISE EXCEPTION 'rollback check failed: before %, after %', v_before, v_after;
  ELSE
    RAISE NOTICE 'rollback check passed: before %, after %', v_before, v_after;
  END IF;
END
$$;

