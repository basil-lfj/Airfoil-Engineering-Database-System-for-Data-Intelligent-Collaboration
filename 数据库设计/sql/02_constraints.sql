BEGIN;

ALTER TABLE public.user_account
  ALTER COLUMN username SET NOT NULL;

ALTER TABLE public.airfoil
  ALTER COLUMN airfoil_code SET NOT NULL,
  ALTER COLUMN name SET NOT NULL,
  ALTER COLUMN source_id SET NOT NULL;

ALTER TABLE public.airfoil_version
  ALTER COLUMN airfoil_id SET NOT NULL,
  ALTER COLUMN version_no SET NOT NULL,
  ALTER COLUMN version_type SET NOT NULL,
  ALTER COLUMN status SET NOT NULL,
  ALTER COLUMN created_by SET NOT NULL;

ALTER TABLE public.coordinate_point
  ALTER COLUMN version_id SET NOT NULL,
  ALTER COLUMN surface SET NOT NULL,
  ALTER COLUMN point_order SET NOT NULL,
  ALTER COLUMN x SET NOT NULL,
  ALTER COLUMN y SET NOT NULL;

ALTER TABLE public.experiment_condition
  ALTER COLUMN alpha_deg SET NOT NULL,
  ALTER COLUMN reynolds_number SET NOT NULL;

ALTER TABLE public.performance_record
  ALTER COLUMN version_id SET NOT NULL,
  ALTER COLUMN condition_id SET NOT NULL,
  ALTER COLUMN cl SET NOT NULL,
  ALTER COLUMN cd SET NOT NULL,
  ALTER COLUMN source_type SET NOT NULL;

ALTER TABLE public.anomaly_rule
  ALTER COLUMN rule_code SET NOT NULL,
  ALTER COLUMN description SET NOT NULL,
  ALTER COLUMN severity SET NOT NULL;

ALTER TABLE public.anomaly_record
  ALTER COLUMN version_id SET NOT NULL,
  ALTER COLUMN rule_id SET NOT NULL,
  ALTER COLUMN status SET NOT NULL,
  ALTER COLUMN detected_at SET NOT NULL;

ALTER TABLE public.change_log
  ALTER COLUMN version_id SET NOT NULL,
  ALTER COLUMN actor_id SET NOT NULL,
  ALTER COLUMN action SET NOT NULL,
  ALTER COLUMN entity_name SET NOT NULL,
  ALTER COLUMN entity_id SET NOT NULL,
  ALTER COLUMN at SET NOT NULL;

ALTER TABLE public.query_log
  ALTER COLUMN user_id SET NOT NULL,
  ALTER COLUMN query_type SET NOT NULL,
  ALTER COLUMN at SET NOT NULL;

ALTER TABLE public.nl2sql_audit
  ALTER COLUMN query_id SET NOT NULL,
  ALTER COLUMN auditor_id SET NOT NULL,
  ALTER COLUMN nl_question SET NOT NULL,
  ALTER COLUMN generated_sql SET NOT NULL,
  ALTER COLUMN audit_status SET NOT NULL,
  ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE public.result_explain_audit
  ALTER COLUMN query_id SET NOT NULL,
  ALTER COLUMN reviewer_id SET NOT NULL,
  ALTER COLUMN llm_explanation SET NOT NULL,
  ALTER COLUMN judgement SET NOT NULL,
  ALTER COLUMN created_at SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_data_source' AND conrelid = 'public.data_source'::regclass) THEN
    ALTER TABLE public.data_source ADD CONSTRAINT pk_data_source PRIMARY KEY (source_id);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_user_account' AND conrelid = 'public.user_account'::regclass) THEN
    ALTER TABLE public.user_account ADD CONSTRAINT pk_user_account PRIMARY KEY (user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_account_username' AND conrelid = 'public.user_account'::regclass) THEN
    ALTER TABLE public.user_account ADD CONSTRAINT uq_user_account_username UNIQUE (username);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_airfoil' AND conrelid = 'public.airfoil'::regclass) THEN
    ALTER TABLE public.airfoil ADD CONSTRAINT pk_airfoil PRIMARY KEY (airfoil_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_airfoil_code' AND conrelid = 'public.airfoil'::regclass) THEN
    ALTER TABLE public.airfoil ADD CONSTRAINT uq_airfoil_code UNIQUE (airfoil_code);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_airfoil_source' AND conrelid = 'public.airfoil'::regclass) THEN
    ALTER TABLE public.airfoil ADD CONSTRAINT fk_airfoil_source FOREIGN KEY (source_id) REFERENCES public.data_source(source_id);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_airfoil_version' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT pk_airfoil_version PRIMARY KEY (version_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_airfoil_version_airfoil_ver' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT uq_airfoil_version_airfoil_ver UNIQUE (airfoil_id, version_no);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_airfoil_version_airfoil' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT fk_airfoil_version_airfoil FOREIGN KEY (airfoil_id) REFERENCES public.airfoil(airfoil_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_airfoil_version_creator' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT fk_airfoil_version_creator FOREIGN KEY (created_by) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_airfoil_version_type' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT ck_airfoil_version_type CHECK (version_type IN ('raw', 'revised', 'synthetic', 'imported'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_airfoil_version_status' AND conrelid = 'public.airfoil_version'::regclass) THEN
    ALTER TABLE public.airfoil_version ADD CONSTRAINT ck_airfoil_version_status CHECK (status IN ('valid', 'invalid', 'draft'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_coordinate_point' AND conrelid = 'public.coordinate_point'::regclass) THEN
    ALTER TABLE public.coordinate_point ADD CONSTRAINT pk_coordinate_point PRIMARY KEY (point_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_coordinate_point_order' AND conrelid = 'public.coordinate_point'::regclass) THEN
    ALTER TABLE public.coordinate_point ADD CONSTRAINT uq_coordinate_point_order UNIQUE (version_id, surface, point_order);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_coordinate_point_version' AND conrelid = 'public.coordinate_point'::regclass) THEN
    ALTER TABLE public.coordinate_point ADD CONSTRAINT fk_coordinate_point_version FOREIGN KEY (version_id) REFERENCES public.airfoil_version(version_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_coordinate_point_surface' AND conrelid = 'public.coordinate_point'::regclass) THEN
    ALTER TABLE public.coordinate_point ADD CONSTRAINT ck_coordinate_point_surface CHECK (surface IN ('upper', 'lower', 'other'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_experiment_condition' AND conrelid = 'public.experiment_condition'::regclass) THEN
    ALTER TABLE public.experiment_condition ADD CONSTRAINT pk_experiment_condition PRIMARY KEY (condition_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_experiment_condition_re' AND conrelid = 'public.experiment_condition'::regclass) THEN
    ALTER TABLE public.experiment_condition ADD CONSTRAINT ck_experiment_condition_re CHECK (reynolds_number > 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_experiment_condition_alpha' AND conrelid = 'public.experiment_condition'::regclass) THEN
    ALTER TABLE public.experiment_condition ADD CONSTRAINT ck_experiment_condition_alpha CHECK (alpha_deg >= -90 AND alpha_deg <= 90);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_performance_record' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT pk_performance_record PRIMARY KEY (record_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_performance_record_ver_cond' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT uq_performance_record_ver_cond UNIQUE (version_id, condition_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_performance_record_version' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT fk_performance_record_version FOREIGN KEY (version_id) REFERENCES public.airfoil_version(version_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_performance_record_condition' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT fk_performance_record_condition FOREIGN KEY (condition_id) REFERENCES public.experiment_condition(condition_id);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_performance_record_cd' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record DROP CONSTRAINT ck_performance_record_cd;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_performance_record_cd_or_anomaly' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT ck_performance_record_cd_or_anomaly CHECK (cd >= 0 OR is_anomaly);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_performance_record_source' AND conrelid = 'public.performance_record'::regclass) THEN
    ALTER TABLE public.performance_record ADD CONSTRAINT ck_performance_record_source CHECK (source_type IN ('real', 'synthetic'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_anomaly_rule' AND conrelid = 'public.anomaly_rule'::regclass) THEN
    ALTER TABLE public.anomaly_rule ADD CONSTRAINT pk_anomaly_rule PRIMARY KEY (rule_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_anomaly_rule_code' AND conrelid = 'public.anomaly_rule'::regclass) THEN
    ALTER TABLE public.anomaly_rule ADD CONSTRAINT uq_anomaly_rule_code UNIQUE (rule_code);
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_anomaly_record' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT pk_anomaly_record PRIMARY KEY (anomaly_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_anomaly_record_version' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT fk_anomaly_record_version FOREIGN KEY (version_id) REFERENCES public.airfoil_version(version_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_anomaly_record_record' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT fk_anomaly_record_record FOREIGN KEY (record_id) REFERENCES public.performance_record(record_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_anomaly_record_point' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT fk_anomaly_record_point FOREIGN KEY (point_id) REFERENCES public.coordinate_point(point_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_anomaly_record_rule' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT fk_anomaly_record_rule FOREIGN KEY (rule_id) REFERENCES public.anomaly_rule(rule_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_anomaly_record_reviewer' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT fk_anomaly_record_reviewer FOREIGN KEY (reviewed_by) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_anomaly_record_target' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT ck_anomaly_record_target CHECK ((record_id IS NOT NULL) <> (point_id IS NOT NULL));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_anomaly_record_status' AND conrelid = 'public.anomaly_record'::regclass) THEN
    ALTER TABLE public.anomaly_record ADD CONSTRAINT ck_anomaly_record_status CHECK (status IN ('open', 'confirmed', 'ignored'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_change_log' AND conrelid = 'public.change_log'::regclass) THEN
    ALTER TABLE public.change_log ADD CONSTRAINT pk_change_log PRIMARY KEY (log_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_change_log_version' AND conrelid = 'public.change_log'::regclass) THEN
    ALTER TABLE public.change_log ADD CONSTRAINT fk_change_log_version FOREIGN KEY (version_id) REFERENCES public.airfoil_version(version_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_change_log_actor' AND conrelid = 'public.change_log'::regclass) THEN
    ALTER TABLE public.change_log ADD CONSTRAINT fk_change_log_actor FOREIGN KEY (actor_id) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_change_log_action' AND conrelid = 'public.change_log'::regclass) THEN
    ALTER TABLE public.change_log ADD CONSTRAINT ck_change_log_action CHECK (action IN ('insert', 'update', 'invalidate', 'import'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_query_log' AND conrelid = 'public.query_log'::regclass) THEN
    ALTER TABLE public.query_log ADD CONSTRAINT pk_query_log PRIMARY KEY (query_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_query_log_user' AND conrelid = 'public.query_log'::regclass) THEN
    ALTER TABLE public.query_log ADD CONSTRAINT fk_query_log_user FOREIGN KEY (user_id) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_query_log_airfoil' AND conrelid = 'public.query_log'::regclass) THEN
    ALTER TABLE public.query_log ADD CONSTRAINT fk_query_log_airfoil FOREIGN KEY (airfoil_id) REFERENCES public.airfoil(airfoil_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_query_log_type' AND conrelid = 'public.query_log'::regclass) THEN
    ALTER TABLE public.query_log ADD CONSTRAINT ck_query_log_type CHECK (query_type IN ('geom', 'perf', 'compare', 'version_diff', 'anomaly'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_nl2sql_audit' AND conrelid = 'public.nl2sql_audit'::regclass) THEN
    ALTER TABLE public.nl2sql_audit ADD CONSTRAINT pk_nl2sql_audit PRIMARY KEY (audit_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_nl2sql_audit_query' AND conrelid = 'public.nl2sql_audit'::regclass) THEN
    ALTER TABLE public.nl2sql_audit ADD CONSTRAINT fk_nl2sql_audit_query FOREIGN KEY (query_id) REFERENCES public.query_log(query_id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_nl2sql_audit_auditor' AND conrelid = 'public.nl2sql_audit'::regclass) THEN
    ALTER TABLE public.nl2sql_audit ADD CONSTRAINT fk_nl2sql_audit_auditor FOREIGN KEY (auditor_id) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_nl2sql_audit_status' AND conrelid = 'public.nl2sql_audit'::regclass) THEN
    ALTER TABLE public.nl2sql_audit ADD CONSTRAINT ck_nl2sql_audit_status CHECK (audit_status IN ('approved', 'rejected', 'needs_fix'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_result_explain_audit' AND conrelid = 'public.result_explain_audit'::regclass) THEN
    ALTER TABLE public.result_explain_audit ADD CONSTRAINT pk_result_explain_audit PRIMARY KEY (explain_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_result_explain_audit_query' AND conrelid = 'public.result_explain_audit'::regclass) THEN
    ALTER TABLE public.result_explain_audit ADD CONSTRAINT fk_result_explain_audit_query FOREIGN KEY (query_id) REFERENCES public.query_log(query_id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_result_explain_audit_reviewer' AND conrelid = 'public.result_explain_audit'::regclass) THEN
    ALTER TABLE public.result_explain_audit ADD CONSTRAINT fk_result_explain_audit_reviewer FOREIGN KEY (reviewer_id) REFERENCES public.user_account(user_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_result_explain_audit_judgement' AND conrelid = 'public.result_explain_audit'::regclass) THEN
    ALTER TABLE public.result_explain_audit ADD CONSTRAINT ck_result_explain_audit_judgement CHECK (judgement IN ('correct', 'incorrect', 'unsupported'));
  END IF;
END
$$;

COMMIT;
