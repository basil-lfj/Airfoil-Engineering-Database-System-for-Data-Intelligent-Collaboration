CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.v_current_airfoil_version AS
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
WHERE
  a.is_deleted = false
  AND av.is_deleted = false
  AND av.status = 'valid'
  AND av.is_current = true;

CREATE OR REPLACE FUNCTION api.get_airfoil_geometry(
  p_airfoil_code text,
  p_only_current boolean DEFAULT true,
  p_version_no integer DEFAULT NULL
)
RETURNS TABLE (
  airfoil_code text,
  version_no integer,
  surface text,
  point_order integer,
  x numeric,
  y numeric
)
LANGUAGE sql
STABLE
AS $$
WITH v AS (
  SELECT
    av.version_id,
    av.version_no,
    a.airfoil_code
  FROM airfoil a
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
  WHERE
    a.airfoil_code = p_airfoil_code
    AND a.is_deleted = false
    AND av.is_deleted = false
    AND av.status = 'valid'
    AND (p_version_no IS NULL OR av.version_no = p_version_no)
    AND (p_version_no IS NOT NULL OR p_only_current = false OR av.is_current = true)
  ORDER BY av.version_no DESC
  LIMIT 1
)
SELECT
  v.airfoil_code,
  v.version_no,
  cp.surface,
  cp.point_order,
  cp.x,
  cp.y
FROM v
JOIN coordinate_point cp ON cp.version_id = v.version_id
WHERE cp.is_deleted = false
ORDER BY cp.surface, cp.point_order;
$$;

CREATE OR REPLACE FUNCTION api.find_airfoils_by_condition(
  p_alpha_deg numeric,
  p_reynolds_number numeric,
  p_min_cl numeric DEFAULT NULL,
  p_max_cd numeric DEFAULT NULL,
  p_min_l_over_d numeric DEFAULT NULL,
  p_only_current boolean DEFAULT true
)
RETURNS TABLE (
  airfoil_code text,
  name text,
  version_no integer,
  cl numeric,
  cd numeric,
  l_over_d numeric,
  source_type text,
  is_anomaly boolean
)
LANGUAGE sql
STABLE
AS $$
WITH c AS (
  SELECT condition_id
  FROM experiment_condition
  WHERE alpha_deg = p_alpha_deg AND reynolds_number = p_reynolds_number
  LIMIT 1
),
v AS (
  SELECT
    a.airfoil_code,
    a.name,
    av.version_id,
    av.version_no
  FROM airfoil a
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
  WHERE
    a.is_deleted = false
    AND av.is_deleted = false
    AND av.status = 'valid'
    AND (p_only_current = false OR av.is_current = true)
)
SELECT
  v.airfoil_code,
  v.name,
  v.version_no,
  pr.cl,
  pr.cd,
  COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
  pr.source_type,
  pr.is_anomaly
FROM v
JOIN performance_record pr ON pr.version_id = v.version_id
JOIN c ON c.condition_id = pr.condition_id
WHERE
  pr.is_deleted = false
  AND (p_min_cl IS NULL OR pr.cl >= p_min_cl)
  AND (p_max_cd IS NULL OR pr.cd <= p_max_cd)
  AND (p_min_l_over_d IS NULL OR COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) >= p_min_l_over_d)
ORDER BY
  COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) DESC NULLS LAST,
  pr.cd ASC NULLS LAST,
  pr.cl DESC NULLS LAST;
$$;

CREATE OR REPLACE FUNCTION api.compare_airfoils_at_reynolds(
  p_airfoil_codes text[],
  p_reynolds_number numeric,
  p_only_current boolean DEFAULT true
)
RETURNS TABLE (
  airfoil_code text,
  version_no integer,
  alpha_deg numeric,
  cl numeric,
  cd numeric,
  l_over_d numeric,
  source_type text,
  is_anomaly boolean
)
LANGUAGE sql
STABLE
AS $$
WITH v AS (
  SELECT
    a.airfoil_code,
    av.version_id,
    av.version_no
  FROM airfoil a
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
  WHERE
    a.airfoil_code = ANY(p_airfoil_codes)
    AND a.is_deleted = false
    AND av.is_deleted = false
    AND av.status = 'valid'
    AND (p_only_current = false OR av.is_current = true)
),
p AS (
  SELECT
    v.airfoil_code,
    v.version_no,
    ec.alpha_deg,
    pr.cl,
    pr.cd,
    COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
    pr.source_type,
    pr.is_anomaly
  FROM v
  JOIN performance_record pr ON pr.version_id = v.version_id
  JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
  WHERE
    pr.is_deleted = false
    AND ec.reynolds_number = p_reynolds_number
)
SELECT *
FROM p
ORDER BY airfoil_code, alpha_deg;
$$;

CREATE OR REPLACE FUNCTION api.get_airfoil_performance_across_versions(
  p_airfoil_code text,
  p_alpha_deg numeric,
  p_reynolds_number numeric
)
RETURNS TABLE (
  airfoil_code text,
  version_no integer,
  version_type text,
  status text,
  is_current boolean,
  cl numeric,
  cd numeric,
  l_over_d numeric,
  source_type text,
  is_anomaly boolean
)
LANGUAGE sql
STABLE
AS $$
WITH c AS (
  SELECT condition_id
  FROM experiment_condition
  WHERE alpha_deg = p_alpha_deg AND reynolds_number = p_reynolds_number
  LIMIT 1
),
v AS (
  SELECT
    a.airfoil_code,
    av.version_id,
    av.version_no,
    av.version_type,
    av.status,
    av.is_current
  FROM airfoil a
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
  WHERE
    a.airfoil_code = p_airfoil_code
    AND a.is_deleted = false
    AND av.is_deleted = false
)
SELECT
  v.airfoil_code,
  v.version_no,
  v.version_type,
  v.status,
  v.is_current,
  pr.cl,
  pr.cd,
  COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d,
  pr.source_type,
  pr.is_anomaly
FROM v
JOIN performance_record pr ON pr.version_id = v.version_id
JOIN c ON c.condition_id = pr.condition_id
WHERE pr.is_deleted = false
ORDER BY v.version_no;
$$;

CREATE OR REPLACE FUNCTION api.compare_airfoil_versions(
  p_airfoil_code text,
  p_alpha_deg numeric,
  p_reynolds_number numeric,
  p_version_no_a integer,
  p_version_no_b integer
)
RETURNS TABLE (
  airfoil_code text,
  alpha_deg numeric,
  reynolds_number numeric,
  version_no_a integer,
  cl_a numeric,
  cd_a numeric,
  l_over_d_a numeric,
  version_no_b integer,
  cl_b numeric,
  cd_b numeric,
  l_over_d_b numeric,
  delta_cl numeric,
  delta_cd numeric,
  delta_l_over_d numeric
)
LANGUAGE sql
STABLE
AS $$
WITH c AS (
  SELECT condition_id
  FROM experiment_condition
  WHERE alpha_deg = p_alpha_deg AND reynolds_number = p_reynolds_number
  LIMIT 1
),
base AS (
  SELECT a.airfoil_id, a.airfoil_code
  FROM airfoil a
  WHERE a.airfoil_code = p_airfoil_code AND a.is_deleted = false
  LIMIT 1
),
va AS (
  SELECT av.version_id, av.version_no
  FROM base b
  JOIN airfoil_version av ON av.airfoil_id = b.airfoil_id
  WHERE av.version_no = p_version_no_a AND av.is_deleted = false
  LIMIT 1
),
vb AS (
  SELECT av.version_id, av.version_no
  FROM base b
  JOIN airfoil_version av ON av.airfoil_id = b.airfoil_id
  WHERE av.version_no = p_version_no_b AND av.is_deleted = false
  LIMIT 1
),
pa AS (
  SELECT
    pr.cl,
    pr.cd,
    COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d
  FROM va
  JOIN performance_record pr ON pr.version_id = va.version_id
  JOIN c ON c.condition_id = pr.condition_id
  WHERE pr.is_deleted = false
  LIMIT 1
),
pb AS (
  SELECT
    pr.cl,
    pr.cd,
    COALESCE(pr.l_over_d, pr.cl / NULLIF(pr.cd, 0)) AS l_over_d
  FROM vb
  JOIN performance_record pr ON pr.version_id = vb.version_id
  JOIN c ON c.condition_id = pr.condition_id
  WHERE pr.is_deleted = false
  LIMIT 1
)
SELECT
  (SELECT airfoil_code FROM base) AS airfoil_code,
  p_alpha_deg AS alpha_deg,
  p_reynolds_number AS reynolds_number,
  p_version_no_a AS version_no_a,
  pa.cl AS cl_a,
  pa.cd AS cd_a,
  pa.l_over_d AS l_over_d_a,
  p_version_no_b AS version_no_b,
  pb.cl AS cl_b,
  pb.cd AS cd_b,
  pb.l_over_d AS l_over_d_b,
  (pb.cl - pa.cl) AS delta_cl,
  (pb.cd - pa.cd) AS delta_cd,
  (pb.l_over_d - pa.l_over_d) AS delta_l_over_d
FROM pa, pb;
$$;

CREATE OR REPLACE FUNCTION api.list_airfoils_with_anomalies(
  p_only_current boolean DEFAULT false
)
RETURNS TABLE (
  airfoil_code text,
  name text,
  anomaly_record_count bigint,
  performance_anomaly_count bigint,
  negative_cd_count bigint,
  total_anomaly_hint bigint
)
LANGUAGE sql
STABLE
AS $$
WITH v AS (
  SELECT
    a.airfoil_id,
    a.airfoil_code,
    a.name,
    av.version_id
  FROM airfoil a
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id
  WHERE
    a.is_deleted = false
    AND av.is_deleted = false
    AND av.status = 'valid'
    AND (p_only_current = false OR av.is_current = true)
),
ar AS (
  SELECT v.airfoil_id, count(*)::bigint AS anomaly_record_count
  FROM v
  JOIN anomaly_record r ON r.version_id = v.version_id
  GROUP BY v.airfoil_id
),
pa AS (
  SELECT v.airfoil_id, count(*)::bigint AS performance_anomaly_count
  FROM v
  JOIN performance_record pr ON pr.version_id = v.version_id
  WHERE pr.is_deleted = false AND pr.is_anomaly = true
  GROUP BY v.airfoil_id
),
neg AS (
  SELECT v.airfoil_id, count(*)::bigint AS negative_cd_count
  FROM v
  JOIN performance_record pr ON pr.version_id = v.version_id
  WHERE pr.is_deleted = false AND pr.cd < 0
  GROUP BY v.airfoil_id
)
SELECT
  v0.airfoil_code,
  v0.name,
  COALESCE(ar.anomaly_record_count, 0) AS anomaly_record_count,
  COALESCE(pa.performance_anomaly_count, 0) AS performance_anomaly_count,
  COALESCE(neg.negative_cd_count, 0) AS negative_cd_count,
  (COALESCE(ar.anomaly_record_count, 0) + COALESCE(pa.performance_anomaly_count, 0) + COALESCE(neg.negative_cd_count, 0)) AS total_anomaly_hint
FROM (
  SELECT DISTINCT airfoil_id, airfoil_code, name FROM v
) v0
LEFT JOIN ar ON ar.airfoil_id = v0.airfoil_id
LEFT JOIN pa ON pa.airfoil_id = v0.airfoil_id
LEFT JOIN neg ON neg.airfoil_id = v0.airfoil_id
WHERE
  COALESCE(ar.anomaly_record_count, 0) > 0
  OR COALESCE(pa.performance_anomaly_count, 0) > 0
  OR COALESCE(neg.negative_cd_count, 0) > 0
ORDER BY total_anomaly_hint DESC, airfoil_code;
$$;

