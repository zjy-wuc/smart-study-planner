-- =====================================================================
-- Smart Study Planner V3.0 · A0 增量迁移（候选稿 · 待审查，尚未执行）
-- 目标库：smart_study_planner（正式业务库 · A7.1 候选）
-- 环境：MySQL 8.4.9 / InnoDB / utf8mb4 / utf8mb4_0900_ai_ci
-- 生成日期：2026-11-27
--
-- 执行协议（必须遵守）：
--   1. 本脚本尚未在任何数据库执行。必须先经开发者 + GPT 审查 DDL 后，
--      且仅在 smart_study_planner（正式业务库）上执行。
--   2. 脚本首尾均断言 DATABASE() = @v3_expected_db，防止连错库。
--   3. 全程禁止 SET FOREIGN_KEY_CHECKS=0，禁止 mysql --force。
--   4. 若出现部分 DDL 成功、部分失败，立即停止并报告实际状态；
--      禁止盲目重跑整个脚本。
--   5. 变更范围仅三处（不得增加其它结构）：
--        (1) users 增加 role 列（ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER'）
--        (2) 新建 admin_audit_logs（管理员操作审计，长期保留，不级联删除）
--        (3) 新建 ai_runtime_config（AI 运行时动态配置，固定单行 id=1）
--   6. 不新增 Key-Value 配置框架，不新增 AI 用量统计表，
--      不修改既有 17 张表的字段/索引/外键。
--   7. 执行方式：
--        mysql --default-character-set=utf8mb4 --database=smart_study_planner \
--          < Smart_Study_Planner_V3.0_A0_Migration.sql
--
-- 分区：
--   A 迁移前断言（只读）
--   B 结构变更（DDL）
--   C 初始化系统配置（DML，单行 id=1）
--   D 迁移后断言（只读 + 强制 CHECK）
--   E 手工负向验证（注释状态，需人工逐条执行，不属于自动流程）
-- =====================================================================

SET NAMES utf8mb4;

SET @v3_expected_db = 'smart_study_planner';

-- =====================================================================
-- 分区 A：迁移前断言（只读，不修改任何数据）
-- =====================================================================

-- A0. 库名、版本、字符集
SELECT
  DATABASE()          AS current_db,
  @v3_expected_db     AS expected_db,
  CURRENT_USER()      AS migration_account,
  VERSION()           AS mysql_version,
  @@collation_server  AS server_collation;

-- A1. 既有 17 张表清单（应恰好 17 张）
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;

-- A2. 目标新结构不应存在（预期 0 行）
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('admin_audit_logs', 'ai_runtime_config');

-- A3. users 不应已存在 role 列（预期 0 行）
SELECT column_name
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'users'
  AND column_name = 'role';

-- A4. 强制断言：库名 / 17 表 / 无目标新结构 / users 无 role / mutex 单行 / users 为空
CREATE TEMPORARY TABLE `__v3_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_v3_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__v3_assert` (`ok`)
SELECT IF(
      DATABASE() = @v3_expected_db
  -- 严格 SQL Mode
  AND @@SESSION.sql_mode LIKE '%STRICT_TRANS_TABLES%'
  -- 表数量与精确表集合（17 张）
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE') = 17
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
         AND table_name IN (
           'users', 'login_sessions', 'refresh_tokens', 'auth_events',
           'email_verifications', 'ai_requests', 'ai_guard_mutex',
           'study_plans', 'plan_steps', 'daily_tasks', 'study_records',
           'schedule_entries', 'task_rollovers', 'knowledge_notes',
           'knowledge_review_records', 'practice_records', 'focus_sessions'
         )) = 17
  -- 目标新结构不存在
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('admin_audit_logs', 'ai_runtime_config')) = 0
  -- users 无 role
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE()
         AND table_name = 'users' AND column_name = 'role') = 0
  -- 系统表初始化
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  -- 原有 16 张非系统表全部为空
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM login_sessions) = 0
  AND (SELECT COUNT(*) FROM refresh_tokens) = 0
  AND (SELECT COUNT(*) FROM auth_events) = 0
  AND (SELECT COUNT(*) FROM email_verifications) = 0
  AND (SELECT COUNT(*) FROM ai_requests) = 0
  AND (SELECT COUNT(*) FROM study_plans) = 0
  AND (SELECT COUNT(*) FROM plan_steps) = 0
  AND (SELECT COUNT(*) FROM daily_tasks) = 0
  AND (SELECT COUNT(*) FROM study_records) = 0
  AND (SELECT COUNT(*) FROM schedule_entries) = 0
  AND (SELECT COUNT(*) FROM task_rollovers) = 0
  AND (SELECT COUNT(*) FROM knowledge_notes) = 0
  AND (SELECT COUNT(*) FROM knowledge_review_records) = 0
  AND (SELECT COUNT(*) FROM practice_records) = 0
  AND (SELECT COUNT(*) FROM focus_sessions) = 0
  , 1, 0
);

DROP TEMPORARY TABLE `__v3_assert`;

-- 未报错即表示分区 A 全部断言通过。

-- =====================================================================
-- 分区 B：结构变更（DDL）
-- =====================================================================

-- B1. users 增加角色列；默认 USER，保证既有/新增用户均为普通角色
ALTER TABLE `users`
  ADD COLUMN `role` ENUM('USER','ADMIN')
    NOT NULL DEFAULT 'USER'
    COMMENT '用户角色：USER=普通用户，ADMIN=管理员'
    AFTER `is_active`;

-- B2. 管理员操作审计日志
--     - 长期保留：admin_id 不建物理外键（与 auth_events.user_id 同策略），
--       避免用户行被删除时阻塞或导致审计数据丢失
--     - 不使用级联删除；不包含 ip / user_agent / result 等未确认字段
--     - action 仅四个取值（由应用层常量/枚举约束，不加 DB CHECK）：
--         BAN_USER / UNBAN_USER / REVOKE_SESSIONS / UPDATE_AI_CONFIG
--     - target_type 仅两个取值：USER / AI_CONFIG
CREATE TABLE `admin_audit_logs` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `admin_id`    BIGINT UNSIGNED NOT NULL COMMENT '操作管理员 users.id（不建外键，审计长期保留）',
  `action`      VARCHAR(32)     NOT NULL COMMENT '操作类型：BAN_USER / UNBAN_USER / REVOKE_SESSIONS / UPDATE_AI_CONFIG',
  `target_type` VARCHAR(32)     NOT NULL COMMENT '目标类型：USER / AI_CONFIG',
  `target_id`   BIGINT UNSIGNED NOT NULL COMMENT '目标主键（users.id 或 ai_runtime_config.id）',
  `before_data` JSON            NOT NULL COMMENT '变更前快照（禁止存放密码哈希/Token）',
  `after_data`  JSON            NOT NULL COMMENT '变更后快照（禁止存放密码哈希/Token）',
  `reason`      VARCHAR(200)    NOT NULL COMMENT '操作原因（1~200 字符）',
  `created_at`  DATETIME(6)     NOT NULL COMMENT '操作时间（UTC，由后端显式写入）',
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_created`        (`created_at`),
  KEY `idx_admin_audit_action_created` (`action`, `created_at`),
  KEY `idx_admin_audit_admin_created`  (`admin_id`, `created_at`),
  KEY `idx_admin_audit_target`         (`target_type`, `target_id`, `created_at`),
  CONSTRAINT `chk_admin_audit_reason_len`
    CHECK (CHAR_LENGTH(TRIM(`reason`)) BETWEEN 1 AND 200)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='管理员操作审计日志（长期保留，不级联删除）';

-- B3. AI 运行时动态配置（固定单行 id=1）
--     - 只承载准入参数：开关 / 单用户日额度 / 全站日额度
--     - 不建 Key-Value 配置框架
--     - updated_at 由应用通过 utc_db_now() 显式写入 UTC，不使用 DB 默认值
CREATE TABLE `ai_runtime_config` (
  `id`                 TINYINT UNSIGNED NOT NULL COMMENT '固定为 1（单行配置）',
  `enabled`            TINYINT          NOT NULL DEFAULT 1 COMMENT 'AI 总开关：1 开启，0 关闭',
  `user_daily_limit`   INT UNSIGNED     NOT NULL DEFAULT 10 COMMENT '单用户每日 AI 请求额度',
  `global_daily_limit` INT UNSIGNED     NOT NULL DEFAULT 80 COMMENT '全站每日 AI 请求额度',
  `updated_at`         DATETIME(6)      NOT NULL COMMENT '最后修改时间（UTC，应用显式写入）',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_ai_runtime_config_single_row` CHECK (`id` = 1),
  CONSTRAINT `chk_ai_runtime_config_enabled`    CHECK (`enabled` IN (0, 1)),
  CONSTRAINT `chk_ai_runtime_config_global_ge_user`
    CHECK (`global_daily_limit` >= `user_daily_limit`),
  CONSTRAINT `chk_ai_runtime_config_positive`
    CHECK (`user_daily_limit` > 0 AND `global_daily_limit` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='AI 运行时动态配置（固定单行，id=1）';

-- B4. 核对结构
SHOW CREATE TABLE `users`;
SHOW CREATE TABLE `admin_audit_logs`;
SHOW CREATE TABLE `ai_runtime_config`;

-- =====================================================================
-- 分区 C：初始化系统配置（以当前生效的 AI 配置为准）
--   实测当前生效值：AI_ENABLED=True，单用户每日 10，全站每日 80
--   若审查时实际配置不同，必须先报告差异，再修改本段常量
-- =====================================================================

INSERT INTO `ai_runtime_config` (
  `id`, `enabled`, `user_daily_limit`, `global_daily_limit`, `updated_at`
) VALUES (
  1, 1, 10, 80, UTC_TIMESTAMP(6)
);

-- =====================================================================
-- 分区 D：迁移后断言（只读 + 强制 CHECK）
-- =====================================================================

-- D1. 表数量（预期 19）与清单
SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';

SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- D2. users.role 定义
SELECT column_name, column_type, is_nullable, column_default, collation_name
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'role';

-- D3. 审计表字段与索引
SELECT column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
ORDER BY ordinal_position;

SELECT index_name, non_unique, seq_in_index, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
ORDER BY index_name, seq_in_index;

SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
ORDER BY constraint_name;

-- D4. 动态配置字段、约束与当前行
SELECT column_name, column_type, is_nullable, column_default, extra
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config'
ORDER BY ordinal_position;

SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config'
ORDER BY constraint_name;

SELECT `id`, `enabled`, `user_daily_limit`, `global_daily_limit`, `updated_at`
FROM `ai_runtime_config`;

-- D5. 强制断言
CREATE TEMPORARY TABLE `__v3_assert` (
  `ok` TINYINT NOT NULL,
  CONSTRAINT `chk_v3_assert` CHECK (`ok` = 1)
) ENGINE=InnoDB;

INSERT INTO `__v3_assert` (`ok`)
SELECT IF(
  -- 库名与 19 张表
      DATABASE() = @v3_expected_db
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE') = 19
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
         AND table_name IN (
           'users', 'refresh_tokens', 'login_sessions', 'email_verifications',
           'auth_events', 'ai_requests', 'ai_guard_mutex',
           'study_plans', 'plan_steps', 'daily_tasks', 'schedule_entries',
           'task_rollovers', 'study_records', 'focus_sessions',
           'knowledge_notes', 'knowledge_review_records', 'practice_records',
           'admin_audit_logs', 'ai_runtime_config'
         )) = 19
  -- users.role 定义
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users'
         AND column_name = 'role'
         AND column_type = 'enum(''USER'',''ADMIN'')'
         AND is_nullable = 'NO'
         AND column_default = 'USER') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'users') = 12
  -- 审计表：9 列、主键、4 个二级索引、1 条 CHECK、无外键
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs') = 9
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND column_name = 'action' AND column_type = 'varchar(32)'
         AND is_nullable = 'NO') = 1
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND column_name IN ('target_id', 'before_data', 'after_data', 'reason')
         AND is_nullable = 'NO') = 4
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND index_name = 'PRIMARY' AND non_unique = 0) = 1
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND index_name IN (
           'idx_admin_audit_created', 'idx_admin_audit_action_created',
           'idx_admin_audit_admin_created', 'idx_admin_audit_target'
         )) = 8
  AND (SELECT COUNT(*) FROM information_schema.table_constraints
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND constraint_type = 'CHECK') = 1
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()
         AND table_name = 'admin_audit_logs') = 0
  -- 动态配置：5 列、固定单行、4 条 CHECK、updated_at 无 DB 默认值
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config') = 5
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config'
         AND column_name = 'updated_at' AND column_type = 'datetime(6)'
         AND is_nullable = 'NO'
         AND column_default IS NULL
         AND extra NOT LIKE '%on update%') = 1
  AND (SELECT COUNT(*) FROM information_schema.table_constraints
       WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config'
         AND constraint_type = 'CHECK') = 4
  AND (SELECT COUNT(*) FROM `ai_runtime_config`) = 1
  AND (SELECT COUNT(*) FROM `ai_runtime_config`
       WHERE id = 1 AND enabled = 1
         AND user_daily_limit = 10 AND global_daily_limit = 80) = 1
  -- ai_guard_mutex 初始化保持正确
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  -- 原有 16 张非系统表仍为空（迁移只改结构，不引入业务数据）
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM login_sessions) = 0
  AND (SELECT COUNT(*) FROM refresh_tokens) = 0
  AND (SELECT COUNT(*) FROM auth_events) = 0
  AND (SELECT COUNT(*) FROM email_verifications) = 0
  AND (SELECT COUNT(*) FROM ai_requests) = 0
  AND (SELECT COUNT(*) FROM study_plans) = 0
  AND (SELECT COUNT(*) FROM plan_steps) = 0
  AND (SELECT COUNT(*) FROM daily_tasks) = 0
  AND (SELECT COUNT(*) FROM study_records) = 0
  AND (SELECT COUNT(*) FROM schedule_entries) = 0
  AND (SELECT COUNT(*) FROM task_rollovers) = 0
  AND (SELECT COUNT(*) FROM knowledge_notes) = 0
  AND (SELECT COUNT(*) FROM knowledge_review_records) = 0
  AND (SELECT COUNT(*) FROM practice_records) = 0
  AND (SELECT COUNT(*) FROM focus_sessions) = 0
  AND (SELECT COUNT(*) FROM admin_audit_logs) = 0
  , 1, 0
);

DROP TEMPORARY TABLE `__v3_assert`;

-- 未报错即表示 V3.0 增量迁移全部断言通过。

-- =====================================================================
-- 分区 E：手工负向验证（不属于自动流程；逐条单独执行）
--   要求：
--     - 每条在显式事务中执行，捕获错误后 ROLLBACK，不遗留探针数据
--     - INSERT 必须提供全部合法必填字段，确保失败原因只能来自目标约束
--     - 每条都应当报错，报错即“被拒绝”，不要修改脚本去绕过
-- =====================================================================
-- E0. 合法基准行（证明“字段齐全时不会因非约束原因失败”；执行后 ROLLBACK）
-- START TRANSACTION;
-- INSERT INTO admin_audit_logs
--   (admin_id, action, target_type, target_id, before_data, after_data, reason, created_at)
-- VALUES
--   (1, 'BAN_USER', 'USER', 1, JSON_OBJECT(), JSON_OBJECT(), '违规操作', UTC_TIMESTAMP(6));
-- ROLLBACK;
--
-- E1. 第二条 AI 配置记录（预期 3819：chk_ai_runtime_config_single_row）
-- START TRANSACTION;
-- INSERT INTO ai_runtime_config (id, enabled, user_daily_limit, global_daily_limit, updated_at)
-- VALUES (2, 1, 10, 80, UTC_TIMESTAMP(6));
-- ROLLBACK;
--
-- E2. 单用户额度大于全站额度（预期 3819：chk_ai_runtime_config_global_ge_user）
-- START TRANSACTION;
-- UPDATE ai_runtime_config SET user_daily_limit = 500 WHERE id = 1;
-- ROLLBACK;
--
-- E3. 负数额度（预期 1264：out of range，UNSIGNED 拒绝）
-- START TRANSACTION;
-- UPDATE ai_runtime_config SET global_daily_limit = -1 WHERE id = 1;
-- ROLLBACK;
--
-- E4. 零额度（预期 3819：chk_ai_runtime_config_positive）
-- START TRANSACTION;
-- UPDATE ai_runtime_config SET user_daily_limit = 0 WHERE id = 1;
-- ROLLBACK;
--
-- E5. 非法开关值（预期 3819：chk_ai_runtime_config_enabled）
-- START TRANSACTION;
-- UPDATE ai_runtime_config SET enabled = 2 WHERE id = 1;
-- ROLLBACK;
--
-- E6. 非法角色（预期 1265：Data truncated，ENUM 拒绝）
--   已提供 users 全部 NOT NULL 字段，失败只能来自 role
-- START TRANSACTION;
-- INSERT INTO users (username, password_hash, password_updated_at, email,
--                    email_verified_at, nickname, is_active, role)
-- VALUES ('tmp_role_probe', 'x', UTC_TIMESTAMP(6), 'probe@example.invalid',
--         UTC_TIMESTAMP(6), 'probe', 1, 'SUPER');
-- ROLLBACK;
--
-- E7. NULL 操作原因（预期 1048：Column 'reason' cannot be null）
-- START TRANSACTION;
-- INSERT INTO admin_audit_logs
--   (admin_id, action, target_type, target_id, before_data, after_data, reason, created_at)
-- VALUES (1, 'BAN_USER', 'USER', 1, JSON_OBJECT(), JSON_OBJECT(), NULL, UTC_TIMESTAMP(6));
-- ROLLBACK;
--
-- E8. 空白操作原因（预期 3819：chk_admin_audit_reason_len）
-- START TRANSACTION;
-- INSERT INTO admin_audit_logs
--   (admin_id, action, target_type, target_id, before_data, after_data, reason, created_at)
-- VALUES (1, 'BAN_USER', 'USER', 1, JSON_OBJECT(), JSON_OBJECT(), '   ', UTC_TIMESTAMP(6));
-- ROLLBACK;
--
-- E9. NULL 审计快照（预期 1048：Column 'before_data' cannot be null）
-- START TRANSACTION;
-- INSERT INTO admin_audit_logs
--   (admin_id, action, target_type, target_id, before_data, after_data, reason, created_at)
-- VALUES (1, 'BAN_USER', 'USER', 1, NULL, JSON_OBJECT(), '违规操作', UTC_TIMESTAMP(6));
-- ROLLBACK;
--
-- 负向验证结束后确认无残留：
-- SELECT COUNT(*) FROM admin_audit_logs;
-- SELECT id, enabled, user_daily_limit, global_daily_limit FROM ai_runtime_config;
-- 预期：审计表 0 行，配置行仍为 1 / 1 / 10 / 80。

-- =====================================================================
-- 迁移结束。
-- 注意：本迁移只建立 V3.0 开发库结构，不包含任何 Auth V2 历史数据清理。
-- Auth V2 的 R3 清理脚本（docs/Auth_V2_A0_Migration.sql）本期未执行。
-- =====================================================================