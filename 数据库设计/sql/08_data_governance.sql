\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS governance;

\echo === Governance: anomaly rules baseline ===
INSERT INTO anomaly_rule(rule_code, description, severity, is_enabled)
VALUES
  ('negative_cd', 'Cd < 0', 'high', true),
  ('extreme_ld', '|L/D| > 300', 'medium', true),
  ('extreme_cl', '|Cl| > 3', 'medium', true),
  ('jump_cl', 'same version/reynolds adjacent alpha delta Cl > 1.2', 'medium', true)
ON CONFLICT (rule_code) DO UPDATE
SET
  description = EXCLUDED.description,
  severity = EXCLUDED.severity,
  is_enabled = EXCLUDED.is_enabled;

\echo === Governance: reusable views for source/version trace ===
CREATE OR REPLACE VIEW governance.v_data_source_summary AS
SELECT
  ds.source_type,
  ds.provider,
  count(DISTINCT a.airfoil_id) AS airfoil_count,
  count(DISTINCT av.version_id) AS version_count,
  count(DISTINCT pr.record_id) AS performance_count
FROM data_source ds
LEFT JOIN airfoil a ON a.source_id = ds.source_id
LEFT JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
LEFT JOIN performance_record pr ON pr.version_id = av.version_id
GROUP BY ds.source_type, ds.provider
ORDER BY ds.source_type, ds.provider;

CREATE OR REPLACE VIEW governance.v_performance_version_trace AS
SELECT
  a.airfoil_code,
  a.name AS airfoil_name,
  av.version_no,
  av.version_type,
  av.status AS version_status,
  av.is_current,
  av.created_at AS version_created_at,
  av.invalidated_at,
  ec.alpha_deg,
  ec.reynolds_number,
  pr.record_id,
  pr.cl,
  pr.cd,
  COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
  pr.source_type,
  pr.is_anomaly
FROM airfoil a
JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
JOIN performance_record pr ON pr.version_id = av.version_id
JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
WHERE a.is_deleted = false
  AND av.is_deleted = false
  AND pr.is_deleted = false;

\echo === Governance: anomaly detection & landing function ===
CREATE OR REPLACE FUNCTION governance.detect_performance_anomalies(
  p_only_current boolean DEFAULT false
)
RETURNS TABLE (
  inserted_records bigint,
  marked_performance_rows bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_inserted bigint := 0;
  v_marked bigint := 0;
BEGIN
  WITH base AS (
    SELECT
      pr.record_id,
      pr.version_id,
      pr.cl,
      pr.cd,
      COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
      ec.alpha_deg,
      ec.reynolds_number,
      av.is_current
    FROM performance_record pr
    JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
    JOIN airfoil_version av ON av.version_id = pr.version_id
    WHERE pr.is_deleted = false
      AND av.is_deleted = false
      AND av.status = 'valid'
      AND (p_only_current = false OR av.is_current = true)
  ),
  jump_candidates AS (
    SELECT
      b.record_id,
      abs(
        b.cl - lag(b.cl) OVER (
          PARTITION BY b.version_id, b.reynolds_number
          ORDER BY b.alpha_deg
        )
      ) AS delta_cl
    FROM base b
  ),
  flagged AS (
    SELECT b.record_id, b.version_id, 'negative_cd'::text AS rule_code
    FROM base b
    WHERE b.cd < 0
    UNION
    SELECT b.record_id, b.version_id, 'extreme_ld'::text AS rule_code
    FROM base b
    WHERE abs(b.l_over_d) > 300
    UNION
    SELECT b.record_id, b.version_id, 'extreme_cl'::text AS rule_code
    FROM base b
    WHERE abs(b.cl) > 3
    UNION
    SELECT j.record_id, b.version_id, 'jump_cl'::text AS rule_code
    FROM jump_candidates j
    JOIN base b ON b.record_id = j.record_id
    WHERE j.delta_cl IS NOT NULL AND j.delta_cl > 1.2
  ),
  ins AS (
    INSERT INTO anomaly_record(version_id, record_id, rule_id, status, details, detected_at)
    SELECT
      f.version_id,
      f.record_id,
      r.rule_id,
      'open',
      'auto_detected_by=governance.detect_performance_anomalies',
      now()
    FROM flagged f
    JOIN anomaly_rule r ON r.rule_code = f.rule_code AND r.is_enabled = true
    LEFT JOIN anomaly_record ar
      ON ar.version_id = f.version_id
      AND ar.record_id = f.record_id
      AND ar.rule_id = r.rule_id
      AND ar.status = 'open'
    WHERE ar.anomaly_id IS NULL
    RETURNING anomaly_id
  )
  SELECT count(*) INTO v_inserted FROM ins;

  UPDATE performance_record pr
  SET is_anomaly = true
  WHERE pr.is_deleted = false
    AND pr.is_anomaly = false
    AND EXISTS (
      SELECT 1 FROM anomaly_record ar
      WHERE ar.record_id = pr.record_id
    );
  GET DIAGNOSTICS v_marked = ROW_COUNT;

  RETURN QUERY SELECT v_inserted, v_marked;
END;
$$;

\echo === Governance: deletion policy (hard delete is blocked for core data) ===
CREATE OR REPLACE FUNCTION governance.prevent_core_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'Physical delete is forbidden on %, use soft-delete function instead.', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_delete_airfoil ON airfoil;
CREATE TRIGGER trg_block_delete_airfoil
BEFORE DELETE ON airfoil
FOR EACH ROW EXECUTE FUNCTION governance.prevent_core_delete();

DROP TRIGGER IF EXISTS trg_block_delete_airfoil_version ON airfoil_version;
CREATE TRIGGER trg_block_delete_airfoil_version
BEFORE DELETE ON airfoil_version
FOR EACH ROW EXECUTE FUNCTION governance.prevent_core_delete();

DROP TRIGGER IF EXISTS trg_block_delete_coordinate_point ON coordinate_point;
CREATE TRIGGER trg_block_delete_coordinate_point
BEFORE DELETE ON coordinate_point
FOR EACH ROW EXECUTE FUNCTION governance.prevent_core_delete();

DROP TRIGGER IF EXISTS trg_block_delete_performance_record ON performance_record;
CREATE TRIGGER trg_block_delete_performance_record
BEFORE DELETE ON performance_record
FOR EACH ROW EXECUTE FUNCTION governance.prevent_core_delete();

\echo === Governance: soft-delete function ===
CREATE OR REPLACE FUNCTION governance.soft_delete_airfoil(
  p_airfoil_code text,
  p_actor_username text DEFAULT 'importer',
  p_reason text DEFAULT 'soft_delete'
)
RETURNS TABLE (
  affected_airfoil bigint,
  affected_versions bigint,
  affected_coordinates bigint,
  affected_performance bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_airfoil_id uuid;
  v_actor_id uuid;
  v_count bigint;
  c_airfoil bigint := 0;
  c_versions bigint := 0;
  c_coordinates bigint := 0;
  c_performance bigint := 0;
BEGIN
  SELECT airfoil_id INTO v_airfoil_id
  FROM airfoil
  WHERE airfoil_code = p_airfoil_code
  LIMIT 1;

  IF v_airfoil_id IS NULL THEN
    RAISE EXCEPTION 'airfoil_code % not found', p_airfoil_code;
  END IF;

  SELECT user_id INTO v_actor_id
  FROM user_account
  WHERE username = p_actor_username
  LIMIT 1;

  IF v_actor_id IS NULL THEN
    INSERT INTO user_account(username, role) VALUES (p_actor_username, 'operator')
    RETURNING user_id INTO v_actor_id;
  END IF;

  UPDATE airfoil
  SET is_deleted = true, updated_at = now()
  WHERE airfoil_id = v_airfoil_id AND is_deleted = false;
  GET DIAGNOSTICS c_airfoil = ROW_COUNT;

  UPDATE airfoil_version
  SET is_deleted = true, status = 'invalid', is_current = false, invalidated_at = now()
  WHERE airfoil_id = v_airfoil_id AND is_deleted = false;
  GET DIAGNOSTICS c_versions = ROW_COUNT;

  UPDATE coordinate_point cp
  SET is_deleted = true
  FROM airfoil_version av
  WHERE cp.version_id = av.version_id
    AND av.airfoil_id = v_airfoil_id
    AND cp.is_deleted = false;
  GET DIAGNOSTICS c_coordinates = ROW_COUNT;

  UPDATE performance_record pr
  SET is_deleted = true
  FROM airfoil_version av
  WHERE pr.version_id = av.version_id
    AND av.airfoil_id = v_airfoil_id
    AND pr.is_deleted = false;
  GET DIAGNOSTICS c_performance = ROW_COUNT;

  INSERT INTO change_log(version_id, actor_id, action, entity_name, entity_id, at, detail)
  SELECT
    av.version_id,
    v_actor_id,
    'invalidate',
    'airfoil',
    v_airfoil_id,
    now(),
    p_reason
  FROM airfoil_version av
  WHERE av.airfoil_id = v_airfoil_id;

  RETURN QUERY
  SELECT c_airfoil, c_versions, c_coordinates, c_performance;
END;
$$;

\echo === Governance validation run (detection and summaries) ===
SELECT * FROM governance.detect_performance_anomalies(false);

SELECT
  (SELECT count(*) FROM anomaly_rule) AS anomaly_rule_count,
  (SELECT count(*) FROM anomaly_record) AS anomaly_record_count,
  (SELECT count(*) FROM performance_record WHERE is_anomaly = true) AS perf_is_anomaly_count;

SELECT * FROM governance.v_data_source_summary ORDER BY source_type, provider;

