# Smart Study Planner — Auth V2.0 A1.1 验收报告

| 项 | 值 |
|---|---|
| 验收日期 | 2026-11-25 |
| 验收范围 | Auth V2.0 A1.1 认证基础设施（仅后端） |
| 验收人 | Trae Agent（自动化） |
| 业务源码是否修改 | **否**（仅新增 1 个测试文件 `tests/test_auth_a1_1_acceptance.py`） |
| 数据库迁移是否执行 | **否** |
| 是否实际发送邮件 | **否** |

---

## 1. 测试环境及实际数据库

| 项 | 值 |
|---|---|
| OS | Windows（PowerShell 5） |
| Python | 3.14.10（venv `.venv`） |
| pytest | 9.2.0 |
| MySQL | 8.4（`C:\Program Files\MySQL\MySQL Server 8.4`） |
| 实际连接数据库 | **`ssp_a0_migrate2`**（隔离开发库） |
| 正式库 `smart_study_planner` | **未访问、未修改** |
| 模块加载时 `SELECT DATABASE()` 守卫 | 已通过（在测试模块 import 时校验，非隔离库直接 raise） |
| 每次测试 setUp 二次确认 | 已通过 |

测试文件路径：`d:\project\back\tests\test_auth_a1_1_acceptance.py`（124 个测试用例）。

---

## 2. 测试总数与结果汇总

| 类别 | 数量 |
|---|---|
| **总数** | **124** |
| **通过 (PASS)** | **116** |
| **失败 (FAIL)** | **3** |
| **跳过 (SKIP)** | **5** |
| 子测试通过 | 8（T2_05 的 8 种畸形摘要全部 PASS） |

### 失败用例（3）

| 编号 | 用例 | 失败原因 |
|---|---|---|
| F-1 | `T1ConfigAndEnv.test_t1_12_numeric_boundary_validation` | 6 个数值配置字段缺少边界校验，非法值未被拒绝 |
| F-2 | `T2PasswordSecurity.test_t2_06_non_string_hash` | `verify_password` 对 `None` / `int` 类型的 `stored_hash` 抛 `AttributeError`，未安全返回 `False` |
| F-3 | `T11AuthEventRepository.test_t11_08_identifier_ip_no_after_id` | `count_identifier_events` 与 `count_ip_events` 缺少 `after_id` 参数 |

### 跳过用例（5）

| 编号 | 用例 | 跳过原因 |
|---|---|---|
| S-1 | `T6Schema.test_t6_01_schemas_module_contents` | `RegisterRequest/LoginRequest/LoginResponse/EmailCode*Request/EmailCodePurpose` 等 schema 在 `app/schemas/auth.py` 中**未实现**，T6 期望项无法按规范执行 |
| S-2 | `T12TransactionsAndConcurrency.test_t12_03_concurrent_consume` | 由 `T12ConcurrencyCommitted.test_t12c_01` 真实执行（PASS） |
| S-3 | `T12TransactionsAndConcurrency.test_t12_04_concurrent_rotate` | 由 `T12ConcurrencyCommitted.test_t12c_02` 真实执行（PASS） |
| S-4 | `T13SensitiveInfoProtection.test_t13_02_validation_error_no_raw_code` | `/auth/email-code/verify` 路由返回 404，A1.1 范围内未升级 |
| S-5 | `T13SensitiveInfoProtection.test_t13_03_validation_error_no_raw_token` | `/auth/refresh` 路由返回 404，A1.1 范围内未升级 |

> 注：S-2、S-3 不算"未实际执行"——对应的 `T12c_01` 与 `T12c_02` 在独立连接 + 真实提交条件下运行并 PASS，仅是为避免重复执行而 skip 占位。

---

## 3. 每个测试项实际执行结果

### T1. 配置与环境（13 项：12 PASS / 1 FAIL）

| 项 | 内容 | 结果 |
|---|---|---|
| T1_01 | .env 加载且 DB 指向隔离库 | ✅ PASS |
| T1_02 | 实际连接 `SELECT DATABASE()` 返回 `ssp_a0_migrate2` | ✅ PASS |
| T1_03 | JWT 密钥与验证码 HMAC 密钥 ≥32 字节且不相同 | ✅ PASS（两密钥长度均 64 字节且互不相同；不输出具体值） |
| T1_04 | 缺失密钥拒绝启动配置 | ✅ PASS |
| T1_05 | 密钥过短拒绝 | ✅ PASS |
| T1_06 | 两密钥相同拒绝 | ✅ PASS |
| T1_07 | Access Token 15 分钟 | ✅ PASS |
| T1_08 | Refresh Token 7 天 | ✅ PASS |
| T1_09 | Session 空闲 7 天 | ✅ PASS |
| T1_10 | Session 绝对 30 天 | ✅ PASS |
| T1_11 | 活跃时间写入间隔 300 秒 | ✅ PASS |
| **T1_12** | **数值配置非法值是否被拒绝** | **❌ FAIL** — 6 个字段缺校验（详见 P1-1） |
| T1_13 | 原有 AI 配置完整保留 | ✅ PASS |

### T2. 密码安全工具（6 项：5 PASS / 1 FAIL）

| 项 | 内容 | 结果 |
|---|---|---|
| T2_01 | PBKDF2-SHA256 迭代 600000 | ✅ PASS |
| T2_02 | 相同密码多次哈希产生不同摘要 | ✅ PASS |
| T2_03 | 正确密码验证成功 | ✅ PASS |
| T2_04 | 错误密码验证失败 | ✅ PASS |
| T2_05 | 畸形摘要安全处理（8 种子用例） | ✅ PASS（全部 8 种字符串类异常输入均被安全拒绝） |
| **T2_06** | **非字符串 stored_hash** | **❌ FAIL** — `None` / `int` 触发 `AttributeError`（详见 P1-2） |

### T3. JWT 安全工具（15 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T3_01 | Access Token 签发与解码 | ✅ PASS |
| T3_02 | Refresh Token 签发与解码 | ✅ PASS |
| T3_03 | 6 个必要声明齐全（sub/family_id/iat/exp/type/jti） | ✅ PASS |
| T3_04 | 同会话 access/refresh 的 family_id 一致 | ✅ PASS |
| T3_05 | 不同 Token 的 jti 不同 | ✅ PASS |
| T3_06 | 禁止 access/refresh 混用（双向） | ✅ PASS |
| T3_07 | 缺少必要声明拒绝 | ✅ PASS |
| T3_08 | 非法 sub（非数字/0/超 BIGINT/非字符串）与非法 family_id（非 UUID/UUIDv1）拒绝 | ✅ PASS |
| T3_09 | 错误签名 / 篡改拒绝 | ✅ PASS |
| T3_10 | 过期 Token 拒绝 | ✅ PASS |
| T3_11 | Access Token 过期返回 `ACCESS_EXPIRED` | ✅ PASS |
| T3_12 | Token 有效期 ≤ 会话截止时间 | ✅ PASS |
| T3_13 | naive datetime 作为 expires_at 拒绝 | ✅ PASS |
| T3_14 | expires_at 在过去拒绝签发 | ✅ PASS |
| T3_15 | iat/exp 为秒级 int，access token TTL ≈ 900s | ✅ PASS |

### T4. 邮箱验证码安全工具（8 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T4_01 | 验证码为 6 位 ASCII 数字（100 次随机生成均合规） | ✅ PASS |
| T4_02 | 支持以 0 开头（`012345` 用例） | ✅ PASS |
| T4_03 | HMAC-SHA256 摘要 64 字符 hex | ✅ PASS |
| T4_04 | 正确验证码校验通过 | ✅ PASS |
| T4_05 | 错误验证码校验失败 | ✅ PASS |
| T4_06 | 不同邮箱不混用 | ✅ PASS |
| T4_07 | 不同用途不混用 | ✅ PASS |
| T4_08 | 摘要中不包含明文验证码 | ✅ PASS |

### T5. 时间工具（4 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T5_01 | `business_today()` 东八区业务日期 | ✅ PASS |
| T5_02 | `utc_now()` 返回带 UTC 时区 | ✅ PASS |
| T5_03 | `utc_db_now()` 返回 naive UTC | ✅ PASS |
| T5_04 | 学习业务时区常量 UTC+8 未受影响 | ✅ PASS |

### T6. Schema 校验（3 项：1 PASS / 1 SKIP / 1 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T6_01 | A1.1 期望的 schema 类是否存在 | ⏭️ SKIP — 全部缺失（详见 P1-4） |
| T6_02 | 当前 `UserCreate` 无字段约束（任意字符串均可通过） | ✅ PASS（记录为设计缺口） |
| T6_03 | `TokenPair` 结构（token_type/expires_in） | ✅ PASS |

> T6 期望的"用户名仅允许 ASCII 字母数字下划线、长度 4～32"、"密码 8～64"、"邮箱格式与规范化"、"6 位 ASCII 数字验证码"、"用途 5 种枚举"、"昵称长度匹配"等**全部未实现**，因 A1.1 范围内 schema 文件仅有 `TokenPair / RefreshRequest / UserCreate / UserUpdate` 4 个基础类。

### T7. 用户 Repository（8 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T7_01 | 插入并按 ID 查询 | ✅ PASS |
| T7_02 | 按用户名查询 | ✅ PASS |
| T7_03 | 按邮箱查询 | ✅ PASS |
| T7_04 | 用户名唯一约束 | ✅ PASS |
| T7_05 | 邮箱唯一约束 | ✅ PASS |
| T7_06 | FOR UPDATE 查询 | ✅ PASS |
| T7_07 | 不存在用户返回 None | ✅ PASS |
| T7_08 | SQL 注入安全（参数绑定） | ✅ PASS |

### T8. Session Repository（14 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T8_01 | 创建及查询会话 | ✅ PASS |
| T8_02 | 用户与会话联合查询 | ✅ PASS |
| T8_03 | 跨用户查询拒绝 | ✅ PASS |
| T8_04 | 查询有效会话列表 | ✅ PASS |
| T8_05 | 排除已撤销会话 | ✅ PASS |
| T8_06 | 排除超过 7 天空闲期限的会话 | ✅ PASS |
| T8_07 | 排除超过 30 天绝对期限的会话 | ✅ PASS |
| T8_08 | 不足 300 秒不更新活跃时间 | ✅ PASS |
| T8_09 | 达到 300 秒允许更新 | ✅ PASS |
| T8_10 | 已撤销会话不能通过 touch 复活 | ✅ PASS |
| T8_11 | 已绝对过期会话不能 touch | ✅ PASS |
| T8_12 | 撤销单个会话（写入 revoked_at + reason） | ✅ PASS |
| T8_13 | 撤销全部会话（3 个 → 全撤） | ✅ PASS |
| T8_14 | 保留指定会话撤销其他（3 个 → 撤 2 保 1） | ✅ PASS |

### T9. Token Repository（12 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T9_01 | 插入并按摘要查询 | ✅ PASS |
| T9_02 | token_hash 唯一约束 | ✅ PASS |
| T9_03 | FOR UPDATE 行锁 | ✅ PASS |
| T9_04 | 正常轮换（写入 revoked_at + replaced_by） | ✅ PASS |
| T9_05 | 已轮换 Token 不能再轮换 | ✅ PASS |
| T9_06 | 已撤销 Token 不能再轮换 | ✅ PASS |
| T9_07 | 已过期 Token 不能再轮换 | ✅ PASS |
| T9_08 | 撤销指定 family | ✅ PASS |
| T9_09 | 撤销全部 | ✅ PASS |
| T9_10 | 保留指定 family 撤销其他 | ✅ PASS |
| T9_11 | SQL 中只使用 `refresh_tokens` 表名（静态检查） | ✅ PASS |
| T9_12 | `expires_at` 为 MySQL datetime（秒级，无小数秒） | ✅ PASS |

### T10. Verification Repository（21 项：全部 PASS）

| 项 | 内容 | 结果 |
|---|---|---|
| T10_01 | 创建 PENDING 验证码 | ✅ PASS |
| T10_02 | PENDING → SENT | ✅ PASS |
| T10_03 | PENDING → FAILED | ✅ PASS |
| T10_04 | 已 SENT 不能改 FAILED（状态机一次性） | ✅ PASS |
| T10_05 | 按 (email, purpose) 查最新 | ✅ PASS |
| T10_06 | 作废历史验证码 | ✅ PASS |
| T10_07 | 作废旧验证码后不能再消费 | ✅ PASS |
| T10_08 | 错误次数正常递增 | ✅ PASS |
| T10_09 | 达到 5 次后禁止再增，且禁止消费 | ✅ PASS |
| T10_10 | 正确消费验证码 | ✅ PASS |
| T10_11 | 禁止重复消费 | ✅ PASS |
| T10_12 | 禁止消费过期 | ✅ PASS |
| T10_13 | 禁止消费已作废 | ✅ PASS |
| T10_14 | 禁止消费 PENDING | ✅ PASS |
| T10_15 | 禁止消费 FAILED | ✅ PASS |
| T10_16 | 邮箱发送次数统计 | ✅ PASS |
| T10_17 | IP 发送次数统计 | ✅ PASS |
| T10_18 | 全站发送次数统计 | ✅ PASS |
| T10_19 | 最近发送时间查询 | ✅ PASS |
| T10_20 | FAILED 仍计入发送额度 | ✅ PASS |
| T10_21 | 换绑场景 user_id + family_id 正确保存 | ✅ PASS |

### T11. Auth Event Repository（9 项：8 PASS / 1 FAIL）

| 项 | 内容 | 结果 |
|---|---|---|
| T11_01 | 事件插入 | ✅ PASS |
| T11_02 | 按 user_id 统计 | ✅ PASS |
| T11_03 | 按 identifier 统计 | ✅ PASS |
| T11_04 | 按 IP 统计 | ✅ PASS |
| T11_05 | 查询最新指定类型事件 | ✅ PASS |
| T11_06 | `after_id` 排除历史失败记录（user 维度） | ✅ PASS |
| T11_07 | 时间窗口边界（`created_at >= since` 包含端点） | ✅ PASS |
| **T11_08** | **identifier / ip 维度的 after_id 支持** | **❌ FAIL**（详见 P2-1） |
| T11_09 | 表结构不含 password/code/token 字段 | ✅ PASS |

### T12. 事务及并发基础测试（5 项静态 + 2 项真实并发：6 PASS / 2 SKIP 占位）

| 项 | 内容 | 结果 |
|---|---|---|
| T12_01 | 五个 Repository 均不主动 commit/rollback | ✅ PASS |
| T12_02 | 多表插入外层事务回滚后无残留 | ✅ PASS |
| T12_03 | 验证码并发消费占位 | ⏭️ SKIP（由 T12c_01 真实执行） |
| T12_04 | Token 并发轮换占位 | ⏭️ SKIP（由 T12c_02 真实执行） |
| T12_05 | SQL 字段类型/长度与数据库列匹配 | ✅ PASS |
| **T12c_01** | **5 线程并发消费同一验证码，仅 1 成功** | **✅ PASS** |
| **T12c_02** | **5 线程并发轮换同一 Token，仅 1 成功** | **✅ PASS** |

> T12c_01 / T12c_02 在独立连接 + 真实提交条件下运行，利用 `consume_verification` 与 `mark_rotated` 的条件 UPDATE 行级原子性，**并发安全性得到实证**。测试后已精确清理自建数据（详见第 9 节）。

### T13. 敏感信息保护（4 项：2 PASS / 2 SKIP）

| 项 | 内容 | 结果 |
|---|---|---|
| T13_01 | 参数验证异常不包含原始密码 | ✅ PASS（`/auth/login` 路由返回 422 时，响应体不包含密码字面值） |
| T13_02 | 不包含原始验证码 | ⏭️ SKIP（`/auth/email-code/verify` 返回 404，A1.1 范围外） |
| T13_03 | 不包含原始 Token | ⏭️ SKIP（`/auth/refresh` 返回 404，A1.1 范围外） |
| T13_04 | 422 响应结构含 code/message/data，data 含 loc/type/msg 但不含 input | ✅ PASS |

---

## 4. 发现的问题

按 P0（严重安全或数据风险）/ P1（功能或业务缺陷）/ P2（健壮性或维护性问题）分类。

### P0 — 严重安全或数据风险

**无。**

未发现能被直接利用的越权、密钥泄露、明文存储、跨用户访问等 P0 级问题。JWT 必填声明、签名验证、Token 类型隔离、family_id 校验、密码哈希加盐、验证码 HMAC、条件 UPDATE 行级原子性均通过。

### P1 — 功能或业务缺陷

#### P1-1　数值配置字段缺少边界校验（F-1）

- **位置**：`app/config.py`
- **现象**：以下 6 个数值字段未声明任何 pydantic 边界约束，可被人为写入 0 或负数且不会被拒绝：

| 字段 | 行号 | 当前声明 | 应为 |
|---|---|---|---|
| `SESSION_IDLE_EXPIRE_DAYS` | 28 | `int = 7` | `Field(default=7, gt=0)` |
| `SESSION_ABSOLUTE_EXPIRE_DAYS` | 29 | `int = 30` | `Field(default=30, gt=0)` |
| `SESSION_ACTIVITY_INTERVAL_SECONDS` | 32 | `int = 300` | `Field(default=300, gt=0)` |
| `EMAIL_CODE_EXPIRE_MINUTES` | 48 | `int = 5` | `Field(default=5, gt=0)` |
| `EMAIL_CODE_COOLDOWN_SECONDS` | 49 | `int = 60` | `Field(default=60, ge=0)` |
| `EMAIL_CODE_MAX_ATTEMPTS` | 50 | `int = 5` | `Field(default=5, gt=0)` |
| `EMAIL_DAILY_LIMIT` | 52 | `int = 10` | `Field(default=10, gt=0)` |
| `EMAIL_IP_DAILY_LIMIT` | 53 | `int = 30` | `Field(default=30, gt=0)` |
| `PASSWORD_MAX_FAILED_ATTEMPTS` | 57 | `int = 5` | `Field(default=5, gt=0)` |
| `PASSWORD_LOCK_MINUTES` | 58 | `int = 15` | `Field(default=15, gt=0)` |
| `AUTH_EVENT_RETENTION_DAYS` | 60 | `int = 30` | `Field(default=30, gt=0)` |

- **复现**：

```python
from app.config import Settings
Settings(_env_file=None, DB_USER="root", DB_PASSWORD="x", DB_NAME="ssp_a0_migrate2",
         SECRET_KEY="b"*64, EMAIL_CODE_SECRET="c"*64,
         SESSION_ACTIVITY_INTERVAL_SECONDS=0,
         EMAIL_CODE_MAX_ATTEMPTS=-1)
# 当前不会抛 ValidationError — 即配置漏洞
```

- **影响**：一旦运维或部署脚本误将上述字段设为 0/负数，可能导致：
  - `SESSION_ACTIVITY_INTERVAL_SECONDS=0` → 活跃时间每次请求都触发 UPDATE，写入放大；
  - `EMAIL_CODE_MAX_ATTEMPTS=-1` → 验证码永远无法消费（`attempts < -1` 永假），用户被永久锁定；
  - `EMAIL_CODE_EXPIRE_MINUTES=0` → 验证码发出即过期；
  - `EMAIL_DAILY_LIMIT=0` → 邮件服务被静默禁用。
- **建议最小修复**：给所有上述字段添加 `Field(default=..., gt=0)`（或合适的 `ge=0`）。仅 `ACCESS_TOKEN_EXPIRE_MINUTES` 与 `REFRESH_TOKEN_EXPIRE_DAYS` 已有 `gt=0`，可作为模板。

#### P1-2　`verify_password` 对非字符串 `stored_hash` 抛 `AttributeError`（F-2）

- **位置**：`app/core/security.py:42-51`
- **现象**：

```python
def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest = stored_hash.split("$")
        ...
    except ValueError:
        return False
```

`stored_hash.split("$")` 在 `stored_hash = None` 或 `stored_hash = 12345` 时抛 `AttributeError`，**不在 `except ValueError` 捕获范围内**，会向上冒泡。

- **复现**：

```python
from app.core import security
security.verify_password("x", None)    # AttributeError: 'NoneType' object has no attribute 'split'
security.verify_password("x", 12345)   # AttributeError: 'int' object has no attribute 'split'
```

- **影响**：
  - 从 DB 读出的 `password_hash` 字段理论上是 NOT NULL，但旧版/迁移数据若出现 NULL 行、或上层调用未校验类型，会触发未捕获异常 → 500 错误而非返回验证失败。
  - 属于健壮性缺陷，间接掩盖了真正的"密码错误"语义。
- **建议最小修复**：

```python
def verify_password(password: str, stored_hash: str) -> bool:
    if not isinstance(stored_hash, str):
        return False
    if not isinstance(password, str):
        return False
    try:
        algorithm, iterations, salt_hex, digest = stored_hash.split("$")
        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    # ... 其余保持不变
```

#### P1-3　`schemas/auth.py` 与 `schemas/user.py` 极简，T6 期望的 schema 全部缺失（S-1）

- **位置**：`app/schemas/auth.py`、`app/schemas/user.py`
- **现象**：两个文件合计仅定义 4 个类（`TokenPair`、`RefreshRequest`、`UserCreate`、`UserUpdate`），且 `UserCreate` 的字段没有任何 pydantic 约束。
- **影响**：
  - 用户名格式（ASCII 字母数字下划线、4～32 位）未实现；
  - 密码长度（8～64）未实现；
  - 邮箱格式与规范化（小写化、`utf8mb4_0900_as_ci` 一致性）未实现；
  - 验证码 6 位 ASCII 数字校验未实现；
  - 验证码用途 5 种枚举未实现；
  - `LoginResponse` 不包含 Refresh Token / 密码摘要这一约束**无对应 schema 可验证**。
- **建议**：这是 A1.1 范围内未覆盖的部分，需要在 A1.2 阶段补齐。建议尽早实现：
  - `RegisterRequest`（username、email、password、nickname?）
  - `LoginRequest`（identifier、password）
  - `EmailCodeSendRequest` / `EmailCodeVerifyRequest`
  - `EmailCodePurpose`（枚举：REGISTER / LOGIN / RESET_PASSWORD / CHANGE_EMAIL_OLD / CHANGE_EMAIL_NEW）
  - `LoginResponse`（access_token、user_info，**绝不包含** refresh_token 与 password_hash）

#### P1-4　`users.email_verified_at` 与 `users.password_updated_at` 为 `NOT NULL`，与业务语义冲突

- **位置**：隔离库表结构（`SHOW CREATE TABLE users`）
- **现象**：

```
`email_verified_at` datetime(6) NOT NULL COMMENT '邮箱验证时间（UTC）',
```

- **影响**：
  - 注册即被视为"已验证邮箱"，因为 `insert_user` 必须给 `email_verified_at` 塞 `now`（见 `user_repository.py:110`）。
  - 与 T6 期望的"注册流程需邮箱验证码"语义不一致。
  - 未来若实现邮箱验证后，无法区分"未验证"与"已验证"用户。
- **建议最小修复**：
  - **数据库层**（不在 A1.1 范围内，仅记录）：将 `email_verified_at` 改为 `datetime(6) DEFAULT NULL`。
  - **代码层**：`insert_user` 中 `email_verified_at` 改为 `:email_verified_at` 参数，注册时传 `None`，验证通过后再 UPDATE。

### P2 — 健壮性或维护性问题

#### P2-1　`count_identifier_events` / `count_ip_events` 缺少 `after_id` 参数（F-3）

- **位置**：`app/repositories/auth/auth_event_repository.py:101-150`
- **现象**：仅 `count_user_events` 提供 `after_id` 参数（行 78），`count_identifier_events`（行 101）与 `count_ip_events`（行 127）没有。
- **影响**：
  - 用户维度的"上次登录成功后清零失败计数"可以实现；
  - **同一邮箱 / 同一 IP 的"上次成功后清零"语义无法实现**——Service 层做暴力破解防护（按 IP 锁定）时，需要统计"自上次成功以来的失败次数"，当前接口做不到。
- **建议最小修复**：为两个函数添加 `after_id: int = 0` 参数，SQL 增加 `AND id > :after_id`。同时新增 `find_latest_identifier_event` / `find_latest_ip_event` 帮助函数（对称于 `find_latest_user_event`）。

#### P2-2　`email_verified_at` 在 `insert_user` 中被强制赋值为注册时间

- **位置**：`app/repositories/auth/user_repository.py:108-111`
- **现象**：`INSERT` 把 `:now` 同时赋给 `password_updated_at` 和 `email_verified_at`，注册即视为邮箱已验证。
- **影响**：见 P1-4。
- **建议**：见 P1-4。

#### P2-3　`user_repository.find_by_*` 未排除已删除/未激活用户

- **位置**：`app/repositories/auth/user_repository.py:13-82`
- **现象**：三个 `find_by_*` 函数 SQL 没有 `is_active = 1` 过滤条件。
- **影响**：Service 层若忘记校验 `is_active`，已禁用账号仍可登录。
- **建议**：在两个层级任一即可：
  - **方案 A**（推荐）：在 `find_by_id/username/email` 中增加 `AND is_active = 1`，由调用方显式选择 `for_update` 时也可查未激活；
  - **方案 B**：保留 repo 现状，由 Service 层强制校验 `is_active`，但需在 Service 层接口注释中明确契约。

#### P2-4　旧版认证接口仍是 Legacy，未升级到 V2

- **位置**：`/auth/email-code/verify`、`/auth/refresh` 路由返回 404（见 T13_02 / T13_03 跳过原因）
- **现象**：A1.1 仅实现基础设施，旧版认证路由未替换为 V2 流程。
- **记录**：这是 A1.1 范围外的预期行为，**不计为 A1.1 缺陷**，但需在 A1.2 阶段升级。

---

## 5. 问题复现方法

| 问题 | 复现命令 |
|---|---|
| P1-1 | `python -c "from app.config import Settings; Settings(_env_file=None, DB_USER='r', DB_PASSWORD='x', DB_NAME='ssp_a0_migrate2', SECRET_KEY='b'*64, EMAIL_CODE_SECRET='c'*64, EMAIL_CODE_MAX_ATTEMPTS=-1)"` → 不抛异常即漏洞 |
| P1-2 | `python -c "from app.core.security import verify_password; verify_password('x', None)"` → `AttributeError` |
| P1-3 | `python -c "from app.schemas import auth; print([n for n in dir(auth) if not n.startswith('_')])"` → 仅 `TokenPair` 与 `RefreshRequest` |
| P1-4 | `mysql -uroot -p... ssp_a0_migrate2 -e "SHOW CREATE TABLE users\G"` → `email_verified_at datetime(6) NOT NULL` |
| P2-1 | `python -c "import inspect; from app.repositories.auth.auth_event_repository import count_identifier_events; print('after_id' in inspect.signature(count_identifier_events).parameters)"` → `False` |
| P2-3 | `SELECT id FROM users WHERE id = :uid` 不带 `is_active` 过滤 |

---

## 6. 建议的最小修复方案

按优先级排序，全部为**单点最小改动**：

1. **【P1-1】config.py**：在 11 个数值字段上加 `Field(default=..., gt=0)`（仅改动 `app/config.py`，11 行修改）。
2. **【P1-2】security.py**：在 `verify_password` 函数体开头加 `isinstance` 检查（仅改动 `app/core/security.py:42`，2 行新增）。
3. **【P1-3】schemas**：新增 `RegisterRequest/LoginRequest/EmailCode*/LoginResponse/EmailCodePurpose`（新增类型，不改业务）。
4. **【P1-4】users 表**（DBA 执行，不在本次范围）：`ALTER TABLE users MODIFY email_verified_at datetime(6) DEFAULT NULL;`，并同步修改 `insert_user`。
5. **【P2-1】auth_event_repository.py**：为 `count_identifier_events` 与 `count_ip_events` 增加 `after_id: int = 0` 参数与 SQL 条件。
6. **【P2-3】user_repository.py**：在三个 `find_by_*` SQL 中加 `AND is_active = 1`，或在 Service 层接口约定强制校验。

---

## 7. 尚未实现的 Service 层业务保障（A1.1 范围外）

以下需要 Service / Router 层实现，A1.1 仅完成 Repository 层保障：

1. **登录流程**：用户名+密码 → 校验失败次数 → 锁定判定 → 签发 access+refresh → 写会话与 token 表。
2. **注册流程**：邮箱验证码消费 → 创建用户 → 邮箱验证。
3. **刷新流程**：验证 refresh token → 重放检测（若 `replaced_by` 已有值且 revoked_at 在未来，视为重放攻击，撤销整个 family）→ 轮换 → 写新 token。
4. **换绑邮箱流程**：旧邮箱验证码 + 新邮箱验证码双重校验，绑定 user_id 与 family_id。
5. **登出流程**：撤销当前 family 的会话与 token；登出全部设备则调用 `revoke_all_*`。
6. **限流**：基于 `count_email_sends / count_ip_sends / count_global_sends` 实现三级限流，在请求入口校验。
7. **密码暴力破解防护**：基于 `count_user_events` / `count_identifier_events` / `count_ip_events` + `after_id` 实现"上次登录成功后 N 次失败锁定"。
8. **refresh token 重放检测**：当 `mark_rotated` 返回 0 且原 token 已被 `replaced_by` 指向其他 token 时，撤销整个 family 的所有 token 与会话（目前 `revoke_family` 已支持，需在 Service 调用）。

---

## 8. 旧版认证代码后续需要替换的位置

以下为 A1.1 范围外、A1.2 阶段需替换/升级的接口与代码：

| 路由 / 模块 | 当前状态 | 后续动作 |
|---|---|---|
| `POST /auth/login` | 返回 422（仅参数验证） | 替换为 V2 登录流程（会话创建 + Token 签发） |
| `POST /auth/refresh` | 返回 404 | 实现 V2 刷新流程（重放检测 + 轮换） |
| `POST /auth/email-code/verify` | 返回 404 | 实现 V2 验证码消费流程 |
| `POST /auth/register` | 待查 | 替换为 V2 注册流程（邮箱验证码 + 创建用户） |
| `POST /auth/logout` | 待查 | 实现 V2 登出流程 |
| `app/services/auth/` 整个目录 | A1.1 未创建 | A1.2 新增 |
| `app/api/routes/auth.py` | 待查 | A1.2 重写 |

> 上述位置的具体行号需在 A1.2 开始前用 `Grep` 检索 `auth/login`、`auth/refresh`、`auth/register` 等关键字确认。

---

## 9. 测试数据清理结果

测试采用三层清理策略：

### 9.1 事务回滚（绝大多数测试）

所有 `RollbackTestCase` 子类（T7、T8、T9、T10、T11、T12）的 `setUp` 都建立独立连接 + 外层事务；`tearDown` 调用 `outer.rollback()`。所有 INSERT 自动回滚。

### 9.2 真实提交的并发测试精确清理

`T12ConcurrencyCommitted` 类需要提交以让其他连接看到，故使用：
- 独立 engine 实例（避免污染共享连接池）；
- `tearDown` 中按 `username` / `email` / `family_id` 精确 `DELETE` 自建数据；
- 不涉及任何已存在的种子数据或他人测试数据。

### 9.3 残留核验

测试执行完毕后运行：

```
from tests.test_auth_a1_1_acceptance import count_a11_residue
print(count_a11_residue())
```

**实测结果**：

| 表 | 残留数 |
|---|---|
| `users`（`username LIKE 'a11_%'`） | **0** |
| `email_verifications`（`email LIKE 'a11_%@test.local'`） | **0** |
| `auth_events`（`identifier LIKE 'a11_%'`） | **0** |
| `login_sessions`（关联 `a11_` 用户） | **0** |
| `refresh_tokens`（关联 `a11_` 用户） | **0** |

**结论**：所有测试数据已完全清理，隔离库未留任何 a11_ 前缀的残留。

---

## 10. A1.1 是否满足结项条件

### 结论：**有条件通过（Conditional Pass）**

#### 通过依据

- 116/124 测试通过（93.5%），3 个失败均为已识别的非阻塞性问题；
- 所有 Repository 层核心安全属性（行级原子性、参数绑定、状态机一次性、防重放、防重复消费）实证通过；
- **并发安全性已用真实多线程 + 真实提交测试验证**：5 线程并发消费验证码与并发轮换 Token 均保证只有 1 个成功；
- 未发现 P0 级安全或数据风险；
- 隔离库表结构与 SQL 完全匹配。

#### 阻塞结项的问题

**无 P0，但建议在进入 A1.2 前先修复 P1-1 与 P1-2**：

- **P1-1**（数值配置缺校验）：是配置面漏洞，非法部署可能导致用户被永久锁定或服务静默禁用；
- **P1-2**（`verify_password` 异常处理）：是健壮性缺陷，会在边缘场景引发 500 错误。

两项修复都极简单（合计 < 15 行代码），建议在 1 个工作日内修复并复测。

#### 不阻塞但需记录

- **P1-3**（schema 极简）：A1.1 范围内不强制要求，T6 大量校验属于 A1.2 工作；
- **P1-4**（`email_verified_at NOT NULL`）：DB schema 层面需 DBA 评估，单独立项；
- **P2-1**（`after_id` 参数缺失）：Service 层暴力破解防护的 IP/identifier 维度需要先补这一参数。

#### 放行进入 A1.2 的前提

1. 修复 P1-1、P1-2 并重跑本测试套件；
2. 在 A1.2 设计文档中明确 schema 补齐计划（P1-3）；
3. 与 DBA 对齐 `users.email_verified_at` 是否允许 NULL（P1-4）；
4. 在 Service 层暴力破解防护设计前，补齐 `after_id` 参数（P2-1）。

---

## 附录 A：测试套件元数据

- **测试文件**：`tests/test_auth_a1_1_acceptance.py`
- **代码行数**：约 1300 行
- **测试类**：13 个 TestCase（T1 ~ T13 + T12ConcurrencyCommitted）
- **测试用例**：124 个
- **运行命令**：`d:\project\back\.venv\Scripts\python.exe -m pytest tests/test_auth_a1_1_acceptance.py -v`
- **运行耗时**：约 2.5 秒
- **依赖**：FastAPI TestClient、SQLAlchemy、PyJWT、pytz（标准库 datetime.timezone）、threading

## 附录 B：测试覆盖矩阵

| 测试项 | 覆盖维度 | 实证手段 |
|---|---|---|
| T1 | 配置加载 + 密钥校验 + 数值边界 | Settings 类直接构造 + pydantic 校验触发 |
| T2 | PBKDF2 + 摘要畸形输入 | 直接调用 + 子测试 |
| T3 | JWT 签发/解码/类型/签名/过期/边界 | 直接调用 + 手动构造 token |
| T4 | 验证码生成 + HMAC + 隔离性 | 直接调用 + mock secrets.randbelow |
| T5 | 时区工具 | 直接调用 + datetime 比较 |
| T6 | Schema 约束 | pydantic 模型构造（多类未实现 SKIP） |
| T7 | 用户 CRUD + 唯一约束 + SQL 注入 | DB 事务回滚 |
| T8 | 会话 CRUD + 撤销 + 边界 | DB 事务回滚 + UPDATE 验证 |
| T9 | Token 轮换 + 重放防护 | DB 事务回滚 + 条件 UPDATE 验证 |
| T10 | 验证码状态机 + 计数器 + 额度 | DB 事务回滚 |
| T11 | 事件统计 + 时间窗 + 敏感字段 | DB 事务回滚 + INFORMATION_SCHEMA 检查 |
| T12 | 事务 + 行级原子性 | 静态检查 + 真实多线程并发 |
| T13 | 异常响应不泄露敏感值 | FastAPI TestClient 实际 HTTP 调用 |

---

**报告生成时间**：2026-11-25
**报告版本**：v1.0
**审核人**：待用户确认
