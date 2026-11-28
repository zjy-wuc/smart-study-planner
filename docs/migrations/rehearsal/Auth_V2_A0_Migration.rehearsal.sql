-- =====================================================================
-- Smart Study Planner · Auth V2.0 · A0 数据库迁移脚本（最终修正版）
-- 目标库：ssp_v3_release_rehearsal（迁移预演库 · 非正式）
-- 环境：MySQL 8.4.9 / InnoDB / utf8mb4_0900_ai_ci
-- 修订：2026-11-24（R3 最终收尾：identifier 排序规则与清理方案）
--
-- 执行协议（必须遵守）：
--   1. 本脚本尚未在正式业务库执行，必须经 ChatGPT 审查 + 用户确认。
--   2. 正式执行前：停止旧后端、定时 Worker 及所有可能写库的程序，
--      重新生成完整备份，并在隔离库验证恢复成功。
--      备份含用户数据与认证摘要，禁止提交 Git 或公开分享。
--   3. 使用 mysql 命令行客户端执行，禁止使用 --force 或任何
--      “出错仍继续”的参数；出现任何错误立即停止，不得继续后续 DDL。
--   4. DDL 必须逐段执行并核对 SHOW CREATE TABLE。若出现部分 DDL 成功、
--      部分失败，立即停止并报告实际数据库状态，禁止盲目重跑整个脚本。
--   5. SELECT 查询只用于展示，不作为断言。真正的断言由
--      __a0_assert 临时表 + CHECK 约束（错误 3819）强制执行；
--      分区 B 的断言由存储过程在 COMMIT 之前完成，失败自动 ROLLBACK。
--   6. 全程禁止 TRUNCATE，禁止 SET FOREIGN_KEY_CHECKS=0。
--   7. 执行方式：mysql --default-character-set=utf8mb4 \
--        --database=ssp_v3_release_rehearsal < Auth_V2_A0_Migration.rehearsal.sql
--      （隔离演练时把 @a0_expected_db 改为隔离库名，并同样用
--        --database 指定隔离库。）
--   8. 迁移账号必须已验证 CREATE TEMPORARY TABLES、CREATE ROUTINE、
--      EXECUTE、ALTER、CREATE、DROP 及所需 DML/SELECT 权限。
--   9. 清理方案：成功时 B18 删除存储过程，各断言后显式删除临时表。
--      失败时 mysql 客户端退出并关闭连接，临时表随连接自动销毁；
--      分区 B 失败会保留存储过程定义，必须人工执行
--      DROP PROCEDURE IF EXISTS a0_auth_v2_cleanup;
--      交互会话未退出时另执行 DROP TEMPORARY TABLE IF EXISTS __a0_assert;
--
-- 分区：
--   A 迁移前安全检查（只读）
--   B 旧数据清理（存储过程内单事务，COMMIT 前断言，失败 ROLLBACK）
--   C 原认证表重命名（DDL）
--   D users 表结构修改（DDL）
--   E 创建三张认证新表（DDL）
--   F 迁移后验证（只读 + 断言）
-- =====================================================================

SET NAMES utf8mb4;

-- 本文件为 A7.1 迁移预演版，仅允许在 ssp_v3_release_rehearsal 执行
SET @a0_expected_db = 'ssp_v3_release_rehearsal';

-- =====================================================================
-- 分区 A：迁移前安全检查（只读，不修改任何数据）
-- =====================================================================

-- A0. 目标库与版本
SELECT
  DATABASE()            AS current_db,
  @a0_expected_db       AS expected_db,
  CURRENT_USER()        AS migration_account,
  VERSION()             AS mysql_version,
  @@version_comment     AS version_comment,
  @@collation_server    AS server_collation;

-- A1. 实际表清单（预期恰好 14 张）
SELECT table_name AS table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

-- A2. 实际外键清单（预期 21 条）
SELECT k.TABLE_NAME AS table_name,
       k.CONSTRAINT_NAME AS constraint_name,
       k.COLUMN_NAME AS column_name,
       k.REFERENCED_TABLE_NAME AS referenced_table,
       k.REFERENCED_COLUMN_NAME AS referenced_column,
       r.DELETE_RULE AS delete_rule
FROM information_schema.KEY_COLUMN_USAGE k
JOIN information_schema.REFERENTIAL_CONSTRAINTS r
  ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
 AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME;

-- A3. 目标新表是否已存在（预期 0 行）
SELECT table_name, 1 AS should_be_zero
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('refresh_tokens', 'login_sessions', 'email_verifications', 'auth_events');

-- A4. users 前置结构（预期 9 列；email varchar(100) NULL；无新列）
SELECT COUNT(*) AS users_column_count
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'users';

SELECT column_name, column_type, is_nullable, collation_name, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'users'
ORDER BY ordinal_position;

-- A5. 清理范围确认
--     users 全部为旧账号（email 全为 NULL），不存在新式账号混入
SELECT COUNT(*) AS users_total,
       COALESCE(SUM(email IS NULL), 0) AS users_without_email,
       COALESCE(SUM(email IS NOT NULL), 0) AS users_with_email
FROM users;

--     业务表孤儿行：每行都必须归属到已存在的旧用户
SELECT 'study_plans' AS tbl, COUNT(*) AS orphan_rows
FROM study_plans p LEFT JOIN users u ON u.id = p.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'study_records', COUNT(*)
FROM study_records r LEFT JOIN users u ON u.id = r.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'focus_sessions', COUNT(*)
FROM focus_sessions f LEFT JOIN users u ON u.id = f.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'knowledge_notes', COUNT(*)
FROM knowledge_notes n LEFT JOIN users u ON u.id = n.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'knowledge_review_records', COUNT(*)
FROM knowledge_review_records v LEFT JOIN users u ON u.id = v.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'practice_records', COUNT(*)
FROM practice_records q LEFT JOIN users u ON u.id = q.user_id WHERE u.id IS NULL;

--     ai_requests 无外键，允许历史孤儿（已批准清理）；此处仅展示
SELECT COUNT(*) AS ai_requests_total,
       COALESCE(SUM(user_id IS NULL), 0) AS ai_requests_null_user,
       COALESCE(SUM(u.id IS NULL), 0) AS ai_requests_orphan
FROM ai_requests a LEFT JOIN users u ON u.id = a.user_id;

-- A6. ai_guard_mutex 必须存在且仅 1 行（id=1）
SELECT COUNT(*) AS mutex_rows, COALESCE(SUM(id = 1), 0) AS mutex_id_1
FROM ai_guard_mutex;

-- A7. 记录迁移前 AUTO_INCREMENT（请抄录到迁移记录，供分区 F 人工核对）
SELECT table_name, auto_increment
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

-- A8. 强制断言：任一条件不满足则报错中断，绝不进入破坏性阶段
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
  -- 目标库
      DATABASE() = @a0_expected_db
  -- 表集合恰好为 14 张且全部命中预期清单
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()) = 14
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN (
           'users', 'tb_refresh_token', 'ai_requests', 'ai_guard_mutex',
           'study_plans', 'plan_steps', 'daily_tasks', 'schedule_entries',
           'task_rollovers', 'study_records', 'focus_sessions',
           'knowledge_notes', 'knowledge_review_records', 'practice_records'
         )) = 14
  -- 外键总数 21 且全部命中预期清单
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()) = 21
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()
         AND constraint_name IN (
           'fk_daily_tasks_plan', 'fk_daily_tasks_step',
           'fk_focus_plan', 'fk_focus_task', 'fk_focus_user',
           'fk_notes_plan', 'fk_notes_step', 'fk_notes_user',
           'fk_review_note', 'fk_review_user',
           'fk_plan_steps_parent', 'fk_plan_steps_plan',
           'fk_practice_note', 'fk_practice_user',
           'fk_schedule_entries_step', 'fk_study_plans_user',
           'fk_study_records_task', 'fk_study_records_user',
           'fk_task_rollovers_source', 'fk_task_rollovers_target',
           'fk_refresh_token_user'
         )) = 21
  -- 目标新表不存在
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('refresh_tokens', 'login_sessions',
                            'email_verifications', 'auth_events')) = 0
  -- users 尚未被改过结构
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users') = 9
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name = 'email'
         AND column_type = 'varchar(100)'
         AND is_nullable = 'YES') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name IN ('email_verified_at', 'password_updated_at')) = 0
  -- 清理范围：users 全部为旧账号（email 全 NULL）
  AND (SELECT COUNT(*) FROM users) > 0
  AND (SELECT COALESCE(SUM(email IS NOT NULL), 0) FROM users) = 0
  -- 清理范围：业务表无孤儿行
  AND (SELECT COUNT(*) FROM study_plans p LEFT JOIN users u ON u.id = p.user_id WHERE u.id IS NULL) = 0
  AND (SELECT COUNT(*) FROM study_records r LEFT JOIN users u ON u.id = r.user_id WHERE u.id IS NULL) = 0
  AND (SELECT COUNT(*) FROM focus_sessions f LEFT JOIN users u ON u.id = f.user_id WHERE u.id IS NULL) = 0
  AND (SELECT COUNT(*) FROM knowledge_notes n LEFT JOIN users u ON u.id = n.user_id WHERE u.id IS NULL) = 0
  AND (SELECT COUNT(*) FROM knowledge_review_records v LEFT JOIN users u ON u.id = v.user_id WHERE u.id IS NULL) = 0
  AND (SELECT COUNT(*) FROM practice_records q LEFT JOIN users u ON u.id = q.user_id WHERE u.id IS NULL) = 0
  -- 保留项
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- 未报错即表示分区 A 全部断言通过。

-- =====================================================================
-- 分区 B：旧数据清理（单事务；COMMIT 前断言；失败自动 ROLLBACK）
-- 依赖顺序：叶子表 -> 父表 -> users
-- =====================================================================

-- B0. 若上次执行遗留过程，先清理（DDL，隐式提交，此时无未提交业务变更）
DROP PROCEDURE IF EXISTS `a0_auth_v2_cleanup`;

DELIMITER $$

CREATE PROCEDURE `a0_auth_v2_cleanup`()
BEGIN
  -- 任意 SQL 异常：先回滚，再抛出，绝不提交
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;

  -- B1. 任务顺延关系（依赖 daily_tasks）
  DELETE FROM task_rollovers;

  -- B2. 学习记录（依赖 users、daily_tasks）
  DELETE FROM study_records;

  -- B3. 专注会话（user_id CASCADE；plan/task 为 SET NULL）
  DELETE FROM focus_sessions;

  -- B4. 草稿排期（依赖 plan_steps）
  DELETE FROM schedule_entries;

  -- B5. 每日任务（依赖 study_plans、plan_steps）
  DELETE FROM daily_tasks;

  -- B6. 计划步骤（自引用 parent_id 为 NO ACTION）
  --     必须先解除父子引用，再删除，避免自引用外键阻塞
  UPDATE plan_steps SET parent_id = NULL;
  DELETE FROM plan_steps;

  -- B7. 学习计划（被 daily_tasks/plan_steps 引用，已先删除子表）
  DELETE FROM study_plans;

  -- B8. 复习记录（依赖 knowledge_notes、users，CASCADE）
  DELETE FROM knowledge_review_records;

  -- B9. 练习历史（依赖 users、knowledge_notes；note_id 为 SET NULL）
  DELETE FROM practice_records;

  -- B10. 知识笔记（依赖 users；被复习/练习引用，已先删除子表）
  DELETE FROM knowledge_notes;

  -- B11. Refresh Token（依赖 users，CASCADE）
  DELETE FROM tb_refresh_token;

  -- B12. AI 请求日志（无外键；含历史孤儿记录，一并清理）
  DELETE FROM ai_requests;

  -- B13. 用户主表（最后删除）
  DELETE FROM users;

  -- B14. 清理结果核对（必须在 COMMIT 之前）
  IF (SELECT COUNT(*) FROM users) <> 0
     OR (SELECT COUNT(*) FROM tb_refresh_token) <> 0
     OR (SELECT COUNT(*) FROM ai_requests) <> 0
     OR (SELECT COUNT(*) FROM study_plans) <> 0
     OR (SELECT COUNT(*) FROM plan_steps) <> 0
     OR (SELECT COUNT(*) FROM daily_tasks) <> 0
     OR (SELECT COUNT(*) FROM schedule_entries) <> 0
     OR (SELECT COUNT(*) FROM task_rollovers) <> 0
     OR (SELECT COUNT(*) FROM study_records) <> 0
     OR (SELECT COUNT(*) FROM focus_sessions) <> 0
     OR (SELECT COUNT(*) FROM knowledge_notes) <> 0
     OR (SELECT COUNT(*) FROM knowledge_review_records) <> 0
     OR (SELECT COUNT(*) FROM practice_records) <> 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'A0 cleanup verification failed: target tables are not empty; transaction rolled back';
  END IF;

  -- B15. 保留项核对：ai_guard_mutex 仅 id=1 一行
  IF (SELECT COUNT(*) FROM ai_guard_mutex) <> 1
     OR (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) <> 1 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'A0 cleanup verification failed: ai_guard_mutex id=1 not preserved; transaction rolled back';
  END IF;

  -- B16. 全部断言通过后才提交
  COMMIT;
END$$

DELIMITER ;

-- B17. 执行清理（失败时过程内已 ROLLBACK 并抛出错误，脚本随即终止）
CALL `a0_auth_v2_cleanup`();

-- B18. 成功路径：显式删除临时过程。
--      失败路径：因客户端立即退出，本语句不会执行；修复后重跑时 B0 会先删除，
--      若不再重跑，必须人工执行 DROP PROCEDURE IF EXISTS a0_auth_v2_cleanup;
DROP PROCEDURE IF EXISTS `a0_auth_v2_cleanup`;

-- B19. 清理结果展示（事务已提交；只读）
SELECT 'users' AS tbl, COUNT(*) AS rows_cnt FROM users
UNION ALL SELECT 'tb_refresh_token', COUNT(*) FROM tb_refresh_token
UNION ALL SELECT 'ai_requests', COUNT(*) FROM ai_requests
UNION ALL SELECT 'ai_guard_mutex', COUNT(*) FROM ai_guard_mutex
UNION ALL SELECT 'study_plans', COUNT(*) FROM study_plans
UNION ALL SELECT 'plan_steps', COUNT(*) FROM plan_steps
UNION ALL SELECT 'daily_tasks', COUNT(*) FROM daily_tasks
UNION ALL SELECT 'schedule_entries', COUNT(*) FROM schedule_entries
UNION ALL SELECT 'task_rollovers', COUNT(*) FROM task_rollovers
UNION ALL SELECT 'study_records', COUNT(*) FROM study_records
UNION ALL SELECT 'focus_sessions', COUNT(*) FROM focus_sessions
UNION ALL SELECT 'knowledge_notes', COUNT(*) FROM knowledge_notes
UNION ALL SELECT 'knowledge_review_records', COUNT(*) FROM knowledge_review_records
UNION ALL SELECT 'practice_records', COUNT(*) FROM practice_records;

-- =====================================================================
-- 分区 C：原认证表重命名（DDL，隐式提交）
-- 执行前必须停写；执行后立即核对 SHOW CREATE TABLE
-- =====================================================================

-- C0. 进入 DDL 前再次断言（只读；防止跳过分区 B 或连错库）
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
      DATABASE() = @a0_expected_db
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM tb_refresh_token) = 0
  AND (SELECT COUNT(*) FROM ai_requests) = 0
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_name = 'refresh_tokens') = 0
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- C1. 重命名；索引名与约束名不含 tb_ 前缀，无需同步改名
RENAME TABLE tb_refresh_token TO refresh_tokens;

-- C2. 重命名后核对
SELECT table_name FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('tb_refresh_token', 'refresh_tokens');

SHOW CREATE TABLE refresh_tokens;

-- C3. 断言：旧名消失、新名存在
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
      (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_name = 'tb_refresh_token') = 0
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_name = 'refresh_tokens') = 1
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- =====================================================================
-- 分区 D：users 表结构修改（DDL，隐式提交）
-- 前提：分区 B 已清空 users
-- email 单独使用 utf8mb4_0900_as_ci：大小写不敏感、重音敏感
-- =====================================================================

ALTER TABLE users
  MODIFY COLUMN email VARCHAR(254)
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci
    NOT NULL COMMENT '邮箱（登录标识，统一小写）',
  ADD COLUMN email_verified_at DATETIME(6) NOT NULL COMMENT '邮箱验证时间（UTC）' AFTER email,
  ADD COLUMN password_updated_at DATETIME(6) NOT NULL COMMENT '密码最近修改时间（UTC）' AFTER password_hash;

-- D1. 核对结构
SHOW CREATE TABLE users;

-- D2. 断言：email 定义与列级排序规则、新列、唯一索引
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
      (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name = 'email'
         AND column_type = 'varchar(254)'
         AND is_nullable = 'NO'
         AND collation_name = 'utf8mb4_0900_as_ci') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name IN ('email_verified_at', 'password_updated_at')
         AND column_type = 'datetime(6)'
         AND is_nullable = 'NO') = 2
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND index_name = 'uk_users_email' AND non_unique = 0) = 1
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND index_name = 'uk_users_username' AND non_unique = 0) = 1
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- =====================================================================
-- 分区 E：创建认证新表（DDL，隐式提交）
-- 时间字段统一 UTC，由后端显式写入，不使用 CURRENT_TIMESTAMP 默认值
-- =====================================================================

-- E1. 多设备登录会话；主键直接复用 refresh_tokens.family_id（UUID4）
CREATE TABLE login_sessions (
  family_id           CHAR(36)        NOT NULL COMMENT '会话 ID，等于 refresh_tokens.family_id',
  user_id             BIGINT UNSIGNED NOT NULL COMMENT '用户 ID',
  user_agent          VARCHAR(255)    DEFAULT NULL COMMENT '登录设备 User-Agent',
  created_at          DATETIME(6)     NOT NULL COMMENT '创建时间（UTC）',
  last_activity_at    DATETIME(6)     NOT NULL COMMENT '最后活跃时间（UTC）',
  absolute_expires_at DATETIME(6)     NOT NULL COMMENT '会话绝对过期时间（UTC）',
  revoked_at          DATETIME(6)     DEFAULT NULL COMMENT '撤销时间（UTC）',
  revoked_reason      VARCHAR(32)     DEFAULT NULL COMMENT 'LOGOUT/LOGOUT_ALL/REPLAY/PASSWORD_CHANGED/ADMIN',
  PRIMARY KEY (family_id),
  KEY idx_login_sessions_user_active (user_id, revoked_at, absolute_expires_at),
  KEY idx_login_sessions_expires (absolute_expires_at),
  CONSTRAINT fk_login_sessions_user
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='登录会话（多设备管理）';

-- E2. 邮箱验证码与发送额度
-- email 单独使用 utf8mb4_0900_as_ci，与 users.email 比较语义一致
CREATE TABLE email_verifications (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  email           VARCHAR(254)
                    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci
                    NOT NULL COMMENT '目标邮箱（统一小写）',
  purpose         ENUM('REGISTER','LOGIN','RESET_PASSWORD','CHANGE_EMAIL_OLD','CHANGE_EMAIL_NEW')
                                  NOT NULL COMMENT '验证码用途',
  user_id         BIGINT UNSIGNED DEFAULT NULL COMMENT '关联用户（换绑/重置时必填）',
  family_id       CHAR(36)        DEFAULT NULL COMMENT '绑定的登录会话（换绑时必填）',
  code_hash       CHAR(64)        NOT NULL COMMENT '验证码 HMAC-SHA256 摘要',
  attempts        TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已尝试次数',
  created_at      DATETIME(6)     NOT NULL COMMENT '创建时间（UTC）',
  expires_at      DATETIME(6)     NOT NULL COMMENT '过期时间（UTC）',
  consumed_at     DATETIME(6)     DEFAULT NULL COMMENT '消费时间（UTC）',
  invalidated_at  DATETIME(6)     DEFAULT NULL COMMENT '主动作废时间（UTC）',
  request_ip      VARCHAR(45)     NOT NULL COMMENT '请求 IP',
  send_status     ENUM('PENDING','SENT','FAILED') NOT NULL DEFAULT 'PENDING' COMMENT '发送状态',
  PRIMARY KEY (id),
  KEY idx_email_verifications_email_purpose_created (email, purpose, created_at),
  KEY idx_email_verifications_email_created (email, created_at),
  KEY idx_email_verifications_ip_created (request_ip, created_at),
  KEY idx_email_verifications_created (created_at),
  KEY idx_email_verifications_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='邮箱验证码与发送额度';

-- E3. 认证安全事件（持久化限流 + 审计）；user_id 不建物理外键
CREATE TABLE auth_events (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id     BIGINT UNSIGNED DEFAULT NULL COMMENT '用户 ID（不建外键，保留历史）',
  identifier  VARCHAR(254)
                CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci
                DEFAULT NULL COMMENT '登录标识（用户名/邮箱）',
  event_type  VARCHAR(32)     NOT NULL COMMENT '事件类型',
  ip          VARCHAR(45)     DEFAULT NULL COMMENT '请求 IP',
  family_id   CHAR(36)        DEFAULT NULL COMMENT '关联会话',
  created_at  DATETIME(6)     NOT NULL COMMENT '发生时间（UTC）',
  PRIMARY KEY (id),
  KEY idx_auth_events_user_time (user_id, created_at),
  KEY idx_auth_events_identifier_type_time (identifier, event_type, created_at),
  KEY idx_auth_events_ip_type_time (ip, event_type, created_at),
  KEY idx_auth_events_type_time (event_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='认证安全事件（保留 30 天）';

-- E4. 核对
SHOW CREATE TABLE login_sessions;
SHOW CREATE TABLE email_verifications;
SHOW CREATE TABLE auth_events;

-- E5. 断言：三表存在且 email / identifier 列级排序规则为 as_ci
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
      (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('login_sessions', 'email_verifications', 'auth_events')) = 3
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'email_verifications'
         AND column_name = 'email'
         AND collation_name = 'utf8mb4_0900_as_ci') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'auth_events'
         AND column_name = 'identifier'
         AND collation_name = 'utf8mb4_0900_as_ci') = 1
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- =====================================================================
-- 分区 F：迁移后验证（只读 + 断言）
-- =====================================================================

-- F1. 表数量（预期 17）
SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema = DATABASE();

SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

-- F2. 最终 DDL
SHOW CREATE TABLE users;
SHOW CREATE TABLE refresh_tokens;
SHOW CREATE TABLE login_sessions;
SHOW CREATE TABLE email_verifications;
SHOW CREATE TABLE auth_events;

-- F3. 行数（预期 users / refresh_tokens / 业务表 / 新表均为 0，ai_guard_mutex = 1）
SELECT 'users' AS tbl, COUNT(*) AS rows_cnt FROM users
UNION ALL SELECT 'refresh_tokens', COUNT(*) FROM refresh_tokens
UNION ALL SELECT 'login_sessions', COUNT(*) FROM login_sessions
UNION ALL SELECT 'email_verifications', COUNT(*) FROM email_verifications
UNION ALL SELECT 'auth_events', COUNT(*) FROM auth_events
UNION ALL SELECT 'ai_requests', COUNT(*) FROM ai_requests
UNION ALL SELECT 'ai_guard_mutex', COUNT(*) FROM ai_guard_mutex
UNION ALL SELECT 'study_plans', COUNT(*) FROM study_plans
UNION ALL SELECT 'plan_steps', COUNT(*) FROM plan_steps
UNION ALL SELECT 'daily_tasks', COUNT(*) FROM daily_tasks
UNION ALL SELECT 'schedule_entries', COUNT(*) FROM schedule_entries
UNION ALL SELECT 'task_rollovers', COUNT(*) FROM task_rollovers
UNION ALL SELECT 'study_records', COUNT(*) FROM study_records
UNION ALL SELECT 'focus_sessions', COUNT(*) FROM focus_sessions
UNION ALL SELECT 'knowledge_notes', COUNT(*) FROM knowledge_notes
UNION ALL SELECT 'knowledge_review_records', COUNT(*) FROM knowledge_review_records
UNION ALL SELECT 'practice_records', COUNT(*) FROM practice_records;

-- F4. AUTO_INCREMENT 当前值（与分区 A7 记录人工逐项比对，确认未被重置）
SELECT table_name, auto_increment
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

-- F5. 外键（预期 22 条）
SELECT k.TABLE_NAME AS table_name,
       k.CONSTRAINT_NAME AS constraint_name,
       k.COLUMN_NAME AS column_name,
       k.REFERENCED_TABLE_NAME AS referenced_table,
       k.REFERENCED_COLUMN_NAME AS referenced_column,
       r.DELETE_RULE AS delete_rule
FROM information_schema.KEY_COLUMN_USAGE k
JOIN information_schema.REFERENTIAL_CONSTRAINTS r
  ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
 AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME;

-- F6. 认证表索引
SELECT table_name, index_name, non_unique, seq_in_index, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN ('users', 'refresh_tokens', 'login_sessions', 'email_verifications', 'auth_events')
ORDER BY table_name, index_name, seq_in_index;

-- F7. 字符集/排序规则
SELECT table_name, table_collation
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('users', 'refresh_tokens', 'login_sessions', 'email_verifications', 'auth_events');

-- F8. email / identifier 列定义与列级排序规则
SELECT table_name, column_name, column_type, is_nullable, character_set_name, collation_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
    (table_name IN ('users', 'email_verifications') AND column_name = 'email')
    OR (table_name = 'auth_events' AND column_name = 'identifier')
  )
ORDER BY table_name;

-- F9. 强制断言
CREATE TEMPORARY TABLE `__a0_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_a0_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__a0_assert` (`ok`)
SELECT IF(
  -- 17 张表且全部命中预期清单
      DATABASE() = @a0_expected_db
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()) = 17
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN (
           'users', 'refresh_tokens', 'login_sessions', 'email_verifications',
           'auth_events', 'ai_requests', 'ai_guard_mutex',
           'study_plans', 'plan_steps', 'daily_tasks', 'schedule_entries',
           'task_rollovers', 'study_records', 'focus_sessions',
           'knowledge_notes', 'knowledge_review_records', 'practice_records'
         )) = 17
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_name LIKE 'tb%') = 0
  -- 22 条外键
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()) = 22
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()
         AND constraint_name = 'fk_login_sessions_user') = 1
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()
         AND constraint_name = 'fk_refresh_token_user') = 1
  -- 数据为空 + 保留 mutex
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM refresh_tokens) = 0
  AND (SELECT COUNT(*) FROM login_sessions) = 0
  AND (SELECT COUNT(*) FROM email_verifications) = 0
  AND (SELECT COUNT(*) FROM auth_events) = 0
  AND (SELECT COUNT(*) FROM ai_requests) = 0
  AND (SELECT COUNT(*) FROM study_plans) = 0
  AND (SELECT COUNT(*) FROM plan_steps) = 0
  AND (SELECT COUNT(*) FROM daily_tasks) = 0
  AND (SELECT COUNT(*) FROM schedule_entries) = 0
  AND (SELECT COUNT(*) FROM task_rollovers) = 0
  AND (SELECT COUNT(*) FROM study_records) = 0
  AND (SELECT COUNT(*) FROM focus_sessions) = 0
  AND (SELECT COUNT(*) FROM knowledge_notes) = 0
  AND (SELECT COUNT(*) FROM knowledge_review_records) = 0
  AND (SELECT COUNT(*) FROM practice_records) = 0
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  -- 结构：email 列级排序规则、NOT NULL、索引
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name = 'email' AND column_type = 'varchar(254)'
         AND is_nullable = 'NO' AND collation_name = 'utf8mb4_0900_as_ci') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'email_verifications'
         AND column_name = 'email' AND column_type = 'varchar(254)'
         AND is_nullable = 'NO' AND collation_name = 'utf8mb4_0900_as_ci') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'auth_events'
         AND column_name = 'identifier' AND column_type = 'varchar(254)'
         AND is_nullable = 'YES' AND collation_name = 'utf8mb4_0900_as_ci') = 1
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND index_name = 'uk_users_email' AND non_unique = 0) = 1
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND index_name = 'uk_users_username' AND non_unique = 0) = 1
  -- 新表默认排序规则不变（仅 email 与 identifier 列单独 as_ci）
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('login_sessions', 'email_verifications', 'auth_events')
         AND table_collation = 'utf8mb4_0900_ai_ci') = 3
  , 1, 0
);

DROP TEMPORARY TABLE `__a0_assert`;

-- 未报错即表示迁移全部验证通过。

-- =====================================================================
-- 失败清理方案（仅供人工处理；出错后不得借此继续执行后续分区）
-- 1. 任意断言或 SQL 失败：mysql 客户端非 0 退出并关闭连接，
--    __a0_assert 临时表随连接自动销毁。
-- 2. 若使用交互会话且连接仍打开：
--      DROP TEMPORARY TABLE IF EXISTS __a0_assert;
-- 3. 若分区 B 失败：过程内事务已 ROLLBACK，但过程定义可能仍存在：
--      DROP PROCEDURE IF EXISTS a0_auth_v2_cleanup;
--    若准备修复后重跑，B0 也会先执行同样的 DROP，不会重复创建。
-- 4. C/D/E 的 DDL 失败：存储过程已在 B18 删除，临时表按上述方式清理；
--    已成功的 DDL 不回滚，必须停止并记录实际状态，禁止整脚本重跑。
-- =====================================================================

-- =====================================================================
-- 迁移完成。下一步：按报告与后端改造方案同批上线新认证代码；
-- 严禁在迁移后的库上启动旧版认证后端（旧注册接口与旧表名已不兼容）。
-- =====================================================================
