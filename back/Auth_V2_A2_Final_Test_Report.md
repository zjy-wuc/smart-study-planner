# Auth V2.0 A2.3 / A2.4 后端集中验收报告

> 报告类型：自动化验收 + 安全审查（只读业务源码，未修改源码与数据库结构）
> 测试时间：2026-11-26
> 测试脚本：`tests/test_auth_a2_3_avatar_profile_cleanup_acceptance.py`（新增，102 项）
> 结论摘要：**头像、个人资料、认证清理、验证码时间边界、当前退出修复全部通过；Worker 集成存在 2 个 P0 阻断缺陷，A2 暂不满足正式结项条件。**

---

## 1. 实际测试环境及数据库

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | Windows（PowerShell 5） |
| Python | 3.14.10（虚拟环境 `D:\project\back\.venv`） |
| 数据库 | MySQL 8.4.9 |
| 数据库名 | `ssp_a0_migrate2`（已执行 `SELECT DATABASE()` 双重确认） |
| SQLAlchemy / PyMySQL | 2.1.5 / 2.2.8 |
| FastAPI / Starlette | 0.143.3 / 1.8.0 |
| Pillow | 13.0.0（WebP、APNG、动画 WebP、EXIF 能力均可用） |
| 时区约定 | 业务时间 UTC+8；认证时间 UTC（naive 存储） |

隔离与约束执行情况：

- 所有写操作前均执行 `SELECT DATABASE()`，仅访问 `ssp_a0_migrate2`，未连接正式库。
- 头像测试将 `settings.AVATAR_DIR` 在导入 `app.main` **之前** 重定向到独立临时目录（`%TEMP%\ssp_a23_avatar_*`），正式目录 `storage/avatars` 全程未被写入（测试后为空）。
- 邮件全部 Mock，未真实发送。
- 报告与本文件中不出现密码、验证码、Token、密钥。
- 清理调度开关默认关闭，测试直接调用 `run_auth_cleanup()`。
- 运行方式：`cwd=D:\project\back`，`.\.venv\Scripts\python.exe -m unittest tests.test_auth_a2_3_avatar_profile_cleanup_acceptance -v`。

---

## 2. 测试总数与结果

### 2.1 本轮新增验收套件

| 指标 | 数量 |
| --- | --- |
| 测试总数 | **102** |
| 通过 | **97** |
| 失败 | **2** |
| 跳过 | **3** |

失败项（均为 Worker 集成，同一代码模块缺陷的两个面）：

1. `TestT7Worker.test_worker_module_imports` —— `app.jobs.plan_expiration_worker` 无法导入。
2. `TestT7Worker.test_cleanup_flag_exposed_on_settings` —— `settings.AUTH_CLEANUP_ENABLED` 不存在。

跳过项（已明确原因，不计入通过）：

1. `TestT3PermissionsStatic.test_symlink_not_followed` —— Windows 当前权限无法创建符号链接（WinError 1314）。
2. `TestT6OrphanAvatars.test_symlink_not_followed` —— 同上。
3. `TestT7Worker.test_enabled_registers_hourly_cleanup` —— 依赖 Worker 模块导入，被 P0-1 阻断，无法运行时验证。

### 2.2 历史/业务回归套件（本次实际执行）

| 测试模块 | 数量 | 通过 | 失败 | 错误 |
| --- | --- | --- | --- | --- |
| `test_auth_a2_account_session_acceptance` | 83 | 83 | 0 | 0 |
| `test_auth_a1_3_acceptance` | 98 | 97 | 1 | 0 |
| `test_lifecycle_regression` | 1 | 0 | 0 | 1（模块导入失败） |
| `test_progress_regression` | 16 | 0 | 0 | 16 |
| `test_rollover_regression` | 5 | 0 | 0 | 5 |
| **合计** | **203** | **180** | **1** | **22** |

说明：回归中的 1 个失败与 22 个错误均为**既有测试用例与新规格/新表结构的适配问题**，详见第 4、7 节，不属于本轮产品逻辑回归。A2.1/A2.2 套件 83/83 全部通过，确认已验收。

---

## 3. 各项测试实际结果

### T0 契约检查（2/2 通过）

| 用例 | 结果 |
| --- | --- |
| `GET /users/me`、`PUT /users/{user_id}`、`POST/DELETE /users/me/avatar` 路由已注册 | 通过 |
| avatar_service、auth_cleanup、cleanup_repository、users 路由、user schema 均可导入 | 通过 |

### T1 头像格式及尺寸校验（18/18 通过）

| 用例 | 结果 |
| --- | --- |
| JPG / PNG / WebP 均可上传 | 通过 |
| 输出为合法 WebP（`Image.format == WEBP`） | 通过 |
| RGBA 透明通道保留（alpha=0 像素保持） | 通过 |
| 最长边不超过 512px | 通过 |
| 等比缩放（1000×500 → 512×256） | 通过 |
| 小图不放大（10×10 → 10×10） | 通过 |
| EXIF Orientation=6 正确转正（80×40 → 40×80） | 通过 |
| EXIF/GPS/描述元数据被剥离（输出不含原始标记、getexif 为空） | 通过 |
| 空文件拒绝（400） | 通过 |
| 超过 2 MiB 拒绝（413） | 通过 |
| 超过最大解码像素拒绝（临时下调阈值验证） | 通过 |
| 动态 WebP 拒绝 | 通过 |
| GIF 拒绝 | 通过 |
| APNG（多帧 PNG）拒绝 | 通过 |
| SVG / PDF 拒绝 | 通过 |
| 伪造扩展名 + 伪造 MIME 不能绕过（非图片内容被拒；真实 JPEG 改名为 .txt 仍按内容接受） | 通过 |
| 损坏/截断图片拒绝 | 通过 |
| 并发解码（8 线程）不崩溃 | 通过（同时记录无并发解码上限风险，见 P2-1） |

### T2 文件与数据库一致性（12/12 通过）

| 用例 | 结果 |
| --- | --- |
| 首次上传成功更新 `avatar_url` | 通过 |
| 文件名由服务器生成（32 位 hex + `.webp`），不使用原始文件名 | 通过 |
| 更换头像生成新 URL | 通过 |
| 新头像存在且可公开读取 | 通过 |
| 数据库提交后才清理旧头像 | 通过 |
| 模拟 UPDATE 失败（affected=0）：旧头像与引用不变，新文件被回收 | 通过 |
| 模拟 COMMIT 结果不确定：不删除数据库可能引用的新文件，旧引用不变 | 通过 |
| 模拟旧文件删除失败：已提交的新头像不受影响 | 通过 |
| 4 路并发上传：最终仅保留数据库引用的文件，不误删 | 通过 |
| 并发上传 + 删除：最终状态一致（有引用必有文件 / 无引用无残留） | 通过 |
| 删除头像后 `avatar_url = NULL` 且文件移除 | 通过 |
| 重复删除安全 | 通过 |
| 不允许删除头像目录之外的文件（穿越、绝对路径、file:// 均无效） | 通过 |

### T3 头像权限及静态资源（10 通过 / 1 跳过）

| 用例 | 结果 |
| --- | --- |
| 未登录无法上传 | 通过（401） |
| 未登录无法删除 | 通过（401） |
| 已撤销 Session 无法上传 | 通过（401 + `SESSION_REVOKED`） |
| 认证通过后、业务事务前会话被撤销，服务层仍拒绝 | 通过 |
| 只能修改自己的头像（A 上传不影响 B） | 通过 |
| CSRF 校验有效（缺少 Origin/CSRF 头 → 403 `CSRF_REJECTED`） | 通过 |
| 处理后的头像可公开访问且为 WebP、≤512 | 通过 |
| 暂存目录与 `storage` 其他内容未暴露（`/media/avatars_staging`、`/storage/avatars`、`..` 均 404） | 通过 |
| 路径穿越无法访问非授权文件 | 通过 |
| 仅挂载 `/media/avatars` 且 `follow_symlink=False` | 通过 |
| 符号链接不被跟随 | 跳过（Windows 无创建权限；源码为 `follow_symlink=False`，配置层面已确认） |

### T4 个人资料（8/8 通过）

| 用例 | 结果 |
| --- | --- |
| `GET /users/me` 返回当前最新头像地址 | 通过 |
| 删除头像后返回 `null` | 通过 |
| 邮箱、昵称、头像等字段正常 | 通过 |
| 不返回 `password_hash` / Refresh Token / Token 摘要 | 通过 |
| `PUT /users/{user_id}` 仅能更新本人昵称 | 通过 |
| 携带 `email` / `password_hash` / `is_active` 无法修改安全字段（被忽略） | 通过 |
| `created_at` / `updated_at` 输出 +08:00，且与数据库值一致 | 通过 |
| `email_verified_at` 保持 UTC（+00:00） | 通过 |

### T5 认证数据清理（12/12 通过）

| 用例 | 结果 |
| --- | --- |
| 当前有效验证码不被删除 | 通过 |
| 当日额度统计不受清理影响 | 通过 |
| 已轮换但未过期的 Refresh Token 不被删除 | 通过 |
| 清理后重放检测仍生效（重放旧 Refresh 触发 `SESSION_REVOKED` 并撤销会话） | 通过 |
| 仍有 Token 关联的历史 Session 不被删除 | 通过 |
| 当前有效 Session 不被删除 | 通过 |
| 认证事件默认保留 30 天（40 天前删除、10 天前保留） | 通过 |
| 仍在生效的限流/锁定事件不被提前删除（2 天前保留） | 通过 |
| 每类数据每轮最多清理 500 条（插入 505 条仅删 500 条） | 通过 |
| 重复执行安全 | 通过 |
| 两个线程并发执行清理结果一致、无异常 | 通过 |
| 清理与登录/刷新/撤销并发无死锁、无失败 | 通过 |

### T6 孤儿头像清理（6 通过 / 1 跳过）

| 用例 | 结果 |
| --- | --- |
| 被数据库引用的头像保留 | 通过 |
| 未满 24 小时的孤儿文件保留 | 通过 |
| 超过 24 小时且无引用的合法 UUID WebP 删除 | 通过 |
| 超过 24 小时的无主暂存文件清理 | 通过 |
| 非系统命名文件不误删（`photo.webp`、`abc.png`） | 通过 |
| 与上传并发执行不误删有效头像 | 通过 |
| 符号链接不被跟随/清理 | 跳过（Windows 无创建权限；`cleanup_orphan_avatars` 对 `is_symlink()` 显式跳过） |

### T7 Worker 集成（6 通过 / 2 失败 / 1 跳过）

| 用例 | 结果 |
| --- | --- |
| `AUTH_CLEANUP_ENABLED` 默认关闭（模块级值为 False） | 通过 |
| `settings.AUTH_CLEANUP_ENABLED` 可作为配置读取 | **失败**（P0-2） |
| `app.jobs.plan_expiration_worker` 可导入 | **失败**（P0-1） |
| 开启后注册每小时一次的认证清理任务 | 跳过（被 P0-1 阻断） |
| 原计划到期任务仍为每 5 分钟（源码 `minutes=5`、`id="expire_study_plans"`） | 通过（源码级） |
| `--once` 行为保持兼容（源码存在 `--once` 与 `run_due_plan_check()`） | 通过（源码级） |
| 不需要新增独立后台进程 | 通过 |
| 不涉及 AI Guard / 学习业务数据 | 通过 |
| 清理失败被吞掉，不阻断其他定时任务（注入异常 → `failed=True` 且不抛出） | 通过 |

### T8 验证码安全时间边界（8/8 通过）

| 用例 | 结果 |
| --- | --- |
| 改密前生成的 RESET_PASSWORD 验证码改密后不可用 | 通过 |
| 改密后重新发送的验证码正常使用 | 通过 |
| 改密前生成的 LOGIN 验证码不可继续使用 | 通过 |
| 邮箱换绑前生成的旧绑定验证码，在邮箱安全状态变化后不可复用且未被消费 | 通过 |
| 新旧换绑码仍正确绑定 `user_id` + `family_id`（错误绑定均拒绝） | 通过 |
| 不影响 REGISTER 验证码（注册成功并消费） | 通过 |
| 边界：`created_at == password_updated_at` 拒绝；早 1 秒拒绝；晚 1 秒可用 | 通过 |
| 发码与改密真实并发：按 `created_at` 与 `password_updated_at` 的实际先后判定，结果一致 | 通过 |

### T9 当前退出修复（9/9 通过）

| 用例 | 结果 |
| --- | --- |
| Refresh 有效、Access 缺失时正常撤销 | 通过 |
| Access 有效、Refresh 缺失时正常撤销 | 通过 |
| Access 过期、Refresh 有效时正常撤销 | 通过 |
| Access 与 Refresh 属于不同会话 → 409，且两个会话均未被撤销 | 通过 |
| 两种凭证均无效 → `session_revoked=false`（服务返回 False） | 通过 |
| 已撤销会话重复退出安全 | 通过 |
| 正常撤销后旧 Access 下一次认证失败（`SESSION_REVOKED`） | 通过 |
| 数据库事务提交失败不返回成功（500，且会话未被撤销） | 通过 |
| 路由级正常退出返回 `session_revoked=true` | 通过 |

### T10 历史回归及缺陷复测（6/6 通过）

| 用例 | 结果 |
| --- | --- |
| P1-1 统一错误信封（401 含 `code/message/data`） | 通过（已修复） |
| P1-2 `verify_password` 类型保护（None/非字符串/malformed hash 均返回 False） | 通过（已修复） |
| P1-3 改密后旧 RESET_PASSWORD 码作废 | 通过（已修复） |
| A1.1 / A1.3 / A2 测试文件存在 | 通过 |
| 登录与资料接口不泄露密码摘要/Token | 通过 |
| 公开 DTO 静态审查（`UserPublic` 过滤、schema 无 password_hash） | 通过 |

---

## 4. 缺陷与风险列表

### P0（阻断结项）

#### P0-1 Worker 引用不存在的模块，进程完全无法启动

- 文件：`app/jobs/plan_expiration_worker.py:14`
- 代码：`from app.jobs.auth_cleanup import run_auth_cleanup`
- 实际实现位于：`app/services/auth/auth_cleanup.py:19`（`run_auth_cleanup`）
- 复现条件：
  1. `cd D:\project\back`
  2. `.\.venv\Scripts\python.exe -c "import app.jobs.plan_expiration_worker"`
  3. 结果：`ModuleNotFoundError: No module named 'app.jobs.auth_cleanup'`
- 影响：Worker 无法启动，`--once` 不可用；既有 `tests/test_lifecycle_regression.py:13` 在导入阶段即失败（本轮回归中 1 个模块级 ImportError 已实测确认）。
- 最小修复建议：将第 14 行改为 `from app.services.auth.auth_cleanup import run_auth_cleanup`（无需新增进程、无需新建文件）。

#### P0-2 清理开关未定义为 Settings 字段

- 文件：`app/config.py:192`（`settings = Settings()`）与 `app/config.py:195`（`AUTH_CLEANUP_ENABLED: bool = False` 位于类外）
- 复现条件：
  1. `.\.venv\Scripts\python.exe -c "from app.config import settings; print(settings.AUTH_CLEANUP_ENABLED)"`
  2. 结果：`AttributeError`（属性不存在）。
- 影响：`app/jobs/plan_expiration_worker.py:105` 的 `if settings.AUTH_CLEANUP_ENABLED:` 在 P0-1 修复后仍会抛错；每小时清理任务无法注册。
- 最小修复建议：把 `AUTH_CLEANUP_ENABLED: bool = False` 移入 `class Settings` 内（默认值不变），删除类外重复声明。若需保留模块级别名，可写成 `AUTH_CLEANUP_ENABLED = settings.AUTH_CLEANUP_ENABLED`。

### P1（安全/部署，需在部署侧落实）

#### P1-1 上传请求体缺少部署层大小限制，2 MiB 检查发生得过晚

- 文件：`app/services/auth/avatar_service.py:54-65`、`app/api/routes/users.py`（上传路由）
- 说明：FastAPI/Starlette 会先把 multipart 请求完整落盘（`SpooledTemporaryFile`）后才进入处理函数，`_convert_image` 的 2 MiB 校验只能阻止“读入图片”，不能阻止超大请求体占用带宽/临时磁盘。
- 复现条件：向 `POST /users/me/avatar` 发送远大于 2 MiB 的 multipart 体，服务器仍会先接收完整请求体。
- 最小修复建议：在反向代理/网关设置 `client_max_body_size`（如 3 MB），并在 ASGI 层增加请求体上限中间件；应用代码逻辑无需改动。

### P2（风险与测试债）

#### P2-1 图片解码无并发上限

- 文件：`app/services/auth/avatar_service.py:51-121`
- 说明：8 线程并发解码实测全部成功，但进程中未使用信号量限制同时解码数量；单图已限制 1600 万像素，极端并发下 CPU/瞬时内存仍可能被放大。
- 建议：为解码阶段增加进程级 `Semaphore`（如 2~4）或在上传路由加每用户限流。

#### P2-2 头像上传无频率限制

- 文件：`app/api/routes/users.py`（头像路由）
- 说明：命名锁只保证串行一致性，不限制调用频率；同一账号可高频“上传-替换”触发磁盘写放大。
- 建议：复用现有 IP/用户准入限流，对头像写操作增加独立配额。

#### P2-3 A1.3 历史用例与新规格冲突（测试债）

- 文件：`tests/test_auth_a1_3_acceptance.py:331`
- 现象：断言 OpenAPI 中不存在任何 `logout-all` 路径；而 A2 新增了**需要密码确认**的 `/auth/logout-all`（`app/api/routes/auth.py:454-472`，`SessionRevokeRequest`）。本轮回归 1 个失败即此项。
- 判定：属于 A1.3 测试预期未随 A2 规格更新，**不是产品缺陷**（A2.1/A2.2 已验证该接口必须密码确认）。
- 建议：更新该历史用例，改为校验“无密码参数的 logout-all 不存在”。

#### P2-4 业务回归测试夹具与新表结构不匹配（测试债）

- 文件：`tests/test_progress_regression.py:22`、`tests/test_rollover_regression.py` 中 `INSERT INTO users (username, password_hash) ...`
- 现象：`users.password_updated_at` 现为 NOT NULL 且无默认值，夹具未提供该列 → 22 个错误（`OperationalError 1364`）。
- 判定：测试夹具陈旧，与本轮功能行为无关；但导致“业务回归全绿”无法达成。
- 建议：在夹具 SQL 中补充 `password_updated_at`（及必要的 `email_verified_at`）取值。

#### P2-5 清理任务每轮 500 条上限的积压风险（观察项）

- 文件：`app/repositories/auth/cleanup_repository.py:12,37,60,94`
- 说明：每小时 500 条上限（约 1.2 万/天）对当前规模充足；若历史事件量突增，可能出现多轮才能追平。本轮 505 条实测确认上限生效且重复执行可继续清理。

---

## 5. 关键文件与定位索引

| 关注点 | 文件:行 |
| --- | --- |
| 图片校验/转换 | `app/services/auth/avatar_service.py:39-132` |
| 头像上传与提交顺序（先 commit 后删旧） | `app/services/auth/avatar_service.py:255-324` |
| 删除头像 | `app/services/auth/avatar_service.py:330-367` |
| 孤儿清理（24h、UUID 命名、跳过符号链接） | `app/services/auth/avatar_service.py:373-431` |
| 清理编排（30 天、500 上限、失败兜底） | `app/services/auth/auth_cleanup.py:19-136` |
| 清理 SQL（NOT EXISTS Token 保护） | `app/repositories/auth/cleanup_repository.py:56-87` |
| 清理调度注册 | `app/jobs/plan_expiration_worker.py:93-116` |
| 退出会话修复（409 / session_revoked） | `app/services/auth/session_service.py`、`app/api/routes/auth.py:204-240` |
| 个人资料时区与字段过滤 | `app/api/routes/users.py`、`app/schemas/user.py` |
| 静态头像挂载（不跟随符号链接） | `app/main.py`（`/media/avatars`，`follow_symlink=False`） |

---

## 6. 测试数据与文件清理结果

| 项目 | 结果 |
| --- | --- |
| 测试用户（`username LIKE 'a13%'`） | 0 条 |
| 测试验证码（email 含测试前缀） | 0 条 |
| 测试认证事件（`TEST_A23%`） | 0 条 |
| `users.avatar_url IS NOT NULL` | 0 条 |
| 临时头像目录 `%TEMP%\ssp_a23_avatar_*` | 已由进程退出钩子递归删除，无残留 |
| 正式头像目录 `storage/avatars` | 未被写入，文件数 0 |

说明：清理任务按设计执行的是全局过期数据删除（仅命中超过 30 天/2 天的记录），本轮未影响活跃数据；测试自身数据由 `tearDownClass` 按测试前缀与用户 ID 精确清理。

---

## 7. 历史缺陷复测情况

| 缺陷 | 复测方式 | 结论 |
| --- | --- | --- |
| A1.3 P1-1 错误响应未统一 | `T10.test_p1_1_unified_error_envelope` | 已修复（401 返回 `code/message/data`） |
| A1.3 P1-2 `verify_password` 类型不安全 | `T10.test_p1_2_verify_password_type_guard` | 已修复（非字符串返回 False，不抛异常） |
| A1.3 P1-3 改密后旧 RESET_PASSWORD 码仍可用 | `T8.test_reset_code_before_password_change_invalid_after`、`T10.test_p1_3_*` | 已修复（`valid_after = max(password_updated_at, email_verified_at)`） |
| A2.1 / A2.2 验收 | 重新执行 `test_auth_a2_account_session_acceptance` | 83/83 通过，确认已验收 |
| A1.3 总体 | 重新执行 | 97/98，唯一失败为 P2-3（用例预期冲突，非产品缺陷） |
| 业务回归（生命周期/进度/滚动） | 重新执行 | 生命周期因 P0-1 导入失败；进度/滚动因 P2-4 夹具问题报错 |

---

## 8. A2 是否满足正式结项条件

**不满足。** 理由：

1. A2.3 相关（头像 T1/T2/T3、个人资料 T4）功能与安全测试全部通过，具备结项质量。
2. A2.4 的认证清理（T5/T6）、验证码时间边界（T8）、当前退出修复（T9）全部通过。
3. **但 Worker 集成（T7）存在 2 个 P0**：清理任务模块无法导入、配置项不在 Settings 中，导致“AUTH_CLEANUP_ENABLED 开启后每小时清理”这一 A2.4 交付项完全不可运行；并已连带使既有生命周期回归模块导入失败。
4. 业务回归套件未全绿（P2-3、P2-4 为测试债，需同步修正）。

结论：A2.3 可以判定通过；A2.4 需在修复 P0-1、P0-2 并完成 3 个跳过项的补跑后，方可宣布 A2 正式结项。

---

## 9. 是否满足进入 A3 前端认证基础设施开发

**有条件满足（接口层已就绪，流程闸门未通过）。**

- 已满足：A2.1/A2.2 全部接口 83/83 通过；头像上传/删除、个人资料读写、会话撤销与当前退出接口契约稳定，返回值与时区约定明确，A3 前端所需的认证 API 均已可用。
- 未满足：按项目“上一阶段正式结项后再进入下一阶段”的闸门口径，A2.4 尚存 P0，不应宣布 A2 完成。
- 建议：允许 A3 前端并行开发（接口无需变更）；但在 A2.4 的 P0-1、P0-2 修复并复跑 T7 全部用例前，不将 A2 标记为“已结项”。

---

## 10. 未执行 / 无法执行的测试（明确标注，不视为通过）

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| SSE 相关认证/活动记录回归 | 未执行 | 本轮范围外，未在本轮清单内执行 |
| 数据库连接池压力测试 | 未执行 | 需独立压测环境与时长，本轮未执行 |
| 账号枚举时间差异测试 | 未执行 | 需高精度计时样本，本轮未执行 |
| T7 每小时清理任务运行时注册验证 | 跳过 | 被 P0-1 阻断 |
| T3/T6 符号链接运行时验证 | 跳过 | Windows 无创建符号链接权限（配置层面已静态确认 `follow_symlink=False` 且清理函数跳过符号链接） |
| 并发解码峰值内存量化 | 部分 | 无 `psutil`，仅验证 8 并发不崩溃；内存风险以静态审查记录为 P2-1 |

---

*本报告仅基于实际执行的命令与断言输出生成；未实际执行的用例一律标记为“跳过/未执行”，未标记为通过。*