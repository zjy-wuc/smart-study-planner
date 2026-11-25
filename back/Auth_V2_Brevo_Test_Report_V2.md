# Auth V2.0 — Brevo 真实邮件服务验收报告 V2

| 项 | 值 |
|---|---|
| 验收日期 | 2026-11-25 |
| 验收范围 | Brevo 真实邮件发送 + A1.2 验证码 Service 完整流程 |
| 测试收件邮箱 | `467782984@qq.com` |
| 隔离数据库 | `ssp_a0_migrate2` |
| 实际发送真实邮件数 | **2**（达到上限，未超限） |
| 业务源码是否修改 | **否**（仅运行测试，未改任何源码） |
| 正式库 `smart_study_planner` | **未访问、未修改** |
| 是否输出密钥/验证码/Token | **否**（验证码仅在进程内存使用，未写入报告） |

---

## 一、上一轮三个阻塞项的复测结果

| 阻塞项 | 上一轮状态 | 本轮复测 | 结果 |
|---|---|---|---|
| P0-1 `schemas/auth.py` 缺 `EmailCodePurpose` | ImportError | T0 导入 + 枚举成员检查 | ✅ **已修复** — 5 个成员齐全：REGISTER / LOGIN / RESET_PASSWORD / CHANGE_EMAIL_OLD / CHANGE_EMAIL_NEW |
| P0-2 `schemas/user.py` 缺 `normalize_email` | ImportError | T0 导入 + 签名检查 | ✅ **已修复** — `normalize_email(value: str) -> str` 存在且可用 |
| P0-3 `config.py` 缺 10 个字段声明 | AttributeError | T1 实际 `settings` 读取 | ✅ **已修复** — 10 个字段全部可访问，值与期望一致 |

---

## 二、T0：模块导入与函数签名检查

### 模块导入（10/10 全部成功）

```
app.config ................................................ OK
app.core.security ......................................... OK
app.core.clock ............................................ OK
app.schemas.user .......................................... OK
app.schemas.auth .......................................... OK
app.repositories.auth.lock_repository ..................... OK
app.repositories.auth.verification_repository ............. OK
app.services.auth.mail_service ............................ OK
app.services.auth.rate_limit_service ...................... OK
app.services.auth.verification_service .................... OK
```

### 函数签名匹配

| 函数 | 实际签名 | 匹配 |
|---|---|---|
| `generate_email_code` | `() -> str` | ✅ |
| `hash_email_code` | `(email: str, purpose: str, code: str) -> str` | ✅ |
| `verify_email_code` | `(email: str, purpose: str, code: str, stored_hash: str) -> bool` | ✅ |
| `normalize_email` | `(value: str) -> str` | ✅ |
| `find_latest_verification` | `(db, email, purpose, for_update=False, *, user_id=None, family_id=None)` | ✅ |
| `invalidate_previous` | `(db, *, email, purpose, now, user_id=None, family_id=None)` | ✅ |
| `acquire_lock` | `(connection, name, timeout) -> bool` | ✅ |
| `release_lock` | `(connection, name) -> bool` | ✅ |
| `send_verification_code` | `(email, code, purpose: EmailCodePurpose) -> bool` | ✅ |
| `mail_ready` | `() -> bool` | ✅ |

**结论**：无未同步的 A1.1 配置、Schema、Security 或 Repository 代码，所有跨模块调用签名一致。

---

## 三、T1：实际 Settings 加载结果

通过 `app.config.settings` 实际读取（非 `.env` 等效解析）：

| 字段 | 实际值 | 期望值 | 结果 |
|---|---|---|---|
| `MAIL_ENABLED` | `True` | `True` | ✅ |
| `BREVO_API_KEY` | 已加载，89 字符，前缀 `xkeysib-...` | 非空 | ✅ |
| `MAIL_FROM_EMAIL` | `noreply@reedswb.dpdns.org` | 正确 | ✅ |
| `MAIL_FROM_NAME` | `Smart Study Planner` | 正确 | ✅ |
| `EMAIL_GLOBAL_DAILY_LIMIT` | `240` | `240` | ✅ |
| `MAIL_TIMEOUT_SECONDS` | `10` | `10` | ✅ |
| `AUTH_LOCK_TIMEOUT_SECONDS` | `3` | `3` | ✅ |
| `AUTH_IP_WINDOW_MINUTES` | `15` | `15` | ✅ |
| `PASSWORD_IP_MAX_ATTEMPTS` | `30` | `30` | ✅ |
| `EMAIL_CODE_IP_MAX_ATTEMPTS` | `30` | `30` | ✅ |

**实际调用 `mail_service.mail_ready()` → 返回 `True`** ✅

---

## 四、T2：Brevo API 权限

免重测。上一轮验收已验证：

- `GET /v3/smtp/statistics/aggregatedReport` → **HTTP 200** ✅（SMTP 资源权限可用）
- API Key 有效（错误 Key 会返回 401，而非 403）
- 网络连通正常

> 注：`GET /v3/account` 和 `GET /v3/senders` 上一轮返回 403（该 Key 未授予 account/senders 资源权限），但 **不影响发邮件**——发邮件使用 `/v3/smtp/email` 属于 SMTP 资源，本轮 T3 实证通过。

---

## 五、T3：真实发送邮件

### 调用

```python
from app.core.security import generate_email_code
from app.schemas.auth import EmailCodePurpose
from app.services.auth.mail_service import send_verification_code

result = send_verification_code(
    email="467782984@qq.com",
    code=generate_email_code(),
    purpose=EmailCodePurpose.REGISTER,
)
```

### 结果

| 验证项 | 结果 |
|---|---|
| Brevo 接受请求 | ✅ |
| HTTP 状态码 | **201**（Service 返回 True 即状态码为 201） |
| Service 返回值 | **`True`** ✅ |
| 用户确认收到 | ⚠️ 未单独确认（第 1 封），但 Brevo 已接受 |

> 第 1 封邮件用于验证 `send_verification_code` 函数本身的发送能力。Brevo 返回 201 即表示请求被接受，邮件已进入发送队列。用户未单独确认第 1 封是否送达，但 T4 的第 2 封用户确认收到，证明通道整体可用。

---

## 六、T4：验证码完整流程

### T4a：`request_email_code` 首次调用（第 2 封真实邮件）

**调用前检查**：
- 隔离库守卫 `SELECT DATABASE()` → `ssp_a0_migrate2` ✅
- 收件邮箱 `467782984@qq.com` 在 `users` 表中未注册 ✅
- 当日全局发送量 = 0，邮箱发送量 = 0（额度充足）✅

**调用**：
```python
request_email_code(
    email="467782984@qq.com",
    purpose=EmailCodePurpose.REGISTER,
    request_ip="127.0.0.1",
)
```

**结果**：调用成功，无异常，发出第 2 封真实邮件。

### T4a 入库状态验证（记录 id=32）

| 字段 | 实际值 | 期望值 | 结果 |
|---|---|---|---|
| `purpose` | `REGISTER` | REGISTER | ✅ |
| `send_status` | `SENT` | SENT（PENDING→SENT 转换正常） | ✅ |
| `attempts` | `0` | 0 | ✅ |
| `consumed_at` | `NULL` | NULL | ✅ |
| `invalidated_at` | `NULL` | NULL | ✅ |
| `code_hash` 长度 | `64` | 64 | ✅ |
| `code_hash` 全 hex | `True` | True | ✅ |
| `expires_at - created_at` | `300.0` 秒 | 300 秒（5 分钟） | ✅ |
| 不存明文验证码 | `True` | True | ✅ |

### T4b：60 秒冷却限制

立即重复调用 `request_email_code`：

| 验证项 | 结果 |
|---|---|
| HTTP 状态码 | **429** ✅ |
| detail | `{'code': 'RATE_LIMITED', 'message': '验证码发送过于频繁，请稍后重试'}` |
| 最新记录 id 未变 | `True`（未产生新记录）✅ |
| 该邮箱总记录数 | `1`（无新增）✅ |
| 未产生额外真实邮件 | ✅ |

**结论**：冷却限制正常生效，60 秒内重复请求被拦截且不消耗邮件配额。

### T4c：用户收件确认

用户在聊天中提供了收到的 **6 位验证码**（第 2 封，记录 id=32），证明：
- ✅ 第 2 封邮件已送达用户邮箱
- ✅ 用户能正确读取验证码

> 第 1 封（T3）用户未单独确认送达，但 Brevo 已接受请求（HTTP 201）。

### T4d：`check_verification` 与 `consume_verification` 测试

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | `check_verification` 用**正确**验证码 | ✅ 返回非 None 记录 |
| 2 | `consume_verification`（同事务） | ✅ 返回 `True`（消费成功） |
| 3 | 重复 `consume_verification`（新事务） | ✅ 返回 `False`（重复消费失败） |
| 4 | 已消费后 `check_verification` | ✅ 返回 `None`（已消费不可再用） |
| 5 | `check_verification` 用**错误**验证码 | ✅ 返回 `None`，`attempts` 从 0→1（递增） |

> 步骤 5 因 id=32 已被消费无法测试 attempts 递增，故新建测试记录 id=33（存错误码 hash）验证错误码分支。该记录已在 T5 清理。

---

## 七、T5：数据清理

### 清理范围

仅清理本次测试新增的 `email_verifications` 记录（收件邮箱为 `467782984@qq.com` 的所有记录）：

| 表 | 清理前 | 操作 | 清理后残留 |
|---|---|---|---|
| `email_verifications` | id 32、33（共 2 条） | `DELETE WHERE email='467782984@qq.com'` | **0** ✅ |
| `users` | 0 条（邮箱未注册） | 无需操作 | **0** ✅ |
| `auth_events` | 0 条（`request_email_code` 不写 auth_events） | 无需操作 | **0** ✅ |

### 残留核验

```
remaining_for_email (email_verifications) = 0
users_with_email (users) = 0
events_for_email (auth_events) = 0
```

**结论**：所有测试数据已精确清理，其他已有数据未受影响。

---

## 八、实际发送邮件数量

| 阶段 | 邮件数 | 说明 |
|---|---|---|
| T3 直接 `send_verification_code` | 1 | 不入库，验证 Service 发送能力 |
| T4a `request_email_code` | 1 | 入库 + 真实发送，用于完整流程 |
| T4b 冷却拦截 | 0 | 429 拦截，未发 |
| **合计** | **2** | **达到上限，未超限** |

---

## 九、剩余缺陷与最小修复建议

### 本轮未发现新缺陷

上一轮的 3 个 P0 阻塞项已全部修复，本轮测试全部通过。

### 设计观察（非缺陷，供参考）

1. **`check_verification` 对"已消费"和"验证码错误"统一返回 `None`**，由上层 `reject_invalid_code()` 统一报 400。从安全角度这是合理的（不泄露具体失败原因），但如需区分用户体验，可在 Service 层细化错误码。当前实现符合安全最佳实践，**无需修改**。

2. **`request_email_code` 不写 `auth_events`**：当前只在 `rate_limit_service._reserve_ip_attempt`（单独调用）时写事件。`request_email_code` 本身只写 `email_verifications`。如需审计发码行为，可在 Service 层补一条 `EMAIL_CODE_SENT` 事件。**属于 A1.2 后续增强，非本轮阻塞**。

3. **Brevo API Key 权限范围**：该 Key 有 SMTP 资源权限但无 account/senders 权限。不影响发邮件，但如果未来需要查询发件人认证状态或账户信息，需在 Brevo 后台为该 Key 勾选相应权限。

---

## 十、是否满足真实邮件服务验收条件

### ✅ **满足**

| 验收维度 | 结论 |
|---|---|
| 模块导入与签名一致性 | ✅ 全部通过 |
| 配置实际加载 | ✅ 全部字段正确 |
| `mail_ready()` | ✅ 返回 True |
| Brevo API 连通性 | ✅ SMTP 资源权限可用 |
| 真实邮件发送 | ✅ Service 返回 True，HTTP 201 |
| 用户收件确认 | ✅ 第 2 封确认收到 |
| 验证码入库状态 | ✅ 全部字段正确 |
| 5 分钟有效期 | ✅ 300 秒 |
| 不存明文 | ✅ code_hash 为 64 位 hex |
| 60 秒冷却 | ✅ 429 拦截，无新邮件 |
| check + consume | ✅ 正确码通过，消费成功 |
| 重复消费防护 | ✅ 重复 consume 返回 False |
| 错误码防护 | ✅ 返回 None，attempts 递增 |
| 测试数据清理 | ✅ 残留全 0 |
| 邮件数量控制 | ✅ 2 封，未超上限 |

**真实邮件服务验收通过，可进入下一阶段。**

---

## 附录：测试执行命令参考

所有测试在 `d:\project\back` 目录下使用现有虚拟环境执行：

```bash
# T0/T1
.venv\Scripts\python.exe -c "..."

# T3
.venv\Scripts\python.exe -c "from app.services.auth.mail_service import send_verification_code; ..."

# T4
.venv\Scripts\python.exe -c "from app.services.auth.verification_service import request_email_code, check_verification, consume_verification; ..."

# T5（清理）
mysql -uroot -p... ssp_a0_migrate2 -e "DELETE FROM email_verifications WHERE email='467782984@qq.com';"
```

---

**报告生成时间**：2026-11-25
**报告版本**：V2.0
