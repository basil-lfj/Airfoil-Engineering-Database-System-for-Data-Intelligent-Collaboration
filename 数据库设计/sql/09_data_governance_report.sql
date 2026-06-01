\set ON_ERROR_STOP on

\echo === Governance Report: rule hit ranking ===
SELECT
  arl.rule_code,
  arl.description,
  count(*)::bigint AS hit_count,
  count(DISTINCT ar.version_id)::bigint AS version_covered
FROM anomaly_record ar
JOIN anomaly_rule arl ON arl.rule_id = ar.rule_id
GROUP BY arl.rule_code, arl.description
ORDER BY hit_count DESC, arl.rule_code;

\echo === Governance Report: top airfoils by anomaly volume ===
SELECT
  a.airfoil_code,
  a.name,
  count(*)::bigint AS anomaly_count
FROM anomaly_record ar
JOIN airfoil_version av ON av.version_id = ar.version_id
JOIN airfoil a ON a.airfoil_id = av.airfoil_id
WHERE a.is_deleted = false
GROUP BY a.airfoil_code, a.name
ORDER BY anomaly_count DESC, a.airfoil_code
LIMIT 20;

\echo === Governance Report: source summary ===
SELECT * FROM governance.v_data_source_summary;

\echo === Governance Report: performance trace sample ===
SELECT
  airfoil_code,
  version_no,
  alpha_deg,
  reynolds_number,
  cl,
  cd,
  l_over_d,
  is_anomaly
FROM governance.v_performance_version_trace
ORDER BY airfoil_code, version_no, reynolds_number, alpha_deg
LIMIT 30;

\echo === Governance Report: quality counters ===
SELECT
  (SELECT count(*) FROM performance_record WHERE cd < 0) AS negative_cd_rows,
  (SELECT count(*) FROM performance_record WHERE is_anomaly) AS marked_anomaly_rows,
  (SELECT count(*) FROM anomaly_record) AS anomaly_record_rows,
  (SELECT count(*) FROM anomaly_rule WHERE is_enabled) AS enabled_rules;

