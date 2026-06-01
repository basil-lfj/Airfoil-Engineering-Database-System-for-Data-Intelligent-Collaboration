CREATE SCHEMA IF NOT EXISTS airfoil_db;

CREATE TABLE IF NOT EXISTS airfoil_db.map_airfoil (
  src_airfoil_id uuid PRIMARY KEY,
  dst_airfoil_id bigint NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS airfoil_db.map_version (
  src_version_id uuid PRIMARY KEY,
  dst_version_id bigint NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS airfoil_db.map_perf (
  src_record_id uuid PRIMARY KEY,
  dst_perf_id bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS airfoil_db.map_rule (
  src_rule_id uuid PRIMARY KEY,
  dst_rule_id bigint NOT NULL
);

TRUNCATE TABLE
  airfoil_db.anomaly_record,
  airfoil_db.anomaly_rule,
  airfoil_db.airfoil_coordinate,
  airfoil_db.airfoil_performance,
  airfoil_db.airfoil_version,
  airfoil_db.airfoil
RESTART IDENTITY;

TRUNCATE TABLE
  airfoil_db.map_rule,
  airfoil_db.map_perf,
  airfoil_db.map_version,
  airfoil_db.map_airfoil;

WITH src AS (
  SELECT
    a.airfoil_id AS src_airfoil_id,
    a.airfoil_code,
    a.name AS airfoil_name,
    a.category,
    a.generation_method,
    a.remark,
    a.source_id
  FROM public.airfoil a
  WHERE a.is_deleted = false
    AND a.airfoil_code IS NOT NULL
),
ins AS (
  INSERT INTO airfoil_db.airfoil (airfoil_code, airfoil_name, category, source, generation_method, remark, created_at, updated_at)
  SELECT
    s.airfoil_code,
    COALESCE(s.airfoil_name, s.airfoil_code) AS airfoil_name,
    s.category,
    s.source_id::text,
    s.generation_method,
    s.remark,
    now(),
    now()
  FROM src s
  RETURNING airfoil_id, airfoil_code
)
INSERT INTO airfoil_db.map_airfoil (src_airfoil_id, dst_airfoil_id)
SELECT s.src_airfoil_id, i.airfoil_id
FROM src s
JOIN ins i ON i.airfoil_code = s.airfoil_code;

WITH srcv AS (
  SELECT
    av.version_id AS src_version_id,
    av.airfoil_id AS src_airfoil_id,
    av.version_no,
    av.version_type,
    av.status,
    av.change_note,
    av.created_by,
    av.created_at
  FROM public.airfoil_version av
  WHERE av.is_deleted = false
),
m AS (
  SELECT
    srcv.*,
    ma.dst_airfoil_id
  FROM srcv
  JOIN airfoil_db.map_airfoil ma ON ma.src_airfoil_id = srcv.src_airfoil_id
),
ins AS (
  INSERT INTO airfoil_db.airfoil_version (airfoil_id, version_no, parent_version_id, change_note, data_source, status, created_by, created_at)
  SELECT
    m.dst_airfoil_id,
    m.version_no,
    NULL,
    m.change_note,
    m.version_type,
    CASE
      WHEN m.status = 'valid' THEN 'released'
      WHEN m.status IS NULL THEN 'draft'
      ELSE 'archived'
    END,
    m.created_by::text,
    COALESCE(m.created_at, now())
  FROM m
  RETURNING version_id, airfoil_id, version_no
)
INSERT INTO airfoil_db.map_version (src_version_id, dst_version_id)
SELECT m.src_version_id, i.version_id
FROM m
JOIN ins i
  ON i.airfoil_id = m.dst_airfoil_id
 AND i.version_no = m.version_no;

UPDATE airfoil_db.airfoil_version v
SET parent_version_id = pv.version_id
FROM airfoil_db.airfoil_version pv
WHERE pv.airfoil_id = v.airfoil_id
  AND pv.version_no = v.version_no - 1;

INSERT INTO airfoil_db.airfoil_coordinate (version_id, surface, seq, x, y, z, tag)
SELECT
  mv.dst_version_id,
  lower(cp.surface),
  cp.point_order,
  cp.x::double precision,
  cp.y::double precision,
  NULL::double precision,
  NULL::text
FROM public.coordinate_point cp
JOIN airfoil_db.map_version mv ON mv.src_version_id = cp.version_id
WHERE cp.is_deleted = false;

WITH srcp AS (
  SELECT
    pr.record_id,
    mv.dst_version_id AS version_id,
    ec.reynolds_number::double precision AS reynolds,
    ec.alpha_deg::double precision AS aoa_deg,
    ec.mach::double precision AS mach,
    pr.cl::double precision AS cl,
    pr.cd::double precision AS cd,
    pr.cm::double precision AS cm,
    pr.l_over_d::double precision AS ldr,
    pr.source_type AS source_run,
    COALESCE(pr.measured_at, now()) AS created_at
  FROM public.performance_record pr
  JOIN public.experiment_condition ec ON ec.condition_id = pr.condition_id
  JOIN airfoil_db.map_version mv ON mv.src_version_id = pr.version_id
  WHERE pr.is_deleted = false
),
dedup AS (
  SELECT DISTINCT ON (version_id, reynolds, aoa_deg, mach)
    record_id, version_id, reynolds, aoa_deg, mach, cl, cd, cm, ldr, source_run, created_at
  FROM srcp
  ORDER BY version_id, reynolds, aoa_deg, mach, created_at DESC
),
ins AS (
  INSERT INTO airfoil_db.airfoil_performance (version_id, reynolds, aoa_deg, mach, cl, cd, cm, ldr, source_run, created_at)
  SELECT
    d.version_id, d.reynolds, d.aoa_deg, d.mach, d.cl, d.cd, d.cm, d.ldr, d.source_run, d.created_at
  FROM dedup d
  RETURNING perf_id, version_id, reynolds, aoa_deg, mach
)
INSERT INTO airfoil_db.map_perf (src_record_id, dst_perf_id)
SELECT DISTINCT
  s.record_id,
  p.perf_id
FROM srcp s
JOIN airfoil_db.airfoil_performance p
  ON p.version_id = s.version_id
 AND p.reynolds = s.reynolds
 AND p.aoa_deg = s.aoa_deg
 AND p.mach IS NOT DISTINCT FROM s.mach;

INSERT INTO airfoil_db.anomaly_rule (rule_code, rule_name, rule_type, params, enabled)
VALUES
  ('negative_cd', '阻力系数为负', 'cd_negative', '{}'::jsonb, true),
  ('extreme_ld', '升阻比异常偏离', 'ldr_outlier', '{"k":3.0,"min_points":8}'::jsonb, true),
  ('jump_cl', '邻近攻角性能突变', 'aoa_jump', '{"max_dcl_per_deg":0.8,"max_daoa_deg":2.0}'::jsonb, true),
  ('extreme_cl', '升力系数异常偏离', 'ldr_outlier', '{"k":3.0,"min_points":8,"target":"cl"}'::jsonb, true)
ON CONFLICT (rule_code) DO NOTHING;

INSERT INTO airfoil_db.map_rule (src_rule_id, dst_rule_id)
SELECT
  r.rule_id AS src_rule_id,
  ar.rule_id AS dst_rule_id
FROM public.anomaly_rule r
JOIN airfoil_db.anomaly_rule ar ON ar.rule_code = r.rule_code;

INSERT INTO airfoil_db.anomaly_record (rule_id, version_id, perf_id, severity, message, details, detected_at)
SELECT DISTINCT
  mr.dst_rule_id,
  mv.dst_version_id,
  mp.dst_perf_id,
  CASE
    WHEN pr.severity IN ('info','warning','critical') THEN pr.severity
    ELSE 'warning'
  END,
  COALESCE(pr.description, '异常记录'),
  jsonb_build_object(
    'status', r.status,
    'details', r.details,
    'source_anomaly_id', r.anomaly_id::text,
    'source_rule_id', r.rule_id::text,
    'source_record_id', r.record_id::text
  ),
  COALESCE(r.detected_at, now())
FROM public.anomaly_record r
JOIN airfoil_db.map_version mv ON mv.src_version_id = r.version_id
JOIN airfoil_db.map_rule mr ON mr.src_rule_id = r.rule_id
LEFT JOIN airfoil_db.map_perf mp ON mp.src_record_id = r.record_id
LEFT JOIN public.anomaly_rule pr ON pr.rule_id = r.rule_id
WHERE mp.dst_perf_id IS NOT NULL
ON CONFLICT (rule_id, perf_id) DO NOTHING;

INSERT INTO airfoil_db.anomaly_record (rule_id, version_id, perf_id, severity, message, details, detected_at)
SELECT DISTINCT
  mr.dst_rule_id,
  mv.dst_version_id,
  NULL::bigint,
  CASE
    WHEN pr.severity IN ('info','warning','critical') THEN pr.severity
    ELSE 'warning'
  END,
  COALESCE(pr.description, '异常记录'),
  jsonb_build_object(
    'status', r.status,
    'details', r.details,
    'source_anomaly_id', r.anomaly_id::text,
    'source_rule_id', r.rule_id::text,
    'source_record_id', r.record_id::text
  ),
  COALESCE(r.detected_at, now())
FROM public.anomaly_record r
JOIN airfoil_db.map_version mv ON mv.src_version_id = r.version_id
JOIN airfoil_db.map_rule mr ON mr.src_rule_id = r.rule_id
LEFT JOIN airfoil_db.map_perf mp ON mp.src_record_id = r.record_id
LEFT JOIN public.anomaly_rule pr ON pr.rule_id = r.rule_id
WHERE mp.dst_perf_id IS NULL;
