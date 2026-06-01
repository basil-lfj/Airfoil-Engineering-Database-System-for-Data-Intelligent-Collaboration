CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS data_source (
  source_id uuid DEFAULT gen_random_uuid(),
  source_type text,
  provider text,
  dataset_name text,
  reference text,
  license_note text,
  imported_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_account (
  user_id uuid DEFAULT gen_random_uuid(),
  username text,
  role text,
  created_at timestamptz DEFAULT now(),
  is_active boolean DEFAULT true
);

CREATE TABLE IF NOT EXISTS airfoil (
  airfoil_id uuid DEFAULT gen_random_uuid(),
  airfoil_code text,
  name text,
  category text,
  family text,
  generation_method text,
  is_generated boolean DEFAULT false,
  remark text,
  source_id uuid,
  is_deleted boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS airfoil_version (
  version_id uuid DEFAULT gen_random_uuid(),
  airfoil_id uuid,
  version_no integer,
  version_type text,
  status text,
  is_current boolean DEFAULT false,
  change_note text,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  invalidated_at timestamptz,
  is_deleted boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS coordinate_point (
  point_id uuid DEFAULT gen_random_uuid(),
  version_id uuid,
  surface text,
  point_order integer,
  x numeric,
  y numeric,
  is_deleted boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS experiment_condition (
  condition_id uuid DEFAULT gen_random_uuid(),
  alpha_deg numeric,
  reynolds_number numeric,
  mach numeric,
  temperature numeric,
  pressure numeric,
  note text
);

CREATE TABLE IF NOT EXISTS performance_record (
  record_id uuid DEFAULT gen_random_uuid(),
  version_id uuid,
  condition_id uuid,
  cl numeric,
  cd numeric,
  cm numeric,
  l_over_d numeric,
  source_type text,
  is_anomaly boolean DEFAULT false,
  measured_at timestamptz,
  is_deleted boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS anomaly_rule (
  rule_id uuid DEFAULT gen_random_uuid(),
  rule_code text,
  description text,
  severity text,
  is_enabled boolean DEFAULT true
);

CREATE TABLE IF NOT EXISTS anomaly_record (
  anomaly_id uuid DEFAULT gen_random_uuid(),
  version_id uuid,
  record_id uuid,
  point_id uuid,
  rule_id uuid,
  status text,
  details text,
  reviewed_by uuid,
  detected_at timestamptz DEFAULT now(),
  reviewed_at timestamptz
);

CREATE TABLE IF NOT EXISTS change_log (
  log_id uuid DEFAULT gen_random_uuid(),
  version_id uuid,
  actor_id uuid,
  action text,
  entity_name text,
  entity_id uuid,
  at timestamptz DEFAULT now(),
  detail text
);

CREATE TABLE IF NOT EXISTS query_log (
  query_id uuid DEFAULT gen_random_uuid(),
  user_id uuid,
  airfoil_id uuid,
  query_type text,
  at timestamptz DEFAULT now(),
  parameters_json text,
  sql_text text,
  is_success boolean DEFAULT true,
  error_message text
);

CREATE TABLE IF NOT EXISTS nl2sql_audit (
  audit_id uuid DEFAULT gen_random_uuid(),
  query_id uuid,
  auditor_id uuid,
  nl_question text,
  generated_sql text,
  audited_sql text,
  audit_status text,
  error_types_json text,
  notes text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS result_explain_audit (
  explain_id uuid DEFAULT gen_random_uuid(),
  query_id uuid,
  reviewer_id uuid,
  result_snapshot_ref text,
  llm_explanation text,
  judgement text,
  issues_json text,
  created_at timestamptz DEFAULT now()
);

