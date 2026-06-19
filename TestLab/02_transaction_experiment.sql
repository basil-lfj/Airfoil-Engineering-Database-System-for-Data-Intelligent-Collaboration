-- ============================================================================
-- §7.2 事务与并发实验
-- 场景 A：批量导入回滚（非法数据导致整批回滚）
-- 场景 B：乐观锁冲突检测（xmin 版本号冲突）
-- 场景 C：悲观锁（SELECT FOR UPDATE 行级锁）
-- ============================================================================


-- 首先确保 import_performance_batch 函数存在（见 11_advanced_mechanisms.sql）
-- 如未创建，此处会报错；请先执行 11_advanced_mechanisms.sql

-- ============================================================================
-- 场景 A：批量导入 + 异常回滚（事务原子性）
-- 模拟导入两条性能数据，其中第二条 cd = -0.010（非法），期望：
--  - 函数内抛出异常
--  - 整个事务回滚，第一条也不写入
--  - 表行数保持不变
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ 场景 A：批量导入回滚（事务原子性）
-- ╚════════════════════════════════════════════════════════════

DO $$
DECLARE
  v_before bigint;
  v_after bigint;
  v_version_id uuid;
BEGIN
  -- 找一个可用的当前版本
  SELECT version_id INTO v_version_id
  FROM airfoil_version
  WHERE is_deleted = false AND status = 'valid'
  ORDER BY is_current DESC, version_no DESC
  LIMIT 1;

  IF v_version_id IS NULL THEN
    RAISE EXCEPTION 'No valid version found for import test';
  END IF;

  -- 记录当前行数
  SELECT count(*) INTO v_before FROM performance_record;

  -- 尝试批量导入：第一条合法，第二条 cd=-0.010 非法
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
    -- 如果执行到这里，说明导入没有抛出异常（测试失败）
    RAISE EXCEPTION 'TEST FAILED: batch import unexpectedly succeeded with invalid data';
  EXCEPTION WHEN OTHERS THEN
    -- 预期：捕获异常，验证行数不变
    RAISE NOTICE 'Expected rollback triggered: % (SQLSTATE: %)', SQLERRM, SQLSTATE;
  END;

  -- 验证行数未变
  SELECT count(*) INTO v_after FROM performance_record;

  IF v_before <> v_after THEN
    RAISE EXCEPTION 'ROLLBACK FAILED: before=%, after=% — data was written despite rollback', v_before, v_after;
  ELSE
    RAISE NOTICE '✅ Transaction rollback verified: before=%, after=% — unchanged', v_before, v_after;
  END IF;
END
$$;

-- ============================================================================
-- 场景 B：乐观锁冲突检测
-- 使用 PostgreSQL 内置的 xmin（元组版本号）作为乐观锁令牌
-- user_a 先更新成功 → user_b 使用旧 xmin 更新 → 期望被拒绝
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ 场景 B：乐观锁冲突检测
-- ╚════════════════════════════════════════════════════════════

DO $$
DECLARE
  v_record_id uuid;
  v_xmin_old text;
  v_xmin_new text;
  v_success boolean;
  v_message text;
BEGIN
  -- 选取一条测试记录
  SELECT record_id, xmin::text
  INTO v_record_id, v_xmin_old
  FROM performance_record
  WHERE is_deleted = false
  LIMIT 1;

  IF v_record_id IS NULL THEN
    RAISE EXCEPTION 'No performance record found for optimistic lock test';
  END IF;

  RAISE NOTICE 'Testing record_id=%, initial xmin=%', v_record_id, v_xmin_old;

  -- user_a 更新成功（使用当前 xmin）
  SELECT success, message
  INTO v_success, v_message
  FROM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old,
    0.6001, 0.0201, NULL,
    'optimistic_user_a'
  );
  RAISE NOTICE 'User A update: success=%, message=%', v_success, v_message;

  -- 获取更新后的 xmin
  SELECT xmin::text INTO v_xmin_new
  FROM performance_record
  WHERE record_id = v_record_id;

  -- user_b 使用旧的 xmin（应被拒绝）
  SELECT success, message
  INTO v_success, v_message
  FROM governance.update_performance_record_optimistic(
    v_record_id, v_xmin_old,
    0.6002, 0.0202, NULL,
    'optimistic_user_b'
  );

  RAISE NOTICE 'User B update (stale xmin): success=%, message=%', v_success, v_message;

  IF v_success = false THEN
    RAISE NOTICE '✅ Optimistic lock correctly prevented stale update';
  ELSE
    RAISE WARNING '⚠️ Optimistic lock did NOT prevent stale update — check function logic';
  END IF;
END
$$;

-- ============================================================================
-- 场景 C：悲观锁（两会话模拟指导）
-- 使用 SELECT ... FOR UPDATE 行级锁确保同一时间只有一个事务能修改
-- 本脚本仅输出操作指引，实际需要两个 psql 会话窗口
-- ============================================================================
-- ════════════════════════════════════════════════════════════
-- ║ 场景 C：悲观锁（两会话手动操作）
-- ╚════════════════════════════════════════════════════════════

-- ----- 请打开两个 psql 窗口，按以下步骤操作：-----
--
-- --- Session A ---
-- BEGIN;
-- SELECT record_id FROM performance_record WHERE is_deleted = false LIMIT 1;
-- -- 记下返回的 record_id，假设为 'abc-123'
-- SELECT * FROM performance_record WHERE record_id = 'abc-123' FOR UPDATE;
-- -- 现在 Session A 持有该行的排他锁
-- -- 保持事务打开（不要 COMMIT）
--
-- --- Session B（在 3 秒内执行）---
-- SET lock_timeout = '3s';
-- BEGIN;
-- SELECT * FROM governance.update_performance_record_pessimistic(
--   'abc-123', 0.9, 0.03, NULL, 'session_b'
-- );
-- -- 预期：等待约 3 秒后，锁超时错误
--
-- --- 回到 Session A ---
-- COMMIT;
-- -- Session A 释放锁
--
-- --- 回到 Session B，再次执行 ---
-- SELECT * FROM governance.update_performance_record_pessimistic(
--   'abc-123', 0.9, 0.03, NULL, 'session_b'
-- );
-- -- 预期：成功更新（Session A 已释放锁）
--

-- === [DONE] Transaction experiment complete ===