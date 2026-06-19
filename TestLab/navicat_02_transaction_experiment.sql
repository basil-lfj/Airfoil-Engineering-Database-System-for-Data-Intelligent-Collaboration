-- ============================================================================
-- §7.2 事务与并发实验 — Navicat 兼容版
-- Navicat 中：选中整个文件 → 运行
--
-- 场景 A + B 可一键运行，场景 C 需要手动开两个查询窗口
-- ============================================================================

-- ============================================================================
-- 场景 A：批量导入 + 异常回滚（事务原子性）
-- ============================================================================

DO $$
DECLARE
  v_before bigint;
  v_after bigint;
  v_version_id uuid;
BEGIN
  SELECT version_id INTO v_version_id
  FROM airfoil_version
  WHERE is_deleted = false AND status = 'valid'
  ORDER BY is_current DESC, version_no DESC
  LIMIT 1;

  IF v_version_id IS NULL THEN
    RAISE EXCEPTION 'No valid version found for import test';
  END IF;

  SELECT count(*) INTO v_before FROM performance_record;

  BEGIN
    PERFORM governance.import_performance_batch(
      v_version_id,
      '[
        {"alpha_deg": 48, "reynolds_number": 777777, "cl": 0.55, "cd": 0.032, "cm": 0.00},
        {"alpha_deg": 49, "reynolds_number": 777777, "cl": 0.58, "cd": -0.010, "cm": 0.00}
      ]'::jsonb,
      'synthetic',
      false
    );
    RAISE EXCEPTION 'TEST FAILED: batch import unexpectedly succeeded with invalid data (cd=-0.010)';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Expected rollback triggered: % (SQLSTATE: %)', SQLERRM, SQLSTATE;
  END;

  SELECT count(*) INTO v_after FROM performance_record;

  IF v_before <> v_after THEN
    RAISE EXCEPTION 'ROLLBACK FAILED: before=%, after=% — data was written despite rollback', v_before, v_after;
  ELSE
    RAISE NOTICE 'Transaction rollback verified: before=%, after=% — unchanged', v_before, v_after;
  END IF;
END
$$;

-- ============================================================================
-- 场景 B：乐观锁冲突检测
-- ============================================================================

DO $$
DECLARE
  v_record_id uuid;
  v_xmin_old text;
  v_xmin_new text;
  v_success boolean;
  v_message text;
BEGIN
  SELECT record_id, xmin::text
  INTO v_record_id, v_xmin_old
  FROM performance_record
  WHERE is_deleted = false
  LIMIT 1;

  IF v_record_id IS NULL THEN
    RAISE EXCEPTION 'No performance record found for optimistic lock test';
  END IF;

  RAISE NOTICE 'Testing record_id=%, initial xmin=%', v_record_id, v_xmin_old;

  -- user_a 使用当前 xmin，应成功
  SELECT success, message
  INTO v_success, v_message
  FROM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old,
    0.6001, 0.0201, NULL,
    'optimistic_user_a'
  );
  RAISE NOTICE 'User A update (correct xmin): success=%, message=%', v_success, v_message;

  -- 获取新 xmin
  SELECT xmin::text INTO v_xmin_new
  FROM performance_record
  WHERE record_id = v_record_id;

  -- user_b 使用旧的 xmin，应被拒绝
  SELECT success, message
  INTO v_success, v_message
  FROM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old,
    0.6002, 0.0202, NULL,
    'optimistic_user_b'
  );

  RAISE NOTICE 'User B update (stale xmin): success=%, message=%', v_success, v_message;

  IF v_success = false THEN
    RAISE NOTICE 'Optimistic lock correctly prevented stale update';
  ELSE
    RAISE WARNING 'Optimistic lock did NOT prevent stale update — check function logic';
  END IF;
END
$$;

-- ============================================================================
-- 场景 C：悲观锁（两会话手动操作）
-- 在 Navicat 中，需要额外打开一个查询窗口
-- ============================================================================

-- 第一步：找到一条测试用的 record_id
SELECT record_id::text
FROM performance_record
WHERE is_deleted = false
LIMIT 1;

-- 然后打开第二个查询窗口（Navicat 中 Ctrl+N 新建），粘贴以下内容：
/*
-- ===== [Session B] 悲观锁测试 =====
SET lock_timeout = '3s';
BEGIN;
SELECT * FROM governance.update_performance_record_pessimistic(
  '上一步查到的 record_id',
  0.9, 0.03, NULL, 'session_b'
);
-- 预期会等待或超时
*/