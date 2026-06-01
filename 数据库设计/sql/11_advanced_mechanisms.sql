\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS governance;

\echo === Advanced mechanism: current valid version view ===
CREATE OR REPLACE VIEW public.v_current_airfoil_version AS
SELECT
  a.airfoil_id,
  a.airfoil_code,
  a.name,
  av.version_id,
  av.version_no,
  av.version_type,
  av.status,
  av.created_at
FROM airfoil a
JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
WHERE a.is_deleted = false
  AND av.is_deleted = false
  AND av.status = 'valid'
  AND av.is_current = true;

\echo === Advanced mechanism: actor helper ===
CREATE OR REPLACE FUNCTION governance.get_or_create_actor_id(
  p_username text DEFAULT 'system'
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_actor_id uuid;
BEGIN
  SELECT user_id INTO v_actor_id
  FROM user_account
  WHERE username = p_username
  LIMIT 1;

  IF v_actor_id IS NULL THEN
    INSERT INTO user_account(username, role, is_active)
    VALUES (p_username, 'operator', true)
    ON CONFLICT (username) DO UPDATE SET is_active = true
    RETURNING user_id INTO v_actor_id;
  END IF;

  RETURN v_actor_id;
END;
$$;

\echo === Advanced mechanism: change-log trigger for versioned tables ===
CREATE OR REPLACE FUNCTION governance.log_change_for_versioned_tables()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_actor_setting text;
  v_actor_id uuid;
  v_version_id uuid;
  v_entity_id uuid;
  v_action text;
  v_detail text;
BEGIN
  v_actor_setting := NULLIF(current_setting('app.current_user_id', true), '');
  IF v_actor_setting IS NOT NULL THEN
    v_actor_id := v_actor_setting::uuid;
  ELSE
    v_actor_id := governance.get_or_create_actor_id('system');
  END IF;

  IF TG_OP = 'INSERT' THEN
    v_version_id := NEW.version_id;
    v_action := 'insert';
  ELSIF TG_OP = 'UPDATE' THEN
    v_version_id := NEW.version_id;
    IF (to_jsonb(NEW) ? 'is_deleted') AND (COALESCE(NEW.is_deleted, false) = true) AND (COALESCE(OLD.is_deleted, false) = false) THEN
      v_action := 'invalidate';
    ELSE
      v_action := 'update';
    END IF;
  ELSE
    v_version_id := OLD.version_id;
    v_action := 'invalidate';
  END IF;

  IF TG_TABLE_NAME = 'airfoil_version' THEN
    v_entity_id := COALESCE(NEW.version_id, OLD.version_id);
  ELSIF TG_TABLE_NAME = 'coordinate_point' THEN
    v_entity_id := COALESCE(NEW.point_id, OLD.point_id);
  ELSE
    v_entity_id := COALESCE(NEW.record_id, OLD.record_id);
  END IF;

  v_detail := format('trigger=%s; table=%s; op=%s', TG_NAME, TG_TABLE_NAME, TG_OP);

  INSERT INTO change_log(version_id, actor_id, action, entity_name, entity_id, at, detail)
  VALUES (v_version_id, v_actor_id, v_action, TG_TABLE_NAME, v_entity_id, now(), v_detail);

  RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_log_change_airfoil_version ON airfoil_version;
CREATE TRIGGER trg_log_change_airfoil_version
AFTER INSERT OR UPDATE ON airfoil_version
FOR EACH ROW EXECUTE FUNCTION governance.log_change_for_versioned_tables();

DROP TRIGGER IF EXISTS trg_log_change_coordinate_point ON coordinate_point;
CREATE TRIGGER trg_log_change_coordinate_point
AFTER INSERT OR UPDATE ON coordinate_point
FOR EACH ROW EXECUTE FUNCTION governance.log_change_for_versioned_tables();

DROP TRIGGER IF EXISTS trg_log_change_performance_record ON performance_record;
CREATE TRIGGER trg_log_change_performance_record
AFTER INSERT OR UPDATE ON performance_record
FOR EACH ROW EXECUTE FUNCTION governance.log_change_for_versioned_tables();

\echo === Advanced mechanism: batch import function (transactional) ===
CREATE OR REPLACE FUNCTION governance.import_performance_batch(
  p_version_id uuid,
  p_rows jsonb,
  p_source_type text DEFAULT 'synthetic',
  p_is_anomaly boolean DEFAULT false
)
RETURNS TABLE(inserted_rows integer)
LANGUAGE plpgsql
AS $$
DECLARE
  v_item jsonb;
  v_alpha numeric;
  v_re numeric;
  v_cl numeric;
  v_cd numeric;
  v_cm numeric;
  v_condition_id uuid;
  v_inserted integer := 0;
BEGIN
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'p_rows must be a JSON array';
  END IF;

  IF p_source_type NOT IN ('real', 'synthetic') THEN
    RAISE EXCEPTION 'source_type must be real/synthetic';
  END IF;

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_rows)
  LOOP
    v_alpha := (v_item ->> 'alpha_deg')::numeric;
    v_re := (v_item ->> 'reynolds_number')::numeric;
    v_cl := (v_item ->> 'cl')::numeric;
    v_cd := (v_item ->> 'cd')::numeric;
    v_cm := NULLIF(v_item ->> 'cm', '')::numeric;

    SELECT condition_id INTO v_condition_id
    FROM experiment_condition
    WHERE alpha_deg = v_alpha AND reynolds_number = v_re
    LIMIT 1;

    IF v_condition_id IS NULL THEN
      INSERT INTO experiment_condition(alpha_deg, reynolds_number)
      VALUES (v_alpha, v_re)
      RETURNING condition_id INTO v_condition_id;
    END IF;

    INSERT INTO performance_record(
      version_id, condition_id, cl, cd, cm, l_over_d, source_type, is_anomaly, measured_at
    )
    VALUES (
      p_version_id,
      v_condition_id,
      v_cl,
      v_cd,
      v_cm,
      CASE WHEN v_cd = 0 THEN NULL ELSE v_cl / v_cd END,
      p_source_type,
      p_is_anomaly,
      now()
    );

    v_inserted := v_inserted + 1;
  END LOOP;

  RETURN QUERY SELECT v_inserted;
END;
$$;

\echo === Advanced mechanism: pessimistic-lock update ===
CREATE OR REPLACE FUNCTION governance.update_performance_record_pessimistic(
  p_record_id uuid,
  p_new_cl numeric,
  p_new_cd numeric,
  p_new_cm numeric DEFAULT NULL,
  p_actor_username text DEFAULT 'operator'
)
RETURNS TABLE(updated_rows integer, new_xmin text)
LANGUAGE plpgsql
AS $$
DECLARE
  v_actor_id uuid;
  v_version_id uuid;
BEGIN
  v_actor_id := governance.get_or_create_actor_id(p_actor_username);

  PERFORM 1
  FROM performance_record
  WHERE record_id = p_record_id AND is_deleted = false
  FOR UPDATE;

  UPDATE performance_record
  SET
    cl = p_new_cl,
    cd = p_new_cd,
    cm = p_new_cm,
    l_over_d = CASE WHEN p_new_cd = 0 THEN NULL ELSE p_new_cl / p_new_cd END,
    measured_at = now()
  WHERE record_id = p_record_id AND is_deleted = false;

  GET DIAGNOSTICS updated_rows = ROW_COUNT;

  IF updated_rows > 0 THEN
    SELECT version_id INTO v_version_id FROM performance_record WHERE record_id = p_record_id;
    INSERT INTO change_log(version_id, actor_id, action, entity_name, entity_id, at, detail)
    VALUES (v_version_id, v_actor_id, 'update', 'performance_record', p_record_id, now(), 'pessimistic_lock_update');
  END IF;

  SELECT xmin::text INTO new_xmin FROM performance_record WHERE record_id = p_record_id;
  RETURN NEXT;
END;
$$;

\echo === Advanced mechanism: optimistic-lock update (xmin token) ===
CREATE OR REPLACE FUNCTION governance.update_performance_record_optimistic(
  p_record_id uuid,
  p_expected_xmin text,
  p_new_cl numeric,
  p_new_cd numeric,
  p_new_cm numeric DEFAULT NULL,
  p_actor_username text DEFAULT 'operator'
)
RETURNS TABLE(success boolean, current_xmin text, message text)
LANGUAGE plpgsql
AS $$
DECLARE
  v_actor_id uuid;
  v_version_id uuid;
  v_rows integer;
BEGIN
  v_actor_id := governance.get_or_create_actor_id(p_actor_username);

  UPDATE performance_record
  SET
    cl = p_new_cl,
    cd = p_new_cd,
    cm = p_new_cm,
    l_over_d = CASE WHEN p_new_cd = 0 THEN NULL ELSE p_new_cl / p_new_cd END,
    measured_at = now()
  WHERE record_id = p_record_id
    AND is_deleted = false
    AND xmin::text = p_expected_xmin;

  GET DIAGNOSTICS v_rows = ROW_COUNT;

  SELECT xmin::text, version_id INTO current_xmin, v_version_id
  FROM performance_record
  WHERE record_id = p_record_id;

  IF v_rows = 1 THEN
    INSERT INTO change_log(version_id, actor_id, action, entity_name, entity_id, at, detail)
    VALUES (v_version_id, v_actor_id, 'update', 'performance_record', p_record_id, now(), 'optimistic_lock_update');
    success := true;
    message := 'update success';
  ELSE
    success := false;
    message := 'concurrency conflict: stale xmin';
  END IF;

  RETURN NEXT;
END;
$$;

\echo === Advanced mechanism validation ===
SELECT count(*) AS current_valid_versions FROM public.v_current_airfoil_version;

