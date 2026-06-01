INSERT INTO airfoil_db.anomaly_rule (rule_code, rule_name, rule_type, params, enabled)
VALUES
  ('negative_cd', '阻力系数为负', 'cd_negative', '{}'::jsonb, true),
  ('extreme_ld', '升阻比异常偏离', 'ldr_outlier', '{"k":3.0,"min_points":8,"target":"ldr"}'::jsonb, true),
  ('jump_cl', '邻近攻角性能突变', 'aoa_jump', '{"max_dcl_per_deg":0.8,"max_daoa_deg":2.0}'::jsonb, true),
  ('extreme_cl', '升力系数异常偏离', 'ldr_outlier', '{"k":3.0,"min_points":8,"target":"cl"}'::jsonb, true)
ON CONFLICT (rule_code) DO NOTHING;

CREATE OR REPLACE FUNCTION airfoil_db.fn_detect_anomaly(p_version_id bigint DEFAULT NULL)
RETURNS TABLE (
  rule_code text,
  inserted_count bigint
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_rule_id bigint;
  v_rule_code text;
  v_cnt bigint;
  v_target text;
BEGIN
  FOR v_rule_id, v_rule_code IN
    SELECT r.rule_id, r.rule_code
    FROM airfoil_db.anomaly_rule r
    WHERE r.rule_type = 'cd_negative' AND r.enabled
    ORDER BY r.rule_id
  LOOP
    INSERT INTO airfoil_db.anomaly_record (rule_id, version_id, perf_id, severity, message, details)
    SELECT
      v_rule_id,
      p.version_id,
      p.perf_id,
      'critical',
      'cd 为负值',
      jsonb_build_object('cd', p.cd, 'reynolds', p.reynolds, 'aoa_deg', p.aoa_deg, 'mach', p.mach)
    FROM airfoil_db.airfoil_performance p
    WHERE p.cd IS NOT NULL
      AND p.cd < 0
      AND (p_version_id IS NULL OR p.version_id = p_version_id)
    ON CONFLICT (rule_id, perf_id) DO NOTHING;

    GET DIAGNOSTICS v_cnt = ROW_COUNT;
    rule_code := v_rule_code;
    inserted_count := v_cnt;
    RETURN NEXT;
  END LOOP;

  FOR v_rule_id, v_rule_code IN
    SELECT r.rule_id, r.rule_code
    FROM airfoil_db.anomaly_rule r
    WHERE r.rule_type = 'ldr_outlier' AND r.enabled
    ORDER BY r.rule_id
  LOOP
    SELECT COALESCE(r.params->>'target', 'ldr')
    INTO v_target
    FROM airfoil_db.anomaly_rule r
    WHERE r.rule_id = v_rule_id;

    WITH cfg AS (
      SELECT
        v_rule_id AS rule_id,
        COALESCE((r.params->>'k')::double precision, 3.0) AS k,
        COALESCE((r.params->>'min_points')::int, 8) AS min_points
      FROM airfoil_db.anomaly_rule r
      WHERE r.rule_id = v_rule_id
    ),
    perf AS (
      SELECT
        p.*,
        CASE
          WHEN v_target = 'cl' THEN p.cl
          WHEN v_target = 'cd' THEN p.cd
          ELSE COALESCE(p.ldr, p.cl / NULLIF(p.cd, 0))
        END AS metric_value
      FROM airfoil_db.airfoil_performance p
      WHERE (p_version_id IS NULL OR p.version_id = p_version_id)
    ),
    stat AS (
      SELECT
        p.version_id,
        p.reynolds,
        p.mach,
        avg(p.metric_value) AS mu,
        stddev_samp(p.metric_value) AS sigma,
        count(*) AS n
      FROM perf p
      WHERE p.metric_value IS NOT NULL
      GROUP BY p.version_id, p.reynolds, p.mach
    )
    INSERT INTO airfoil_db.anomaly_record (rule_id, version_id, perf_id, severity, message, details)
    SELECT
      cfg.rule_id,
      p.version_id,
      p.perf_id,
      'warning',
      CASE
        WHEN v_target = 'cl' THEN '升力系数偏离统计范围'
        WHEN v_target = 'cd' THEN '阻力系数偏离统计范围'
        ELSE '升阻比偏离统计范围'
      END,
      jsonb_build_object(
        'target', v_target,
        'value', p.metric_value,
        'mu', s.mu,
        'sigma', s.sigma,
        'k', cfg.k,
        'reynolds', p.reynolds, 'aoa_deg', p.aoa_deg, 'mach', p.mach
      )
    FROM cfg
    JOIN perf p ON true
    JOIN stat s
      ON s.version_id = p.version_id
     AND s.reynolds = p.reynolds
     AND s.mach IS NOT DISTINCT FROM p.mach
    WHERE p.metric_value IS NOT NULL
      AND s.n >= cfg.min_points
      AND s.sigma IS NOT NULL
      AND abs(p.metric_value - s.mu) > cfg.k * s.sigma
    ON CONFLICT (rule_id, perf_id) DO NOTHING;

    GET DIAGNOSTICS v_cnt = ROW_COUNT;
    rule_code := v_rule_code;
    inserted_count := v_cnt;
    RETURN NEXT;
  END LOOP;

  FOR v_rule_id, v_rule_code IN
    SELECT r.rule_id, r.rule_code
    FROM airfoil_db.anomaly_rule r
    WHERE r.rule_type = 'aoa_jump' AND r.enabled
    ORDER BY r.rule_id
  LOOP
    WITH cfg AS (
      SELECT
        v_rule_id AS rule_id,
        COALESCE((r.params->>'max_dcl_per_deg')::double precision, 0.8) AS max_dcl_per_deg,
        COALESCE((r.params->>'max_daoa_deg')::double precision, 2.0) AS max_daoa_deg
      FROM airfoil_db.anomaly_rule r
      WHERE r.rule_id = v_rule_id
    ),
    ordered AS (
      SELECT
        p.perf_id,
        p.version_id,
        p.reynolds,
        p.mach,
        p.aoa_deg,
        p.cl,
        lag(p.aoa_deg) OVER w AS prev_aoa,
        lag(p.cl) OVER w AS prev_cl
      FROM airfoil_db.airfoil_performance p
      WHERE (p_version_id IS NULL OR p.version_id = p_version_id)
      WINDOW w AS (PARTITION BY p.version_id, p.reynolds, p.mach ORDER BY p.aoa_deg)
    )
    INSERT INTO airfoil_db.anomaly_record (rule_id, version_id, perf_id, severity, message, details)
    SELECT
      cfg.rule_id,
      o.version_id,
      o.perf_id,
      'warning',
      '邻近攻角 cl 变化不合理',
      jsonb_build_object(
        'prev_aoa', o.prev_aoa, 'aoa_deg', o.aoa_deg,
        'prev_cl', o.prev_cl, 'cl', o.cl,
        'dcl_per_deg', (o.cl - o.prev_cl) / NULLIF(o.aoa_deg - o.prev_aoa, 0),
        'reynolds', o.reynolds, 'mach', o.mach
      )
    FROM cfg
    JOIN ordered o ON true
    WHERE o.prev_aoa IS NOT NULL
      AND o.prev_cl IS NOT NULL
      AND o.cl IS NOT NULL
      AND (o.aoa_deg - o.prev_aoa) > 0
      AND (o.aoa_deg - o.prev_aoa) <= cfg.max_daoa_deg
      AND abs((o.cl - o.prev_cl) / NULLIF(o.aoa_deg - o.prev_aoa, 0)) > cfg.max_dcl_per_deg
    ON CONFLICT (rule_id, perf_id) DO NOTHING;

    GET DIAGNOSTICS v_cnt = ROW_COUNT;
    rule_code := v_rule_code;
    inserted_count := v_cnt;
    RETURN NEXT;
  END LOOP;

  RETURN;
END;
$$;
