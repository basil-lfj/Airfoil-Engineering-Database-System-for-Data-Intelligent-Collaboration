BEGIN;

CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_id ON airfoil_version(airfoil_id);
CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil_current ON airfoil_version(airfoil_id) WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_coordinate_point_version_surface_order ON coordinate_point(version_id, surface, point_order);

CREATE INDEX IF NOT EXISTS idx_experiment_condition_alpha_re ON experiment_condition(alpha_deg, reynolds_number);
CREATE INDEX IF NOT EXISTS idx_experiment_condition_re_alpha ON experiment_condition(reynolds_number, alpha_deg);

CREATE INDEX IF NOT EXISTS idx_performance_record_condition_lod ON performance_record(condition_id, l_over_d DESC);
CREATE INDEX IF NOT EXISTS idx_performance_record_condition_cd_cl ON performance_record(condition_id, cd, cl);
CREATE INDEX IF NOT EXISTS idx_performance_record_version ON performance_record(version_id);
CREATE INDEX IF NOT EXISTS idx_performance_record_anomaly_version ON performance_record(version_id) WHERE is_anomaly;

CREATE INDEX IF NOT EXISTS idx_anomaly_record_version ON anomaly_record(version_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_rule ON anomaly_record(rule_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_record_status ON anomaly_record(status);

CREATE INDEX IF NOT EXISTS idx_query_log_user_at ON query_log(user_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_airfoil_at ON query_log(airfoil_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_type_at ON query_log(query_type, at DESC);

CREATE INDEX IF NOT EXISTS idx_nl2sql_audit_query ON nl2sql_audit(query_id);
CREATE INDEX IF NOT EXISTS idx_result_explain_audit_query ON result_explain_audit(query_id);

COMMIT;
