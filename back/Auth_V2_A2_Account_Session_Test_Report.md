# Auth V2.0 — A2.1 / A2.2 账号与会话集中验收报告

| 项 | 值 |
|---|---|
| 验收日期 | 2026-11-26 |
| 验收范围 | A2.1/A2.2：密码重置、主动改密、邮箱换绑、登录会话查询、指定会话撤销、退出其他/全部设备 |
| 验收方式 | 自动化测试（unittest + 真实 MySQL + 多线程独立连接）+ 只读源码审查 |
| 业务行为是否被改变 | **否**（仅修复工作区中 `app/config.py` 结构性放错，见第一节） |
| 数据库结构是否修改 | **否** |
| 是否实际发送邮件 | **否**（全部 Mock） |
| 测试数据库 | **`ssp_a0_migrate2`**（隔离库，已 `SELECT DATABASE()` 确认） |
| 正式库 `smart_study_planner` | **未访问、未修改** |
| 测试文件 | `tests/test_auth_a2_account_session_acceptance.py`（83 用例） |
| 最终结果 | **83 / 83 通过，0 失败，0 错误，0 跳过** |

---

## 一、数据库及测试环境

| 项 | 值 |
|---|---|
| OS | Windows（PowerShell 5） |
| Python | 3.14（venv `.venv`） |
| 框架 | FastAPI 0.143 / Starlette 1.8 / SQLAlchemy 2.1 |
| MySQL | 8.4.9（`C:\Program Files\MySQL\MySQL Server 8.4`） |
| 实际连接数据库 | **`ssp_a0_migrate2`**（`SELECT DATABASE()` 确认） |
| 连接时区 | `SET time_zone='+08:00'`（业务时区），认证时间字段为 UTC naive |
| 邮件 | `mail_service` 全部 Mock，未真实外发 |
| HTTP 客户端 | `TestClient(app, base_url="https://ssp.test", client=("127.0.0.1", 51888), raise_server_exceptions=False)` |
| CSRF | 请求头 `Origin: http://localhost:3000` + `X-CSRF-Protection: 1` |
| 并发测试 | 多线程 + `threading.Barrier` + 各自独立 `SessionLocal()` 连接，真实并发访问数据库 |

**环境修复说明（非 A2 范围）**：本轮发现 `app/config.py` 中头像配置块被放在 `settings = Settings()` 之后（模块级），导致 `settings.AVATAR_DIR` 缺失、应用无法导入。已做最小结构性修复：将 `AVATAR_MAX_BYTES / AVATAR_MAX_SIZE / AVATAR_MAX_PIXELS / AVATAR_DIR` 移入 `Settings` 类内并删除末尾重复模块级块。**未改变任何默认值或业务行为**，所有调用方均使用 `settings.AVATAR_*`，不受影响。

---

## 二、A1.1–A1.3 现有验收状态

| 阶段 | 测试数 | 通过 | 失败 | 跳过 | 状态 |
|---|---|---|---|---|---|
| A1.1 认证基础设施 | 124 | 116 | 3 | 5 | 已验收；原 P1（verify_password 类型保护）、P2（配置边界）本轮已修复 |
| A1.2 Brevo 真实邮件 | — | — | — | — | 已验收（2 封真实邮件用户确认收到）；本轮不涉及 |
| A1.3 注册/登录/刷新/退出集中验收 | 98 | 97 | 1 | 0 | 已验收；原 P1（4xx 统一响应）本轮已修复 |

**A1.3 行为说明**：本轮 `auth.py` 的 `logout` 增加了 Cookie/Bearer 一致性校验——当两者归属不同会话时返回 `409 SESSION_MISMATCH` 且不撤销任何会话（此前为仅依据 Cookie 撤销）。该增强已在 T7 覆盖，属向后兼容的安全强化。

---

## 三、本轮测试总数及通过 / 失败 / 跳过

| 类别 | 数量 |
|---|---|
| **总数** | **83** |
| **通过 (PASS)** | **83** |
| **失败 (FAIL)** | **0** |
| **跳过 (SKIP)** | **0** |

分模块：

| 模块 | 测试数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|
| T0 合约检查 | 6 | 6 | 0 | 0 |
| T1 忘记密码 | 15 | 15 | 0 | 0 |
| T2 主动改密 | 11 | 11 | 0 | 0 |
| T3 邮箱换绑 | 14 | 14 | 0 | 0 |
| T4 会话查询 | 9 | 9 | 0 | 0 |
| T5 指定会话撤销 | 8 | 8 | 0 | 0 |
| T6 退出其他/全部设备 | 8 | 8 | 0 | 0 |
| T7 并发与安全审查 | 12 | 12 | 0 | 0 |
| **合计** | **83** | **83** | **0** | **0** |

---

## 四、每个测试项的执行结果（全部 PASS）

### T0 合约检查（6）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_eight_new_routes_registered` | PASS | 8 个新增路由均已注册 |
| `test_existing_routes_not_broken` | PASS | 注册/登录/刷新/退出未被覆盖 |
| `test_repository_capabilities_exist` | PASS | 仓储能力齐全 |
| `test_account_service_functions_exist` | PASS | account_service 函数齐全 |
| `test_session_service_api_complete` | PASS | session_service 4 个函数齐全 |
| `test_all_new_routes_do_not_500` | PASS | 8 路由均无 5xx |

### T1 忘记密码（15）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_reset_success` | PASS | RESET 码重置成功 |
| `test_reset_updates_hash_and_time` | PASS | password_hash 与 password_updated_at 更新 |
| `test_old_password_invalid_new_password_valid` | PASS | 旧密码失效、新密码可登录 |
| `test_reset_revokes_all_sessions_and_tokens` | PASS | 旧 Session + Refresh Token 全撤销 |
| `test_old_access_fails_after_reset` | PASS | 旧 Access Token 下次认证失败 |
| `test_reset_consumes_code_once` | PASS | 验证码仅消费一次 |
| `test_reset_does_not_create_session` | PASS | 不自动创建登录会话 |
| `test_reset_nonexistent_email_rejected` | PASS | 不存在邮箱 400 |
| `test_reset_disabled_account_rejected` | PASS | 禁用账号 400 |
| `test_reset_rejects_login_purpose_code` | PASS | LOGIN/REGISTER 码不可用于重置 |
| `test_reset_wrong_code_attempts_persisted` | PASS | 错误次数持久化 |
| `test_reset_weak_password_rejected` | PASS | 弱密码拒绝 |
| `test_reset_rollback_on_failure` | PASS | 事务失败时密码/会话/验证码全回滚 |
| `test_reset_does_not_clear_other_account_cookie` | PASS | 不误清其他账号 Cookie |
| `test_reset_concurrent_consume_once` | PASS | 并发重置最多一次消费同一验证码 |

### T2 主动改密（11）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_change_with_correct_old_password` | PASS | 正确旧密码可改 |
| `test_change_with_wrong_old_password` | PASS | 错误旧密码返回 `INVALID_PASSWORD` |
| `test_change_wrong_password_records_failure` | PASS | 错误次数持久化 |
| `test_change_shares_failure_counter_with_login` | PASS | 与登录共享账号失败计数 |
| `test_change_keeps_current_session` | PASS | 当前会话保留 |
| `test_change_tokens_still_valid` | PASS | 当前 Access/Refresh 继续有效 |
| `test_change_revokes_other_sessions` | PASS | 其他会话与 Token 撤销 |
| `test_change_requires_active_session` | PASS | 会话失效后拒绝（401） |
| `test_change_disabled_user_denied` | PASS | 禁用用户拒绝（403） |
| `test_change_rechecks_session_after_auth` | PASS | 认证后、事务前撤销会话 → 敏感操作失败 |
| `test_change_does_not_leave_partial_state` | PASS | 异常时无部分修改 |

### T3 邮箱换绑（14）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_change_email_success` | PASS | 密码 + 双验证码正确时换绑成功 |
| `test_change_email_updates_verified_at` | PASS | email 与 email_verified_at 更新 |
| `test_change_email_keeps_current_session_and_revokes_others` | PASS | 保留当前、撤销其他会话 |
| `test_old_email_login_fails_new_email_works` | PASS | 原邮箱失效、新邮箱可登录 |
| `test_new_email_equals_old_rejected` | PASS | 新旧邮箱相同拒绝 |
| `test_new_email_taken_rejected` | PASS | 已占用邮箱拒绝 |
| `test_code_bound_to_other_user_rejected` | PASS | 他人/他会话验证码拒绝 |
| `test_purposes_cannot_be_mixed` | PASS | 两种换绑用途不可混用 |
| `test_wrong_old_code_records_attempts` | PASS | 旧码错误记录次数 |
| `test_wrong_new_code_keeps_old_code_unconsumed` | PASS | 新码错误时不消费旧码 |
| `test_both_codes_in_same_transaction` | PASS | 双码与邮箱更新同事务，失败整体回滚 |
| `test_concurrent_same_new_email_only_one` | PASS | 两用户竞争同一新邮箱仅一个成功 |
| `test_unique_conflict_maps_409` | PASS | 唯一约束冲突 → 409 |
| `test_old_email_code_cannot_bypass_binding` | PASS | 原邮箱验证码无法绕过绑定检查 |

### T4 会话查询（9）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_list_sessions` | PASS | 仅返回当前用户有效会话 |
| `test_list_excludes_revoked_and_expired` | PASS | 排除撤销/空闲过期/绝对过期 |
| `test_total_matches_page` | PASS | 总数与分页一致 |
| `test_current_flag` | PASS | `is_current` 正确 |
| `test_no_sensitive_fields` | PASS | 不返回敏感字段 |
| `test_current_session_probe` | PASS | 当前会话探针正确 |
| `test_probe_does_not_touch_activity` | PASS | 探针不更新 last_activity_at |
| `test_page_boundaries` | PASS | page/page_size 边界 422 |
| `test_invalid_session_cannot_list` | PASS | 无效会话 401 |

### T5 指定会话撤销（8）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_revoke_other_session` | PASS | 重新验证密码后可撤销 |
| `test_wrong_password_revokes_nothing` | PASS | 密码错误不撤销任何会话 |
| `test_cannot_revoke_other_users_session` | PASS | 不能撤销他人会话 |
| `test_target_old_access_fails` | PASS | 目标旧 Access 立即失效 |
| `test_other_sessions_unaffected` | PASS | 其他会话不受影响 |
| `test_already_revoked_target_business_error` | PASS | 已撤销/过期返回合理业务错误（404），不误判当前会话 |
| `test_cannot_revoke_current_session` | PASS | 指定当前会话拒绝（400） |
| `test_concurrent_revoke_and_refresh` | PASS | 撤销与刷新并发后最终一致（会话已撤销、无残留 Token） |

### T6 退出其他/全部设备（8）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_revoke_others_keep_current` | PASS | `keep_current=True` 保留当前 |
| `test_revoke_others_wrong_password` | PASS | 错误密码拒绝 |
| `test_logout_all_revokes_everything` | PASS | `keep_current=False` 撤销全部 |
| `test_revoked_count_matches_db` | PASS | `revoked_count` 与实际一致 |
| `test_cannot_touch_other_user` | PASS | 不能撤销他人数据 |
| `test_logout_all_requires_password` | PASS | 缺密码 422 |
| `test_old_passwordless_logout_all_gone` | PASS | 旧免密 logout-all 不可用 |
| `test_atomicity` | PASS | 全部撤销事务原子性（异常回滚） |

### T7 并发与安全审查（12）

| 用例 | 结果 | 验证点 |
|---|---|---|
| `test_lock_order_reserve_before_row_lock` | PASS | IP 准入命名锁在用户行锁之前获取 |
| `test_reset_reserve_before_transaction` | PASS | 准入限制早于业务事务 |
| `test_error_codes_distinguish_causes` | PASS | `SESSION_REVOKED` 与 `INVALID_CREDENTIALS` 可区分 |
| `test_logout_missing_cookie` | PASS | Cookie 缺失正确清理并返回 |
| `test_logout_invalid_cookie` | PASS | Cookie 无效不误撤销 |
| `test_logout_cookie_mismatch_with_bearer` | PASS | Cookie/Bearer 不匹配 → 409 `SESSION_MISMATCH`，不撤销 |
| `test_concurrent_password_change_same_user` | PASS | 双设备并发改密仅一次成功，最终密码=成功方 |
| `test_concurrent_reset_and_login` | PASS | 重置与密码登录并发后旧密码失效、新密码可用 |
| `test_concurrent_email_change_and_code_login` | PASS | 换绑与邮箱验证码登录并发后仅保留当前会话，新邮箱可登录、旧邮箱失效 |
| `test_concurrent_email_change_and_resend` | PASS | 换绑与验证码重发并发后邮箱不出现半更新 |
| `test_concurrent_failure_counter` | PASS | 并发错误计数无丢失（3 次=3 条事件） |
| `test_multi_user_same_new_email_race` | PASS | 多用户争用同一新邮箱仅一个成功 |

---

## 五、缺陷与风险分类

### 已解决（本轮复验确认）

| 编号 | 原缺陷 | 状态 |
|---|---|---|
| P0-1 | `session_service` 缺 4 个函数导致 8 路由 500 | **已修复**（4 函数已实现并回归通过） |
| P1-1 | 4xx 未输出统一 `{code,message,data}` | **已修复**（`main.py` 统一处理器输出顶层 `code/message/data`） |
| P1-2 | `verify_password` 对非字符串抛 `AttributeError` | **已修复**（增加 `isinstance` 保护返回 `False`） |
| P2-1 | `AUTH_ALLOWED_ORIGINS` 缺 `127.0.0.1:3000` | **已修复** |
| P2-2 | 配置数值字段缺 `gt=0` | **已修复**（改为 `Field(..., gt=0)`） |

### 仍存在（需整改 / 建议）

| 编号 | 级别 | 缺陷/风险 | 说明 |
|---|---|---|---|
| **P1-3** | P1（安全整改） | 主动改密成功后，**未作废此前签发但未消费的 `RESET_PASSWORD` 验证码** | 若攻击者已在改密前获得该类验证码，可在其有效期（默认 300 秒）内继续重置密码，削弱“改密即切断旧凭证”的语义。`change_password` 未调用任何验证码作废逻辑。 |
| **P2-3** | P2（记录） | `revoke_other_session` 对“目标=当前会话”的拒绝发生在密码校验之前 | 无状态变更，风险低，仅记录。 |

---

## 六、缺陷文件、行号与复现方法

### P0-1（已修复，留档）

- 修复文件：[session_service.py](file:///d:/project/back/app/services/auth/session_service.py) 已补齐 `lock_current_user`、`revoke_user_sessions`、`list_sessions`、`get_current_session`（`revoke_user_sessions` 同时撤销 Session 与 Refresh Token）。
- 回归：T0 `test_session_service_api_complete`、`test_all_new_routes_do_not_500` 通过。

### P1-3（仍存在）

- [account_service.py](file:///d:/project/back/app/services/auth/account_service.py) `change_password` 成功分支仅执行 `update_password` + 撤销会话 + 清失败计数 + 记录事件，**未作废 `RESET_PASSWORD` 验证码**；`verification_service` / `verification_repository` 亦无“按用户批量作废指定用途验证码”的接口（现有 `invalidate_previous` 仅按 email+purpose）。
- 复现：
  1. 为用户签发一枚 `RESET_PASSWORD` 验证码（不消费）；
  2. 用户主动改密成功；
  3. 在验证码有效期（默认 300 秒）内用该旧码调用 `POST /auth/password/reset`，仍会被接受。

### P2-3

- [account_service.py](file:///d:/project/back/app/services/auth/account_service.py) `revoke_other_session` 中“目标=当前会话”判断先于密码校验；无写入，风险低。

### 环境修复（非 A2）

- `app/config.py`：头像字段原位于 `settings = Settings()` 之后（模块级），已移入 `Settings` 类内并删除重复块；不改变默认值与行为。

---

## 七、最小修复建议（P1-3）

> 仅建议，按约束不改动业务源码。

- 在 `change_password` 成功分支内（同一事务、持有用户行锁期间）作废该用户遗留的 `RESET_PASSWORD` 验证码，例如新增 `verification_repository.invalidate_user_purpose(db, user_id=..., purpose="RESET_PASSWORD", now=...)`，或复用 `invalidate_previous(db, email=user["email"], purpose="RESET_PASSWORD", now=now)`。
- 建议同步评估 `reset_password` 成功后是否作废同用途历史未消费验证码，保持“一次性凭证”语义一致。

---

## 八、测试数据清理情况

清理策略：`tearDownClass` 按 `PREFIX="a13..."` 精确删除 users / email_verifications / auth_events / login_sessions / refresh_tokens，并删除测试时间窗内的匿名 IP 事件；不触碰其他数据。

清理后核验（`ssp_a0_migrate2`）：

| 校验项 | 结果 |
|---|---|
| `SELECT DATABASE()` | `ssp_a0_migrate2` ✅ |
| `users` `a13%` 残留 | 0 ✅ |
| `email_verifications` `a13%` 残留 | 0 ✅ |
| `auth_events` 关联 `a13%` 用户残留 | 0 ✅ |
| 孤立 `login_sessions` | 0 ✅ |
| 孤立 `refresh_tokens`（user/session） | 0 ✅ |

结论：测试数据已精确清理，无残留、无孤立记录、未影响正式库。

---

## 九、是否满足 A2.1 / A2.2 结项条件

| 维度 | 结论 |
|---|---|
| 新增路由注册与契约 | 满足（8 路由、4 缺失函数已补齐） |
| 既有登录/注册/刷新/退出未被破坏 | 满足 |
| 忘记密码 / 主动改密 / 邮箱换绑 | 满足（含事务回滚、并发一致性） |
| 会话查询 / 指定撤销 / 退出其他与全部设备 | 满足 |
| 依赖层与业务层安全校验 | 满足 |
| 并发与安全审查（行锁串行化、事务一致性、验证码消费、唯一冲突、死锁/范围锁） | 满足（T7 12 项真实并发执行通过） |
| 遗留安全风险 P1-3 | **未整改**（建议结项前处理或明确风险接受） |
| 测试数据清理 | 满足（残留 0） |

**结项结论：A2.1 / A2.2 自动化验收 83/83 全部通过，功能层面满足结项条件。**

唯一遗留为 **P1-3**（改密后未作废遗留密码重置验证码）的安全整改项。建议在最终结项前完成 P1-3 修复并补一条回归用例；若以风险接受方式结项，需在结项记录中明确该残余风险。

---

*本报告仅陈述实测与只读审查结果；未执行项为 0。测试全程运行于隔离库 `ssp_a0_migrate2`，邮件全部 Mock，未输出任何真实密钥、密码、验证码或 Token。*