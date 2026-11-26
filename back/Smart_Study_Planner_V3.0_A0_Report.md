# Smart Study Planner V3.0 — A0 源码与架构盘点报告

> 阶段：A0（只读盘点）
> 盘点时间：2026-11-26
> 盘点范围：`d:\project\back` 后端源码、MySQL 8.4.9 实际库结构、现有测试与运行环境
> 约束执行：未修改任何业务代码、未安装依赖、未执行数据库迁移、未发送真实邮件、未调用真实 AI API
> 说明：本报告不含密码、API Key、JWT 密钥、Redis 密码、Token 或完整 `.env`

---

## 1. 项目当前真实开发状态

### 1.1 总体结论

| 维度 | 结论 |
| --- | --- |
| 技术栈 | Python 3.14 + FastAPI 0.143.3 + SQLAlchemy 2.1.5 + PyMySQL + MySQL 8.4.9；无 ORM 模型层，仓储层全部使用原生 SQL（`text()`） |
| 认证体系 | Auth V2 代码已完成到 A2.4（双 Token、会话管理、邮箱验证码登录、密码重置、头像、清理 Worker） |
| AI 模块 | A3（笔记生成/整理/总结）、A4（知识问答）、A5（出题/批改/历史）均已实现，共享同一套 AI Guard |
| 管理员系统 | **完全未实现**：源码中无 `admin`、`role`、`permission`、`is_admin` 任何业务实现 |
| Redis | **完全未引入**：无服务、无依赖、无配置、无代码 |
| 数据迁移 | **Auth V2 迁移未上正式库**：正式库仍为旧结构（`tb_refresh_token`），新结构仅存在于演练库 |
| 部署形态 | 仓库内无 Dockerfile / docker-compose / gunicorn 配置；未发现多 Worker 配置 |
| 迁移框架 | 无 Alembic / 无 migrations 目录，表结构由手工 SQL 维护 |

### 1.2 数据库分布（本机 MySQL 实测）

| 数据库 | 表数 | 用户数 | 说明 | 判定 |
| --- | --- | --- | --- | --- |
| `smart_study_planner` | 14 | 47（实际 47 行） | 含 `tb_refresh_token`，`users` 无 `password_updated_at`/`email_verified_at`，无 `login_sessions`/`auth_events`/`email_verifications` | **正式库（旧结构）** |
| `ssp_a0_legacy` | 14 | 47 | 与正式库同结构，含业务数据（plans 39、tasks 280） | 迁移前备份 |
| `ssp_a0_migrate` | 17 | 0 | Auth V2 新结构，空数据 | 迁移演练库 |
| `ssp_a0_migrate2` | 17 | 0 | Auth V2 新结构，仅 `auth_events` 183 行（测试产物） | **当前 `.env` 指向的测试/演练库** |
| `student_db` | 1 | — | 与本项目无关的示例库 | 忽略 |

> 关键事实：当前后端进程与全部自动化测试连接的是 `ssp_a0_migrate2`（空库），**正式库 `smart_study_planner` 尚未执行 Auth V2 迁移**。这直接影响 V3.0 的上线路径。

---

## 2. 后端目录及关键文件

```
d:\project\back
├─ app
│  ├─ config.py                     # 全部配置（pydantic-settings），含 AI 限额、会话、邮件
│  ├─ database.py                   # 引擎/SessionLocal，MySQL 时区 +08:00
│  ├─ main.py                       # FastAPI 实例、CORS、活跃时间中间件、统一异常
│  ├─ response.py                   # 统一响应信封
│  ├─ api
│  │  ├─ router.py                  # 总路由注册（无 admin 路由）
│  │  └─ routes/                    # auth/users/plans/steps/tasks/rollovers/
│  │                                # statistics/knowledge/knowledge_ai/ai_practice/focus...
│  ├─ core
│  │  ├─ security.py                # 密码哈希、JWT 签发/校验、Refresh 摘要、验证码 HMAC
│  │  ├─ deps.py                    # oauth2_scheme、authenticate_access、get_current_user
│  │  ├─ auth_cookie.py             # Refresh Cookie、CSRF、客户端 IP、认证响应
│  │  ├─ clock.py                   # business_today（UTC+8）、utc_now、utc_db_now
│  │  └─ practice_ticket.py         # 练习票据签名/过期
│  ├─ repositories
│  │  ├─ auth/                      # user/session/token/verification/auth_event/cleanup/lock
│  │  ├─ knowledge/                 # note/practice/review/ai_guard
│  │  ├─ plans/ tasks/ steps/ ...   # 各业务仓储，全部原生 SQL
│  ├─ services
│  │  ├─ auth/                      # auth/account/session/verification/avatar/
│  │  │                             # rate_limit/activity/mail/user/auth_cleanup
│  │  └─ knowledge/                 # ai_guard/ai_note/ai_qa/ai_practice/
│  │                                # ai_practice_grading/ai_practice_history/ai_service/ai_provider
│  ├─ schemas/                      # Pydantic 请求/响应模型
│  └─ jobs/plan_expiration_worker.py# APScheduler：计划到期 + 可选认证清理
├─ tests/                           # 6 个认证/回归大套件 + 5 个 AI 套件
├─ storage/avatars/                 # 头像目录（静态挂载 /media/avatars）
├─ requirements.txt                 # 无 redis、无 alembic、无 gunicorn
└─ .env                             # 本地配置（不回显敏感值）
```

---

## 3. 已实现功能清单（19 项盘点）

> 状态标签严格限定为五种。测试结论区分「历史通过记录」「本会话实测」「未验证」。

| # | 功能 | 状态 | 实际证据（文件/接口/表/测试） |
| --- | --- | --- | --- |
| 1 | 基础用户管理 | 已实现且有通过的测试证据 | `app/api/routes/users.py`（注册/`GET /users/me`/`GET,PUT /users/{id}`/头像）；`users` 表；`tests/test_auth_a1_1_acceptance.py` 124 项、`test_auth_a1_3_acceptance.py` 98 项（历史与上个窗口执行，97/98 通过，1 项旧用例与 `/auth/logout-all` 新规格冲突） |
| 2 | Auth V2 邮箱验证码登录 | 已实现且有通过的测试证据 | `POST /auth/email-code`、`POST /auth/login/email`；`verification_service.py`、`email_verifications` 表；A1.3 `TestEmailCodeLogin` 9 项（含并发同码仅一次成功） |
| 3 | 密码重置 | 已实现且有通过的测试证据 | `POST /auth/password/reset` → `account_service.reset_password`（account_service.py L110-206）；A2 套件 83/83 通过（上个窗口执行），本轮 A0 未复跑 |
| 4 | 头像管理 | 已实现且有通过的测试证据 | `POST/DELETE /users/me/avatar`；`avatar_service.py`；**本会话 A0 实测** `test_auth_a2_3...`：101 通过 / 2 跳过 / 0 失败 |
| 5 | 双 Token 认证及轮换 | 已实现且有通过的测试证据 | `POST /auth/refresh`；`auth_service.rotate_refresh_token`（L548-698）含重放检测；A1.3 `TestRefreshToken` 8 项（历史通过） |
| 6 | 登录会话管理 | 已实现且有通过的测试证据 | `GET /auth/sessions`、`GET /auth/sessions/current`；`login_sessions` 表；A2 套件 83/83（上个窗口） |
| 7 | 即时会话撤销 | 已实现且有通过的测试证据 | `POST /auth/logout`、`/auth/sessions/{family_id}/revoke`、`/auth/sessions/revoke-others`、`/auth/logout-all`；每次请求都查库校验会话（`get_active_session`），撤销即时生效；A1.3 `test_revoked_session_access_fails` 等 |
| 8 | 树形学习计划 | 已实现但尚未验证 | `plans.py`/`steps.py`/`schedules.py`；`study_plans`、`plan_steps`、`schedule_entries`；无独立计划 CRUD 测试，仅被 lifecycle/progress 回归间接覆盖 |
| 9 | 每日任务及任务顺延 | 已实现但尚未验证 | `tasks.py`、`rollovers.py`；`daily_tasks`、`task_rollovers`；`test_rollover_regression.py` 仅 4 项，历史执行因夹具缺 `password_updated_at` 报 1364 未完成复跑 |
| 10 | 学习统计 | 已实现但尚未验证 | `GET /statistics/overview`；`statistics_service.get_statistics_overview`；`test_progress_regression.py` 17 项历史执行存在夹具报错，尚未得到干净结果 |
| 11 | 知识管理 | 已实现但尚未验证 | `knowledge.py`（笔记 CRUD/回收站/复习记录）；`knowledge_notes`、`knowledge_review_records`；无笔记 CRUD 专项测试 |
| 12 | 专注及番茄钟 | 已实现但尚未验证 | `focus.py`（sessions/current/sync/pause/resume/finish/cancel/statistics）；`focus_sessions` 表；无任何测试 |
| 13 | 每日未打卡提醒 | 部分实现 | 仅提供 `GET /tasks/today/unchecked-count` 计数接口；无定时提醒、无站内信/邮件/推送；`activity_service.py:27` 注释也确认「后台提醒轮询」由前端完成 |
| 14 | AI 笔记助手（生成/整理/总结） | 已实现且有通过的测试证据 | `knowledge_ai.py` L76-185；`ai_note_service.py`；`test_ai_a3_structure.py` 11 项 + `test_knowledge_ai.py` 10 项（本会话实测全部通过） |
| 15 | AI 知识问答 | 已实现且有通过的测试证据 | `POST /notes/{id}/ai/ask`（knowledge_ai.py L193-240）；`ai_qa_service.py`；`test_ai_a4_qa.py` 21 项（本会话实测通过） |
| 16 | AI 出题、批改及历史 | 已实现但尚未验证 | 出题 `POST /ai/practices/generate`、批改 `POST /ai/practices/submit`、历史 `GET/DELETE /ai/practices`；`practice_records` 表；批改 `test_ai_a5_grade.py` 11 项通过；**出题 6 项本会话实测失败（测试夹具与去重规则冲突，见 §14）**；历史接口无测试 |
| 17 | AI 安全与资源控制 | 部分实现 | 共享 MySQL Guard（额度/并发/租约/结算）已实现；但**无请求频率限制**、**无自动化额度/并发限额测试**、**仅单库单点串行**，多实例靠同一 MySQL 强制串行（详见 §6） |
| 18 | 已有管理员、角色及权限 | 未实现 | 全仓库 grep `role|admin|permission|is_admin` 仅命中 LLM 消息 `role` 字段；`users` 表无 `role`；无管理端路由/服务/表 |
| 19 | 已有 Redis 相关实现 | 未实现 | 6379 端口不通、无 Redis 服务、venv 中 `redis` 包不存在、无 Redis 配置/连接池/Lua/锁/计数 |

---

## 4. 可直接复用的代码与接口

### 4.1 认证与会话（V3.0 管理员系统的核心可复用资产）

| 能力 | 位置 | 可复用方式 |
| --- | --- | --- |
| 当前用户认证依赖 | `app/core/deps.py:62-74` `get_current_user` | DIRECT：管理员路由继续使用 |
| Access Token 解码 | `app/core/security.py:256-277` | DIRECT |
| 会话有效性统一校验 | `app/services/auth/session_service.py:38-72` `require_active_session` | DIRECT |
| 查询有效会话+用户 | `session_service.py:108-134` `get_active_session`（含 `is_active` 403） | DIRECT |
| 撤销单个会话+其 Refresh | `session_service.py:137-164` `revoke_session`（**不提交事务**） | DIRECT |
| 撤销用户全部会话+Token | `session_service.py:218-248` `revoke_user_sessions`（**不提交事务**，支持 `exclude_family_id`） | DIRECT：管理员封禁/强制下线直接调用 |
| 批量 UPDATE 会话 | `repositories/auth/session_repository.py:179-237` | DIRECT（仓储层，无事务提交） |
| 用户行锁查询 | `repositories/auth/user_repository.py:7-30` `find_by_id(for_update=True)` | DIRECT：封禁需先锁用户 |
| 认证事件落库 | `repositories/auth/auth_event_repository.py` + `auth_events` 表 | EXTEND：可承载管理员操作审计，但缺 operator 字段 |
| 账户禁用状态 | `users.is_active`，在登录、刷新、每次请求、锁定用户时均校验 | DIRECT：封禁只需置 0 + 撤销会话 |

### 4.2 AI 资源治理

| 能力 | 位置 | 可复用方式 |
| --- | --- | --- |
| 准入（额度+并发+落库） | `ai_guard_service.py:42-147` `admit_request` | DIRECT |
| SSE 生命周期结算 | `ai_guard_service.py:204-356` `metered_ai_stream` | DIRECT |
| 日额度/并发 SQL | `ai_guard_repository.py:28-82` | DIRECT / EXTEND（统计查询） |
| 用量记录 | `ai_requests` 表（user_id/operation/request_date/status/created_at/finished_at/tokens） | EXTEND：缺耗时、错误码 |
| 模型调用 | `ai_provider.py:29-203` + `ai_service.py:68-124` | DIRECT |

### 4.3 统计与业务

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| 学习统计聚合写法 | `statistics_service.py` + `statistics_repository.py` | 可作为 Dashboard 聚合的模板（按日期补零、UTC+8 窗口） |
| 统一响应 | `app/response.py` | DIRECT |
| 业务日期 | `app/core/clock.py:8-10` `business_today()` | DIRECT：AI 统计跨日口径必须复用 |
| 定时任务框架 | `app/jobs/plan_expiration_worker.py` | EXTEND：可挂 AI 数据清理/统计任务 |

---

## 5. Auth V2 认证与会话架构

### 5.1 Token 结构

签发逻辑 `app/core/security.py:136-205`，解码 `:211-289`。

| 字段 | Access Token | Refresh Token |
| --- | --- | --- |
| `sub` | 用户 ID 字符串（1..20 位数字，≤2^64-1） | 同 |
| `family_id` | 会话 UUID4 | 同 |
| `iat` / `exp` | 有 | 有 |
| `type` | `"access"` | `"refresh"` |
| `jti` | UUID4 | UUID4 |
| 算法 | HS256（`SECRET_KEY`） | HS256 |

- Access Token **不绑定** `session_id`，而是绑定 `family_id`（= `login_sessions.family_id` = `refresh_tokens.family_id`）。
- Token 的 `exp` 会被 `absolute_expires_at` 截断（`security.py:148-158`），不会超过会话绝对期限。
- Refresh Token 仅通过 HttpOnly Cookie（`ssp_refresh`，path=`/auth`，SameSite=Lax）传输；JSON 响应永不返回 refresh（`auth_cookie.py:127-153`）。
- Refresh 库中只存 SHA-256 摘要（`hash_refresh_token`），支持 `replaced_by` 轮换链与重放检测。

### 5.2 请求认证流程（逐次校验，无缓存）

```
Authorization: Bearer <access>
  → deps.authenticate_access(token)                     # deps.py:19-59
  → security.decode_access_token_detailed               # 验签/过期/type/jti/sub/family_id
  → 独立短事务 SessionLocal()
  → session_service.get_active_session                  # session_service.py:108-134
      → session_repository.find_session_with_user       # JOIN users，取 is_active
      → require_active_session                          # revoked_at / absolute_expires / idle 判定
      → if not users.is_active → 403 ACCOUNT_DISABLED
  → request.state.auth_identity = (user_id, family_id)  # 供活跃时间中间件使用
```

结论：
- **每次请求都实时查库**校验会话撤销与有效期（不是 JWT 自包含授权）。
- **实时校验账户状态**（`is_active`）。
- **没有 `role` 字段**，也**没有角色权限依赖**（除 `get_current_user` 外无其他鉴权依赖）。
- 当前用户接口 `GET /users/me` 返回 `UserPublic`：`id, username, nickname, email, avatar_url, email_verified_at, is_active`（`schemas/user.py:94-101`）。

### 5.3 会话与 Refresh Token 表

- 登录会话表实际名为 **`login_sessions`**（不是 `tb_login_session`）：主键 `family_id`，含 `user_id, user_agent, created_at, last_activity_at, absolute_expires_at, revoked_at, revoked_reason`，FK → `users.id` ON DELETE CASCADE。
- Refresh 表实际名为 **`refresh_tokens`**（正式库旧表为 `tb_refresh_token`）：`token_hash` 唯一、`family_id`、`expires_at`、`revoked_at`、`replaced_by`。

### 5.4 会话相关函数清单

| 需求 | 现有函数 | 是否提交事务 |
| --- | --- | --- |
| 创建会话 | `session_service.create_session`（L75-105） | 否（调用方提交） |
| 撤销单会话 | `session_service.revoke_session`（L137-164） | 否 |
| 撤销全部会话 | `session_service.revoke_user_sessions`（L218-248） | 否 |
| 锁定并复核用户+会话 | `session_service.lock_current_user`（L171-215） | 否 |
| 密码重置后处理 | `account_service.reset_password`（L110-206）：更新密码 + `revoke_user_sessions(reason="PASSWORD_RESET")`，同一 `with db.begin()` | 是（整段事务） |
| 封禁账户逻辑 | 仅存在“被动拒绝”：`is_active=0` 时登录/刷新/请求返回 403；**无任何写入 `is_active` 的接口** | — |
| 可直接复用的强制下线 | `revoke_user_sessions`（支持保留当前会话） | 否，正适合管理员服务调用 |

`revoked_reason` 字段注释已预留 `ADMIN`（`login_sessions` DDL COMMENT），说明设计上已预期管理员撤销。

---

## 6. 现有 AI Guard 的完整工作流程

### 6.1 入口与调用链（全部经过共享 Guard）

| 操作 | 接口 | 路由位置 | operation | Service |
| --- | --- | --- | --- | --- |
| 生成笔记 | `POST /notes/ai/generate` | `knowledge_ai.py:76-109` | `GENERATE` | `ai_note_service.stream_generate_note` |
| 整理笔记 | `POST /notes/{id}/ai/organize` | `:112-147` | `ORGANIZE` | `stream_organize_note` |
| 总结笔记 | `POST /notes/{id}/ai/summary` | `:150-185` | `SUMMARY` | `stream_summary_note` |
| 知识问答 | `POST /notes/{id}/ai/ask` | `:193-240` | `ASK` | `ai_qa_service.stream_ask_note` |
| AI 出题 | `POST /ai/practices/generate` | `ai_practice.py:45-85` | `PRACTICE_GENERATE` | `stream_generate_practice` |
| AI 批改 | `POST /ai/practices/submit` | `:88-139` | `PRACTICE_GRADE` | `stream_grade_practice` |
| 练习历史 | `GET/DELETE /ai/practices...` | `:142-193` | 不调用 AI | `ai_practice_history_service` |

调用路径统一为：
```
Router → require_ai_available() → 输入/快照校验 → admit_request() → metered_ai_stream(业务流)
业务流 → ai_note/ai_qa/ai_practice service → ai_service.stream_checked_completion
      → ai_provider.stream_completion → https://api.deepseek.com/chat/completions (SSE)
```
`grep` 结果显示 `admit_request(` 与 `metered_ai_stream(` 只在这两个路由文件出现，**没有发现绕过 Guard 的 AI 入口**。`ai_provider` 仅被 `ai_service` 引用，业务层无法直接触达。

### 6.2 Guard 逐项核实

`admit_request`（ai_guard_service.py:42-147）：

| 检查项 | 是否实现 | 实现方式 |
| --- | --- | --- |
| 请求频率限制（每秒/每分钟） | **否** | 无任何 rate limit；仅有日额度与并发 |
| 单用户每日额度 | 是 | `COUNT(ai_requests WHERE request_date=today AND user_id=?)`（repo L42-53）对比 `AI_USER_DAILY_LIMIT`（默认 10） |
| 全站每日额度 | 是 | 同表按 `request_date` 计数（repo L33-40）对比 `AI_GLOBAL_DAILY_LIMIT`（默认 80） |
| 单用户并发限制 | 是 | `COUNT(status='RUNNING' AND leased_until > UTC_TIMESTAMP(6) AND user_id=?)` 对比 `AI_USER_CONCURRENCY`（默认 1） |
| 全站并发限制 | 是 | 同上不带 user 条件，对比 `AI_GLOBAL_CONCURRENCY`（默认 2） |
| AI 总开关 | 是 | `require_ai_available()`：`AI_ENABLED` + `DEEPSEEK_API_KEY`，开关关闭时 503 且不占额度 |
| 额度检查与占用原子性 | 是 | `SELECT id FROM ai_guard_mutex WHERE id=1 FOR UPDATE`（repo L8-25）串行化“计数→检查→INSERT” |
| 额度计数存储 | MySQL `ai_requests`（按 `request_date`） | 无计数器表，无缓存 |
| 并发状态存储 | MySQL `ai_requests.status='RUNNING'` + `leased_until` | 租约 `AI_LEASE_SECONDS=180` |
| 同步机制 | MySQL 行锁（`SELECT ... FOR UPDATE`），**无 Python 锁、无进程内锁** | — |
| 多 Worker 支持 | **支持（受限）** | 只要共享同一 MySQL，所有进程经同一互斥行串行准入 |
| 多实例部署 | **支持（受限）** | 同上；代价是全站准入被单行锁完全串行，成为吞吐瓶颈；且数据库是单点 |
| 北京时间跨日 | 是 | `business_today()`（UTC+8）写入 `request_date`；租约比较用 `UTC_TIMESTAMP(6)` |
| 请求失败/超时/取消 | 是 | `metered_ai_stream`：`done→SUCCESS`、`blocked→BLOCKED`、`error/STALE→ERROR/STALE`、`TimeoutError→TIMEOUT`、`CancelledError→CANCELLED`，`finally` 用 `CancelScope(shield=True)` 兜底写库 |
| SSE 结束后的资源释放 | 是 | 先 `finish_request` 落库再发 `done`；未落库则租约到期后自动不再计入并发 |
| 后端异常退出后的恢复 | **部分** | 并发靠 180s 租约自然过期恢复；**`RUNNING` 状态会永久残留**，没有任何清理任务（`grep ai_requests` 仅 Guard 仓储使用；`auth_cleanup` 只清理认证表） |
| 配额持久化与重启恢复 | 是 | 全部在 MySQL，重启不丢；但“已准入即扣额度、失败不退还” |

### 6.3 已知语义细节

1. **扣额度时机**：准入成功即写 `RUNNING` 并占一次日额度，失败/取消/超时都不退还（注释 `ai_guard_service.py:126`）。
2. **练习生成预留 2 次额度**：`PRACTICE_GENERATE` 额外要求剩余 ≥2（生成 1 次 + 批改 1 次），见 L83-95。
3. **锁不跨模型调用**：`admit_request` 在调用模型前 `db.commit()` 释放互斥行，避免长事务（L137）。
4. **结算使用独立短事务**：`_finish_request_record` 用新的 `SessionLocal`（L170）。
5. **状态集合**：`SUCCESS / BLOCKED / ERROR / STALE / TIMEOUT / CANCELLED`（`RUNNING` 为初始）。
6. **Token 用量**：`prompt_tokens/completion_tokens` 来自上游 `usage`，缺失写 NULL，不伪造 0。
7. **无耗时字段**：`ai_requests` 只有 `created_at` 与 `finished_at`，可推算耗时，但无显式 duration、无错误码、无取消原因。

### 6.4 AI 统计基础评估（V3.0 四项统计）

| V3.0 统计 | 现有数据是否支持 | 说明 |
| --- | --- | --- |
| 今日额度消耗 | **可直接复用** | `COUNT(*) WHERE request_date=TODAY`（与 Guard 口径一致） |
| 近七日调用趋势 | **可直接复用** | `request_date` + `idx_ai_request_date`，按日期分组即可 |
| 成功/失败/取消统计 | **可复用但需口径约定** | `status` 已区分 SUCCESS/ERROR/TIMEOUT/CANCELLED/BLOCKED/STALE；但历史 `RUNNING` 残留需在统计时排除或归为“异常未结算” |
| AI 功能使用分布 | **可直接复用** | `operation` 字段（6 类） |

缺失字段（若要做更细的运营统计）：
- 无 `duration_ms`（可由 `finished_at-created_at` 计算，但客户端取消时可能为空）；
- 无 `error_code`（当前只写 `status=ERROR`，无法区分上游 429/网络/格式错误）；
- 无 `ip` / `user_agent`；
- 无“拒绝”记录（429 拒绝根本不落库，**拒绝次数无法统计**）。

最小补充方案（不新增表）：`ai_requests` 增加 `duration_ms INT NULL`、`error_code VARCHAR(32) NULL`；如需拒绝统计，增加 `ai_rejections` 或写一条 `status='REJECTED'` 的记录（会污染额度计数，需注意）。

---

## 7. Redis 环境与已有实现

| 检查项 | 实测结果 |
| --- | --- |
| Redis 服务 | 本机 `127.0.0.1:6379` 连接失败；无 `*redis*` Windows 服务 |
| Python 客户端依赖 | venv 中 `redis` 包不存在；`requirements.txt` 无 redis |
| 连接配置 | `app/config.py` 无任何 REDIS_* 字段；`.env` 无 Redis 配置 |
| 连接池 / 生命周期 | 无 |
| Redis 限流 / Lua / 分布式锁 / 额度计数 / 并发控制 | 无 |
| Redis 持久化配置 | 无 |
| Docker / Docker Compose | 仓库内无 Dockerfile / compose 文件 |
| FastAPI Worker 数量 | 未发现 `--workers`、gunicorn 或进程管理配置；按默认单进程推断（**部署方式未知**） |
| 同时运行的后端实例数 | **未知**（仓库内无部署编排，无法从源码确认） |
| 服务器内存 / Redis 可用内存预算 | **未知**（无部署清单/监控） |

### 7.1 现有 AI Guard 中“适合继续 MySQL”与“适合迁 Redis”的部分

| 组件 | 建议 | 理由 |
| --- | --- | --- |
| 每日额度（user/global） | 可继续 MySQL，或迁 Redis | 写入频率低（每用户 ≤10 次/日），MySQL 足够；Redis 可降低主库压力 |
| 并发租约 | **适合 Redis（若要多实例/高并发）** | 需要短 TTL、原子增减、自动过期；MySQL 需靠 `leased_until` 轮询式判断 |
| 准入互斥 | **适合 Redis Lua** | 一条 Lua 完成“查额度+查并发+占用+设 TTL”，避免 MySQL 单行锁全局串行 |
| 请求明细/结算 | 保留 MySQL | 需要持久化、可查询、可做统计 |
| 账户/会话撤销 | 保留 MySQL | 强一致、需审计 |
| 认证 IP 限流 | 可迁 Redis | 当前用 MySQL 命名锁 `GET_LOCK`（`rate_limit_service.py:85-153`），多实例可用但每次要占连接 |

### 7.2 Redis 引入必须回答的 7 个问题（当前均无实现）

1. **MySQL 动态配置与 Redis 准入一致性**：当前配置只在 `Settings`（环境变量），没有动态配置表；若 V3.0 做动态配置，需定义“DB 配置变更 → Redis 阈值刷新”的传播方式。
2. **多 Worker 共享额度/并发**：Redis 天然共享；MySQL 也已共享，但串行。
3. **Redis 不可用 Fail Closed**：当前无 Redis，故无策略。V3.0 若引入，需明确“连接失败即拒绝 AI 请求”（推荐）而非放行。
4. **Redis 重启后日额度恢复**：Redis 持久化（AOF/RDB）不足以保证强一致；建议启动时从 MySQL `ai_requests` 回填当日计数，或始终以 MySQL 为真源、Redis 只做快速准入。
5. **并发资源泄漏/过期/重复释放**：Redis 需用 TTL + 唯一 lease id + Lua 条件释放，避免重复释放或误删他人租约。
6. **SSE 取消/异常结束释放**：当前 `metered_ai_stream` 已覆盖；迁 Redis 时需在 `finally` 中同样做 shield 释放，并处理“客户端断开后协程被取消”的 Windows/uvicorn 行为。
7. **跨日未结束请求**：当前按 `request_date`（开始日）计额度，跨日请求仍算前一天；迁移时需保持同一口径，避免凌晨前后额度翻倍/丢失。

**本阶段结论：不建议在“一天内完成管理员系统”的目标里同时引入 Redis。** 现有 MySQL Guard 已能支撑单实例/单库多 Worker 的正确性；Redis 属于性能与多实例扩展项，建议单独立项（DEFER）。

---

## 8. 实际数据库 DDL

以下为本机 `ssp_a0_migrate2`（Auth V2 新结构，测试/演练库）的 `SHOW CREATE TABLE` 原始结果（已去除敏感信息）。

### 8.1 users

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
  `is_active` tinyint NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

> **`users` 无角色字段。** 正式库 `smart_study_planner.users` 更旧：9 列（无 `password_updated_at`、`email_verified_at`）。

### 8.2 login_sessions

```sql
CREATE TABLE `login_sessions` (
  `family_id` char(36) NOT NULL COMMENT '会话 ID，等于 refresh_tokens.family_id',
  `user_id` bigint unsigned NOT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `last_activity_at` datetime(6) NOT NULL,
  `absolute_expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `revoked_reason` varchar(32) DEFAULT NULL COMMENT 'LOGOUT/LOGOUT_ALL/REPLAY/PASSWORD_CHANGED/ADMIN',
  PRIMARY KEY (`family_id`),
  KEY `idx_login_sessions_user_active` (`user_id`,`revoked_at`,`absolute_expires_at`),
  KEY `idx_login_sessions_expires` (`absolute_expires_at`),
  CONSTRAINT `fk_login_sessions_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.3 refresh_tokens

```sql
CREATE TABLE `refresh_tokens` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `token_hash` char(64) NOT NULL COMMENT 'SHA-256 摘要',
  `family_id` char(36) NOT NULL,
  `expires_at` datetime NOT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `replaced_by` char(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_refresh_token_hash` (`token_hash`),
  KEY `idx_refresh_user_family` (`user_id`,`family_id`),
  KEY `idx_refresh_expires_at` (`expires_at`),
  CONSTRAINT `fk_refresh_token_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.4 auth_events（现有“审计”资产）

```sql
CREATE TABLE `auth_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned DEFAULT NULL COMMENT '不建外键，保留历史',
  `identifier` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci DEFAULT NULL,
  `event_type` varchar(32) NOT NULL,
  `ip` varchar(45) DEFAULT NULL,
  `family_id` char(36) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_auth_events_user_time` (`user_id`,`created_at`),
  KEY `idx_auth_events_identifier_type_time` (`identifier`,`event_type`,`created_at`),
  KEY `idx_auth_events_ip_type_time` (`ip`,`event_type`,`created_at`),
  KEY `idx_auth_events_type_time` (`event_type`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='认证安全事件（保留 30 天）';
```

> 无 `operator_id`（操作人）、无 `target_user_id`、无 `detail/json` 字段 → **不能直接满足管理员操作审计**。

### 8.5 email_verifications

```sql
CREATE TABLE `email_verifications` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `email` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL,
  `purpose` enum('REGISTER','LOGIN','RESET_PASSWORD','CHANGE_EMAIL_OLD','CHANGE_EMAIL_NEW') NOT NULL,
  `user_id` bigint unsigned DEFAULT NULL,
  `family_id` char(36) DEFAULT NULL,
  `code_hash` char(64) NOT NULL,
  `attempts` tinyint unsigned NOT NULL DEFAULT '0',
  `created_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  `invalidated_at` datetime(6) DEFAULT NULL,
  `request_ip` varchar(45) NOT NULL,
  `send_status` enum('PENDING','SENT','FAILED') NOT NULL DEFAULT 'PENDING',
  PRIMARY KEY (`id`),
  KEY `idx_email_verifications_email_purpose_created` (`email`,`purpose`,`created_at`),
  KEY `idx_email_verifications_email_created` (`email`,`created_at`),
  KEY `idx_email_verifications_ip_created` (`request_ip`,`created_at`),
  KEY `idx_email_verifications_created` (`created_at`),
  KEY `idx_email_verifications_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.6 ai_requests（AI 用量记录，V3.0 统计主数据源）

```sql
CREATE TABLE `ai_requests` (
  `request_id` char(36) NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `note_id` bigint unsigned DEFAULT NULL,
  `operation` varchar(24) NOT NULL,
  `request_date` date NOT NULL,
  `status` varchar(20) NOT NULL,
  `leased_until` datetime(6) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `finished_at` datetime(6) DEFAULT NULL,
  `prompt_tokens` int unsigned DEFAULT NULL,
  `completion_tokens` int unsigned DEFAULT NULL,
  PRIMARY KEY (`request_id`),
  KEY `idx_ai_request_date` (`request_date`),
  KEY `idx_ai_user_date` (`user_id`,`request_date`),
  KEY `idx_ai_active` (`status`,`leased_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.7 ai_guard_mutex

```sql
CREATE TABLE `ai_guard_mutex` (
  `id` tinyint unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
```

> 必须存在 `id=1` 的行，否则 `admit_request` 抛 `AI admission mutex is missing`。空库演练时需手工插入该行（属迁移脚本的一部分）。

### 8.8 study_plans / plan_steps / daily_tasks / study_records

```sql
CREATE TABLE `study_plans` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` text,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `status` enum('DRAFT','ACTIVE','ENDED') NOT NULL DEFAULT 'DRAFT',
  `started_at` datetime DEFAULT NULL,
  `ended_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_study_plans_user_status` (`user_id`,`status`,`deleted_at`),
  CONSTRAINT `fk_study_plans_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `chk_study_plans_dates` CHECK ((`start_date` <= `end_date`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `plan_steps` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `plan_id` bigint unsigned NOT NULL,
  `parent_id` bigint unsigned DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `description` text,
  `node_type` enum('GROUP','LEAF') NOT NULL,
  `task_type` enum('BOOLEAN','NUMERIC') DEFAULT NULL,
  `schedule_mode` enum('REPEAT','DAILY_CUSTOM','AUTO_DISTRIBUTE','DAILY_MANUAL') DEFAULT NULL,
  `repeat_content` varchar(255) DEFAULT NULL,
  `total_target` bigint unsigned DEFAULT NULL,
  `sort_order` int unsigned NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_plan_steps_parent` (`parent_id`),
  KEY `idx_plan_steps_tree` (`plan_id`,`parent_id`,`deleted_at`),
  CONSTRAINT `fk_plan_steps_parent` FOREIGN KEY (`parent_id`) REFERENCES `plan_steps` (`id`),
  CONSTRAINT `fk_plan_steps_plan` FOREIGN KEY (`plan_id`) REFERENCES `study_plans` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `daily_tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `plan_id` bigint unsigned NOT NULL,
  `step_id` bigint unsigned NOT NULL,
  `task_date` date NOT NULL,
  `task_type` enum('BOOLEAN','NUMERIC') NOT NULL,
  `content` varchar(255) NOT NULL,
  `target_quantity` bigint unsigned DEFAULT NULL,
  `actual_quantity` bigint unsigned NOT NULL DEFAULT '0',
  `rollover_out_quantity` bigint unsigned NOT NULL DEFAULT '0',
  `status` enum('PENDING','IN_PROGRESS','COMPLETED','OVERDUE','ENDED') NOT NULL DEFAULT 'PENDING',
  `completed_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `numeric_active_date` date GENERATED ALWAYS AS ((case when ((`task_type` = _utf8mb4'NUMERIC') and (`deleted_at` is null)) then `task_date` else NULL end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_daily_tasks_numeric_day` (`step_id`,`numeric_active_date`),
  KEY `idx_daily_tasks_plan_date` (`plan_id`,`task_date`,`deleted_at`),
  KEY `idx_daily_tasks_step_date` (`step_id`,`task_date`),
  CONSTRAINT `fk_daily_tasks_plan` FOREIGN KEY (`plan_id`) REFERENCES `study_plans` (`id`),
  CONSTRAINT `fk_daily_tasks_step` FOREIGN KEY (`step_id`) REFERENCES `plan_steps` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `study_records` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `task_id` bigint unsigned NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `event_type` enum('BOOLEAN_COMPLETE','NUMERIC_PROGRESS') NOT NULL,
  `recorded_value` bigint unsigned DEFAULT NULL,
  `task_date` date NOT NULL,
  `recorded_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_study_records_user` (`user_id`),
  KEY `idx_study_records_task_time` (`task_id`,`recorded_at`),
  CONSTRAINT `fk_study_records_task` FOREIGN KEY (`task_id`) REFERENCES `daily_tasks` (`id`),
  CONSTRAINT `fk_study_records_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.9 knowledge_notes / knowledge_review_records / practice_records

```sql
CREATE TABLE `knowledge_notes` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `plan_id` bigint unsigned DEFAULT NULL,
  `step_id` bigint unsigned DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `content_md` mediumtext NOT NULL,
  `tags` json NOT NULL DEFAULT (json_array()),
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_notes_user_deleted` (`user_id`,`deleted_at`),
  KEY `idx_notes_plan` (`plan_id`),
  KEY `idx_notes_step` (`step_id`),
  CONSTRAINT `fk_notes_plan` FOREIGN KEY (`plan_id`) REFERENCES `study_plans` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_notes_step` FOREIGN KEY (`step_id`) REFERENCES `plan_steps` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_notes_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `knowledge_review_records` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `note_id` bigint unsigned NOT NULL,
  `user_id` bigint unsigned NOT NULL,
  `reviewed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_review_note_time` (`note_id`,`reviewed_at`),
  KEY `idx_review_user_time` (`user_id`,`reviewed_at`),
  CONSTRAINT `fk_review_note` FOREIGN KEY (`note_id`) REFERENCES `knowledge_notes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_review_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `practice_records` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `note_id` bigint unsigned DEFAULT NULL,
  `note_title_snapshot` varchar(255) NOT NULL,
  `generation_id` char(36) NOT NULL,
  `question_count` tinyint unsigned NOT NULL,
  `score` decimal(5,2) NOT NULL,
  `questions_json` json NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_practice_user_generation` (`user_id`,`generation_id`),
  KEY `idx_practice_user_created` (`user_id`,`created_at`,`id`),
  KEY `idx_practice_user_note_created` (`user_id`,`note_id`,`created_at`,`id`),
  KEY `idx_practice_note` (`note_id`),
  CONSTRAINT `fk_practice_note` FOREIGN KEY (`note_id`) REFERENCES `knowledge_notes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_practice_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `chk_practice_question_count` CHECK ((`question_count` in (5,10,15))),
  CONSTRAINT `chk_practice_score` CHECK ((`score` >= 0) and (`score` <= 100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.10 focus_sessions / task_rollovers / schedule_entries

```sql
CREATE TABLE `focus_sessions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `plan_id` bigint unsigned DEFAULT NULL,
  `task_id` bigint unsigned DEFAULT NULL,
  `session_type` enum('POMODORO','STOPWATCH') NOT NULL,
  `status` enum('RUNNING','PAUSED','COMPLETED','CANCELLED') NOT NULL DEFAULT 'RUNNING',
  `planned_seconds` int unsigned DEFAULT NULL,
  `focused_seconds` int unsigned NOT NULL DEFAULT '0',
  `running_started_at` datetime(6) DEFAULT NULL,
  `started_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `ended_at` datetime(6) DEFAULT NULL,
  `focus_date` date NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_focus_user_status` (`user_id`,`status`),
  KEY `idx_focus_user_date` (`user_id`,`focus_date`),
  KEY `idx_focus_user_started` (`user_id`,`started_at`),
  KEY `idx_focus_plan` (`plan_id`),
  KEY `idx_focus_task` (`task_id`),
  CONSTRAINT `fk_focus_plan` FOREIGN KEY (`plan_id`) REFERENCES `study_plans` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_focus_task` FOREIGN KEY (`task_id`) REFERENCES `daily_tasks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_focus_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `chk_focus_planned_seconds` CHECK ((((`session_type` = _utf8mb4'POMODORO') and (`planned_seconds` is not null) and (`planned_seconds` > 0)) or ((`session_type` = _utf8mb4'STOPWATCH') and (`planned_seconds` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `task_rollovers` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `source_task_id` bigint unsigned NOT NULL,
  `target_task_id` bigint unsigned NOT NULL,
  `quantity` bigint unsigned DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rollover_source_target` (`source_task_id`,`target_task_id`),
  KEY `fk_task_rollovers_target` (`target_task_id`),
  CONSTRAINT `fk_task_rollovers_source` FOREIGN KEY (`source_task_id`) REFERENCES `daily_tasks` (`id`),
  CONSTRAINT `fk_task_rollovers_target` FOREIGN KEY (`target_task_id`) REFERENCES `daily_tasks` (`id`),
  CONSTRAINT `chk_rollover_not_self` CHECK ((`source_task_id` <> `target_task_id`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `schedule_entries` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `step_id` bigint unsigned NOT NULL,
  `task_date` date NOT NULL,
  `content` varchar(255) DEFAULT NULL,
  `target_quantity` bigint unsigned DEFAULT NULL,
  `sort_order` int unsigned NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_schedule_entries_step_date` (`step_id`,`task_date`,`deleted_at`),
  CONSTRAINT `fk_schedule_entries_step` FOREIGN KEY (`step_id`) REFERENCES `plan_steps` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 8.11 管理/配置/审计相关表盘点结论

| 表 | 是否存在 | 结论 |
| --- | --- | --- |
| 管理员/角色/权限表 | **不存在** | 需新增 `users.role`（或角色表） |
| 管理员审计表 | **不存在** | `auth_events` 结构不足（无 operator/target/detail） |
| AI 动态配置表 | **不存在** | 配置仅来自 `Settings`（环境变量） |
| AI 用量记录表 | **存在** `ai_requests` | 可直接用于 V3.0 统计（见 §6.4） |

### 8.12 迁移状态判定

- **Auth V2 正式库迁移未完成**：`smart_study_planner` 无 `login_sessions` / `refresh_tokens` / `auth_events` / `email_verifications`，且 `users` 缺 `password_updated_at`、`email_verified_at`（共 9 列），旧 `tb_refresh_token`（实际 216 行）仍在。
- **AI 相关表已上正式库**：正式库 `ai_requests` 的列与演练库完全一致（11 列，实际 17 行），`ai_guard_mutex` 含 `id=1`，`practice_records` / `focus_sessions` / `knowledge_review_records` 均存在 → 缺口仅在 Auth V2，不在 AI 模块。
- 当前代码在正式库上**无法运行**（`session_repository` 直接查 `login_sessions`）。
- `ssp_a0_migrate2` 有 17 张表但**无业务数据**（`users=0`、`ai_requests=0`、`auth_events=183` 为测试产物）；`ai_guard_mutex` 已含 `id=1` 行（迁移脚本已插入，Guard 可用）。
- 因此，**V3.0「只需扩展 users + 新增两张表」的前提目前不成立**：必须先完成 Auth V2 的正式库迁移与数据搬迁。

---

## 9. V3.0 功能复用分析矩阵

| V3.0 功能 | 现有实现位置 | 当前状态 | 复用方式 | 必要修改 | 工程量 |
| --- | --- | --- | --- | --- | --- |
| 管理员身份校验 | `users` 无 role；`deps.get_current_user` 可用 | 无角色能力 | **NEW** | `users` 增 `role`；新增 `require_admin` 依赖；`get_current_user` 之后二次查询 role（或 JOIN 返回） | 小（0.2 人日） |
| 即时会话撤销 | `session_service.revoke_session` / `revoke_user_sessions`（不提交事务） | 完整可用 | **DIRECT** | 管理员服务内先锁 users 行，再调用，最后一次 commit | 极小 |
| 用户封禁与解封 | `users.is_active` + 登录/刷新/请求全链路校验 | 能力完整但无写入口 | **EXTEND** | 新增 admin 接口：`UPDATE users.is_active` + `revoke_user_sessions(reason=ADMIN/UNBAN)`，同一事务 | 小（0.3 人日） |
| 强制下线 | `revoke_user_sessions(exclude_family_id=None)` | 完整可用 | **DIRECT** | 无（仅需权限校验与审计） | 极小 |
| 用户分页查询 | `user_repository` 仅有按 id/username/email 单查 | 无列表/计数 | **NEW** | 新增 `list_users(page,size,keyword,status)` + `count_users`，注意 `users` 无 role/created 索引 | 小（0.3 人日） |
| 操作审计 | `auth_events` 表 + `auth_event_repository` | 仅认证事件 | **REFACTOR** | `auth_events` 增 `operator_id`、`target_user_id`、`detail JSON`；或新建 `admin_audit_logs`；统一写入函数 | 中（0.4 人日） |
| Dashboard | 无管理端聚合；`statistics_repository` 可参考 | 不存在 | **NEW** | 新增聚合 SQL：用户总数/今日新增/活跃会话/AI 今日用量/近 7 日趋势 | 中（0.4 人日） |
| AI 用量统计 | `ai_requests`（user/operation/date/status/tokens/时间） | 数据基础足够，缺接口 | **EXTEND** | 新增统计查询（今日额度、7 日趋势、状态分布、功能分布）；建议补 `duration_ms/error_code` | 小（0.3 人日） |
| AI 动态配置 | 仅 `Settings` 环境变量 | 无 DB 配置 | **NEW** | 新增 `ai_configs` 表（key/value/updated_by/updated_at）；Guard 读取时优先 DB；需缓存与一致性策略 | 中（0.4～0.6 人日） |
| Redis 资源治理 | 无 | 未引入 | **DEFER** | 若做：连接池 + Lua 准入 + 租约 + 启动回填 + Fail Closed；涉及部署、监控、回滚 | 大（1.5+ 人日） |

> **为什么这些是 REFACTOR/NEW：**
> - 管理员身份：`users` 无任何角色字段，`get_current_user` 只返回会话+用户基础字段，无法表达权限。
> - 用户分页：仓储层没有列表/计数 SQL，也没有 `role/status/created_at` 组合索引。
> - 操作审计：`auth_events` 是“认证安全事件”，缺操作人、目标用户、操作详情，且被 `auth_cleanup` 30 天清理，不适合作为长期管理审计。
> - AI 动态配置：Guard 直接读 `settings.*` 常量，运行期无法变更；无配置表、无热更新机制。
> - Redis：整条链路（依赖、配置、连接、脚本、部署）为零。

---

## 10. 必要新增和修改的文件清单

### 10.1 新增（建议）

| 文件 | 作用 |
| --- | --- |
| `app/api/routes/admin.py` | 管理端路由：用户列表/详情/封禁/解封/强制下线/会话查看/审计查询/Dashboard/AI 统计/AI 配置 |
| `app/services/admin/admin_user_service.py` | 封禁/解封/强制下线的事务编排（锁 users → 改 is_active → revoke sessions → 写审计 → 一次 commit） |
| `app/services/admin/admin_query_service.py` | 用户分页、Dashboard、AI 统计聚合 |
| `app/services/admin/audit_service.py` | 统一审计写入（operator/target/action/result/ip/detail） |
| `app/repositories/admin/user_admin_repository.py` | 分页/计数/按状态筛选/批量更新 is_active 的 SQL |
| `app/repositories/admin/audit_repository.py` | 审计表读写 |
| `app/repositories/admin/ai_stats_repository.py` | `ai_requests` 聚合 SQL（按日/operation/status） |
| `app/schemas/admin.py` | 管理端请求/响应模型（分页、封禁原因、配置项） |
| `sql/2026xxxx_v3_admin.sql`（或项目约定的 SQL 目录） | 最小迁移脚本（无 Alembic，需手工执行并记录） |

### 10.2 修改

| 文件 | 修改点 |
| --- | --- |
| `app/core/deps.py` | 新增 `require_admin`（在 `get_current_user` 基础上校验角色） |
| `app/api/router.py` | 注册 `admin.router` |
| `app/config.py` | 可选：`ADMIN_*` 开关；若引入 Redis 则增加 `REDIS_*` |
| `app/repositories/auth/user_repository.py` | 可选：`find_by_id` 增加 `role` 字段返回（供 `require_admin`），或新增专用查询 |
| `requirements.txt` | 仅当引入 Redis 时增加 `redis` |

### 10.3 明确“不需要改”的部分

- `app/services/auth/session_service.py`（撤销能力已满足）
- `app/services/auth/auth_service.py`（登录/刷新/重放检测无需改）
- `app/services/knowledge/ai_guard_service.py`（统计只读，不需要改 Guard 逻辑）
- `app/services/knowledge/ai_provider.py` / `ai_service.py`

---

## 11. 最小数据库迁移建议

### 11.1 前置条件（必须先做）

1. **把 Auth V2 结构迁移到正式库 `smart_study_planner`**：
   - 新建 `login_sessions`、`refresh_tokens`、`auth_events`、`email_verifications`；
   - `users` 增 `password_updated_at`、`email_verified_at`（并回填合理默认值）；
   - 旧 `tb_refresh_token` 数据迁移或作废（建议全部作废，强制重新登录）；
   - 插入 `ai_guard_mutex(id=1)`。
2. 迁移演练库已验证结构（`ssp_a0_migrate2`），但**没有数据搬迁脚本**在仓库中（未发现 migrations 目录）。

### 11.2 V3.0 最小增量（仅 3 处）

```sql
-- 1) 管理员角色（最小方案：单角色枚举）
ALTER TABLE users
  ADD COLUMN role ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER' AFTER is_active,
  ADD KEY idx_users_role_created (role, created_at);

-- 2) 管理员操作审计（不复用 auth_events，避免 30 天清理与语义混淆）
CREATE TABLE admin_audit_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  operator_id BIGINT UNSIGNED NOT NULL,
  target_user_id BIGINT UNSIGNED DEFAULT NULL,
  action VARCHAR(32) NOT NULL,            -- BAN / UNBAN / FORCE_LOGOUT / UPDATE_AI_CONFIG ...
  result VARCHAR(16) NOT NULL,            -- SUCCESS / FAILED
  ip VARCHAR(45) DEFAULT NULL,
  detail JSON DEFAULT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_admin_audit_operator_time (operator_id, created_at),
  KEY idx_admin_audit_target_time (target_user_id, created_at),
  KEY idx_admin_audit_action_time (action, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 3) AI 动态配置（单行或 key-value）
CREATE TABLE ai_configs (
  config_key VARCHAR(64) NOT NULL,
  config_value VARCHAR(255) NOT NULL,
  updated_by BIGINT UNSIGNED DEFAULT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

### 11.3 不建议现在就做的

- 不要新建 `admin_users` 表（与 `users` 重复）。
- 不要新建 `ai_usage_daily` 汇总表（`ai_requests` 足够，先加索引）。
- 不要改 `auth_events` 结构（会影响清理任务与现有测试），审计单独建表更安全。
- 不要引入 Redis 相关表/键（本期不做）。

---

## 12. Redis 最小集成建议（建议 DEFER）

若开发者决定本期引入，最小可行方案：

1. **依赖**：`redis>=5`（async 客户端 `redis.asyncio`）。
2. **配置**：`REDIS_URL`、`REDIS_MAX_CONNECTIONS`、`REDIS_SOCKET_TIMEOUT`、`REDIS_ENABLED`（默认 False）。
3. **生命周期**：`app/main.py` lifespan 中创建/关闭连接池；单例 `Redis` 客户端。
4. **键设计**（均带 TTL，跨日自动过期）：
   - `ai:quota:global:{yyyy-mm-dd}` → 计数，TTL 至次日 02:00（UTC+8）
   - `ai:quota:user:{user_id}:{yyyy-mm-dd}` → 计数
   - `ai:conc:global` / `ai:conc:user:{user_id}` → ZSET（member=request_id, score=过期时间戳）或租约 key
5. **Lua 原子准入**：一次脚本完成「检查日额度 → 检查并发 → INCR 日额度 → ZADD 并发租约」，返回 `ALLOW/DENY(reason)`，避免多实例竞态。
6. **Fail Closed**：Redis 连接/超时异常 → 直接 503/429，不允许放行（AI 是付费资源）。
7. **MySQL 为真源**：启动时用 `ai_requests` 当日计数回填 Redis；Redis 只做快速准入，最终仍写 `ai_requests` 结算。
8. **释放**：SSE `finally` 中用 Lua 按 `request_id` 条件 `ZREM`，防止误删/重复释放；租约到期由 `ZREMRANGEBYSCORE` 惰性清理。
9. **跨日**：沿用 `business_today()`（UTC+8）作为 key 日期；跨日请求仍记开始日，统计口径与 MySQL 一致。
10. **监控/回滚**：`REDIS_ENABLED=false` 可一键回到 MySQL Guard；需监控连接失败率、准入耗时。

**结论**：Redis 的价值在“多实例 + 高并发”，当前项目没有部署多实例的证据，且 MySQL Guard 已正确工作。**一天内完成管理员系统时不应包含 Redis。**

---

## 13. 事务、锁顺序及并发风险

### 13.1 现有锁顺序（必须保持）

| 流程 | 加锁顺序 | 位置 |
| --- | --- | --- |
| 密码登录 | `users` FOR UPDATE → 插 login_sessions → 插 refresh_tokens | `auth_service.py:401-476` |
| 邮箱登录 | `users` FOR UPDATE → 消费验证码 → 建会话 | `auth_service.py:493-542` |
| Refresh 轮换 | `users` FOR UPDATE → `login_sessions` FOR UPDATE → `refresh_tokens` FOR UPDATE | `auth_service.py:570-698`（注释 L572-573 明确） |
| 退出当前会话 | `users` → `login_sessions` →（必要时）`refresh_tokens` | `auth_service.py:750-813` |
| 改密/换绑/撤销设备 | `users` → 当前 `login_sessions` → 目标 `login_sessions` | `account_service.py:227-283, 502-569, 587-638` |
| 密码重置 | `users` FOR UPDATE → 更新密码 → 批量撤销会话/Token | `account_service.py:123-206` |
| AI 准入 | `ai_guard_mutex` 单行 FOR UPDATE → 计数 → INSERT `ai_requests` → COMMIT | `ai_guard_service.py:71-137` |

**统一规则**：任何新写路径（管理员封禁）必须遵循 `users → login_sessions → refresh_tokens`，否则与 Refresh 轮换形成死锁（例如管理员先锁会话、后锁用户，而刷新先锁用户、后锁会话）。

### 13.2 管理员封禁与并发登录/刷新的竞态分析

- **安全点**：`get_current_user` 每次请求都 JOIN `users.is_active` 并检查 `revoked_at`，因此封禁一旦提交，旧 Access Token 在下一次请求立即 403。
- **风险 1（封禁后仍拿到新 Token）**：若封禁流程分两个事务（先 `is_active=0` 提交，再撤销会话），中间的刷新请求可能成功。虽然 `rotate_refresh_token` 会检查 `is_active`（L587-592）并在 `is_active=0` 后拒绝，但若刷新已先锁住用户行并完成检查，则可能抢在封禁前完成轮换。**必须在同一事务内完成「锁用户 → 置 is_active=0 → 撤销全部会话/Token → 写审计 → commit」。**
- **风险 2（锁顺序反转）**：若先撤销会话再改 `is_active`，且撤销函数内部按 `family_id` 更新（不锁 users），仍可与刷新并发；由于刷新先锁 users，正确顺序可保证串行。
- **风险 3（重复提交**）：`revoke_*` 都是幂等 UPDATE（`revoked_at IS NULL` / `WHERE status='RUNNING'`），重复调用安全。
- **风险 4（管理员把自己封禁）**：需业务层禁止 `operator_id == target_user_id` 或至少保留最后一个 ADMIN。
- **风险 5（解封）**：只需 `is_active=1`；旧会话已被撤销，用户需重新登录，符合预期。

### 13.3 其他并发/一致性风险

1. **`revoke_user_sessions` / `revoke_session` 不提交事务**——这是优点（管理员可组合事务），但调用方若忘记 commit 会静默不生效；需在服务层显式 `db.commit()` 并在异常时 `rollback`。
2. **AI 互斥行是全局单点**：所有 AI 准入串行；若管理员 Dashboard 也去 `FOR UPDATE` 该行，会阻塞 AI。Dashboard 只做只读 `COUNT`，不要加锁。
3. **`ai_requests` 无清理**：长期运行会累积；建议增加“保留 N 天”的清理任务（可挂到现有 worker），否则 7 日/30 日统计会变慢。
4. **`RUNNING` 永久残留**：并发判断依赖 `leased_until` 自动失效，但统计“成功率”时若把 `RUNNING` 算作失败会失真；建议统计口径：`finished_at IS NOT NULL` 才算已结算。
5. **跨日请求**：`request_date` 在准入时固定；若 23:59 准入、次日 00:03 结束，额度记在前一天，`finished_at` 在次日。按 `request_date` 出报表即可，不要用 `finished_at` 分组。
6. **认证限流用 MySQL 命名锁**（`rate_limit_service.admission_session`，L85-153）：每个认证请求占用一条物理连接并 `GET_LOCK`，高并发下可能成为瓶颈；V3.0 管理端不要复用该锁做无关限流。
7. **`auth_events` 无外键**：`user_id` 指向已删除用户时仍保留，管理员审计不要依赖它做用户关联。
8. **`ai_guard_mutex` 必须存在 `id=1` 行**：空库迁移遗漏会导致所有 AI 请求 500（RuntimeError）。
9. **`db.begin()` 与已有隐式事务**：现有代码在 `get_db`（autoflush=False/autocommit=False）下直接 `with db.begin()`；新增管理端代码应沿用同一模式，避免嵌套事务异常。
10. **CORS/CSRF**：所有 POST 认证接口依赖 `require_auth_request`（Origin 白名单 + `X-CSRF-Protection: 1`）。管理端新增 POST 也必须加该依赖，否则会被 403 或出现 CSRF 缺口。

---

## 14. 现有测试与验证结果

### 14.1 测试文件与规模（实测统计）

| 文件 | 用例数 | 覆盖 |
| --- | --- | --- |
| `test_auth_a1_1_acceptance.py` | 124 | 认证基础、配置、JWT、限流、Cookie、CSRF |
| `test_auth_a1_3_acceptance.py` | 98 | 注册/登录/刷新/登出/活跃/业务回归 |
| `test_auth_a2_account_session_acceptance.py` | 83 | 密码重置、改密、换绑、设备撤销、并发 |
| `test_auth_a2_3_avatar_profile_cleanup_acceptance.py` | 103 | 头像、资料、清理、验证码边界、Worker |
| `test_lifecycle_regression.py` | 17 | 计划到期/生命周期 |
| `test_progress_regression.py` | 17 | 进度/统计 |
| `test_rollover_regression.py` | 4 | 任务顺延 |
| `test_ai_a3_structure.py` | 11 | 笔记生成/整理/总结 + Guard 状态 |
| `test_ai_a4_qa.py` | 21 | 问答 + Guard 取消/STALE/回滚 |
| `test_ai_a5_generate.py` | 12 | 出题解析/票据 |
| `test_ai_a5_grade.py` | 11 | 批改 |
| `test_knowledge_ai.py` | 10 | SSE/Provider/总结 |

### 14.2 本轮 A0 实际执行结果（2026-11-26，测试库 `ssp_a0_migrate2`）

| 套件 | 结果 | 说明 |
| --- | --- | --- |
| AI 5 个套件（a3+a4+a5 generate+a5 grade+knowledge_ai） | **59 通过 / 6 失败**（共 65） | 6 项失败全部在 `test_ai_a5_generate.py`：`test_parse_five_questions`、`test_supported_question_counts[5/10/15]`、`test_public_questions_hide_answers`、`test_stream_does_not_expose_model_delta`（`StopIteration`） |
| `test_auth_a2_3_avatar_profile_cleanup_acceptance.py` | **101 通过 / 2 跳过 / 0 失败**（共 103） | 跳过项为 Windows 无符号链接权限（WinError 1314），与本轮结论无关 |

**6 项失败根因（已定位，非产品回归）**：
`tests/test_ai_a5_generate.py:16-45` 的 `make_paper()` 生成 5 道题干，仅下标数字不同（“知识点0…”“知识点1…”“知识点2…”）。产品在 `app/services/knowledge/ai_practice_service.py:136-153` 新增了题干相似度去重（归一化后 `SequenceMatcher.ratio() >= 0.92` 即拒绝），这些高度相似的测试题干被判定为重复，抛出 `DUPLICATE_PRACTICE_QUESTIONS`。
→ 结论：**测试夹具过时**，需把夹具题干改为语义不同的文本；**不影响线上出题逻辑**（真实模型被要求生成互不相同的题目）。该问题应记录为“待修测试”，而不是产品缺陷。

### 14.3 历史执行结果（非本轮，需注意时效）

| 套件 | 历史结果 | 来源/备注 |
| --- | --- | --- |
| A1.3 认证 | 97 通过 / 1 失败（98） | 上个窗口执行；1 项旧用例与 `/auth/logout-all` 新规格冲突 |
| A2 账号会话 | 83 / 83 通过 | 上个窗口执行 |
| A2.3 头像清理 | 修复 P0 后 101 通过 / 0 失败 / 2 跳过 | 与本轮 A0 实测一致 |
| lifecycle 回归 | 曾因 P0-1（worker 导入不存在模块）模块导入失败；已修复，本轮未复跑 | `Auth_V2_A2_Final_Test_Report.md` 仍为修复前数字，**该报告文件未同步更新** |
| progress / rollover 回归 | 历史执行因夹具缺 `users.password_updated_at` 报 MySQL 1364，未得到干净结果 | 本轮未复跑 |

### 14.4 覆盖缺口（V3.0 关注）

| 主题 | 是否有测试 | 结论 |
| --- | --- | --- |
| JWT 认证 / payload / 过期 / 签名 | 有 | A1.3 `TestSessionAndAccess` |
| 即时会话撤销 | 有 | A1.3 `test_revoked_session_access_fails`、A2 |
| Refresh 轮换 / 重放 | 有 | A1.3 `TestRefreshToken`（含并发单次成功） |
| 并发登录 / 并发刷新 | 有 | `test_concurrent_refresh_single_success`、`test_register_concurrent_same_username_only_one` |
| 邮箱验证码 | 有 | A1.3 `TestEmailCodeLogin`、A2.3 |
| 密码重置 | 有 | A2 套件（reset 多场景） |
| AI Guard 准入落库/回滚 | 有 | a4 `test_ask_admission_persists_operation`、`..._failure_rolls_back` |
| AI Guard 超时/取消/STALE | 有 | a3 `test_guard_timeout`、a4 `test_guard_cancel_closes_upstream_and_settles`、`test_guard_maps_stale_status` |
| **AI 日额度/并发上限（429）** | **无** | 全仓库仅断言配置项存在（A1.1 L276-277），**没有触发额度耗尽/并发占满的用例** |
| **AI 多进程/多实例准入竞争** | **无** | 无并发准入测试 |
| **AI 请求频率限制** | **无（功能本身不存在）** | — |
| 事务回滚 | 部分 | A1.3 `test_rotation_rollback_leaves_old_token_active`、lifecycle `test_L15_failure_rolls_back_task_updates`、a4 admission 回滚 |
| 管理员/封禁/审计 | **无（功能不存在）** | — |

---

## 15. 一天开发目标的工程量评估

### 15.1 结论

**在“不引入 Redis、不做正式库迁移、管理端只做后端 API”的前提下，一天可以完成“可演示的最小管理员系统”；若要求包含审计、AI 动态配置、Dashboard、完整测试与正式库上线，则一天不可行（约 1.5～2 人日）。**

### 15.2 拆分（按改动点，而非时长承诺）

| 工作项 | 复用基础 | 新增/修改量 | 一天内可行性 |
| --- | --- | --- | --- |
| users.role + `require_admin` | `get_current_user` | 1 列 + 1 依赖 + 1 查询 | 可行（最先做） |
| 用户分页查询 | 仓储模式 | 2 条 SQL + schema + 路由 | 可行 |
| 封禁/解封 | `is_active` + `revoke_user_sessions` | 1 个事务服务 + 2 个接口 | 可行（核心） |
| 强制下线 | `revoke_user_sessions` | 1 个接口 | 可行（几乎零成本） |
| 操作审计 | `auth_events` 结构不足 | 新表 + 写入封装 + 查询接口 | 可行但需裁剪字段 |
| Dashboard | 参考 statistics | 3～5 条聚合 SQL | 可裁剪（可先只做 4 个数字） |
| AI 用量统计 | `ai_requests` | 4 条聚合 SQL | 可行 |
| AI 动态配置 | 无 | 新表 + Guard 读配置改造 + 缓存一致性 | **高风险，建议延期** |
| Redis 资源治理 | 无 | 依赖/部署/Lua/回填/监控 | **一天内不可行，建议 DEFER** |
| 测试 | 现有测试基建 | 管理员接口测试 + 封禁并发测试 | 需 0.5 人日 |

### 15.3 最大阻塞项（不是写代码）

1. **正式库 Auth V2 迁移未完成**：代码在 `smart_study_planner` 上跑不起来。若一天内要“上线”，必须把迁移 + 数据搬迁 + 回滚方案算进去。
2. **无迁移框架**：所有 DDL 手工执行，缺少版本记录与回滚脚本。
3. **AI Guard 额度/并发无测试**：V3.0 做 AI 配置/统计前，最好先补 429 与并发用例，否则动态配置上线风险高。
4. **`ai_requests` 无清理策略**：数据量增长后统计与索引会退化。

### 15.4 建议的一天范围（若必须一天交付）

- 做：`role` + `require_admin`、用户分页、封禁/解封、强制下线、审计（新表，最小字段）、AI 统计 4 项（今日额度/7 日趋势/状态分布/功能分布）。
- 不做：Redis、AI 动态配置、复杂 Dashboard、用户排行/Token 成本、正式库迁移（另立窗口）。
- 测试：至少覆盖「封禁后旧 Token 立即 403」「封禁与刷新并发仅一个结果」「强制下线后刷新失败」。

---

## 16. 需要开发者进一步决定的问题

1. **Redis 是否本期引入？** 现有 MySQL Guard 在单库多 Worker 下是正确的；Redis 的收益主要在“多实例 + 高并发”。若服务器只有 1 个后端实例，建议 DEFER。
2. **正式库迁移何时做？** `smart_study_planner` 仍是旧结构，V3.0 管理端无法在其上运行。是否需要先完成 Auth V2 数据迁移（含 `tb_refresh_token` 处理策略：迁移还是全部作废）？
3. **角色模型选型**：`users.role ENUM('USER','ADMIN')` 够用，还是需要多角色/权限点（RBAC）？前者一天可完成，后者需要 3 张表。
4. **审计存储**：新建 `admin_audit_logs`（推荐，长期保留）还是扩展 `auth_events`（会被 30 天清理，且缺 operator 字段）？
5. **AI 动态配置是否必须运行期生效？** 若必须，需确定「DB 配置 → Guard 读取」的缓存策略（每请求查 DB / TTL 缓存 / 配置变更广播），并补额度与并发测试。
6. **封禁语义**：永久封禁还是支持临时封禁（`banned_until`）？是否需要封禁原因、解封审批？
7. **管理员能否查看用户业务数据**（计划/笔记/练习）？涉及隐私与接口边界，需明确只读范围。
8. **部署形态**：是否计划多 Worker / 多实例？服务器内存与是否允许部署 Redis？当前仓库无部署配置，**未知**。
9. **一天目标是否包含前端管理页**？本报告仅评估后端；前端工作量未计入。
10. **测试口径**：`test_ai_a5_generate.py` 的 6 项夹具冲突是否允许本轮顺手修复（只改测试，不改业务）？若允许，可在 A0 后单独执行。

---

## 附录 A：关键函数索引（供后续 GPT 分析）

| 函数 | 文件:行 |
| --- | --- |
| `get_current_user` | `app/core/deps.py:62-74` |
| `authenticate_access` | `app/core/deps.py:19-59` |
| `_create_token` / `create_access_token` / `create_refresh_token` | `app/core/security.py:136-205` |
| `decode_access_token_detailed` | `app/core/security.py:256-271` |
| `create_session` | `app/services/auth/session_service.py:75-105` |
| `get_active_session` | `app/services/auth/session_service.py:108-134` |
| `require_active_session` | `app/services/auth/session_service.py:38-72` |
| `revoke_session` | `app/services/auth/session_service.py:137-164` |
| `revoke_user_sessions` | `app/services/auth/session_service.py:218-248` |
| `lock_current_user` | `app/services/auth/session_service.py:171-215` |
| `revoke_session`（SQL） | `app/repositories/auth/session_repository.py:179-205` |
| `revoke_all_sessions`（SQL） | `app/repositories/auth/session_repository.py:208-237` |
| `find_by_id(for_update)` | `app/repositories/auth/user_repository.py:7-30` |
| `login_with_password` | `app/services/auth/auth_service.py:381-476` |
| `login_with_email` | `app/services/auth/auth_service.py:482-542` |
| `rotate_refresh_token` | `app/services/auth/auth_service.py:548-698` |
| `revoke_current_session` | `app/services/auth/auth_service.py:702-815` |
| `reset_password` | `app/services/auth/account_service.py:110-206` |
| `change_password` | `app/services/auth/account_service.py:212-283` |
| `revoke_sessions`（其他/全部设备） | `app/services/auth/account_service.py:575-638` |
| `admit_request` | `app/services/knowledge/ai_guard_service.py:42-147` |
| `_finish_request_record` | `app/services/knowledge/ai_guard_service.py:150-187` |
| `metered_ai_stream` | `app/services/knowledge/ai_guard_service.py:204-356` |
| `lock_admission` | `app/repositories/knowledge/ai_guard_repository.py:8-25` |
| `daily_counts` | `app/repositories/knowledge/ai_guard_repository.py:28-55` |
| `active_counts` | `app/repositories/knowledge/ai_guard_repository.py:58-82` |
| `insert_request` | `app/repositories/knowledge/ai_guard_repository.py:86-127` |
| `finish_request` | `app/repositories/knowledge/ai_guard_repository.py:130-153` |
| `stream_completion`（DeepSeek） | `app/services/knowledge/ai_provider.py:29-203` |
| `stream_checked_completion` | `app/services/knowledge/ai_service.py:68-124` |
| `admission_session`（MySQL 命名锁） | `app/services/auth/rate_limit_service.py:84-153` |
| `business_today` | `app/core/clock.py:8-10` |
| `parse_practice_questions`（去重规则） | `app/services/knowledge/ai_practice_service.py:103-167` |

---

## 附录 B：无法验证 / 未知项清单

| 项 | 状态 | 原因 |
| --- | --- | --- |
| 正式服务器部署方式与实例数 | **未知** | 仓库无 Docker/编排/systemd/进程管理配置 |
| 服务器内存、Redis 内存预算 | **未知** | 无监控/部署清单 |
| 历史测试的完整通过记录 | 部分可查 | `Auth_V2_A2_Final_Test_Report.md` 为修复前数字，未同步更新 |
| 正式库数据迁移是否已演练成功 | **未知** | `ssp_a0_migrate2` 为空库，无搬迁脚本 |
| `ai_requests` 在正式库的真实数据量 | **未知** | 正式库 `ai_requests` 17 行（旧结构无 `login_sessions`），当前代码不读该库 |
| 前端管理端是否存在 | **未知** | 本阶段仅盘点后端目录 |
| Redis 是否在其他机器/容器中存在 | **未知** | 仅检查本机 127.0.0.1:6379 |

---

**报告结束。本阶段未修改任何业务代码、未执行数据库迁移、未安装依赖。等待开发者与 GPT 审查后再进入下一阶段。**