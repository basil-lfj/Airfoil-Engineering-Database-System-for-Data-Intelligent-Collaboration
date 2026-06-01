CREATE SCHEMA IF NOT EXISTS airfoil_db;

CREATE TABLE IF NOT EXISTS airfoil_db.airfoil (
  airfoil_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  airfoil_code      text NOT NULL UNIQUE,
  airfoil_name      text NOT NULL,
  category          text,
  source            text,
  generation_method text,
  remark            text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS airfoil_db.airfoil_version (
  version_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  airfoil_id        bigint NOT NULL REFERENCES airfoil_db.airfoil(airfoil_id),
  version_no        integer NOT NULL,
  parent_version_id bigint REFERENCES airfoil_db.airfoil_version(version_id),
  change_note       text,
  data_source       text,
  status            text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'released', 'archived')),
  created_by        text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (airfoil_id, version_no)
);

CREATE TABLE IF NOT EXISTS airfoil_db.airfoil_coordinate (
  coord_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version_id bigint NOT NULL REFERENCES airfoil_db.airfoil_version(version_id) ON DELETE CASCADE,
  surface    text NOT NULL CHECK (surface IN ('upper', 'lower', 'other')),
  seq        integer NOT NULL,
  x          double precision NOT NULL,
  y          double precision NOT NULL,
  z          double precision,
  tag        text,
  UNIQUE (version_id, surface, seq)
);

CREATE TABLE IF NOT EXISTS airfoil_db.airfoil_performance (
  perf_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version_id bigint NOT NULL REFERENCES airfoil_db.airfoil_version(version_id) ON DELETE CASCADE,
  reynolds   double precision NOT NULL,
  aoa_deg    double precision NOT NULL,
  mach       double precision,
  cl         double precision,
  cd         double precision,
  cm         double precision,
  ldr        double precision,
  source_run text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (version_id, reynolds, aoa_deg, mach)
);

CREATE TABLE IF NOT EXISTS airfoil_db.anomaly_rule (
  rule_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rule_code   text NOT NULL UNIQUE,
  rule_name   text NOT NULL,
  rule_type   text NOT NULL CHECK (rule_type IN ('cd_negative', 'ldr_outlier', 'aoa_jump')),
  params      jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled     boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS airfoil_db.anomaly_record (
  anomaly_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rule_id     bigint NOT NULL REFERENCES airfoil_db.anomaly_rule(rule_id),
  version_id  bigint NOT NULL REFERENCES airfoil_db.airfoil_version(version_id) ON DELETE CASCADE,
  perf_id     bigint REFERENCES airfoil_db.airfoil_performance(perf_id) ON DELETE SET NULL,
  severity    text NOT NULL DEFAULT 'warning' CHECK (severity IN ('info', 'warning', 'critical')),
  message     text NOT NULL,
  details     jsonb NOT NULL DEFAULT '{}'::jsonb,
  detected_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_airfoil_version_airfoil ON airfoil_db.airfoil_version(airfoil_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_coord_version_surface_seq ON airfoil_db.airfoil_coordinate(version_id, surface, seq);

CREATE INDEX IF NOT EXISTS idx_perf_version ON airfoil_db.airfoil_performance(version_id);
CREATE INDEX IF NOT EXISTS idx_perf_condition ON airfoil_db.airfoil_performance(reynolds, mach, aoa_deg);
CREATE INDEX IF NOT EXISTS idx_perf_threshold ON airfoil_db.airfoil_performance(reynolds, mach, ldr);

CREATE INDEX IF NOT EXISTS idx_anom_version ON airfoil_db.anomaly_record(version_id, detected_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_anom_rule_perf_notnull ON airfoil_db.anomaly_record(rule_id, perf_id) WHERE perf_id IS NOT NULL;

