CREATE OR REPLACE FUNCTION airfoil_db.get_airfoil_geometry(
  p_airfoil_code text,
  p_version_no integer DEFAULT NULL
)
RETURNS TABLE (
  airfoil_code text,
  version_no integer,
  surface text,
  seq integer,
  x double precision,
  y double precision,
  z double precision,
  tag text
)
LANGUAGE sql
STABLE
AS $$
WITH a AS (
  SELECT airfoil_id, airfoil_code
  FROM airfoil_db.airfoil
  WHERE airfoil_code = p_airfoil_code
  LIMIT 1
),
v AS (
  SELECT version_id, version_no
  FROM airfoil_db.airfoil_version
  WHERE airfoil_id = (SELECT airfoil_id FROM a)
    AND (p_version_no IS NULL OR version_no = p_version_no)
  ORDER BY version_no DESC
  LIMIT 1
)
SELECT
  (SELECT airfoil_code FROM a) AS airfoil_code,
  v.version_no,
  c.surface,
  c.seq,
  c.x,
  c.y,
  c.z,
  c.tag
FROM v
JOIN airfoil_db.airfoil_coordinate c ON c.version_id = v.version_id
ORDER BY c.surface, c.seq;
$$;

CREATE OR REPLACE FUNCTION airfoil_db.find_airfoils_by_condition(
  p_reynolds double precision,
  p_mach double precision DEFAULT NULL,
  p_aoa_deg double precision DEFAULT NULL,
  p_min_cl double precision DEFAULT NULL,
  p_max_cd double precision DEFAULT NULL,
  p_min_ldr double precision DEFAULT NULL,
  p_only_latest boolean DEFAULT true
)
RETURNS TABLE (
  airfoil_code text,
  airfoil_name text,
  version_no integer,
  reynolds double precision,
  mach double precision,
  aoa_deg double precision,
  cl double precision,
  cd double precision,
  ldr double precision
)
LANGUAGE sql
STABLE
AS $$
WITH latest AS (
  SELECT v.airfoil_id, max(v.version_no) AS version_no
  FROM airfoil_db.airfoil_version v
  GROUP BY v.airfoil_id
),
v AS (
  SELECT v.version_id, v.airfoil_id, v.version_no
  FROM airfoil_db.airfoil_version v
  LEFT JOIN latest l ON l.airfoil_id = v.airfoil_id
  WHERE (p_only_latest = false OR v.version_no = l.version_no)
)
SELECT
  a.airfoil_code,
  a.airfoil_name,
  v.version_no,
  p.reynolds,
  p.mach,
  p.aoa_deg,
  p.cl,
  p.cd,
  COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) AS ldr
FROM v
JOIN airfoil_db.airfoil a ON a.airfoil_id = v.airfoil_id
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id
WHERE p.reynolds = p_reynolds
  AND p.mach IS NOT DISTINCT FROM p_mach
  AND (p_aoa_deg IS NULL OR p.aoa_deg = p_aoa_deg)
  AND (p_min_cl IS NULL OR p.cl >= p_min_cl)
  AND (p_max_cd IS NULL OR p.cd <= p_max_cd)
  AND (p_min_ldr IS NULL OR COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) >= p_min_ldr)
ORDER BY COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) DESC NULLS LAST;
$$;

CREATE OR REPLACE FUNCTION airfoil_db.compare_airfoils_at_reynolds(
  p_airfoil_codes text[],
  p_reynolds double precision,
  p_mach double precision DEFAULT NULL,
  p_only_latest boolean DEFAULT true
)
RETURNS TABLE (
  airfoil_code text,
  airfoil_name text,
  version_no integer,
  aoa_deg double precision,
  cl double precision,
  cd double precision,
  ldr double precision
)
LANGUAGE sql
STABLE
AS $$
WITH a AS (
  SELECT airfoil_id, airfoil_code, airfoil_name
  FROM airfoil_db.airfoil
  WHERE airfoil_code = ANY(p_airfoil_codes)
),
latest AS (
  SELECT v.airfoil_id, max(v.version_no) AS version_no
  FROM airfoil_db.airfoil_version v
  JOIN a ON a.airfoil_id = v.airfoil_id
  GROUP BY v.airfoil_id
),
v AS (
  SELECT v.version_id, v.airfoil_id, v.version_no
  FROM airfoil_db.airfoil_version v
  JOIN a ON a.airfoil_id = v.airfoil_id
  LEFT JOIN latest l ON l.airfoil_id = v.airfoil_id
  WHERE (p_only_latest = false OR v.version_no = l.version_no)
)
SELECT
  a.airfoil_code,
  a.airfoil_name,
  v.version_no,
  p.aoa_deg,
  p.cl,
  p.cd,
  COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) AS ldr
FROM v
JOIN a ON a.airfoil_id = v.airfoil_id
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id
WHERE p.reynolds = p_reynolds
  AND p.mach IS NOT DISTINCT FROM p_mach
ORDER BY a.airfoil_code, p.aoa_deg;
$$;

CREATE OR REPLACE FUNCTION airfoil_db.get_airfoil_performance_across_versions(
  p_airfoil_code text,
  p_reynolds double precision,
  p_aoa_deg double precision,
  p_mach double precision DEFAULT NULL
)
RETURNS TABLE (
  airfoil_code text,
  version_no integer,
  status text,
  reynolds double precision,
  mach double precision,
  aoa_deg double precision,
  cl double precision,
  cd double precision,
  ldr double precision
)
LANGUAGE sql
STABLE
AS $$
WITH a AS (
  SELECT airfoil_id, airfoil_code
  FROM airfoil_db.airfoil
  WHERE airfoil_code = p_airfoil_code
  LIMIT 1
),
v AS (
  SELECT version_id, version_no, status
  FROM airfoil_db.airfoil_version
  WHERE airfoil_id = (SELECT airfoil_id FROM a)
)
SELECT
  (SELECT airfoil_code FROM a) AS airfoil_code,
  v.version_no,
  v.status,
  p.reynolds,
  p.mach,
  p.aoa_deg,
  p.cl,
  p.cd,
  COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) AS ldr
FROM v
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id
WHERE p.reynolds = p_reynolds
  AND p.mach IS NOT DISTINCT FROM p_mach
  AND p.aoa_deg = p_aoa_deg
ORDER BY v.version_no;
$$;

CREATE OR REPLACE FUNCTION airfoil_db.compare_airfoil_versions(
  p_airfoil_code text,
  p_reynolds double precision,
  p_aoa_deg double precision,
  p_version_no_a integer,
  p_version_no_b integer,
  p_mach double precision DEFAULT NULL
)
RETURNS TABLE (
  airfoil_code text,
  reynolds double precision,
  mach double precision,
  aoa_deg double precision,
  version_no_a integer,
  cl_a double precision,
  cd_a double precision,
  ldr_a double precision,
  version_no_b integer,
  cl_b double precision,
  cd_b double precision,
  ldr_b double precision,
  delta_cl double precision,
  delta_cd double precision,
  delta_ldr double precision
)
LANGUAGE sql
STABLE
AS $$
WITH a AS (
  SELECT airfoil_id, airfoil_code
  FROM airfoil_db.airfoil
  WHERE airfoil_code = p_airfoil_code
  LIMIT 1
),
va AS (
  SELECT version_id, version_no
  FROM airfoil_db.airfoil_version
  WHERE airfoil_id = (SELECT airfoil_id FROM a)
    AND version_no = p_version_no_a
  LIMIT 1
),
vb AS (
  SELECT version_id, version_no
  FROM airfoil_db.airfoil_version
  WHERE airfoil_id = (SELECT airfoil_id FROM a)
    AND version_no = p_version_no_b
  LIMIT 1
),
pa AS (
  SELECT
    p.cl,
    p.cd,
    COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) AS ldr
  FROM va
  LEFT JOIN airfoil_db.airfoil_performance p
    ON p.version_id = va.version_id
   AND p.reynolds = p_reynolds
   AND p.aoa_deg = p_aoa_deg
   AND p.mach IS NOT DISTINCT FROM p_mach
  LIMIT 1
),
pb AS (
  SELECT
    p.cl,
    p.cd,
    COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0)) AS ldr
  FROM vb
  LEFT JOIN airfoil_db.airfoil_performance p
    ON p.version_id = vb.version_id
   AND p.reynolds = p_reynolds
   AND p.aoa_deg = p_aoa_deg
   AND p.mach IS NOT DISTINCT FROM p_mach
  LIMIT 1
)
SELECT
  (SELECT airfoil_code FROM a) AS airfoil_code,
  p_reynolds AS reynolds,
  p_mach AS mach,
  p_aoa_deg AS aoa_deg,
  p_version_no_a AS version_no_a,
  pa.cl AS cl_a,
  pa.cd AS cd_a,
  pa.ldr AS ldr_a,
  p_version_no_b AS version_no_b,
  pb.cl AS cl_b,
  pb.cd AS cd_b,
  pb.ldr AS ldr_b,
  (pb.cl - pa.cl) AS delta_cl,
  (pb.cd - pa.cd) AS delta_cd,
  (pb.ldr - pa.ldr) AS delta_ldr
FROM pa, pb;
$$;

CREATE OR REPLACE FUNCTION airfoil_db.list_airfoils_with_anomalies(
  p_only_latest boolean DEFAULT true
)
RETURNS TABLE (
  airfoil_code text,
  airfoil_name text,
  version_no integer,
  anomaly_count bigint,
  last_detected_at timestamptz
)
LANGUAGE sql
STABLE
AS $$
WITH latest AS (
  SELECT v.airfoil_id, max(v.version_no) AS version_no
  FROM airfoil_db.airfoil_version v
  GROUP BY v.airfoil_id
),
v AS (
  SELECT v.version_id, v.airfoil_id, v.version_no
  FROM airfoil_db.airfoil_version v
  LEFT JOIN latest l ON l.airfoil_id = v.airfoil_id
  WHERE (p_only_latest = false OR v.version_no = l.version_no)
),
ar AS (
  SELECT version_id, count(*)::bigint AS anomaly_count, max(detected_at) AS last_detected_at
  FROM airfoil_db.anomaly_record
  GROUP BY version_id
)
SELECT
  a.airfoil_code,
  a.airfoil_name,
  v.version_no,
  COALESCE(ar.anomaly_count, 0) AS anomaly_count,
  ar.last_detected_at
FROM v
JOIN airfoil_db.airfoil a ON a.airfoil_id = v.airfoil_id
LEFT JOIN ar ON ar.version_id = v.version_id
WHERE COALESCE(ar.anomaly_count, 0) > 0
ORDER BY COALESCE(ar.anomaly_count, 0) DESC, a.airfoil_code;
$$;
