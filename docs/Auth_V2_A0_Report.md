# Smart Study Planner · Auth V2.0 · A0 迁移准备报告

- 报告日期：2026-11-24
- 版本：**R3（A0 最终收尾，供审查）**
- 阶段：A0（仅迁移准备，不修改后端/前端业务代码）
- 目标库：`smart_study_planner`（MySQL 8.4.9 / InnoDB）
- 迁移脚本：[Auth_V2_A0_Migration.sql](file:///d:/project/docs/Auth_V2_A0_Migration.sql)
- 备份文件：`d:\project\docs\backups\smart_study_planner_pre_auth_v2_20261124.sql`
- 状态：**R3 最终结构已在保留的隔离库 `ssp_a0_migrate2` 验证通过；未在正式业务库执行任何破坏性 DML/DDL；等待新版后端通过认证安全及业务回归测试后，再停服、重新备份并执行正式迁移。**

### R3 最终收尾（本轮）

1. `auth_events.identifier` 改为列级 `utf8mb4_0900_as_ci`，与 `users.email`、`email_verifications.email` 完全一致。
2. 已同步保留的隔离库 `ssp_a0_migrate2`，该库继续作为 A1 后端开发和测试数据库。
3. 实测认证标识大小写/重音比较，以及 `auth_events`、`email_verifications` 组合索引执行计划。
4. 已检查正式迁移账号权限，并在隔离库实测临时表、存储过程的创建、执行与删除。
5. 明确成功/失败时的存储过程与临时断言表清理方案；再次验证断言失败后客户端立即停止。
6. 保留已安装依赖版本，R3 再次执行 `pip check` 通过；方向书缺失暂不处理。

### R2 相对 R1 的变更

1. 分区 B 改为存储过程 + 单事务，清理结果断言移到 `COMMIT` **之前**，任何异常/断言失败自动 `ROLLBACK` 并抛错，脚本终止。
2. 新增分区 A 强制断言：目标库、14 张表集合、21 条外键集合、users 前置结构、清理范围、`ai_guard_mutex` id=1。
3. `users.email` 与 `email_verifications.email` 改用列级 `utf8mb4_0900_as_ci`，并在隔离库验证大小写/重音行为。
4. 已安装 `Pillow`、`email-validator`，更新 `requirements.txt`。
5. 在新隔离库 `ssp_a0_migrate2` 重跑迁移，并完成“清理失败回滚”“前置条件失败不进入破坏性阶段”两类演练。
6. 方向书仍不存在，无法同步更新（不阻塞迁移准备）。

---

## 0. 执行结论摘要

| 项目 | 结果 |
|---|---|
| 备份 | 已完成，158,053 字节 |
| 备份可恢复性 | 隔离库 `ssp_a0_legacy` / `ssp_a0_migrate2` 恢复并与备份快照逐表一致 ✅ |
| 迁移演练（R2/R3） | R2 全脚本 rc=0；R3 最终分区 F 断言 rc=0 ✅ |
| 表数量 | 14 → 17 ✅ |
| 外键数量 | 21 → 22 ✅ |
| 旧数据清理 | 业务表、认证表、users 全为 0；`ai_guard_mutex` 保留 id=1 ✅ |
| 清理事务断言 | 在 `COMMIT` 前执行，失败自动 `ROLLBACK` ✅ |
| 失败演练 | 清理失败 → 数据完整回滚；前置失败 → 未进入清理与 DDL ✅ |
| `tb_` 前缀 | 迁移后无 `tb_` 表 ✅ |
| AUTO_INCREMENT | 迁移前后一致，未被重置 ✅ |
| 标识排序规则 | 两处 email 与 `auth_events.identifier` 均为 `utf8mb4_0900_as_ci`；大小写不敏感、重音敏感 ✅ |
| 组合索引 | 两个标识组合索引列顺序不变，EXPLAIN 均命中预期索引 ✅ |
| 迁移账号权限 | DML/DDL、临时表、存储过程创建/执行/删除均验证通过 ✅ |
| 失败清理 | 断言失败后立即停止；临时表随连接清理，失败存储过程有人工清理方案 ✅ |
| 依赖 | `Pillow 13.0.0`、`email-validator 2.4.0` 已安装；R3 `pip check` 通过 ✅ |
| 旧版认证基线 | 隔离库 14/14 PASS ✅ |
| 方向书 | 仍不存在，无法同步更新 ❌（不阻塞） |

> 正式库当前仍在被运行中的后端写入（备份后 `tb_refresh_token` 由 212 增至 213）。正式迁移前必须停写并重新备份，本报告数据为备份时点快照。

---

## 1. 命名规范与表清单

| 原名称 | 最终名称 | 操作 | 状态 |
|---|---|---|---|
| `users` | `users` | 修改结构 | ✅ |
| `tb_refresh_token` | `refresh_tokens` | `RENAME TABLE` | ✅ |
| `tb_login_session` | `login_sessions` | 新建 | ✅ |
| `tb_email_verification` | `email_verifications` | 新建 | ✅ |
| `tb_auth_event` | `auth_events` | 新建 | ✅ |

- 数据库总表数：14 → 17。
- 其他现有业务表名称与结构均未改动。

**未完成项**：`docs/Smart_Study_Planner_Auth_V2_Direction.md` 仍然不存在（已再次全项目 glob 检索 `*Direction*`、`*方向*`，无结果）。按约定仅报告，不阻塞迁移准备；表名映射已写入本节，待文件补齐后可直接套用。

---

## 2. 数据库备份与恢复验证

### 2.1 备份

- 文件：`d:\project\docs\backups\smart_study_planner_pre_auth_v2_20261124.sql`
- 大小：158,053 字节
- 方式：`mysqldump --single-transaction --routines --events --triggers --hex-blob --default-character-set=utf8mb4`
- 内容：全部 14 张表结构 + 数据 + 约束。
- 安全：备份含用户数据与认证摘要，**禁止提交 Git 或公开分享**。

### 2.2 隔离库恢复验证

| 隔离库 | 用途 | 结果 |
|---|---|---|
| `ssp_a0_legacy` | 恢复备份，旧版认证测试基线 | 恢复成功 |
| `ssp_a0_migrate` | R1 迁移演练 | 已完成（历史） |
| `ssp_a0_migrate2` | R2 修正版迁移演练；R3 最终排序规则同步；保留供 A1 开发测试 | 17 表 / 22 外键，最终结构验证通过，保留 |
| `ssp_a0_fail_cleanup` | 清理失败回滚演练 | 已回滚，验证后删除 |
| `ssp_a0_fail_pre` | 前置条件失败演练 | 已阻断，验证后删除 |

对备份时点内容逐表 `COUNT(*)` 比对（恢复后 vs 备份快照）：

| 表 | 备份时点行数 | 恢复后行数 | 结果 |
|---|---:|---:|---|
| users | 47 | 47 | ✅ |
| tb_refresh_token | 212 | 212 | ✅ |
| ai_requests | 17 | 17 | ✅ |
| ai_guard_mutex | 1 | 1 | ✅ |
| study_plans | 39 | 39 | ✅ |
| plan_steps | 91 | 91 | ✅ |
| daily_tasks | 280 | 280 | ✅ |
| schedule_entries | 85 | 85 | ✅ |
| task_rollovers | 7 | 7 | ✅ |
| study_records | 52 | 52 | ✅ |
| focus_sessions | 14 | 14 | ✅ |
| knowledge_notes | 4 | 4 | ✅ |
| knowledge_review_records | 5 | 5 | ✅ |
| practice_records | 1 | 1 | ✅ |

结论：备份文件可恢复，数据完整。

### 2.3 实时库漂移说明

复检时正式库 `tb_refresh_token` 已为 213 条（备份时 212），说明后端仍在写入。**正式迁移前必须停止旧后端、定时 Worker 及全部写库程序，并重新备份**。

### 2.4 失败演练（R2）

| 场景 | 注入方式 | 实际结果 |
|---|---|---|
| 清理失败回滚 | 在分区 B 断言中强制加入 `OR 1 = 1` | `ERROR 1644 (45000)`，`ROLLBACK` 生效；14 张表、users=47、tb_refresh_token=212、daily_tasks=280 等全部保持原值；未出现 `refresh_tokens`，证明未进入 DDL |
| 前置条件失败 | 迁移前新增非预期表 `rogue_extra` | `ERROR 3819`（CHECK 断言失败）在第 136 行中断；15 张表保持原样；所有业务数据未删除；未出现任何新表 |
| 断言机制 | `__a0_assert` 临时表 + `CHECK (ok = 1)` | MySQL 3819 强制中断；`CREATE TEMPORARY TABLE` 不隐式提交，回滚验证通过 |
| 事务边界 | `SET autocommit=0` + 插入 + 建临时表 + `ROLLBACK` | 插入被完整回滚，确认临时表 DDL 不破坏事务 |
| R3 最终断言 | 在 `ssp_a0_migrate2` 单独执行最终版分区 F | rc=0，17 表 / 22 外键及三处 `as_ci` 断言通过 |
| R3 强制失败 | `CHECK` 断言后放置 `SELECT 'SHOULD_NOT_RUN'` | rc=1、错误 3819，后续语句未执行；未使用 `--force` |
| R3 过程失败清理 | 强制过程 `SIGNAL` 后检查例程并人工删除 | 过程定义按预期保留，人工 `DROP PROCEDURE` 后无残留 |

---

## 3. 待清理数据统计

### 3.1 清理范围

| 表 | 清理前 | 清理后 | 处理 |
|---|---:|---:|---|
| task_rollovers | 7 | 0 | DELETE |
| study_records | 52 | 0 | DELETE |
| focus_sessions | 14 | 0 | DELETE |
| schedule_entries | 85 | 0 | DELETE |
| daily_tasks | 280 | 0 | DELETE |
| plan_steps | 91 | 0 | 先置空 `parent_id` 再 DELETE |
| study_plans | 39 | 0 | DELETE |
| knowledge_review_records | 5 | 0 | DELETE |
| practice_records | 1 | 0 | DELETE |
| knowledge_notes | 4 | 0 | DELETE |
| tb_refresh_token | 212 | 0 | DELETE（随后重命名） |
| ai_requests | 17 | 0 | DELETE |
| users | 47 | 0 | DELETE（最后） |
| ai_guard_mutex | 1 | **1** | **保留 id=1** |

### 3.2 外键依赖与清理顺序

```
task_rollovers → study_records → focus_sessions → schedule_entries → daily_tasks
→ plan_steps → study_plans → knowledge_review_records → practice_records
→ knowledge_notes → tb_refresh_token → ai_requests → users
```

关键点：

- `task_rollovers` 同时引用 `daily_tasks`（source/target），必须先删。
- `study_records` 引用 `daily_tasks`、`users`，必须先于两者删除。
- `focus_sessions` 对 plan/task 为 `SET NULL`、对 user 为 `CASCADE`，提前删除便于统计。
- `schedule_entries` 引用 `plan_steps`，先于 `plan_steps`。
- `daily_tasks` 引用 `study_plans`、`plan_steps`，位置居中。
- `plan_steps` 自引用 `fk_plan_steps_parent`（`NO ACTION`），必须先 `UPDATE plan_steps SET parent_id = NULL`。
- `study_plans` 被多表引用，必须最后删。
- `ai_requests` 无外键，含 2 条历史孤儿记录（已批准清理）。
- `users` 最后删除；`tb_refresh_token.user_id` 为 CASCADE，脚本仍显式删除以便统计。

### 3.3 事务与断言（R2 核心修正）

分区 B 已改为存储过程 `a0_auth_v2_cleanup`：

1. `START TRANSACTION`；
2. 按依赖顺序 `DELETE`；
3. **在 `COMMIT` 之前**逐表校验行数为 0、`ai_guard_mutex` 仅 id=1；
4. 任一不满足 → `SIGNAL SQLSTATE '45000'`；
5. `EXIT HANDLER FOR SQLEXCEPTION` → `ROLLBACK` + `RESIGNAL`；
6. 全部通过后才 `COMMIT`。

因此清理与检查使用**同一连接、同一事务**；失败不会提交，也不会继续执行后续 DDL。

### 3.4 约束遵守情况

- ✅ 未使用 `TRUNCATE`，全部 `DELETE`。
- ✅ 未使用 `SET FOREIGN_KEY_CHECKS=0`。
- ✅ 清理（事务）与 DDL（隐式提交）严格分离。
- ✅ `ai_guard_mutex` id=1 保留。
- ✅ 未触碰其他系统数据。
- ✅ 执行客户端禁止 `--force` 等“出错继续”参数。

---

## 4. 迁移脚本说明

[Auth_V2_A0_Migration.sql](file:///d:/project/docs/Auth_V2_A0_Migration.sql) 分区结构：

| 分区 | 内容 | 事务性 | 强制断言 |
|---|---|---|---|
| A | 目标库/版本、表清单、外键清单、新表存在性、users 前置结构、清理范围、mutex、AUTO_INCREMENT 记录 | 只读 | `__a0_assert` CHECK |
| B | 存储过程内单事务清理；COMMIT 前断开言 | 可回滚 | 存储过程 `IF ... SIGNAL` |
| C | 进入 DDL 前复断言 + `RENAME TABLE` + 结果断言 | DDL 隐式提交 | C0/C3 CHECK |
| D | `ALTER TABLE users`（email 收窄 + as_ci + 新增两列） | DDL 隐式提交 | D2 CHECK |
| E | 创建三张新表（email / identifier 列 as_ci） | DDL 隐式提交 | E5 CHECK |
| F | 17 表 / 22 外键 / 行数 / 排序规则 / 索引 / 最终 DDL | 只读 | F9 CHECK |

断言机制说明：

- MySQL 8.4.9 不支持在 `PREPARE` 中执行 `SIGNAL`（错误 1295，已实测）。
- 因此分区 A/C/D/E/F 使用临时表 + `CHECK (ok = 1)`：断言条件为假时插入触发错误 **3819**，mysql 客户端立即以非 0 退出。
- `CREATE TEMPORARY TABLE` / `DROP TEMPORARY TABLE` **不会隐式提交**事务（已实测：事务内插入可被回滚）。
- 分区 B 使用存储过程，`EXIT HANDLER` 显式 `ROLLBACK`，比依赖客户端断连更可靠。

迁移账号权限（R3 已验证）：当前配置账号为 `root@localhost`，对正式迁移所需 `SELECT`、`INSERT`、`UPDATE`、`DELETE`、`CREATE`、`DROP`、`ALTER`、`CREATE TEMPORARY TABLES`、`CREATE ROUTINE`、`EXECUTE` 均具备权限。另在 `ssp_a0_migrate2` 实测：临时表创建/插入/删除通过；存储过程创建/`CALL`/删除通过。正式执行若更换账号，必须重新检查，不得仅凭本报告推定权限。

### 4.1 存储过程与临时断言表清理方案

| 场景 | 存储过程 `a0_auth_v2_cleanup` | 临时表 `__a0_assert` |
|---|---|---|
| 全部成功 | B18 显式 `DROP PROCEDURE IF EXISTS` | 每个断言成功后立即显式 `DROP TEMPORARY TABLE` |
| 分区 A/C/D/E/F 断言失败 | 若分区 B 已成功，过程已删除 | mysql 客户端非 0 退出并关闭连接，临时表随连接自动销毁；交互会话未退出时人工 `DROP TEMPORARY TABLE IF EXISTS __a0_assert` |
| 分区 B 失败 | 过程内已 `ROLLBACK`，但过程定义会保留；必须人工 `DROP PROCEDURE IF EXISTS a0_auth_v2_cleanup`，或修复后重跑时由 B0 先删除 | 分区 B 不使用该临时表 |
| C/D/E 部分 DDL 失败 | 过程已在 B18 删除 | 按上述临时表方案清理；已成功的 DDL 不回滚，禁止整脚本重跑 |

R3 已实测：强制断言失败返回 rc=1，后续标记语句未执行；失败存储过程定义确实保留，人工删除后无残留。整个过程不得使用 `--force` 或其他忽略错误继续执行的参数。

---

## 5. 最终 DDL（隔离库实测）

以下为 `ssp_a0_migrate2` 执行后的真实结构。

### 5.1 users

```sql
CREATE TABLE `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL COMMENT '登录用户名',
  `password_hash` varchar(255) NOT NULL COMMENT '密码哈希',
  `password_updated_at` datetime(6) NOT NULL COMMENT '密码最近修改时间（UTC）',
  `email` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL COMMENT '邮箱（登录标识，统一小写）',
  `email_verified_at` datetime(6) NOT NULL COMMENT '邮箱验证时间（UTC）',
  `nickname` varchar(50) DEFAULT NULL COMMENT '用户昵称',
  `avatar_url` varchar(255) DEFAULT NULL COMMENT '头像地址（可选）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_active` tinyint NOT NULL DEFAULT '1' COMMENT 'Whether the user account is active',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=852 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户表'
```

- `email`：`varchar(100) NULL` → `varchar(254) NOT NULL`，列级 `utf8mb4_0900_as_ci`。
- 新增 `password_updated_at`、`email_verified_at`（`DATETIME(6) NOT NULL`）。
- 表默认排序规则仍为 `utf8mb4_0900_ai_ci`，未修改全局与无关字段。

### 5.2 refresh_tokens

```sql
CREATE TABLE `refresh_tokens` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` bigint unsigned NOT NULL COMMENT '用户 ID',
  `token_hash` char(64) NOT NULL COMMENT 'Refresh Token 的 SHA-256 摘要',
  `family_id` char(36) NOT NULL COMMENT '登录会话家族',
  `expires_at` datetime NOT NULL COMMENT '过期时间',
  `revoked_at` datetime DEFAULT NULL COMMENT '撤销时间',
  `replaced_by` char(64) DEFAULT NULL COMMENT '下一代 Token 摘要',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_refresh_token_hash` (`token_hash`),
  KEY `idx_refresh_user_family` (`user_id`,`family_id`),
  KEY `idx_refresh_expires_at` (`expires_at`),
  CONSTRAINT `fk_refresh_token_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=263 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='刷新令牌表'
```

字段、主键、唯一索引、组合索引、外键全部保留。索引名/约束名不含 `tb_`，无需改名。

### 5.3 login_sessions

```sql
CREATE TABLE `login_sessions` (
  `family_id` char(36) NOT NULL COMMENT '会话 ID，等于 refresh_tokens.family_id',
  `user_id` bigint unsigned NOT NULL COMMENT '用户 ID',
  `user_agent` varchar(255) DEFAULT NULL COMMENT '登录设备 User-Agent',
  `created_at` datetime(6) NOT NULL COMMENT '创建时间（UTC）',
  `last_activity_at` datetime(6) NOT NULL COMMENT '最后活跃时间（UTC）',
  `absolute_expires_at` datetime(6) NOT NULL COMMENT '会话绝对过期时间（UTC）',
  `revoked_at` datetime(6) DEFAULT NULL COMMENT '撤销时间（UTC）',
  `revoked_reason` varchar(32) DEFAULT NULL COMMENT 'LOGOUT/LOGOUT_ALL/REPLAY/PASSWORD_CHANGED/ADMIN',
  PRIMARY KEY (`family_id`),
  KEY `idx_login_sessions_user_active` (`user_id`,`revoked_at`,`absolute_expires_at`),
  KEY `idx_login_sessions_expires` (`absolute_expires_at`),
  CONSTRAINT `fk_login_sessions_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='登录会话（多设备管理）'
```

- 主键复用 UUID4 `family_id`，不新增 `session_id`。
- 不含 `status`、`device_id`、`device_label`、`idle_expires_at`、IP。
- 与 `refresh_tokens.family_id` 为逻辑关联，无物理外键。

### 5.4 email_verifications

```sql
CREATE TABLE `email_verifications` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `email` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL COMMENT '目标邮箱（统一小写）',
  `purpose` enum('REGISTER','LOGIN','RESET_PASSWORD','CHANGE_EMAIL_OLD','CHANGE_EMAIL_NEW') NOT NULL COMMENT '验证码用途',
  `user_id` bigint unsigned DEFAULT NULL COMMENT '关联用户（换绑/重置时必填）',
  `family_id` char(36) DEFAULT NULL COMMENT '绑定的登录会话（换绑时必填）',
  `code_hash` char(64) NOT NULL COMMENT '验证码 HMAC-SHA256 摘要',
  `attempts` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '已尝试次数',
  `created_at` datetime(6) NOT NULL COMMENT '创建时间（UTC）',
  `expires_at` datetime(6) NOT NULL COMMENT '过期时间（UTC）',
  `consumed_at` datetime(6) DEFAULT NULL COMMENT '消费时间（UTC）',
  `invalidated_at` datetime(6) DEFAULT NULL COMMENT '主动作废时间（UTC）',
  `request_ip` varchar(45) NOT NULL COMMENT '请求 IP',
  `send_status` enum('PENDING','SENT','FAILED') NOT NULL DEFAULT 'PENDING' COMMENT '发送状态',
  PRIMARY KEY (`id`),
  KEY `idx_email_verifications_email_purpose_created` (`email`,`purpose`,`created_at`),
  KEY `idx_email_verifications_email_created` (`email`,`created_at`),
  KEY `idx_email_verifications_ip_created` (`request_ip`,`created_at`),
  KEY `idx_email_verifications_created` (`created_at`),
  KEY `idx_email_verifications_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='邮箱验证码与发送额度'
```

- `purpose` ENUM 限定 5 种取值。
- 不存明文验证码；`code_hash` 由后端 HMAC-SHA256 写入。
- 换绑需 `user_id` + `family_id` 同时绑定（Service 校验）。

### 5.5 auth_events

```sql
CREATE TABLE `auth_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` bigint unsigned DEFAULT NULL COMMENT '用户 ID（不建外键，保留历史）',
  `identifier` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci DEFAULT NULL COMMENT '登录标识（用户名/邮箱）',
  `event_type` varchar(32) NOT NULL COMMENT '事件类型',
  `ip` varchar(45) DEFAULT NULL COMMENT '请求 IP',
  `family_id` char(36) DEFAULT NULL COMMENT '关联会话',
  `created_at` datetime(6) NOT NULL COMMENT '发生时间（UTC）',
  PRIMARY KEY (`id`),
  KEY `idx_auth_events_user_time` (`user_id`,`created_at`),
  KEY `idx_auth_events_identifier_type_time` (`identifier`,`event_type`,`created_at`),
  KEY `idx_auth_events_ip_type_time` (`ip`,`event_type`,`created_at`),
  KEY `idx_auth_events_type_time` (`event_type`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='认证安全事件（保留 30 天）'
```

- `user_id` 不建外键，保留历史安全事件。
- 不新增独立限流表，不复用 AI Guard 业务表。
- 30 天保留由后端定时任务负责（本轮不实现）。

---

## 6. 索引与外键说明

### 6.1 索引

| 表 | 索引 | 用途 |
|---|---|---|
| users | `uk_users_username` | 用户名唯一（保留） |
| users | `uk_users_email` | 邮箱唯一（保留，随列改用 as_ci） |
| refresh_tokens | `uk_refresh_token_hash` | Token 摘要唯一（保留） |
| refresh_tokens | `idx_refresh_user_family` | 按用户/家族查询 |
| refresh_tokens | `idx_refresh_expires_at` | 过期清理 |
| login_sessions | `idx_login_sessions_user_active` | 有效会话、用户会话撤销 |
| login_sessions | `idx_login_sessions_expires` | 过期会话清理 |
| email_verifications | 5 个组合/单列索引 | email+purpose+time、email+time、ip+time、created_at、expires_at |
| auth_events | 4 个组合索引 | 用户、标识、IP、事件类型的时间窗口查询 |

### 6.2 外键

| 表 | 约束 | 引用 | 规则 |
|---|---|---|---|
| refresh_tokens | `fk_refresh_token_user` | users(id) | CASCADE |
| login_sessions | `fk_login_sessions_user` | users(id) | CASCADE |

- 迁移前 21 条 → 迁移后 22 条（仅新增 `fk_login_sessions_user`）。
- `email_verifications.user_id/family_id`、`auth_events.user_id/family_id` 不建物理外键。
- 新表外键类型与 `users.id` 一致：`BIGINT UNSIGNED`。

### 6.3 排序规则

- 17 张表中 16 张表默认 `utf8mb4_0900_ai_ci`；`ai_guard_mutex` 保持 `utf8mb4_general_ci`（未改动）。
- `users.email`、`email_verifications.email`、`auth_events.identifier` 均为**列级** `utf8mb4_0900_as_ci`。
- 未执行任何 `ALTER DATABASE`，数据库全局排序规则未变。
- 未修改无关业务字段。

---

## 7. 标识列排序规则与组合索引验证（`utf8mb4_0900_as_ci`）

在 MySQL 8.4.9 实测：

| 验证项 | 结果 |
|---|---|
| 大小写不同的同一邮箱不能重复注册 | ✅ `A@Example.com` 后插入 `a@example.com` → 1062 重复键 |
| 重音不同的邮箱不会被错误合并 | ✅ `é@example.com` 与 `e@example.com` 可同时存在 |
| `as_ci` 比较语义 | `'A@X.com' = 'a@x.com'` → 1；`'é@x.com' = 'e@x.com'` → 0 |
| `ai_ci` 对比 | `'é@x.com' = 'e@x.com'` → 1（证明旧规则会错误合并） |
| 唯一索引有效性 | `uk_users_email` 仍为 `non_unique=0`，迁移后结构断言通过 |
| `auth_events.identifier` 大小写比较 | 存入 `A@Example.com`，以 `a@example.com` 查询命中 1 行 ✅ |
| `auth_events.identifier` 重音比较 | 分别存入 `é@example.com`、`e@example.com`，任一查询只命中本标识 1 行 ✅ |
| `auth_events` 组合索引 | 列顺序保持 `identifier,event_type,created_at`；EXPLAIN `type=range`，命中 `idx_auth_events_identifier_type_time` ✅ |
| `email_verifications` 组合索引 | 列顺序保持 `email,purpose,created_at`；EXPLAIN `type=range`，命中 `idx_email_verifications_email_purpose_created` ✅ |
| 三列结构一致性 | 全库仅上述三列使用 `utf8mb4_0900_as_ci`；`auth_events` 表默认仍为 `ai_ci` ✅ |
| 全局排序规则 | 未修改 |

后端要求：写入前统一 `strip()` + `lower()`，并建议限制为 ASCII 邮箱字符集，避免 `as_ci` 下大小写/重音边界差异。

三处认证标识列的比较语义现已一致。上述行为测试均在事务内插入测试数据并全部 `ROLLBACK`，最终 `users`、`auth_events`、`email_verifications` 仍为 0 行；未修改其他字段、索引或数据表。

---

## 8. 表重命名影响范围

### 8.1 数据库对象层面

- 仅 `RENAME TABLE tb_refresh_token TO refresh_tokens`。
- 数据、主键、索引、外键、AUTO_INCREMENT 全部保留。

### 8.2 源码引用清单（后续需修改）

全局检索 `tb_refresh_token`：**运行时源码仅 1 个文件、7 处 SQL**。

| 文件 | 行号 | 语句 | 需改为 |
|---|---|---|---|
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L94) | 94 | `INSERT INTO tb_refresh_token` | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L209) | 209 | `FROM tb_refresh_token`（轮换 `SELECT ... FOR UPDATE`） | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L276) | 276 | `UPDATE tb_refresh_token`（重放撤销） | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L313) | 313 | `UPDATE tb_refresh_token`（轮换更新旧 Token） | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L420) | 420 | `FROM tb_refresh_token`（退出当前会话） | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L444) | 444 | `UPDATE tb_refresh_token`（撤销当前 family） | `refresh_tokens` |
| [auth_service.py](file:///d:/project/back/app/services/auth/auth_service.py#L478) | 478 | `UPDATE tb_refresh_token`（退出全部会话） | `refresh_tokens` |

其他检索结果：

- `back/tests/**`：无引用。
- `docs/init_all_tables.sql`、`docs/migration_20261101.sql`：无引用。
- 前端 `next-fro/**`：无引用。
- 无 SQLAlchemy ORM 模型、无 Alembic。

### 8.3 非源码引用（本轮不改）

备份文件、审计文档、历史学习文档中仍出现旧表名（`Auth_V2_Backend_Audit.md`、`docs/database-schema.md` 等），不影响运行。

---

## 9. 依赖检查与安装

### 9.1 实际安装结果（Python 3.14.10 / `back/.venv`）

| 依赖 | 处理 | 实测版本 | 结果 |
|---|---|---|---|
| httpx | 保留 | 0.28.1 | ✅ |
| python-multipart | 保留 | 0.0.33 | ✅ |
| Pillow | 本轮安装 | **13.0.0** | ✅ 导入成功 |
| email-validator | 本轮安装 | **2.4.0** | ✅ 导入成功 |
| dnspython | email-validator 传递依赖，已安装 | **2.9.2** | ✅ |
| APScheduler | 已安装，本轮补入 requirements | 3.11.3 | ✅ |

- `pip check`：`No broken requirements found.`（R2 安装后及 R3 最终收尾均通过）
- 导入测试：`PIL 13.0.0`、`email_validator 2.4.0`、`apscheduler 3.11.3`。
- 未批量升级其他依赖。

### 9.2 requirements.txt 变更

[requirements.txt](file:///d:/project/back/requirements.txt) 已新增：

```text
APScheduler==3.11.3
dnspython==2.9.2
email-validator==2.4.0
Pillow==13.0.0
```

`httpx==0.28.1`、`python-multipart==0.0.33` 保持不变。

### 9.3 邮件 API 出站连通性

- `https://api.resend.com` HEAD → 200。
- TCP 443（api.resend.com）可连通。
- TCP 465（smtp.qq.com）TLS 握手成功，TLSv1.3。
- 代码中尚未发现邮件服务配置项（无 `RESEND`/`SMTP`/`EMAIL_`），A1 阶段新增。
- 本报告未输出任何真实 API Key / 密码 / Token。

---

## 10. 旧版本认证测试基线（隔离库 `ssp_a0_legacy`）

| 编号 | 用例 | 结果 | 证据 |
|---|---|---|---|
| T1 | 用户注册 | PASS | 201，id=854（测试后清理） |
| T2 | 重复用户名注册被拒绝 | PASS | 409 |
| T3 | 错误密码登录被拒绝 | PASS | 401 |
| T4 | 密码登录签发双 Token | PASS | `Bearer`，access 225 / refresh 295 字符 |
| T5 | Access Token 认证通过 | PASS | 正确解析用户 |
| T6 | 非法 Access Token 被拒绝 | PASS | 401 |
| T7 | 过期 Access Token 被拒绝 | PASS | `ACCESS_EXPIRED` |
| T8 | Refresh Token 不能当 Access Token | PASS | `TOKEN_TYPE_INVALID` |
| T9 | Refresh Token 正常轮换 | PASS | 新 token、`family_id` 不变 |
| T10 | 轮换后旧 Token 标记撤销 | PASS | `revoked_at` 非空、`replaced_by` 正确 |
| T11 | Refresh Token 重放检测 | PASS | 401，family 全部撤销 |
| T12 | 退出当前会话 | PASS | family 撤销，旧 token 无法轮换 |
| T13 | 退出全部会话 | PASS | 全部 family 撤销 |
| T14 | 退出后 Access Token 仍可用 | PASS（已知缺陷） | 无状态 Access Token |

**汇总：14/14 PASS，0 失败。** 未污染正式库（脚本强制校验 `DATABASE()` 为 `ssp_a0_legacy`，结束时清理测试用户）。

> T14 是现有双 Token 设计的已知缺口，属于 Auth V2.0 业务设计议题。

---

## 11. GET_LOCK / RELEASE_LOCK 连接池行为验证

| 结论 | 实测 |
|---|---|
| 命名锁是**连接级**的 | conn1 获取后 `IS_USED_LOCK=conn1`；conn2 `GET_LOCK(...,0)=0` |
| `COMMIT` / `ROLLBACK` **不释放**命名锁 | 提交/回滚后其他连接仍拿不到 |
| `RELEASE_LOCK` 必须由**持有连接的同一物理连接**执行 | 同连接返回 1；非持有连接返回 0 / NULL |
| 同一连接**可重入** | 两次 `GET_LOCK` 需两次 `RELEASE_LOCK` |
| 锁名上限 64 字符 | 65 字符触发错误 **4163** |
| 连接归还池但未释放 → 锁泄漏 | 新连接 `RELEASE_LOCK` 返回 0，锁仍归旧连接 |
| 推荐模式 | `with engine.connect() as conn:` 全程同一连接，实测稳定 |

限流实现要求：额度检查、记录写入、事务提交、`RELEASE_LOCK` 必须在同一 `engine.connect()` 上下文；不要用 `Session` 跨 `commit` 持有命名锁；命名锁不能替代业务事务。

---

## 12. 潜在风险与待确认事项

| 级别 | 事项 | 说明 / 建议 |
|---|---|---|
| 高 | 方向书缺失 | `docs/Smart_Study_Planner_Auth_V2_Direction.md` 不存在，无法同步表名；不阻塞迁移准备。 |
| 高 | 正式库仍在写入 | 备份后 `tb_refresh_token` 212→213；正式迁移前必须停写并重新备份。 |
| 高 | 新 NOT NULL 列打断旧注册接口 | `create_user` 只插 5 个字段，迁移后缺 `email/email_verified_at/password_updated_at` 会报 1364；必须与业务改造同批上线。 |
| 高 | email NOT NULL | 旧注册无 email；新流程必须提供并校验邮箱。 |
| 中 | 时区语义混用 | 旧列走连接时区 `+08:00`，新认证列写 UTC；读取时不可一概而论。 |
| 低 | 认证标识比较语义 | 三处标识列已统一 `as_ci` 并通过组合索引验证；后端仍需统一 trim/lowercase 规范化。 |
| 中 | 额度语义 | “尝试即占用额度”：`PENDING` 也计入；先落库再发送，失败置 `FAILED` 但不退还额度。 |
| 中 | 清理任务未实现 | 验证码过期清理、30 天安全事件保留需后续定时任务。 |
| 中 | 命名锁泄漏 | 必须同物理连接释放；已实测泄漏场景。 |
| 低 | 迁移账号权限 | 当前账号所需权限已实测通过；正式执行若更换账号必须重新验证。 |
| 中 | 部分 DDL 失败 | DDL 隐式提交，失败后必须停止并报告实际状态，禁止整脚本重跑。 |
| 低 | 索引/约束名 | `refresh_tokens` 现有名称不含 `tb_`，无需改名。 |
| 低 | 演练 AUTO_INCREMENT 归位 | dump 恢复把 AI 归位到 `max(id)+1`（如 refresh 264→263）；正式库 `DELETE` 不重置 AI。 |
| 低 | 逻辑关联 | `login_sessions` 与 `refresh_tokens` 无物理外键，需 Service 保证同事务一致。 |

---

## 13. 正式迁移执行清单

1. 先让新版后端在 `ssp_a0_migrate2` 通过认证安全及业务回归测试。
2. 停止旧后端、定时 Worker、所有写库程序。
3. 重新执行完整备份，并在隔离库验证恢复。
4. 确认迁移账号具备 `CREATE TEMPORARY TABLES`、`CREATE ROUTINE`、`EXECUTE` 及 DDL/DML 权限；当前账号已验证，换账号必须重验。
5. 确认 `@a0_expected_db` 为 `smart_study_planner`。
6. 用 mysql 客户端执行，**不得使用 `--force`**；任何错误立即停止。
7. 依次执行并核对分区 A → B → C → D → E → F；每个 DDL 分区后核对 `SHOW CREATE TABLE`。
8. 抄录分区 A7 的 AUTO_INCREMENT，与分区 F4 逐项比对。
9. 若分区 B 失败：确认过程已 ROLLBACK、数据未变，并执行 `DROP PROCEDURE IF EXISTS a0_auth_v2_cleanup`；修复后再重试。
10. 若临时断言失败且交互连接仍打开：执行 `DROP TEMPORARY TABLE IF EXISTS __a0_assert`；mysql 客户端已退出时临时表会随连接自动销毁。
11. 若 C/D/E 部分成功：停止，记录实际数据库状态，按报告恢复方案处理，禁止整脚本重跑。
12. 迁移成功后与后端改造同批上线；**严禁启动旧版认证后端**。

---

## 14. 本轮边界

- 未修改 FastAPI 业务代码、前端代码及无关模块。
- 未在正式业务库执行破坏性 DML/DDL；仅进行只读权限检查。
- 保留 `ssp_a0_migrate2` 作为 A1 开发测试库，仅同步 `auth_events.identifier` 排序规则；测试数据全部回滚。
- 保留 `Pillow`、`email-validator`、`dnspython`、`APScheduler` 等已安装版本，R3 未安装或升级依赖，`pip check` 再次通过。
- 未新增需求之外的数据表，未修改其他字段或无关模块。
- 未输出真实密码、Token、API Key。
- 未额外生成重复的规划文档，仅更新 `Auth_V2_A0_Migration.sql` 与本报告。
