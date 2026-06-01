CREATE OR REPLACE FUNCTION airfoil_db.import_performance_batch(
  p_version_id bigint,
  p_rows jsonb,
  p_source_run text DEFAULT 'import'
)
RETURNS TABLE(inserted_rows integer)
LANGUAGE plpgsql
AS $$
DECLARE
  v_item jsonb;
  v_reynolds double precision;
  v_aoa double precision;
  v_mach double precision;
  v_cl double precision;
  v_cd double precision;
  v_cm double precision;
  v_ldr double precision;
  v_inserted integer := 0;
BEGIN
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'p_rows must be a JSON array';
  END IF;

  IF p_version_id IS NULL THEN
    RAISE EXCEPTION 'p_version_id is required';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM airfoil_db.airfoil_version v WHERE v.version_id = p_version_id) THEN
    RAISE EXCEPTION 'version_id % not found', p_version_id;
  END IF;

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_rows)
  LOOP
    v_reynolds := NULLIF(v_item ->> 'reynolds', '')::double precision;
    v_aoa := NULLIF(v_item ->> 'aoa_deg', '')::double precision;
    v_mach := NULLIF(v_item ->> 'mach', '')::double precision;
    v_cl := NULLIF(v_item ->> 'cl', '')::double precision;
    v_cd := NULLIF(v_item ->> 'cd', '')::double precision;
    v_cm := NULLIF(v_item ->> 'cm', '')::double precision;
    v_ldr := NULLIF(v_item ->> 'ldr', '')::double precision;

    INSERT INTO airfoil_db.airfoil_performance(
      version_id, reynolds, aoa_deg, mach, cl, cd, cm, ldr, source_run, created_at
    )
    VALUES (
      p_version_id, v_reynolds, v_aoa, v_mach, v_cl, v_cd, v_cm, v_ldr, p_source_run, now()
    );

    v_inserted := v_inserted + 1;
  END LOOP;

  RETURN QUERY SELECT v_inserted;
END;
$$;

