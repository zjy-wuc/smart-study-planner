# Smart Study Planner V3.0 — A0.3 最终数据库准备与测试基线报告

> 阶段：A0.3（独立开发库准备 / 增量迁移候选稿 / Auth V2 资产核对 / 测试基线）
> 完成时间：2026-11-27
> 代码基线：`d511f08`（2026-11-27，Auth V2 A2 + V3.0 A0 盘点报告）
> 运行环境：Windows / PowerShell 5 / Python 3.14 / MySQL 8.4.9（127.0.0.1:3306）
> 约束执行声明：未修改正式业务库结构或数据；未执行 V3.0 增量迁移；未执行 Auth V2 的 R3 清理；
> 未安装 Redis；未发送真实邮件；未调用真实付费 AI；未修改任何业务源码（仅 5 个测试文件的最小夹具/断言修正）。

---

## 0. 结论摘要

| 项目 | 结果 |
| --- | --- |
| 独立开发库 `ssp_v3_admin_dev` | **已创建**：17 张表（结构签名与 `ssp_a0_migrate2` 完全一致），仅保留 `ai_guard_mutex` id=1 一行，未复制任何用户/会话/Token/认证事件 |
| V3.0 增量迁移 SQL | **已生成候选稿**（3 处变更），**尚未执行**，等待开发者 + GPT 审查 |
| Auth V2 R3 迁移资产 | `docs/Auth_V2_A0_Migration.sql` 确认为 **R3 最终版**，SHA256 已记录；**未执行** |
| 测试基线 | 全量 511 项：**497 通过 / 5 失败 / 9 跳过 / 8 子测试通过**；5 个失败中 1 个为真实产品缺陷，2 个为已过时断言，2 个为测试隔离问题 |
| Redis | 未安装、未接入、未编写业务代码（符合本期边界） |

**审查门（Gate）**：`Smart_Study_Planner_V3.0_A0_Migration.sql` 未在任何数据库执行。审查通过前不得执行。

---

## 1. 独立开发数据库准备结果

### 1.1 处理原则

- 保留且不修改：`smart_study_planner`、`ssp_a0_legacy`、`ssp_a0_migrate`、`ssp_a0_migrate2`。
- 以 `ssp_a0_migrate2`（Auth V2 最终 17 表结构）为模板，新建 `ssp_v3_admin_dev`。
- 仅复制结构 + 必要系统初始化记录（`ai_guard_mutex` id=1）。
- 不复制：测试用户、`auth_events`、`refresh_tokens`、`login_sessions`、`email_verifications`、`ai_requests` 等任何业务/测试数据。

### 1.2 数据库与字符集实测

| 项 | 实测值 |
| --- | --- |
| MySQL 版本 | 8.4.9 |
| 服务器 `collation_server` | `utf8mb4_general_ci` |
| 源库 `ssp_a0_migrate2` 默认字符集/排序规则 | `utf8mb4` / `utf8mb4_0900_ai_ci` |
| 新库 `ssp_v3_admin_dev` | `utf8mb4` / `utf8mb4_0900_ai_ci` |
| `ai_guard_mutex` 表排序规则（历史遗留） | `utf8mb4_general_ci`（与源库一致，未改动） |

### 1.3 建库方式（可复核）

未使用 `mysqldump`（避免把凭据写入命令行），改用只读方式：

1. 读取 `information_schema` 统计 17 表及其外键依赖；
2. 按外键拓扑序生成建表顺序：
   `ai_guard_mutex → ai_requests → auth_events → users → study_plans → plan_steps → daily_tasks → email_verifications → focus_sessions → knowledge_notes → knowledge_review_records → login_sessions → practice_records → refresh_tokens → schedule_entries → study_records → task_rollovers`
3. 逐表执行源库 `SHOW CREATE TABLE` 的原始 DDL（**未关闭外键检查**）；
4. 执行 `INSERT INTO ai_guard_mutex (id) VALUES (1);`
5. 结构与数据双向校验。

### 1.4 创建结果

```
table_count: 17
tables: ai_guard_mutex, ai_requests, auth_events, daily_tasks, email_verifications,
        focus_sessions, knowledge_notes, knowledge_review_records, login_sessions,
        plan_steps, practice_records, refresh_tokens, schedule_entries, study_plans,
        study_records, task_rollovers, users
非空表：ai_guard_mutex = 1 行（id=1）；其余 16 张表均为 0 行
结构差异（列/索引/约束/排序规则逐表比对）：NONE
```

`ssp_v3_admin_dev` 当前 `users` 仍为 11 列（无 `role`），符合"迁移未执行"的预期状态。

### 1.5 V3.0 独立开发配置方案（未落地、未改动共享 `.env`）

当前后端 `.env` 实际指向 `ssp_a0_migrate2`（Auth V2 测试库）。为不覆盖 Auth V2 的共享配置：

- 建议新增独立配置文件（例如 `back/.env.v3`）或进程级环境变量，仅设置 `DB_NAME=ssp_v3_admin_dev`；
- 测试使用隔离环境（独立 `DB_NAME` + Mock 邮件 + Mock AI），不改动现有 `.env`；
- **本阶段未创建/未修改任何 `.env` 文件**。是否采用 `.env.v3` 由开发者确认。

---

## 2. 最终候选增量迁移 SQL

- 文件路径：`d:\project\back\Smart_Study_Planner_V3.0_A0_Migration.sql`
- 文件大小：约 13 KB
- SHA256：`D952515F43F91BBF23D537EB28B75F144BD1EEBF09A053FCDE49826FE6AEE07E`
- 状态：**未执行**；目标库唯一允许为 `ssp_v3_admin_dev`
- 变更范围：仅 `users.role`、新建 `admin_audit_logs`、新建 `ai_runtime_config`

### 2.1 完整 SQL（候选稿原文）

```sql
-- =====================================================================
-- Smart Study Planner V3.0 · A0 增量迁移（候选稿 · 待审查，尚未执行）
-- 目标库：ssp_v3_admin_dev（V3.0 独立开发库）
-- 环境：MySQL 8.4.9 / InnoDB / utf8mb4 / utf8mb4_0900_ai_ci
-- 生成日期：2026-11-27
--
-- 执行协议（必须遵守）：
--   1. 本脚本尚未在任何数据库执行。必须先经开发者 + GPT 审查 DDL 后，
--      且仅在 ssp_v3_admin_dev 上执行。
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
--        mysql --default-character-set=utf8mb4 --database=ssp_v3_admin_dev \
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

SET @v3_expected_db = 'ssp_v3_admin_dev';

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
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE') = 17
  AND (SELECT COUNT(*) FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN ('admin_audit_logs', 'ai_runtime_config')) = 0
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE()
         AND table_name = 'users' AND column_name = 'role') = 0
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM login_sessions) = 0
  AND (SELECT COUNT(*) FROM refresh_tokens) = 0
  AND (SELECT COUNT(*) FROM auth_events) = 0
  AND (SELECT COUNT(*) FROM email_verifications) = 0
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
CREATE TABLE `admin_audit_logs` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `admin_id`    BIGINT UNSIGNED NOT NULL COMMENT '操作管理员 users.id（不建外键，审计长期保留）',
  `action`      VARCHAR(64)     NOT NULL COMMENT '操作类型，如 USER_BAN / USER_UNBAN / USER_FORCE_LOGOUT / USER_ROLE_UPDATE / AI_CONFIG_UPDATE',
  `target_type` VARCHAR(32)     NOT NULL COMMENT '目标类型：USER / AI_CONFIG / SYSTEM',
  `target_id`   BIGINT UNSIGNED DEFAULT NULL COMMENT '目标主键（users.id 或 ai_runtime_config.id）',
  `before_data` JSON            DEFAULT NULL COMMENT '变更前快照（仅敏感字段，禁止存放密码哈希/Token）',
  `after_data`  JSON            DEFAULT NULL COMMENT '变更后快照（仅敏感字段，禁止存放密码哈希/Token）',
  `reason`      VARCHAR(200)    DEFAULT NULL COMMENT '操作原因（用户可见）',
  `created_at`  DATETIME(6)     NOT NULL COMMENT '操作时间（UTC，由后端显式写入）',
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_created`        (`created_at`),
  KEY `idx_admin_audit_action_created` (`action`, `created_at`),
  KEY `idx_admin_audit_admin_created`  (`admin_id`, `created_at`),
  KEY `idx_admin_audit_target`         (`target_type`, `target_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='管理员操作审计日志（长期保留，不级联删除）';

-- B3. AI 运行时动态配置（固定单行 id=1）
--     - 只承载准入参数：开关 / 单用户日额度 / 全站日额度
--     - 不建 Key-Value 配置框架
--     - updated_at 由 MySQL 会话时区（+08:00）维护，与 users.created_at 一致
CREATE TABLE `ai_runtime_config` (
  `id`                 TINYINT UNSIGNED NOT NULL COMMENT '固定为 1（单行配置）',
  `enabled`            TINYINT          NOT NULL DEFAULT 1 COMMENT 'AI 总开关：1 开启，0 关闭',
  `user_daily_limit`   INT UNSIGNED     NOT NULL DEFAULT 10 COMMENT '单用户每日 AI 请求额度',
  `global_daily_limit` INT UNSIGNED     NOT NULL DEFAULT 80 COMMENT '全站每日 AI 请求额度',
  `updated_at`         DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                        ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后修改时间',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_ai_runtime_config_single_row` CHECK (`id` = 1),
  CONSTRAINT `chk_ai_runtime_config_enabled`    CHECK (`enabled` IN (0, 1)),
  CONSTRAINT `chk_ai_runtime_config_global_ge_user`
    CHECK (`global_daily_limit` >= `user_daily_limit`)
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

-- D4. 动态配置字段、约束与当前行
SELECT column_name, column_type, is_nullable, column_default
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
  -- 审计表：9 列、主键、4 个二级索引
  AND (SELECT COUNT(*) FROM information_schema.columns
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs') = 9
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND index_name = 'PRIMARY' AND non_unique = 0) = 1
  AND (SELECT COUNT(*) FROM information_schema.statistics
       WHERE table_schema = DATABASE() AND table_name = 'admin_audit_logs'
         AND index_name IN (
           'idx_admin_audit_created', 'idx_admin_audit_action_created',
           'idx_admin_audit_admin_created', 'idx_admin_audit_target'
         )) = 8
  -- 审计表无物理外键（长期保留策略）
  AND (SELECT COUNT(*) FROM information_schema.referential_constraints
       WHERE constraint_schema = DATABASE()
         AND table_name = 'admin_audit_logs') = 0
  -- 动态配置：固定单行、4 条 CHECK、初始值与当前生效配置一致
  AND (SELECT COUNT(*) FROM `ai_runtime_config`) = 1
  AND (SELECT COUNT(*) FROM `ai_runtime_config`
       WHERE id = 1 AND enabled = 1
         AND user_daily_limit = 10 AND global_daily_limit = 80) = 1
  AND (SELECT COUNT(*) FROM information_schema.table_constraints
       WHERE table_schema = DATABASE() AND table_name = 'ai_runtime_config'
         AND constraint_type = 'CHECK') = 4
  -- ai_guard_mutex 初始化保持正确
  AND (SELECT COUNT(*) FROM ai_guard_mutex) = 1
  AND (SELECT COALESCE(SUM(id = 1), 0) FROM ai_guard_mutex) = 1
  -- 原有表数据仍为空（迁移只改结构，不引入业务数据）
  AND (SELECT COUNT(*) FROM users) = 0
  AND (SELECT COUNT(*) FROM login_sessions) = 0
  AND (SELECT COUNT(*) FROM refresh_tokens) = 0
  AND (SELECT COUNT(*) FROM auth_events) = 0
  AND (SELECT COUNT(*) FROM email_verifications) = 0
  AND (SELECT COUNT(*) FROM ai_requests) = 0
  AND (SELECT COUNT(*) FROM admin_audit_logs) = 0
  , 1, 0
);

DROP TEMPORARY TABLE `__v3_assert`;

-- 未报错即表示 V3.0 增量迁移全部断言通过。

-- =====================================================================
-- 分区 E：手工负向验证（不属于自动流程；逐条单独执行）
--   每条都应当报错，报错即“被拒绝”，不要修改脚本去绕过
-- =====================================================================
-- E1. 动态配置只允许单行 id=1（预期错误 3819：CHECK 约束失败）
-- INSERT INTO ai_runtime_config (id, enabled, user_daily_limit, global_daily_limit)
-- VALUES (2, 1, 10, 80);
--
-- E2. 非法额度：单用户额度大于全站额度（预期错误 3819）
-- UPDATE ai_runtime_config SET user_daily_limit = 500 WHERE id = 1;
--
-- E3. 非法额度：负数（预期错误 1264：out of range，UNSIGNED 拒绝）
-- UPDATE ai_runtime_config SET global_daily_limit = -1 WHERE id = 1;
--
-- E4. 非法开关值（预期错误 3819）
-- UPDATE ai_runtime_config SET enabled = 2 WHERE id = 1;
--
-- E5. 非法角色值（预期错误 1265：Data truncated，ENUM 拒绝）
-- INSERT INTO users (username, password_hash, password_updated_at, email,
--                    email_verified_at, nickname, role)
-- VALUES ('tmp_role_probe', 'x', UTC_TIMESTAMP(6), 'probe@example.invalid',
--         UTC_TIMESTAMP(6), 'probe', 'SUPER');
-- 执行后如产生临时行需删除：DELETE FROM users WHERE username = 'tmp_role_probe';
--
-- 负向验证结束后，确认配置行恢复为初始值：
-- SELECT id, enabled, user_daily_limit, global_daily_limit FROM ai_runtime_config;
-- 若被 E2/E3/E4 修改过并未回滚，必须手工恢复为 enabled=1 / 10 / 80。

-- =====================================================================
-- 迁移结束。
-- 注意：本迁移只建立 V3.0 开发库结构，不包含任何 Auth V2 历史数据清理。
-- Auth V2 的 R3 清理脚本（docs/Auth_V2_A0_Migration.sql）本期未执行。
-- =====================================================================
```

---

## 3. DDL、索引及约束汇总

### 3.1 `users.role`

| 项 | 值 |
| --- | --- |
| 列名 | `role` |
| 类型 | `ENUM('USER','ADMIN')` |
| 可空 | `NOT NULL` |
| 默认值 | `'USER'` |
| 位置 | `AFTER is_active`（第 12 列） |
| 索引 | 不新增（用户量级小，按 role 过滤不是高频分页条件） |
| 迁移后 `users` 列数 | 12 |

### 3.2 `admin_audit_logs`

| 列 | 类型 | 空 | 说明 |
| --- | --- | --- | --- |
| `id` | `BIGINT UNSIGNED AUTO_INCREMENT` | NO | PK |
| `admin_id` | `BIGINT UNSIGNED` | NO | 操作管理员 `users.id`，**不建物理外键**（长期保留） |
| `action` | `VARCHAR(64)` | NO | 操作类型（字典由 A1 常量约束，不写死 CHECK） |
| `target_type` | `VARCHAR(32)` | NO | `USER` / `AI_CONFIG` / `SYSTEM` |
| `target_id` | `BIGINT UNSIGNED` | YES | 目标主键 |
| `before_data` | `JSON` | YES | 变更前快照 |
| `after_data` | `JSON` | YES | 变更后快照 |
| `reason` | `VARCHAR(200)` | YES | 操作原因 |
| `created_at` | `DATETIME(6)` | NO | 操作时间（UTC，应用写入；同 `auth_events` 策略，不用 `CURRENT_TIMESTAMP`） |

索引：

| 索引 | 列 | 用途 |
| --- | --- | --- |
| `PRIMARY` | `id` | 主键 |
| `idx_admin_audit_created` | `created_at` | 时间倒序分页 |
| `idx_admin_audit_action_created` | `action`, `created_at` | 按操作类型筛选 + 时间倒序 |
| `idx_admin_audit_admin_created` | `admin_id`, `created_at` | 按管理员追溯 |
| `idx_admin_audit_target` | `target_type`, `target_id`, `created_at` | 按目标对象追溯（如某用户被操作历史） |

约束：无外键、无级联删除。字符集 `utf8mb4` / `utf8mb4_0900_ai_ci`。

### 3.3 `ai_runtime_config`

| 列 | 类型 | 空 | 默认 |
| --- | --- | --- | --- |
| `id` | `TINYINT UNSIGNED` | NO | —（PK，固定 1） |
| `enabled` | `TINYINT` | NO | 1 |
| `user_daily_limit` | `INT UNSIGNED` | NO | 10 |
| `global_daily_limit` | `INT UNSIGNED` | NO | 80 |
| `updated_at` | `DATETIME(6)` | NO | `CURRENT_TIMESTAMP(6)` + `ON UPDATE` |

CHECK 约束（共 4 条）：

| 约束 | 语义 |
| --- | --- |
| `chk_ai_runtime_config_single_row` | `id = 1` → 配合 PK 保证"只允许固定单行" |
| `chk_ai_runtime_config_enabled` | `enabled IN (0,1)` |
| `chk_ai_runtime_config_global_ge_user` | 全站额度 ≥ 单用户额度（拒绝非法组合） |
| （UNSIGNED 类型层） | 负数额度直接 `1264 out of range` 拒绝 |

初始化：`id=1, enabled=1, user_daily_limit=10, global_daily_limit=80`。
实测当前生效配置：`AI_ENABLED=True`、`AI_USER_DAILY_LIMIT=10`、`AI_GLOBAL_DAILY_LIMIT=80`（与预期一致，**无差异**）。

### 3.4 迁移后断言清单（脚本内 CHECK 强制）

1. `DATABASE() = 'ssp_v3_admin_dev'`；
2. 业务表总数 = 19，且表名集合完全匹配；
3. `users.role` 为 `enum('USER','ADMIN') NOT NULL DEFAULT 'USER'`，`users` 共 12 列；
4. `admin_audit_logs` 9 列、PK、4 个二级索引、无外键；
5. `ai_runtime_config` 恰好 1 行且等于 `1/1/10/80`，CHECK 约束 4 条；
6. `ai_guard_mutex` 恰好 1 行且 id=1；
7. 原有 16 张表数据仍为 0 行，审计表 0 行。

---

## 4. 原数据库未修改的验证证据

采集时间：2026-11-27（迁移候选稿生成后、执行前）。

| 数据库 | 表数 | `users` | `tb_refresh_token` / `refresh_tokens` | `ai_requests` | `ai_guard_mutex` | `study_plans` | `daily_tasks` | `role` 列 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `smart_study_planner`（正式） | 14 | 47 | 216 | 17 | 1 | 39 | 280 | 无 |
| `ssp_a0_legacy` | 14 | 47 | 212 | 17 | 1 | 39 | 280 | 无 |
| `ssp_a0_migrate` | 17 | 0 | 0 | 0 | 1 | 0 | 0 | 无 |
| `ssp_a0_migrate2` | 17 | 0 | 0 | 0 | 1 | 0 | 0 | 无 |
| `ssp_v3_admin_dev`（新建） | 17 | 0 | 0 | 0 | 1 | 0 | 0 | 无 |

结论：

- 正式库 `smart_study_planner` 的 14 表、47 用户、216 Refresh Token、17 条 AI 请求、39 学习计划、280 每日任务与 A0 盘点完全一致 → **未发生任何结构或数据变化**。
- 四个原有库均无 `role` 列、无 `admin_audit_logs`、无 `ai_runtime_config` → **V3.0 增量迁移未被误执行到原库**。
- `ssp_a0_migrate2.auth_events` 由 183 增至 220：来源是本阶段执行自动化测试（该库即测试库），属于预期测试产物，非迁移行为。
- `ssp_v3_admin_dev` 与 `ssp_a0_migrate2` 的 17 表结构签名（列/类型/可空/默认值/索引/约束/排序规则）逐表比对结果为 **NONE（完全一致）**。

---

## 5. Auth V2 R3 迁移资产核对结果

| 项 | 实测 |
| --- | --- |
| 文件路径 | `D:\project\docs\Auth_V2_A0_Migration.sql` |
| 大小 / 行数 | 33,070 字节 / 约 700 行 |
| SHA256 | `EDB6C74B1206E763BB5238DAC2A5E28FA1A22FB1387B2B5CB1B401A897078806` |
| 版本标识 | 头部第 5 行："修订：2026-11-24（R3 最终收尾：identifier 排序规则与清理方案）" → **确认为 R3 最终版** |
| 目标库 | `SET @a0_expected_db = 'smart_study_planner'`（正式库） |
| 迁移报告 | `D:\project\docs\Auth_V2_A0_Report.md`（32,777 字节） |
| 备份路径 | `D:\project\docs\backups\smart_study_planner_pre_auth_v2_20261124.sql`（158,053 字节，2026-11-24 22:36） |
| 备份 SHA256 | `2A01CF37F0A647ABB29D2F73D45CD477D5D68C2C5C5DB710354A0F8393BB31` |
| 执行状态 | **未执行**（本阶段只核对） |

### 5.1 R3 历史数据清理范围（原文行为）

分区 B 在存储过程 `a0_auth_v2_cleanup` 内以单事务执行，COMMIT 前断言、失败自动 ROLLBACK：

1. **清空全部业务数据**：`task_rollovers`、`study_records`、`focus_sessions`、`schedule_entries`、`daily_tasks`、`plan_steps`（先 `parent_id=NULL` 解除自引用）、`study_plans`、`knowledge_review_records`、`practice_records`、`knowledge_notes`；
2. **清空全部账号与认证数据**：`tb_refresh_token`、`ai_requests`、`users`；
3. **保留项**：`ai_guard_mutex` 仅 `id=1` 一行（断言强制）；
4. 清理后断言 13 张目标表全为 0 行；`RENAME TABLE tb_refresh_token TO refresh_tokens`；`users` 增加 `email_verified_at` / `password_updated_at`，`email` 改为 `VARCHAR(254) NOT NULL`（列级 `utf8mb4_0900_as_ci`）；新建 `login_sessions` / `email_verifications` / `auth_events`；最终 17 表、22 外键。

**风险提示（需开发者确认）**：R3 会删除正式库全部 47 个账号、216 条 Refresh Token、39 个学习计划、280 条每日任务及全部笔记/记录/练习历史。本阶段**未执行、未删除任何正式账号或学习数据**。备份文件含用户数据与认证摘要，**禁止提交 Git 或公开分享**（当前为 untracked，未被提交）。

---

## 6. A1 所需关键源码交接

> 全部为只读交接，本阶段未修改任何业务文件。

### 6.1 `app/core/deps.py`（认证依赖）

- `oauth2_scheme`：L13-16，`tokenUrl="/auth/login"`，`auto_error=False`。
- `authenticate_access(token)`：L19-59。解码 Access Token → 校验 `type/exp/jti/sub/family_id` → **使用独立短事务 `with SessionLocal() as db`** 调 `session_service.get_active_session` → 返回含 `id/family_id/is_active` 的会话+用户字典。
- `get_current_user`：L62-74。调用上面的函数，并把 `(user_id, family_id)` 写入 `request.state.auth_identity`，供活跃时间中间件使用。

关键点：认证查询与业务事务**完全分离**（认证用独立 `SessionLocal`，业务用 `get_db`），认证不会提前开启业务事务。

### 6.2 `app/repositories/auth/session_repository.py`（会话仓储）

| 函数 | 行号 | 说明 |
| --- | --- | --- |
| `insert_session` | L7-44 | 插入会话，不提交 |
| `find_session` | L46-74 | 支持 `FOR UPDATE` |
| `find_session_with_user` | L77-112 | JOIN `users`，取 `is_active`；**SELECT 列表不含 `role`** |
| `touch_session` | L115-146 | 条件更新活跃时间（含 idle/write cutoff） |
| `list_active_sessions` | L148-177 | 列表 |
| `revoke_session` | L179-206 | 单会话撤销，返回 `rowcount`，不提交 |
| `revoke_all_sessions` | L208-241 | 批量撤销，支持 `exclude_family_id`，返回 `rowcount`，不提交 |
| `count_active_sessions` | L243-268 | 有效会话计数 |
| `list_active_sessions_page` | L270-… | 分页 |

### 6.3 `app/repositories/auth/user_repository.py`（用户仓储）

- `find_by_id`：L7-30，支持 `for_update=True`；SELECT 列为 `id, username, password_hash, email, email_verified_at, password_updated_at, nickname, avatar_url, is_active`（**无 `role`**）。
- `find_by_username` L33-56、`find_by_email` L59-82：同上，均支持行锁。
- `insert_user`：L85-123（写入 `password_updated_at` / `email_verified_at`）。
- `find_profile`：L125-148（个人资料，无 `role`）。
- `update_password`：L175-197；`update_email`：L200-222；`update_avatar`：L230-249。

### 6.4 `app/services/auth/session_service.py`（会话服务）

| 函数 | 行号 | 行为 |
| --- | --- | --- |
| `reject_auth` | L23-35 | 统一 401/403 错误体 `{code, message}` |
| `require_active_session` | L38-72 | `None`→`SESSION_REVOKED`；`revoked_at`→`SESSION_REVOKED`；`absolute_expires_at <= now`→`SESSION_EXPIRED`；idle 超期→`SESSION_EXPIRED` |
| `create_session` | L75-105 | 生成 `family_id` 与绝对过期时间，插入，不提交 |
| `get_active_session` | L108-134 | 查有效会话 + 用户；`is_active=0` → 403 `ACCOUNT_DISABLED` |
| `revoke_session` | L137-164 | 撤销会话 + 该 family 的 Refresh Token；**返回 None（丢弃 rowcount）**；调用方负责加锁与提交 |
| `lock_current_user` | L171-215 | 先锁 `users` 行再锁 `login_sessions` 行，并复核账号与会话状态 |
| `revoke_user_sessions` | L218-248 | 批量撤销会话 + Token，**返回受影响会话数**；调用前必须已锁用户行 |
| `public_session` / `list_sessions` / `get_current_session` | L303-… / L335-… / L382-… | 设备信息与分页 |

### 6.5 `app/schemas/user.py`

`UserPublic`：L94-101，字段为 `id, username, nickname, email, avatar_url, email_verified_at, is_active`。**无 `role`**。

### 6.6 `auth_service.public_user` 及公开用户响应

`app/services/auth/auth_service.py:58-72`：

```python
def public_user(user: dict) -> dict:
    """只返回允许对外公开的用户字段"""
    data = dict(user)
    verified_at = data["email_verified_at"]
    if verified_at.tzinfo is None:
        data["email_verified_at"] = verified_at.replace(tzinfo=timezone.utc)
    return UserPublic.model_validate(data).model_dump(mode="json")
```

结论：对外用户响应由 `UserPublic` 白名单过滤。A1 若要暴露 `role`，需**同时**修改 `UserPublic` 与支撑 SQL（否则 `role` 会被静默丢弃）。

### 6.7 `token_repository.revoke_all_tokens`

`app/repositories/auth/token_repository.py:124-150`：

```python
def revoke_all_tokens(db, *, user_id, now, exclude_family_id=None) -> int:
    result = db.execute(text("""
        UPDATE refresh_tokens
        SET revoked_at = :now
        WHERE user_id = :user_id
          AND revoked_at IS NULL
          AND (:exclude_family_id IS NULL OR family_id <> :exclude_family_id)
    """), {...})
    return result.rowcount
```

- 只做 `UPDATE`，**不提交**；由调用方（`revoke_user_sessions`）在同一事务内与会话撤销一起提交。
- 连带：`revoke_family`：L98-121（单 family）。

### 6.8 `auth_cookie.require_auth_request`

`app/core/auth_cookie.py:15-34`：校验 `Origin ∈ settings.AUTH_ALLOWED_ORIGINS` 且 `X-CSRF-Protection == "1"`，否则 403 `CSRF_REJECTED`。管理员写操作（封禁/改配置/改角色）必须复用该依赖。

### 6.9 `database.py` 的 `SessionLocal` 与 `get_db`

`app/database.py:8-41`：

```python
DATABASE_URL = URL.create(drivername="mysql+pymysql", ..., database=settings.DB_NAME,
                          query={"charset": "utf8mb4"})
engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       connect_args={"init_command": "SET time_zone = '+08:00'"})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

注意：会话时区固定 `+08:00`，而认证/审计大量时间字段语义为 UTC（由后端显式写入）。A1 新增写库代码必须沿用"显式 UTC"约定。

### 6.10 重点核实结论（A1 直接相关）

| 核实项 | 结论 |
| --- | --- |
| `role` 最小接入位置 | ① `users.role` 列（迁移）；② `session_repository.find_session_with_user` 的 SELECT 增加 `u.role`（**唯一必须改的认证 SQL**）；③ `get_current_user` 返回字典自然携带 `role`；④ 新增 `require_admin` 依赖（`role != 'ADMIN'` → 403）；⑤ 若前端需展示，`UserPublic` + `find_profile` 增加 `role` |
| 认证与业务 Session 是否独立 | 是。`authenticate_access` 用独立 `with SessionLocal()`；路由业务用 `get_db`；活跃时间中间件经线程池另行处理。管理员操作可在业务 Session 内完成，不必复用认证 Session |
| 会话撤销返回值 | Repository 均返回 `rowcount`；`session_service.revoke_user_sessions` 返回受影响会话数（`/auth/logout-all` 已使用）；`session_service.revoke_session`（单会话）**丢弃返回值返回 None**，管理员"强制下线指定会话"若要回显命中数，需扩展该函数或直接调用 Repository（REFACTOR 点） |
| 过期会话处理 | 绝对过期与 idle 超期均 401 `SESSION_EXPIRED`；已撤销 401 `SESSION_REVOKED`；账号禁用 403 `ACCOUNT_DISABLED`；每次请求实时查库，无缓存 |
| 锁顺序 | `users` → `login_sessions` → `refresh_tokens`（`lock_current_user` L171-215；登录 L368-378/L495-499；刷新 L575-599）。管理员封禁必须"先锁 users 行，再批量撤销会话/Token"，否则与并发刷新存在死锁/竞态风险 |
| 封禁竞态 | 封禁 = `is_active=0` + `revoke_user_sessions`（同一事务）。并发刷新若已持有 users 行锁会串行化；若刷新在封禁提交前完成，则新 Token 属于新会话，封禁的批量撤销已覆盖（需在锁内先更新 `is_active` 再撤销，保证"提交后无新会话可续期"） |

---

## 7. 测试基线

### 7.1 执行环境与命令

- 数据库：`ssp_a0_migrate2`（测试库，隔离于正式库）
- 邮件：全部 Mock；AI：`stream_checked_completion` / Provider 全部 Mock，无真实付费调用
- 命令：

```powershell
cd d:\project\back
.\.venv\Scripts\python.exe -m pytest tests -q --no-header -p no:cacheprovider --tb=line
```

### 7.2 最终全量结果（本次真实执行）

```
5 failed, 497 passed, 9 skipped, 2 warnings, 8 subtests passed in 52.41s
```

| 测试文件 | 收集数 | 结果 |
| --- | --- | --- |
| `test_auth_a1_1_acceptance.py` | 124 | 115 通过 / 2 失败 / 7 跳过 |
| `test_auth_a1_3_acceptance.py` | 98 | 98 通过（修正后） |
| `test_auth_a2_account_session_acceptance.py` | 83 | 83 通过 |
| `test_auth_a2_3_avatar_profile_cleanup_acceptance.py` | 103 | 101 通过 / 2 跳过；全量顺序下 2 项 404（见 7.5） |
| `test_lifecycle_regression.py` | 17 | 16 通过 / 1 失败（真实缺陷，见 7.4） |
| `test_progress_regression.py` | 17 | 17 通过（修正后） |
| `test_rollover_regression.py` | 4 | 4 通过（修正后） |
| `test_ai_a3_structure.py` | 11 | 11 通过 |
| `test_ai_a4_qa.py` | 21 | 21 通过 |
| `test_ai_a5_generate.py` | 12 | 12 通过（修正后） |
| `test_ai_a5_grade.py` | 11 | 11 通过 |
| `test_knowledge_ai.py` | 10 | 10 通过 |
| **合计** | **511** | **497 通过 / 5 失败 / 9 跳过** |

### 7.3 本阶段修正的过时测试（仅夹具/断言）

修正前（同样 5 个文件）：`45 failed, 103 passed`；修正后：`147 passed, 1 failed`（该 1 项为真实缺陷）。

| 文件 | 问题 | 修正 |
| --- | --- | --- |
| `tests/test_progress_regression.py` | 2 处 `INSERT INTO users (username, password_hash)` 缺少 Auth V2 必填列 → `1364 Field 'password_updated_at' doesn't have a default value`（17 项全失败） | 补齐 `password_updated_at / email / email_verified_at`（`UTC_TIMESTAMP(6)` + 唯一邮箱） |
| `tests/test_rollover_regression.py` | 同上（4 项全失败） | 同上 |
| `tests/test_lifecycle_regression.py` | 同上（17 项全失败，并因异常导致连接池耗尽） | 同上（2 处） |
| `tests/test_ai_a5_generate.py` | `make_paper()` 题干仅数字不同（"知识点0/1/2…"），产品去重规则 `SequenceMatcher >= 0.92` 判定为重复 → 6 项 `DUPLICATE_PRACTICE_QUESTIONS` | 题干/选项改为主题化文本 + 5 种句式模板；实测最大相似度：5 题 0.300 / 10 题 0.537 / 15 题 0.600，全部 < 0.92 |
| `tests/test_auth_a1_3_acceptance.py` | `test_no_legacy_route_refs` 断言"不存在 logout-all"，与 A2 新契约冲突（`POST /auth/logout-all` + 密码确认，`app/api/routes/auth.py:455`） | 改为断言 `POST /auth/logout-all` 存在，同时保留"匿名 GET /users 不开放"断言 |

**AI 出题 6 项失败根因结论**：不是产品缺陷。`app/services/knowledge/ai_practice_service.py:136-153` 的重复题干检查（归一化后 `SequenceMatcher >= 0.92`）逻辑正确；失败由测试夹具题干高度雷同导致。已修夹具，产品规则未改。

### 7.4 真实产品缺陷（仅报告，未修改）

| 项 | 内容 |
| --- | --- |
| 位置 | `app/jobs/plan_expiration_worker.py:44`（`run_due_plan_check`） |
| 现象 | `NameError: name 'plan_lifecycle_service' is not defined. Did you mean: 'plan_lifecycle_repository'?` |
| 原因 | 该模块仅 `from app.repositories.plans import plan_lifecycle_repository`（L10），**从未导入 `plan_lifecycle_service`** |
| 复现 | `pytest tests/test_lifecycle_regression.py::PlanLifecycleRegression::test_L10_worker_is_idempotent -q`；或 `python -m app.jobs.plan_expiration_worker --once` |
| 影响 | 每个到期计划都抛异常并被 `except Exception` 吞掉（L54-60），`ended_count` 恒为 0、`failed_count` 递增；**计划永远不会被定时置为 ENDED**，仅在日志出现 ERROR。首次启动检查和每 5 分钟调度均受影响 |
| 建议修复 | 增加 `from app.services.plans import plan_lifecycle_service`（并核对函数名 `expire_due_plan` 是否存在）。**本阶段未修改**，等待授权 |
| 测试状态 | `test_L10_worker_is_idempotent` 因此失败（该测试断言正确，不应修改） |

### 7.5 全量顺序下的测试隔离问题（非产品缺陷）

| 项 | 内容 |
| --- | --- |
| 位置 | `tests/test_auth_a2_3_avatar_profile_cleanup_acceptance.py:50-64`；`app/main.py:29-41` |
| 现象 | 单独执行该文件：101 通过 / 2 跳过；全量执行时 `test_new_avatar_exists_and_publicly_readable`、`test_processed_avatar_publicly_accessible` 返回 404 |
| 原因 | 该测试在**模块导入期**把 `settings.AVATAR_DIR` 指向临时目录；而 `app.main` 在**导入期**用当时的 `settings.AVATAR_DIR` 绑定 `StaticFiles` 的 `directory`。全量运行时 `test_auth_a1_1` / `test_auth_a1_3` 先 `from app.main import app`，静态目录被绑定到仓库 `storage/avatars`，文件却写入临时目录 → 404。测试文件第 50 行注释已声明该隐式依赖 |
| 影响 | 仅影响全量顺序执行结果，不影响产品功能 |
| 建议 | 在 A1 前把静态挂载改为惰性读取目录，或在夹具中重建 mount；本阶段**未修改**（超出"过时夹具"授权范围） |

### 7.6 已过时但未修改的断言（建议 A1 前处理）

| 用例 | 现状 | 说明 |
| --- | --- | --- |
| `test_auth_a1_1_acceptance.py::T6Schema::test_t6_02_user_create_no_constraints` | 断言 `UserCreate(username="a", password="1", nickname="")` 可通过（文档化"无约束"缺陷） | 当前 Schema 已加 `min_length` / 必填 `email` / `code`，约束已修复，断言过时 |
| `test_auth_a1_1_acceptance.py::T11AuthEventRepository::test_t11_08_identifier_ip_no_after_id` | 要求 `count_identifier_events/count_ip_events` 支持 `after_id` | 现行实现采用 `since` 固定时间窗（`rate_limit_service.py:252` 调用 `count_ip_events(..., since=...)`），`after_id` 设计已被取代 |

### 7.7 认证两个历史 P0

按交接要求**未重复修改、未重复验证**（A2.3 报告已确认修复）。

---

## 8. 剩余阻塞项

| # | 阻塞项 | 状态 / 需要谁决定 |
| --- | --- | --- |
| 1 | V3.0 增量迁移 SQL 未执行 | 等待开发者 + GPT 审查 DDL；通过后仅在 `ssp_v3_admin_dev` 执行并复核 19 表断言 |
| 2 | V3.0 独立数据库配置未落地 | 当前 `.env` 仍指向 `ssp_a0_migrate2`；需确认采用 `.env.v3` 还是进程级变量，**不得覆盖共享 `.env`** |
| 3 | **真实缺陷**：`plan_expiration_worker.py:44` 未导入 `plan_lifecycle_service` | 计划自动到期全部失效；需授权后修复（1 行 import + 函数名核对） |
| 4 | `a1_1` 两项过时断言（T6-02、T11-08） | 需确认是新契约生效还是补齐产品能力（尤其 `after_id` 语义） |
| 5 | `a2_3` 全量顺序 404（`settings.AVATAR_DIR` 导入期覆盖 vs `main.py` 导入期 mount） | 需确认测试隔离整改方式（改 main 惰性挂载 / 改夹具） |
| 6 | `ai_runtime_config.updated_at` 时区口径 | 当前 `CURRENT_TIMESTAMP(6)` 为会话时区 `+08:00`；`admin_audit_logs.created_at` 为 UTC。需确认是否统一为显式 UTC |
| 7 | `admin_audit_logs.action` 取值字典 | 未加 CHECK（避免频繁 DDL），需 A1 以常量/枚举固化 `USER_BAN / USER_UNBAN / USER_FORCE_LOGOUT / USER_ROLE_UPDATE / AI_CONFIG_UPDATE` |
| 8 | `role` 尚未进入 JWT / `UserPublic` | 需决定"改角色即时生效"（推荐：每次请求查库校验，JWT 不携带 role） |
| 9 | AI 统计字段缺口 | `ai_requests` 无耗时/错误码/取消原因；沿用 A0 结论，本期未新增统计表 |
| 10 | `docs/backups/*.sql` 含用户与认证摘要 | 保持 untracked，禁止提交 Git |
| 11 | Redis | 本期不安装、不迁移 MySQL Guard、不写业务代码（边界确认） |

---

## 附：本阶段文件变更清单

| 文件 | 类型 |
| --- | --- |
| `d:\project\back\Smart_Study_Planner_V3.0_A0_Migration.sql` | 新增（候选稿，未执行） |
| `d:\project\back\Smart_Study_Planner_V3.0_A0_Final_Report.md` | 新增（本报告） |
| `d:\project\back\tests\test_progress_regression.py` | 修改（2 处夹具） |
| `d:\project\back\tests\test_rollover_regression.py` | 修改（1 处夹具） |
| `d:\project\back\tests\test_lifecycle_regression.py` | 修改（2 处夹具） |
| `d:\project\back\tests\test_ai_a5_generate.py` | 修改（`make_paper` 夹具） |
| `d:\project\back\tests\test_auth_a1_3_acceptance.py` | 修改（1 处过期断言） |
| 业务源码 | **未修改** |
| 正式/原有数据库 | **未修改**（`ssp_a0_migrate2` 仅新增测试产生的 `auth_events` 行） |