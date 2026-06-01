CREATE OR REPLACE VIEW airfoil_db.v_airfoil_latest_version AS
SELECT v.*
FROM airfoil_db.airfoil_version v
JOIN (
  SELECT airfoil_id, max(version_no) AS max_version_no
  FROM airfoil_db.airfoil_version
  GROUP BY airfoil_id
) x
  ON x.airfoil_id = v.airfoil_id
 AND x.max_version_no = v.version_no;

CREATE OR REPLACE VIEW airfoil_db.v_airfoil_coord_latest AS
SELECT
  a.airfoil_id,
  a.airfoil_code,
  a.airfoil_name,
  v.version_id,
  v.version_no,
  c.coord_id,
  c.surface,
  c.seq,
  c.x,
  c.y,
  c.z,
  c.tag
FROM airfoil_db.airfoil a
JOIN airfoil_db.v_airfoil_latest_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_coordinate c ON c.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_airfoil_perf_latest AS
SELECT
  a.airfoil_id,
  a.airfoil_code,
  a.airfoil_name,
  v.version_id,
  v.version_no,
  p.perf_id,
  p.reynolds,
  p.mach,
  p.aoa_deg,
  p.cl,
  p.cd,
  p.cm,
  p.ldr,
  p.source_run,
  p.created_at
FROM airfoil_db.airfoil a
JOIN airfoil_db.v_airfoil_latest_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_geometry AS
SELECT
  a.airfoil_code,
  v.version_no,
  c.surface,
  c.seq,
  c.x,
  c.y,
  c.z,
  c.tag
FROM airfoil_db.airfoil a
JOIN airfoil_db.airfoil_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_coordinate c ON c.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_performance AS
SELECT
  a.airfoil_code,
  v.version_no,
  p.reynolds,
  p.mach,
  p.aoa_deg,
  p.cl,
  p.cd,
  p.cm,
  p.ldr,
  p.source_run,
  p.created_at
FROM airfoil_db.airfoil a
JOIN airfoil_db.airfoil_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_anomaly AS
SELECT
  a.airfoil_code,
  v.version_no,
  r.rule_code,
  ar.severity,
  ar.message,
  ar.detected_at,
  ar.details
FROM airfoil_db.anomaly_record ar
JOIN airfoil_db.anomaly_rule r ON r.rule_id = ar.rule_id
JOIN airfoil_db.airfoil_version v ON v.version_id = ar.version_id
JOIN airfoil_db.airfoil a ON a.airfoil_id = v.airfoil_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_geometry_latest AS
SELECT
  a.airfoil_code,
  v.version_no,
  c.surface,
  c.seq,
  c.x,
  c.y,
  c.z,
  c.tag
FROM airfoil_db.airfoil a
JOIN airfoil_db.v_airfoil_latest_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_coordinate c ON c.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_performance_latest AS
SELECT
  a.airfoil_code,
  v.version_no,
  p.reynolds,
  p.mach,
  p.aoa_deg,
  p.cl,
  p.cd,
  p.cm,
  p.ldr,
  p.source_run,
  p.created_at
FROM airfoil_db.airfoil a
JOIN airfoil_db.v_airfoil_latest_version v ON v.airfoil_id = a.airfoil_id
JOIN airfoil_db.airfoil_performance p ON p.version_id = v.version_id;

CREATE OR REPLACE VIEW airfoil_db.v_export_anomaly_latest AS
SELECT
  a.airfoil_code,
  v.version_no,
  r.rule_code,
  ar.severity,
  ar.message,
  ar.detected_at,
  ar.details
FROM airfoil_db.anomaly_record ar
JOIN airfoil_db.anomaly_rule r ON r.rule_id = ar.rule_id
JOIN airfoil_db.v_airfoil_latest_version v ON v.version_id = ar.version_id
JOIN airfoil_db.airfoil a ON a.airfoil_id = v.airfoil_id;
