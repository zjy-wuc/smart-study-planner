# Auth V2.0 A1.3 集中验收测试报告

| 项 | 值 |
|---|---|
| 验收日期 | 2026-11-26 |
| 验收范围 | A1.3 核心认证闭环（Session / 双 Token / 轮换与重放 / Cookie / CSRF / get_current_user / 注册 / 两种登录 / 退出 / 活跃时间 / 原业务回归） |
| 实际数据库 | `ssp_a0_migrate2`（每个测试类启动前执行 `SELECT DATABASE()` 校验，非该库直接中止） |
| 正式库 `smart_study_planner` | 未访问、未修改 |
| 业务源码 | 未修改（仅新增 1 个测试文件） |
| 邮件发送 | 全部 Mock，实际发送 0 封 |
| 密钥/Token/密码/验证码 | 未输出、未记录 |

---

## 一、测试总数与结果

### 1.1 A1.3 本轮结果

| 指标 | 数值 |
|---|---|
| 测试总数 | **98** |
| 通过 | **97** |
| 失败 | **1**（P1-1，统一响应结构缺陷，见第四节） |
| 跳过 | **0**（3 个"仅代码审查未执行"项在第六节单独列出，未计入通过） |

测试文件：`tests/test_auth_a1_3_acceptance.py`
执行命令：`d:\project\back\.venv\Scripts\python.exe -m unittest tests.test_auth_a1_3_acceptance`

### 1.2 分阶段结果

| 阶段 | 测试数 | 通过 | 失败 | 跳过 | 说明 |
|---|---|---|---|---|---|
| A1.1 认证基础设施 | 124 | 116 | 3 | 5 | 历史轮次执行结果（`Auth_V2_A1.1_Test_Report.md`），3 个 P1/P2 至今未修复，本轮复核仍存在（见 4.2） |
| A1.2 验证码邮件服务 | 12 | 12 | 0 | 0 | 历史轮次执行结果（`Auth_V2_Brevo_Test_Report_V2.md`），本轮未重复执行真实发信 |
| A1.3 核心认证闭环 | 98 | 97 | 1 | 0 | **本轮实际执行** |

---

## 二、逐项实际执行结果（A1.3）

### 第 3 节 模块导入与接口检查（7 项，6 通过 / 1 失败）

| 测试项 | 结果 |
|---|---|
| 20 个认证相关模块全部可导入 | 通过 |
| FastAPI app 构建成功，`/health` `/users` `/auth/login` `/auth/refresh` 均注册 | 通过 |
| 无 `logout-all` 路由；`/users` 无 GET 方法 | 通过 |
| `revoke_all_sessions` / `revoke_all_tokens` 仓库能力存在（A2 使用，当前无路由引用） | 通过 |
| 新代码无 `issue_token_pair` / `RefreshRequest` 运行时引用 | 通过 |
| `session_service` / `verification_service` 关键函数可调用且签名与调用方一致 | 通过 |
| **HTTPException 4xx 统一响应结构契约** | **失败（P1-1）** |

实际响应证据（`GET /users/me` 无 Token）：

```json
{"detail": {"code": "INVALID_TOKEN", "message": "缺少 Access Token"}}
```

缺少顶层 `code` / `message` / `data` 字段。

### 第 4 节 注册（13 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 正确验证码注册 201，返回 Access Token + Set-Cookie | 通过 |
| 仅创建 1 用户 / 1 Session / 1 Refresh Token | 通过 |
| 省略昵称时默认等于用户名 | 通过 |
| JSON 响应不含 refresh_token | 通过 |
| 错误验证码返回 400，`attempts` 持久化为 1 | 通过 |
| 已消费 / 已作废 / 已过期 / 其他用途验证码均被拒绝 | 通过 |
| 重复用户名 409、重复邮箱 409 | 通过 |
| 注册失败（用户名冲突）不消费验证码（`consumed_at`、`invalidated_at` 均 NULL） | 通过 |
| 弱密码（`12345678`）400 拒绝 | 通过 |
| 过短密码（`Ab1!`）422 schema 拒绝 | 通过 |
| 并发同用户名注册，仅 1 个成功 | 通过 |

### 第 5 节 密码登录（11 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 用户名 + 密码登录成功 | 通过 |
| 邮箱 + 密码登录成功 | 通过 |
| 用户名/邮箱共享失败计数（各失败 2 次 → PASSWORD_FAILED = 4） | 通过 |
| 连续 5 次失败锁定，第 6 次正确密码仍返回 429 | 通过 |
| 锁定事件 `PASSWORD_LOCKED` 仅 1 条 | 通过 |
| 锁定期内再次尝试不延长锁定期限（created_at 不变） | 通过 |
| 锁定期结束后正常恢复登录 | 通过 |
| 成功登录写入 `PASSWORD_CLEAR`，失败计数重置 | 通过 |
| 禁用账号正确密码登录返回 403 `ACCOUNT_DISABLED` | 通过 |
| 不存在账号返回 401 `INVALID_CREDENTIALS` | 通过 |
| IP 限流持久化（超限 429） | 通过 |
| IP 限流并发 8 线程 / 上限 3，恰好 3 次通过，未绕过 | 通过 |

### 第 6 节 邮箱验证码登录（7 项，全部通过）

| 测试项 | 结果 |
|---|---|
| LOGIN 验证码登录成功并消费验证码 | 通过 |
| REGISTER 验证码不能用于登录 | 通过 |
| RESET_PASSWORD 验证码不能用于登录 | 通过 |
| 不存在邮箱不自动注册（用户总数不变） | 通过 |
| 禁用账号不可用验证码登录 | 通过 |
| 错误验证码 `attempts` 递增持久化 | 通过 |
| 4 线程并发使用同一验证码，仅 1 个成功 | 通过 |

### 第 7 节 Session 与 Access Token（17 项，全部通过）

| 测试项 | 结果 |
|---|---|
| Access / Refresh 均含 `sub` `family_id` `iat` `exp` `type` `jti` | 通过 |
| 同会话 Access 与 Refresh 的 `family_id` 一致、`jti` 不同 | 通过 |
| 不同登录生成不同 `family_id` | 通过 |
| Refresh 不能作为 Access 使用（`TOKEN_TYPE_INVALID`） | 通过 |
| Access 不能作为 Refresh 使用 | 通过 |
| 缺少 `family_id` 的旧 JWT 被拒绝 | 通过 |
| 非法 UUID、非法用户 ID、超出 BIGINT UNSIGNED 的 sub 被拒绝且无 500 | 通过 |
| 签名错误被拒绝 | 通过 |
| 过期 Access 返回 `ACCESS_EXPIRED` | 通过 |
| 禁用用户 Access 访问 403 | 通过 |
| Session 撤销后旧 Access 下一次认证 401 | 通过 |
| 空闲 7 天失效（401） | 通过 |
| 绝对 30 天失效（401） | 通过 |
| 绝对期限边界：未来 60 秒允许、已过期 1 毫秒拒绝 | 通过 |
| Token 有效期不超过 Session 绝对截止时间 | 通过 |
| Access 默认有效期 15 分钟（exp - iat = 900） | 通过 |
| Refresh 默认有效期 7 天（exp - iat = 604800） | 通过 |

### 第 8 节 Refresh Token（8 项，全部通过）

| 测试项 | 结果 |
|---|---|
| Cookie 正常刷新，产生新 Token | 通过 |
| `family_id` 不变 | 通过 |
| 旧 Token 正确标记 `revoked_at` + `replaced_by` | 通过 |
| 数据库摘要与实际签发 Token 匹配 | 通过 |
| Refresh 操作不更新 `last_activity_at` | 通过 |
| 重放旧 Token：401 `SESSION_REVOKED`，会话与整个 family 已撤销（已提交） | 通过 |
| 重放不影响其他设备会话 | 通过 |
| 3 线程并发刷新，仅 1 个成功（严格重放检测） | 通过 |
| 已轮换 Token 不能再次轮换 | 通过 |
| `expires_in` 与 Access 实际剩余时间一致 | 通过 |
| 事务中途异常 → 旧 Token 未被部分轮换，仍可正常轮换 | 通过 |
| `mark_rotated` 条件更新：首次 1 行、二次 0 行 | 通过 |

### 第 9 节 Cookie 与 CSRF（12 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 注册 / 登录响应设置 Refresh Cookie | 通过 |
| 所有 JSON 响应不含 Refresh Token | 通过 |
| `HttpOnly`、`Path=/auth`、`SameSite=Lax`、不设 `Domain` | 通过 |
| 生产配置 `Secure=true` 时 Cookie 带 `Secure` 属性 | 通过 |
| `Max-Age` 不超过 Refresh 剩余期限（≤ 7 天） | 通过 |
| 认证响应 `Cache-Control: no-store` | 通过 |
| 合法 Origin + `X-CSRF-Protection: 1` 正常访问 | 通过 |
| 缺少 Origin / 非法 Origin / 缺少或错误自定义头 → 403 | 通过 |
| CORS 白名单与 `AUTH_ALLOWED_ORIGINS` 一致且 `allow_credentials=True` | 通过 |
| 请求体中的 Refresh Token 不作为凭据（401） | 通过 |
| 不信任 `X-Forwarded-For`（记录 IP 为 127.0.0.1） | 通过 |

### 第 10 节 退出当前会话（4 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 使用 Cookie 正常退出，Session 与 family 均撤销 | 通过 |
| 旧 Access 下一次访问失败（401） | 通过 |
| 响应 `Set-Cookie` 含 `Max-Age=0` | 通过 |
| 无 Cookie 退出、重复退出均安全返回 200 | 通过 |
| 不影响同一用户其他 Session | 通过 |

### 第 11 节 活跃时间（8 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 带 `X-User-Activity: 1` 的成功业务请求更新 `last_activity_at` | 通过 |
| 无活动标记不更新 | 通过 |
| `/auth/*` 路径不更新 | 通过 |
| 非 2xx 响应不更新 | 通过 |
| 300 秒内不重复写入 | 通过 |
| `touch_session` 不复活已撤销会话（影响行数 0） | 通过 |
| 活跃更新抛异常被吞掉，不影响业务响应 | 通过 |
| `is_activity_path` 规则（含 `/tasks/today/unchecked-count` 排除） | 通过 |

### 第 12 节 原业务回归（7 项，全部通过）

| 测试项 | 结果 |
|---|---|
| `business_today()` 仍为 UTC+8 业务日期 | 通过 |
| `/users/me` `/plans` `/tasks/today` 均走新版 `get_current_user`，200 | 通过 |
| 匿名访问受保护接口统一 401 | 通过 |
| 越权访问他人 `/users/{id}` 返回 403 | 通过 |
| 昵称修改 PUT `/users/{id}` 生效 | 通过 |
| `ai_guard_mutex` 表数据量不受认证流程影响 | 通过 |
| 用户 A/B 的 `/plans` 列表相互隔离（`user_id` 匹配） | 通过 |

### 第 13 节 敏感信息保护（4 项，全部通过）

| 测试项 | 结果 |
|---|---|
| 422 响应不回显原始密码 | 通过 |
| 422 响应不回显原始验证码 | 通过 |
| 登录失败响应不回显账号标识 | 通过 |
| 错误响应保留字段定位信息（`loc` / `type` / `msg`） | 通过 |

---

## 三、事务与并发审查结论

| 检查点 | 结论 |
|---|---|
| Repository 不主动 commit/rollback | 通过（5 个 auth 仓库均为纯 SQL 操作，事务边界在 Service） |
| 多表插入可统一回滚 | 通过（模拟轮换中途异常，旧 Token 保持可用） |
| 验证码条件消费并发安全 | 通过（4 线程仅 1 成功） |
| Token 条件轮换并发安全 | 通过（3 线程仅 1 成功；`mark_rotated` 二次返回 0） |
| 重放撤销先提交后 401 | 通过（异常返回后会话 `revoked_at` 已落库） |
| 注册并发唯一性 | 通过（DB 唯一索引 + IntegrityError → 409，仅 1 成功） |
| IP 限流并发不绕过 | 通过（命名锁 + 事件计数） |

---

## 四、问题清单

### 4.1 P1（功能/契约缺陷）

#### P1-1　HTTPException 4xx 响应缺少统一响应结构

- **文件/行号**：`app/main.py:4`（导入 `StarletteHTTPException` 但从未使用）、`app/main.py:84-128`（仅注册 `RequestValidationError` 与 `Exception` 处理器）
- **现象**：所有 401/403/409/429 业务错误直接返回 FastAPI 默认结构 `{"detail": {...}}`，缺少顶层 `code` / `message` / `data`。
- **复现**：

```bash
curl -s http://127.0.0.1:8000/users/me
# {"detail":{"code":"INVALID_TOKEN","message":"缺少 Access Token"}}
```

- **影响**：与 A1.1 报告所述统一 `{code,message,detail,data}` 契约不一致；前端拦截器若依赖 `body.code` 判断状态将失效；401 的 `WWW-Authenticate` 头也无法统一保留。
- **最小修复（约 12 行，不改业务逻辑）**：

```python
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message") or "请求失败"
    else:
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": message,
                 "detail": detail, "data": None},
        headers=getattr(exc, "headers", None),
    )
```

#### P1-2　`verify_password` 对非字符串摘要抛异常（A1.1 遗留，未修复）

- **文件/行号**：`app/core/security.py:38-50`（仅捕获 `ValueError`）
- **复现**：`security.verify_password("x", None)` → `AttributeError: 'NoneType' object has no attribute 'split'`；`verify_password("x", 123)` → 同类异常；`b"bytes"` → `TypeError`
- **影响**：当前业务路径恒传字符串，实际风险低；但属于防御性缺陷，异常会冒泡为 500。
- **最小修复**：

```python
if not isinstance(stored_hash, str):
    return False
...
except (ValueError, TypeError):
    return False
```

#### P1-3　11 个数值配置缺少 `gt=0` 校验（A1.1 遗留，未修复）

- **文件/行号**：`app/config.py:28,29,32,48,49,50,52,53,97,98,100`
- **字段**：`SESSION_IDLE_EXPIRE_DAYS`、`SESSION_ABSOLUTE_EXPIRE_DAYS`、`SESSION_ACTIVITY_INTERVAL_SECONDS`、`EMAIL_CODE_EXPIRE_MINUTES`、`EMAIL_CODE_COOLDOWN_SECONDS`、`EMAIL_CODE_MAX_ATTEMPTS`、`EMAIL_DAILY_LIMIT`、`EMAIL_IP_DAILY_LIMIT`、`PASSWORD_MAX_FAILED_ATTEMPTS`、`PASSWORD_LOCK_MINUTES`、`AUTH_EVENT_RETENTION_DAYS`
- **复现**：在 `.env` 设 `SESSION_IDLE_EXPIRE_DAYS=0`，应用可正常启动，随后所有会话立即判定空闲过期。
- **最小修复**：统一改为 `Field(default=..., gt=0)`（`SESSION_ACTIVITY_INTERVAL_SECONDS` 建议 `ge=0` 以允许关闭）。

### 4.2 P2（健壮性/维护性）

| 编号 | 位置 | 问题 | 复现 | 最小修复 |
|---|---|---|---|---|
| P2-1 | `app/main.py:84-123` | `validation_exception_handler` 重复定义两次（完全相同），后者覆盖前者；`StarletteHTTPException` 导入闲置 | 查看源码即可 | 删除重复函数，并用该导入实现 P1-1 |
| P2-2 | `app/services/auth/auth_service.py:255,435,503,629` | 在 `with db.begin()` 作用域内显式 `db.commit()`，依赖 SQLAlchemy 对已关闭事务的容错，语义脆弱 | 代码审查；实测可用 | 失败事件改用独立短事务提交，或调整为先提交再抛异常的控制流 |
| P2-3 | `app/services/auth/activity_service.py` | 每次活跃更新新开 `SessionLocal`，高并发下与业务请求争抢连接池（默认 5+10） | 未压测（见第六节） | 独立小连接池 / 批量合并 / 限流采样 |
| P2-4 | `app/config.py:40-42` | `AUTH_ALLOWED_ORIGINS` 默认仅 `http://localhost:3000`，用 `127.0.0.1:3000` 打开前端会被 403 拒绝 | 用 127.0.0.1:3000 访问并登录 | 开发环境同时加入 `http://127.0.0.1:3000` |
| P2-5 | `app/repositories/auth/user_repository.py`（`update_nickname` 等使用 `NOW()`） | 用户资料时间字段按连接时区 `+08:00` 写入，而认证时间字段为 UTC 无时区，同一响应内时间语义不一致 | 修改昵称后对比 `users.updated_at` 与 `login_sessions.last_activity_at` | 统一为 UTC 写入，或统一 +08:00 并在文档标注 |
| P2-6 | `app/api/routes/auth.py`（logout） | 无 Cookie / 无效 Cookie 时返回 200 且不撤销任何会话（幂等语义）；若产品期望"退出必须失效"，需澄清 | 无 Cookie 调 `POST /auth/logout` | 属设计取舍，仅记录 |

---

## 五、安全性与事务一致性审查

| 审查项 | 结论 |
|---|---|
| 密码哈希 | PBKDF2-SHA256，迭代 600000，随机盐，`hmac.compare_digest` 比较 |
| 密钥校验 | `SECRET_KEY` / `EMAIL_CODE_SECRET` 均 ≥32 字节且不相同，启动期校验（`config.py:129-142`） |
| Token 类型隔离 | `type` 声明强制校验，Access/Refresh 不可混用 |
| Refresh 存储 | 仅存 SHA-256 摘要，不落明文 |
| 重放检测 | 严格模式：已轮换 Token 再次使用 → 撤销整个 family 并先提交后 401 |
| 账号枚举 | 不存在账号执行 dummy 哈希校验；锁定统一 429；未做计时侧信道测量（见第六节） |
| CSRF | 双重校验：Origin 白名单 + `X-CSRF-Protection: 1` 自定义头 |
| Cookie | HttpOnly、Path=/auth、SameSite=Lax、无 Domain、生产 Secure、Max-Age 受 Token 剩余期限约束 |
| IP 来源 | 仅使用 `request.client.host`，不信任 `X-Forwarded-For` |
| 限流 | 命名锁保证并发不绕过；事件计数持久化 |
| 敏感信息 | 422 统一 `msg="Invalid input"`；错误响应不回显密码/验证码/Token |
| 业务所有权 | 所有业务路由经 `get_current_user` + `user_id` 过滤，越权返回 403 |

---

## 六、仅代码审查、未执行的项（不计入通过）

| 项 | 原因 | 结论 |
|---|---|---|
| SSE 请求不更新活跃时间 | 本地 `AI_ENABLED=false`，`/ai/*` 流式接口返回 503，无法建立真实 SSE | 代码确认 `app/main.py:54-66` 对 `text/event-stream` 显式排除；未执行 |
| 已建立 SSE 流不要求随会话撤销立即终止 | 同上 | 未执行 |
| 账号枚举响应时间侧信道 | 需毫秒级统计采样，本轮未做 | 代码层面已用 dummy 校验，未测量 |
| 高并发连接池耗尽 | 需压测工具与独立环境 | 未执行，已列 P2-3 |
| 邮箱验证码登录的 IP 限流并发 | 与密码路径共用 `_reserve_ip_attempt`，本轮以密码路径并发验证 | 未单独并发压测 |

---

## 七、尚未实现的 Service 层业务保障（属 A2，不要求本轮）

1. 忘记密码 / 密码重置（含 `RESET_PASSWORD` 验证码落地流程）
2. 主动修改密码（`password_updated_at` 轮换）
3. 邮箱换绑最终提交（`CHANGE_EMAIL_OLD/NEW` 校验码联动）
4. 头像上传与删除（`AVATAR_*` 配置已有，接口未接）
5. 登录设备列表
6. 远程撤销指定设备会话
7. 退出其他设备 / 退出全部设备（`revoke_all_sessions` / `revoke_all_tokens` 仓库能力已具备，未接路由）
8. 定时清理任务（过期验证码 / 事件 / Token 归档）

前端 Axios 封装、AuthContext、跨标签页刷新协调、认证页面亦属 A2。

---

## 八、旧版认证代码后续需要替换的位置

| 检查项 | 现状 |
|---|---|
| `issue_token_pair` | 已无引用 |
| `RefreshRequest`（请求体 Refresh Token） | 已无引用，改为 HttpOnly Cookie |
| `revoke_all_sessions` | 仓库层保留，Service/路由未接入（A2 使用） |
| `revoke_all_tokens` | 同上 |
| `tb_refresh_token` 旧表 | 数据库中不存在，仅 `refresh_tokens` |
| 旧 `logout-all` 路由 | 已关闭 |
| 匿名 `GET /users` | 已移除（仅 `POST /users`、`GET /users/me`、`GET/PUT /users/{id}`） |
| 旧账号删除接口 | 已移除（`users.py` 无 DELETE） |
| `app/main.py:4` 的 `StarletteHTTPException` | 导入未使用，应在修复 P1-1 时启用 |
| 依赖旧认证签名的既有测试 | 未发现；现有业务测试未因 `get_current_user` 重构而失败 |

---

## 九、测试数据清理结果

清理策略：每个测试类 `tearDownClass` 按 `PREFIX`（`a13<class>xxxxxx`）精确删除自己创建的用户、Session、Token、验证码与事件；并清理本次测试窗口内产生的匿名 IP 限流事件。

清理后核验（`ssp_a0_migrate2`）：

| 检查项 | 结果 |
|---|---|
| `users WHERE username LIKE 'a13%'` | 0 |
| `email_verifications WHERE email LIKE 'a13%'` | 0 |
| `auth_events WHERE identifier LIKE 'a13%'` | 0 |
| 孤立 `login_sessions`（user_id 不存在） | 0 |
| 孤立 `refresh_tokens`（user_id 不存在） | 0 |
| 测试窗口内匿名 IP 事件 | 0 |
| 全表残留：users / login_sessions / refresh_tokens / email_verifications / auth_events | 0 / 0 / 0 / 0 / 0 |

正式库 `smart_study_planner`：全程未连接。

---

## 十、是否满足进入 A2 的条件

**有条件通过 —— 建议先修复 P1-1 再进入 A2。**

| 维度 | 结论 |
|---|---|
| 核心认证闭环功能 | 通过（注册 / 登录 / 静默刷新 / 退出 / 活跃时间 / 会话撤销全部实测可用） |
| 安全防护 | 通过（CSRF、Cookie 属性、Token 类型隔离、重放检测、限流并发均实测有效） |
| 并发与事务 | 通过（并发注册 / 并发消费 / 并发刷新 / 回滚一致性均实测正确） |
| 原业务回归 | 通过（受保护接口统一新版认证，所有权隔离正常，AI Guard 与北京时间规则未受影响） |
| 统一响应契约 | **不通过**（P1-1：4xx 缺顶层 `code/message/data`） |
| 遗留 P1 | P1-2、P1-3 自 A1.1 起未修复，建议一并处理 |

**放行建议**：P1-1 为前后端契约级问题，A2 前端（Axios 拦截器）会直接依赖该结构，务必在 A2 开发前修复（约 12 行 + 1 条新测试）。P1-2、P1-3 为低风险加固，可与 A2 并行修复。