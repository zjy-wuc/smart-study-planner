# Smart Study Planner V3.0 — A0.4 迁移修正与最终验收报告

> 阶段：A0.4（迁移 SQL 修正 → 仅在 `ssp_v3_admin_dev` 执行 → 负向验证 → 测试基线清零）
> 完成时间：2026-11-27
> 代码基线：`d511f08` + 本阶段修正
> 执行边界：未执行正式库迁移；未执行 Auth V2 R3；未删除任何正式账号或业务数据；未安装 Redis；未实现管理员业务；未修改 Auth V2 认证协议。

---

## 1. 修正后的增量迁移 SQL

| 项 | 值 |
| --- | --- |
| 文件 | `d:\project\back\Smart_Study_Planner_V3.0_A0_Migration.sql` |
| 字节 | 20,526 |
| **SHA256** | **`AB9E428C18FB1A532B5EF8A5E2E743F0818E24CC3657AC11917A27503CE9824E`** |
| 状态 | **已在 `ssp_v3_admin_dev` 执行成功**（其余库未执行） |

### 1.1 相对 A0.3 候选稿的修正

| 对象 | A0.3 | A0.4（当前） |
| --- | --- | --- |
| `users.role` | `ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER'` | **保持不变** |
| `admin_audit_logs.action` | `VARCHAR(64)` | `VARCHAR(32)`；取值固定为 `BAN_USER / UNBAN_USER / REVOKE_SESSIONS / UPDATE_AI_CONFIG`（应用层常量约束，不加 DB CHECK） |
| `admin_audit_logs.target_type` | 注释含 `SYSTEM` | 仅 `USER / AI_CONFIG`，删除 `SYSTEM`、`USER_ROLE_UPDATE` 等未实现业务 |
| `admin_audit_logs.target_id / reason / before_data / after_data` | 允许 NULL | **全部 `NOT NULL`** |
| `reason` 约束 | 无 | 新增 `chk_admin_audit_reason_len CHECK (CHAR_LENGTH(TRIM(reason)) BETWEEN 1 AND 200)` |
| 审计表索引 / 外键 | 4 个二级索引、无外键 | **保持不变**（无外键、无级联删除） |
| `ai_runtime_config` CHECK | 3 条（与 D 区断言 4 条不一致 → 阻断） | **4 条**：新增 `chk_ai_runtime_config_positive CHECK (user_daily_limit > 0 AND global_daily_limit > 0)` |
| `ai_runtime_config.updated_at` | `DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)` | `DATETIME(6) NOT NULL`，**移除 DB 默认与 ON UPDATE**，由应用 `utc_db_now()` 显式写入 |
| 初始化 | `1/1/10/80` | 保持 `1/1/10/80`，`updated_at` 用 `UTC_TIMESTAMP(6)` |
| 前置断言 | 17 表数量、部分空表 | 增加 **17 表精确集合**、**严格 SQL Mode**、**16 张非系统表全空** |
| 后置断言 | 4 条 CHECK 与实际 DDL 不符 | 与实际 DDL 完全一致（见 §2） |
| 负向验证 | 5 条，部分 INSERT 缺必填字段 | **9 条**，全部提供合法必填字段 + 显式事务 + ROLLBACK |

### 1.2 最终 DDL（关键片段）

```sql
ALTER TABLE `users`
  ADD COLUMN `role` ENUM('USER','ADMIN')
    NOT NULL DEFAULT 'USER'
    COMMENT '用户角色：USER=普通用户，ADMIN=管理员'
    AFTER `is_active`;

CREATE TABLE `admin_audit_logs` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `admin_id`    BIGINT UNSIGNED NOT NULL COMMENT '操作管理员 users.id（不建外键，审计长期保留）',
  `action`      VARCHAR(32)     NOT NULL COMMENT '动作：BAN_USER/UNBAN_USER/REVOKE_SESSIONS/UPDATE_AI_CONFIG',
  `target_type` VARCHAR(32)     NOT NULL COMMENT '目标类型：USER / AI_CONFIG',
  `target_id`   BIGINT UNSIGNED NOT NULL COMMENT '目标主键',
  `before_data` JSON            NOT NULL COMMENT '变更前快照',
  `after_data`  JSON            NOT NULL COMMENT '变更后快照',
  `reason`      VARCHAR(200)    NOT NULL COMMENT '操作原因（1~200 字符）',
  `created_at`  DATETIME(6)     NOT NULL COMMENT '操作时间（UTC，后端显式写入）',
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_created`        (`created_at`),
  KEY `idx_admin_audit_action_created` (`action`, `created_at`),
  KEY `idx_admin_audit_admin_created`  (`admin_id`, `created_at`),
  KEY `idx_admin_audit_target`         (`target_type`, `target_id`, `created_at`),
  CONSTRAINT `chk_admin_audit_reason_len`
    CHECK (CHAR_LENGTH(TRIM(`reason`)) BETWEEN 1 AND 200)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='管理员操作审计日志（长期保留，不级联删除）';

CREATE TABLE `ai_runtime_config` (
  `id`                 TINYINT UNSIGNED NOT NULL COMMENT '固定为 1（单行配置）',
  `enabled`            TINYINT          NOT NULL DEFAULT 1,
  `user_daily_limit`   INT UNSIGNED     NOT NULL DEFAULT 10,
  `global_daily_limit` INT UNSIGNED     NOT NULL DEFAULT 80,
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
```

### 1.3 前置解析结果

- 严格模式：`@@GLOBAL.sql_mode` = `ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`；脚本断言 `@@SESSION.sql_mode LIKE '%STRICT_TRANS_TABLES%'` 通过。
- 前置状态：`ssp_v3_admin_dev` 恰好 17 表、`users` 无 `role`、`admin_audit_logs`/`ai_runtime_config` 不存在、`ai_guard_mutex` 1 行且 id=1、16 张非系统表全空。
- 执行方式：`pymysql` 单连接逐语句执行（等价于 `mysql --database=ssp_v3_admin_dev < file.sql`），**首条错误即中止**，未使用 `--force`，全程未关闭 `FOREIGN_KEY_CHECKS`。

---

## 2. 实际迁移结果与 19 表验证

执行结果：**全部前置断言 + 全部 DDL + 初始化 + 全部后置断言均通过，无 SQL 错误。**

| 验证项 | 实测 |
| --- | --- |
| 业务表总数 | **19** |
| 表集合 | users, login_sessions, refresh_tokens, auth_events, email_verifications, ai_requests, ai_guard_mutex, study_plans, plan_steps, daily_tasks, study_records, schedule_entries, task_rollovers, knowledge_notes, knowledge_review_records, practice_records, focus_sessions, **admin_audit_logs**, **ai_runtime_config** |
| `users.role` | `enum('USER','ADMIN')`，`NOT NULL`，默认 **`USER`**；`users` 共 **12** 列 |
| `admin_audit_logs` | **9** 列；`PRIMARY` + 4 个二级索引（共 8 行 statistics）；**1 条 CHECK**；**0 个外键** |
| `ai_runtime_config` | **5** 列；**4 条 CHECK**；`updated_at` 为 `datetime(6) NOT NULL` 且无 DB 默认/ON UPDATE |
| 初始配置 | `id=1, enabled=1, user_daily_limit=10, global_daily_limit=80`，`updated_at` 为 UTC 时间 |
| `ai_guard_mutex` | 仍为 1 行且 id=1 |
| 原有 16 张非系统表 | 迁移后全部 0 行（含 `admin_audit_logs`） |
| 与 `ssp_a0_migrate2` 结构比对（users 忽略 role） | **diffs: NONE** |

补充说明：结构克隆时沿用了源表的 `AUTO_INCREMENT` 计数器（如 `users`=2552）。已在开发库中对 16 张空表执行 `ALTER TABLE ... AUTO_INCREMENT = 1`（仅元数据，不改结构、不改数据），现 `SHOW CREATE TABLE` 不再输出 `AUTO_INCREMENT=`。

### 2.1 四个原有数据库核对

| 数据库 | 表数 | `users` | `tb_refresh_token`/`refresh_tokens` | `ai_requests` | `study_plans` | `daily_tasks` | `role` 列 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `smart_study_planner` | 14 | 47 | 216 | 17 | 39 | 280 | 无 |
| `ssp_a0_legacy` | 14 | 47 | 212 | 17 | 39 | 280 | 无 |
| `ssp_a0_migrate` | 17 | 0 | 0 | 0 | 0 | 0 | 无 |
| `ssp_a0_migrate2` | 17 | 0 | 0 | 0 | 0 | 0 | 无 |

结论：与 A0.3 完全一致，**无迁移相关变化**（`ssp_a0_migrate2.auth_events` 仅因自动化测试增加，属测试产物）。

---

## 3. 负向测试结果（全部真实执行）

全部用例：显式事务 → 捕获错误 → `ROLLBACK`；INSERT 均提供合法必填字段（`E0` 正向对照证明字段齐全时不会因非约束原因失败）。

| # | 用例 | 预期错误码 | 实际错误码 | 结果 |
| --- | --- | --- | --- | --- |
| E0 | 合法审计行（对照，随后回滚） | 成功 | 插入成功并回滚 | PASS |
| E1 | 第二条 AI 配置记录 `id=2` | 3819 | 3819 | PASS |
| E2 | `user_daily_limit=500 > global=80` | 3819 | 3819 | PASS |
| E3 | `global_daily_limit=-1` | 1264 | 1264 | PASS |
| E4 | `user_daily_limit=0` | 3819 | 3819 | PASS |
| E5 | `enabled=2` | 3819 | 3819 | PASS |
| E6 | `role='SUPER'` | 1265 | 1265 | PASS |
| E7 | `reason=NULL` | 1048 | 1048 | PASS |
| E8 | `reason='   '`（空白） | 3819 | 3819 | PASS |
| E9 | `before_data=NULL` | 1048 | 1048 | PASS |

- 3819 = `CHECK constraint ... is violated`；1264 = `Out of range value`；1265 = `Data truncated for column 'role'`；1048 = `Column ... cannot be null`。
- 残留检查：`admin_audit_logs` 0 行、`ai_runtime_config` 仍为 `1/1/10/80`、`users` 0 行 → **无探针数据遗留**。

---

## 4. Worker 缺陷修复

| 项 | 内容 |
| --- | --- |
| 文件 | `app/jobs/plan_expiration_worker.py:11` |
| 缺陷 | `run_due_plan_check` 使用 `plan_lifecycle_service.expire_due_plan`，但模块从未导入该名称 → `NameError`，被 `except Exception` 吞掉，计划永不自动到期 |
| 修复 | 新增 `from app.services.plans import plan_lifecycle_service`（**仅 1 行**，未重构） |
| 签名核对 | `plan_lifecycle_service.expire_due_plan(db, plan_id: int, today: date) -> bool`，与 Worker 关键字调用 `db=/plan_id=/today=` 完全匹配 |
| 验证 1 | `tests/test_lifecycle_regression.py`：**17/17 通过**（含 `test_L10_worker_is_idempotent`，使用真实到期计划断言 `ended_count > 0`） |
| 验证 2 | 隔离库单次运行（`DB_NAME=ssp_v3_admin_dev`，等价 `--once`）：`{'checked_count': 0, 'ended_count': 0, 'failed_count': 0}`，无异常 |

---

## 5. 测试文件实际修改清单

| 文件 | 修改 | 性质 |
| --- | --- | --- |
| `app/jobs/plan_expiration_worker.py` | 新增 1 行 import | **业务缺陷修复**（A0.4 授权） |
| `tests/test_auth_a1_1_acceptance.py` | `test_t6_02` 改为校验 UserCreate 真实约束（用户名长度/字符集、密码长度、邮箱格式、验证码 6 位数字）；`test_t11_08` 改为校验 `since` 时间窗口契约 | 过时断言更新（覆盖扩大，未删除断言） |
| `tests/test_auth_a2_3_avatar_profile_cleanup_acceptance.py` | 导入 `app.main` 后重建 `/media/avatars` 的 StaticFiles 挂载指向临时目录，并 `atexit` 恢复原挂载 | 测试夹具隔离（未改 `main.py`） |
| `tests/test_progress_regression.py` | 2 处用户夹具补齐 `password_updated_at/email/email_verified_at` | 过时夹具（A0.3） |
| `tests/test_rollover_regression.py` | 1 处用户夹具同上 | 过时夹具（A0.3） |
| `tests/test_lifecycle_regression.py` | 2 处用户夹具同上 | 过时夹具（A0.3） |
| `tests/test_ai_a5_generate.py` | `make_paper()` 题干主题化（15 主题 × 5 句式） | 过时夹具（A0.3） |
| `tests/test_auth_a1_3_acceptance.py` | `test_no_legacy_route_refs` 改为断言 `POST /auth/logout-all` 存在 | 过时断言（A0.3） |

未删除任何测试、未降低覆盖、未修改真实业务规则（Worker 1 行导入除外）。

---

## 6. 全量回归结果

命令：

```powershell
cd d:\project\back
.\.venv\Scripts\python.exe -m pytest tests -q --no-header -p no:cacheprovider --tb=line
```

结果：

```
502 passed, 9 skipped, 8 subtests passed, 2 warnings in 51.93s
```

- **0 failed / 0 error**；总数 511（502 + 9）。
- 相对 A0.3（497 通过 / 5 失败），5 项失败全部清零：1 项真实缺陷修复、2 项过时断言更新、2 项测试隔离修复。
- 全部邮件与 AI 调用均为 Mock/隔离，无真实付费调用。

### 6.1 跳过项（9 项，均有明确原因）

| 数量 | 位置 | 原因 |
| --- | --- | --- |
| 3 | `test_auth_a1_1_acceptance.py:1760/1765/…` | 并发用例已由 `T12ConcurrencyCommitted` 覆盖（有意去重） |
| 4 | `test_auth_a1_1_acceptance.py:2054/2074/2085/2096` | 兼容性探测：旧版路由 `/auth/login`、`/auth/email-code/verify`、`/auth/refresh` 返回 403/404 时跳过 |
| 2 | `test_auth_a2_3_avatar_profile_cleanup_acceptance.py:977/1447` | Windows 无创建符号链接权限（`WinError 1314`），符号链接攻击用例跳过 |

---

## 7. 独立环境验证

| 项 | 结果 |
| --- | --- |
| 进程级覆盖方式 | `$env:DB_NAME='ssp_v3_admin_dev'` 后启动进程 |
| Pydantic Settings 优先级 | 环境变量 **优先于** `.env`：实测 `settings.DB_NAME = ssp_v3_admin_dev` |
| 实际连接 | `SELECT DATABASE()` = `ssp_v3_admin_dev`；`information_schema` 表数 19；`role` 默认 `USER`；配置行 `1/1/10/80` |
| 共享 `.env` | **未修改** |
| 并行运行隔离建议 | ① 端口：Auth V2 用 8000，V3.0 用 8001；② 头像：各自 `AVATAR_DIR`（V3 建议 `storage/v3/avatars`）；③ 浏览器认证：不同端口即不同 Cookie 域端口隔离，建议使用独立浏览器 Profile；④ CORS/`AUTH_ALLOWED_ORIGINS` 按端口分别配置 |
| 测试库 | 自动化测试仍使用 `ssp_a0_migrate2`（`test_auth_a2_3` 内含 `ssp_a0_migrate2` 隔离断言，且测试会写入 `auth_events`），**不指向开发库** |

---

## 8. A1 所需完整源码

已生成独立交接文件：

- `d:\project\back\Smart_Study_Planner_V3.0_A0.4_A1_Source_Handoff.md`（19,678 字节）

包含：

1. 4 个文件的**最新完整源码**（含 SHA256/行数/字节）：`app/core/deps.py`、`app/repositories/auth/session_repository.py`、`app/repositories/auth/user_repository.py`、`app/schemas/user.py`；
2. 全部 `UserPublic` 构造点与相关 SELECT 查询位置（`auth_service.py:58/223`、`users.py:82`、`user_service.py:51`、`account_service.py:455`、`schemas/auth.py:83`、`session_repository.py:85`、`user_repository.py:14/40/66/132-142`、`user_repository.py:256`）；
3. `role` 最小接入结论：
   - 认证必需：`find_session_with_user` 增加 `u.role`；
   - 响应必需：`UserPublic` 增加 `role`，同步 `find_profile` 与登录查询 SELECT；
   - 无需修改：`find_avatar`、Token/认证事件查询；
   - 推荐 JWT 不携带 `role`，每请求实时取，改角色即时生效。

---

## 9. 剩余失败、跳过与阻塞事项

| # | 项 | 状态 |
| --- | --- | --- |
| 1 | 迁移已执行（仅 `ssp_v3_admin_dev`） | 完成；正式库未执行 |
| 2 | 测试失败项 | **0 项** |
| 3 | 跳过项 9 项 | 均为设计去重/兼容性探测/Windows 符号链接权限，合理 |
| 4 | `a1_1` 中 `T6` 有一项既有跳过（旧 `RegisterRequest/LoginRequest` 等 schema 未实现） | 与本次无关，保留原状 |
| 5 | `role` 尚未进入 `UserPublic`/JWT/管理端依赖 | A1 实施（见交接文档 §2） |
| 6 | `admin_audit_logs.action` 字典 | 应用层常量固化（DB 未加 CHECK） |
| 7 | AI 统计字段缺口（耗时/错误码/取消原因） | 沿用 A0 结论，本期未新增 |
| 8 | Redis | 未安装、未接入（边界确认） |
| 9 | `docs/backups/*.sql` 含用户数据 | 保持 untracked，禁止提交 |

**停止点**：迁移与测试基线已完成，等待 GPT 审查后进入 A1 开发。