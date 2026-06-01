\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS staging;

DROP TABLE IF EXISTS staging.airfoils_raw;
DROP TABLE IF EXISTS staging.data_versions_raw;
DROP TABLE IF EXISTS staging.coordinates_raw;
DROP TABLE IF EXISTS staging.performance_raw;
DROP TABLE IF EXISTS staging.anomalies_raw;

CREATE TABLE staging.airfoils_raw (
  airfoil_id text,
  name text,
  geom_source text,
  geom_source_url text,
  family text,
  is_generated integer
);

CREATE TABLE staging.data_versions_raw (
  version_id text,
  airfoil_id text,
  version_no integer,
  version_type text,
  geom_source text,
  geom_source_url text
);

CREATE TABLE staging.coordinates_raw (
  airfoil_id text,
  version_id text,
  point_order integer,
  x numeric,
  y numeric,
  surface text,
  geom_source text,
  geom_source_url text,
  is_generated integer,
  raw_file text
);

CREATE TABLE staging.performance_raw (
  airfoil_id text,
  version_id text,
  alpha_deg numeric,
  reynolds_number numeric,
  cl numeric,
  cd numeric,
  perf_source text,
  perf_rule text,
  is_anomaly integer
);

CREATE TABLE staging.anomalies_raw (
  anomaly_id integer,
  airfoil_id text,
  version_id text,
  alpha_deg numeric,
  reynolds_number numeric,
  rule text,
  cl numeric,
  cd numeric,
  ld numeric
);

\echo === Loading CSV into staging (client-side copy) ===
\copy staging.airfoils_raw FROM 'project_data/output/airfoils.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
\copy staging.data_versions_raw FROM 'project_data/output/data_versions.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
\copy staging.coordinates_raw FROM 'project_data/output/coordinates.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
\copy staging.performance_raw FROM 'project_data/output/performance.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
\copy staging.anomalies_raw FROM 'project_data/output/anomalies.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

\echo === Pre-checks (staging row counts) ===
SELECT
  (SELECT count(*) FROM staging.airfoils_raw) AS airfoils_rows,
  (SELECT count(*) FROM staging.data_versions_raw) AS versions_rows,
  (SELECT count(*) FROM staging.coordinates_raw) AS coordinates_rows,
  (SELECT count(*) FROM staging.performance_raw) AS performance_rows,
  (SELECT count(*) FROM staging.anomalies_raw) AS anomalies_rows;

\echo === Preparing target tables (truncate) ===
TRUNCATE TABLE
  anomaly_record,
  anomaly_rule,
  performance_record,
  experiment_condition,
  coordinate_point,
  airfoil_version,
  airfoil,
  query_log,
  change_log,
  nl2sql_audit,
  result_explain_audit,
  user_account,
  data_source
RESTART IDENTITY CASCADE;

\echo === Insert base users & sources ===
INSERT INTO user_account(username, role) VALUES
  ('importer', 'system')
RETURNING user_id \gset

INSERT INTO data_source(source_type, provider, dataset_name, reference) VALUES
  ('real', 'UIUC', 'UIUC Airfoil Coordinates Database', (SELECT geom_source_url FROM staging.airfoils_raw WHERE geom_source_url IS NOT NULL LIMIT 1)),
  ('synthetic', 'generator', 'synthetic_dataset', 'synthetic_aero_model_v1');

WITH s AS (
  SELECT
    (SELECT source_id FROM data_source WHERE source_type='real' AND provider='UIUC' LIMIT 1) AS uiuc_source_id,
    (SELECT source_id FROM data_source WHERE source_type='synthetic' AND provider='generator' LIMIT 1) AS syn_source_id
)
INSERT INTO airfoil(airfoil_code, name, family, is_generated, category, source_id, generation_method, remark)
SELECT
  r.airfoil_id AS airfoil_code,
  r.name,
  NULLIF(r.family, 'unknown') AS family,
  (r.is_generated <> 0) AS is_generated,
  NULL AS category,
  CASE WHEN r.is_generated <> 0 THEN s.syn_source_id ELSE s.uiuc_source_id END AS source_id,
  CASE WHEN r.is_generated <> 0 THEN 'generated' ELSE 'imported' END AS generation_method,
  r.geom_source || ' ' || r.geom_source_url AS remark
FROM staging.airfoils_raw r
CROSS JOIN s;

\echo === Insert versions ===
WITH v AS (
  SELECT
    r.airfoil_id,
    r.version_no,
    r.version_id AS version_code,
    r.version_type AS raw_version_type,
    CASE
      WHEN r.version_type ILIKE 'imported%' THEN 'imported'
      WHEN r.version_type ILIKE 'generated%' THEN 'synthetic'
      WHEN r.version_type ILIKE 'synthetic%' THEN 'synthetic'
      WHEN r.version_type ILIKE 'revised%' THEN 'revised'
      ELSE 'revised'
    END AS version_type_mapped
  FROM staging.data_versions_raw r
)
INSERT INTO airfoil_version(airfoil_id, version_no, version_type, status, is_current, change_note, created_by)
SELECT
  a.airfoil_id,
  v.version_no,
  v.version_type_mapped,
  'valid',
  false,
  'version_code=' || v.version_code || '; raw_version_type=' || v.raw_version_type,
  :'user_id'::uuid
FROM v
JOIN airfoil a ON a.airfoil_code = v.airfoil_id;

UPDATE airfoil_version av
SET is_current = (av.version_no = mx.max_version_no)
FROM (
  SELECT airfoil_id, max(version_no) AS max_version_no
  FROM airfoil_version
  GROUP BY airfoil_id
) mx
WHERE av.airfoil_id = mx.airfoil_id;

\echo === Insert coordinate points ===
WITH coord AS (
  SELECT
    c.version_id AS version_code,
    c.point_order,
    c.x,
    c.y,
    c.surface
  FROM staging.coordinates_raw c
),
map AS (
  SELECT
    dv.version_id AS version_code,
    dv.airfoil_id AS airfoil_code,
    dv.version_no
  FROM staging.data_versions_raw dv
)
INSERT INTO coordinate_point(version_id, surface, point_order, x, y)
SELECT
  av.version_id,
  c.surface,
  c.point_order,
  c.x,
  c.y
FROM coord c
JOIN map m ON m.version_code = c.version_code
JOIN airfoil a ON a.airfoil_code = m.airfoil_code
JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id AND av.version_no = m.version_no
ON CONFLICT (version_id, surface, point_order) DO NOTHING;

\echo === Insert experiment conditions ===
INSERT INTO experiment_condition(alpha_deg, reynolds_number)
SELECT DISTINCT p.alpha_deg, p.reynolds_number
FROM staging.performance_raw p;

\echo === Insert performance records ===
WITH map AS (
  SELECT
    dv.version_id AS version_code,
    dv.airfoil_id AS airfoil_code,
    dv.version_no
  FROM staging.data_versions_raw dv
)
INSERT INTO performance_record(version_id, condition_id, cl, cd, l_over_d, source_type, is_anomaly)
SELECT
  av.version_id,
  ec.condition_id,
  p.cl,
  p.cd,
  CASE WHEN p.cd = 0 THEN NULL ELSE (p.cl / p.cd) END AS l_over_d,
  CASE WHEN p.perf_source ILIKE 'synthetic%' THEN 'synthetic' ELSE 'real' END AS source_type,
  ((p.is_anomaly <> 0) OR (p.cd < 0)) AS is_anomaly
FROM staging.performance_raw p
JOIN map m ON m.version_code = p.version_id
JOIN airfoil a ON a.airfoil_code = m.airfoil_code
JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id AND av.version_no = m.version_no
JOIN experiment_condition ec ON ec.alpha_deg = p.alpha_deg AND ec.reynolds_number = p.reynolds_number
ON CONFLICT (version_id, condition_id) DO NOTHING;

\echo === Insert anomaly rules ===
INSERT INTO anomaly_rule(rule_code, description, severity, is_enabled)
SELECT
  replace(r.rule, 'rule:', '') AS rule_code,
  r.rule AS description,
  CASE
    WHEN r.rule ILIKE '%negative_cd%' THEN 'high'
    WHEN r.rule ILIKE '%extreme_%' THEN 'medium'
    WHEN r.rule ILIKE '%jump_%' THEN 'medium'
    ELSE 'low'
  END AS severity,
  true
FROM (SELECT DISTINCT rule FROM staging.anomalies_raw) r
ON CONFLICT (rule_code) DO NOTHING;

\echo === Insert anomaly records (link to performance_record) ===
WITH map AS (
  SELECT
    dv.version_id AS version_code,
    dv.airfoil_id AS airfoil_code,
    dv.version_no
  FROM staging.data_versions_raw dv
),
target_perf AS (
  SELECT
    a.airfoil_code,
    m.version_code,
    av.version_id AS version_uuid,
    ec.alpha_deg,
    ec.reynolds_number,
    pr.record_id
  FROM map m
  JOIN airfoil a ON a.airfoil_code = m.airfoil_code
  JOIN airfoil_version av ON av.airfoil_id = a.airfoil_id AND av.version_no = m.version_no
  JOIN performance_record pr ON pr.version_id = av.version_id
  JOIN experiment_condition ec ON ec.condition_id = pr.condition_id
)
INSERT INTO anomaly_record(version_id, record_id, rule_id, status, details, detected_at)
SELECT
  tp.version_uuid,
  tp.record_id,
  ar.rule_id,
  'open',
  'alpha=' || an.alpha_deg || '; re=' || an.reynolds_number || '; cl=' || an.cl || '; cd=' || an.cd || '; ld=' || an.ld,
  now()
FROM staging.anomalies_raw an
JOIN anomaly_rule ar ON ar.rule_code = replace(an.rule, 'rule:', '')
JOIN target_perf tp ON tp.airfoil_code = an.airfoil_id
  AND tp.version_code = an.version_id
  AND tp.alpha_deg = an.alpha_deg
  AND tp.reynolds_number = an.reynolds_number;

\echo === Post-checks (target row counts) ===
SELECT
  (SELECT count(*) FROM airfoil) AS airfoils,
  (SELECT count(*) FROM airfoil_version) AS versions,
  (SELECT count(*) FROM coordinate_point) AS coordinate_points,
  (SELECT count(*) FROM experiment_condition) AS conditions,
  (SELECT count(*) FROM performance_record) AS performance_records,
  (SELECT count(*) FROM anomaly_rule) AS anomaly_rules,
  (SELECT count(*) FROM anomaly_record) AS anomaly_records;

\echo === Data quality checks ===
\echo -- Versions without airfoil mapping (should be 0)
SELECT count(*) AS versions_missing_airfoil
FROM staging.data_versions_raw dv
LEFT JOIN airfoil a ON a.airfoil_code = dv.airfoil_id
WHERE a.airfoil_id IS NULL;

\echo -- Coordinate rows without version mapping (should be 0)
SELECT count(*) AS coordinates_missing_version
FROM staging.coordinates_raw c
LEFT JOIN staging.data_versions_raw dv ON dv.version_id = c.version_id
WHERE dv.version_id IS NULL;

\echo -- Performance rows without version mapping (should be 0)
SELECT count(*) AS performance_missing_version
FROM staging.performance_raw p
LEFT JOIN staging.data_versions_raw dv ON dv.version_id = p.version_id
WHERE dv.version_id IS NULL;

\echo -- Anomalies that cannot link to a performance_record (should be 0, may be >0 if performance duplicates missing)
WITH missing AS (
  SELECT an.*
  FROM staging.anomalies_raw an
  LEFT JOIN staging.performance_raw p
    ON p.version_id = an.version_id
    AND p.airfoil_id = an.airfoil_id
    AND p.alpha_deg = an.alpha_deg
    AND p.reynolds_number = an.reynolds_number
  WHERE p.version_id IS NULL
)
SELECT count(*) AS anomalies_missing_performance_row FROM missing;
