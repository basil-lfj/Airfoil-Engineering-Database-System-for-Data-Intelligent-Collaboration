CREATE TABLE IF NOT EXISTS airfoil_db.change_log (
  log_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  version_id  bigint,
  actor       text NOT NULL,
  action      text NOT NULL CHECK (action IN ('insert', 'update', 'invalidate', 'import')),
  entity_name text NOT NULL,
  entity_id   bigint,
  at          timestamptz NOT NULL DEFAULT now(),
  detail      text
);

CREATE INDEX IF NOT EXISTS idx_airfoil_db_change_log_version_at
  ON airfoil_db.change_log(version_id, at DESC);

CREATE OR REPLACE FUNCTION airfoil_db.log_change_for_versioned_tables()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_version_id bigint;
  v_entity_id bigint;
  v_action text;
  v_detail text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    v_action := 'insert';
    v_version_id := COALESCE(NEW.version_id, NULL);
  ELSIF TG_OP = 'UPDATE' THEN
    v_action := 'update';
    v_version_id := COALESCE(NEW.version_id, OLD.version_id, NULL);
  ELSE
    v_action := 'invalidate';
    v_version_id := COALESCE(OLD.version_id, NULL);
  END IF;

  IF TG_TABLE_NAME = 'airfoil_version' THEN
    v_entity_id := COALESCE(NEW.version_id, OLD.version_id);
  ELSIF TG_TABLE_NAME = 'airfoil_coordinate' THEN
    v_entity_id := COALESCE(NEW.coord_id, OLD.coord_id);
  ELSIF TG_TABLE_NAME = 'airfoil_performance' THEN
    v_entity_id := COALESCE(NEW.perf_id, OLD.perf_id);
  ELSIF TG_TABLE_NAME = 'anomaly_record' THEN
    v_entity_id := COALESCE(NEW.anomaly_id, OLD.anomaly_id);
  ELSE
    v_entity_id := NULL;
  END IF;

  v_detail := format('trigger=%s; table=%s; op=%s', TG_NAME, TG_TABLE_NAME, TG_OP);

  INSERT INTO airfoil_db.change_log(version_id, actor, action, entity_name, entity_id, at, detail)
  VALUES (v_version_id, current_user, v_action, TG_TABLE_NAME, v_entity_id, now(), v_detail);

  RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_airfoil_db_log_change_airfoil_version ON airfoil_db.airfoil_version;
CREATE TRIGGER trg_airfoil_db_log_change_airfoil_version
AFTER INSERT OR UPDATE ON airfoil_db.airfoil_version
FOR EACH ROW EXECUTE FUNCTION airfoil_db.log_change_for_versioned_tables();

DROP TRIGGER IF EXISTS trg_airfoil_db_log_change_airfoil_coordinate ON airfoil_db.airfoil_coordinate;
CREATE TRIGGER trg_airfoil_db_log_change_airfoil_coordinate
AFTER INSERT OR UPDATE ON airfoil_db.airfoil_coordinate
FOR EACH ROW EXECUTE FUNCTION airfoil_db.log_change_for_versioned_tables();

DROP TRIGGER IF EXISTS trg_airfoil_db_log_change_airfoil_performance ON airfoil_db.airfoil_performance;
CREATE TRIGGER trg_airfoil_db_log_change_airfoil_performance
AFTER INSERT OR UPDATE ON airfoil_db.airfoil_performance
FOR EACH ROW EXECUTE FUNCTION airfoil_db.log_change_for_versioned_tables();

DROP TRIGGER IF EXISTS trg_airfoil_db_log_change_anomaly_record ON airfoil_db.anomaly_record;
CREATE TRIGGER trg_airfoil_db_log_change_anomaly_record
AFTER INSERT OR UPDATE ON airfoil_db.anomaly_record
FOR EACH ROW EXECUTE FUNCTION airfoil_db.log_change_for_versioned_tables();

