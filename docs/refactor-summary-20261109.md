# 后端分层重构变更摘要

- 日期：2026-11-09
- 范围：`back/app` 后端路由分层
- 基线提交：`222a942 feat: 完成单 Access Token 的登录与用户信息接口`
- 变更规模：5 个文件，`+228 / -299`

---

## 一、重构目标

把原本全部堆在 `app/main.py` 的接口，按职责拆到 `api/routes/` 下，让 `main.py` 只负责应用装配。

重构前 `main.py` 同时承担五件事：创建 app、配置 CORS、定义 Pydantic 模型、实现业务接口、注册异常处理器。接口与装配混在一起，新增业务时冲突多、可读性差。

---

## 二、结构调整

### 重构前

```
app/
├── main.py        # app + CORS + 模型 + 全部接口 + 异常处理
├── config.py
├── database.py
├── response.py
└── core/
    ├── security.py
    └── deps.py
```

### 重构后

```
app/
├── main.py                 # 只保留：app 创建、CORS、include_router、异常处理器
├── api/
│   ├── router.py           # 汇总挂载各子路由
│   └── routes/
│       ├── system.py       # GET /       GET /health
│       ├── users.py        # 用户 CRUD（6 个）
│       └── auth.py         # POST /auth/login
├── schemas/
│   └── user.py             # UserCreate / UserUpdate
├── config.py
├── database.py
├── response.py
└── core/
    ├── security.py
    └── deps.py
```

---

## 三、逐文件变更

### 1. `app/main.py`（-289 行）

删除内容：

- 6 个 `/users` 路由：`POST /users`、`GET /users`、`GET /users/me`、`GET /users/{user_id}`、`PUT /users/{user_id}`、`DELETE /users/{user_id}`
- 1 个 `/auth/login` 路由
- `UserCreate`、`UserUpdate` 两个模型定义

保留内容：

- `FastAPI(...)` 实例与元信息
- `app.include_router(api_router)`
- CORS 中间件（`http://localhost:3000`、`http://127.0.0.1:3000`）
- 3 个异常处理器：`StarletteHTTPException` → 统一 error 格式、`RequestValidationError` → 422、`Exception` → 500

### 2. `app/api/routes/users.py`（+145 行）

承载全部用户接口，沿用原有 SQL 与鉴权逻辑：

| 接口 | 鉴权 | 说明 |
|------|------|------|
| `POST /users` | 否 | 注册，`IntegrityError` → 409「用户名已存在」 |
| `GET /users` | 否 | 用户列表 |
| `GET /users/me` | 是 | 当前用户信息 |
| `GET /users/{user_id}` | 是 | 非本人 → 403，不存在 → 404 |
| `PUT /users/{user_id}` | 是 | 更新昵称，`rowcount == 0` → 404 |
| `DELETE /users/{user_id}` | 是 | 删除用户，`rowcount == 0` → 404 |

### 3. `app/api/routes/auth.py`（+83 行）

- `POST /auth/login`：`OAuth2PasswordRequestForm` 表单登录
- 校验失败统一返回 `401 Incorrect username or password`，并带 `WWW-Authenticate: Bearer`
- 成功返回 `access_token` + `token_type: Bearer`
- 文件末尾新增登录限流辅助函数：`_is_rate_limited` / `_record_failed_attempt` / `_clear_failed_attempts`（窗口 60 秒，最多 5 次失败）

### 4. `app/api/routes/system.py`（重构前已建，本次生效）

- `GET /`：返回服务名与版本
- `GET /health`：返回 `{"status": "ok"}`

### 5. `app/api/router.py`（+6 行）

```python
from app.api.routes import auth, system, users

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)
```

### 6. `app/schemas/user.py`

`UserCreate`、`UserUpdate` 成为全局唯一定义，`main.py` 不再重复声明。

---

## 四、过程中修复的问题

| 问题 | 现象 | 修复 |
|------|------|------|
| `router.py` 未导入 `auth` | `NameError: name 'auth' is not defined`，服务无法启动 | import 补上 `auth` |
| `auth.py` 使用了未导入的 `time`、`defaultdict` | `NameError: name 'defaultdict' is not defined`，导入即失败 | 补充 `import time`、`from collections import defaultdict` |
| 新旧路由重复注册 | 启动日志 4 条 `Duplicate Operation ID`，旧代码可能遮蔽新代码 | 删除 `main.py` 中的旧路由 |

---

## 五、验证结果

启动方式：`d:\project\back` 下 `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`

- `python -W error::UserWarning -c "from app.main import app"` → 无告警、导入成功
- 接口回归：**14 项全部通过**

```
[PASS] GET /                  200
[PASS] GET /health            200
[PASS] POST /users            201（"User created"，确认走 routes/users.py）
[PASS] POST /users 重名        409
[PASS] POST /auth/login       200（返回 token）
[PASS] POST /auth/login 错误密码 401
[PASS] GET /users/me          200
[PASS] GET /users/me 无 token  401
[PASS] GET /users             200
[PASS] GET /users/{他人}       403
[PASS] PUT /users/{本人}       200
[PASS] DELETE /users/{本人}    200
[PASS] 删除后旧 token          401
```

测试数据已清理，库中仅保留原有用户：`testuser`、`REED`、`u_test_ff`。

---

## 六、遗留事项

1. **登录限流尚未接入**：`auth.py` 中的三个限流函数只是定义，`login()` 里还没调用，实际不生效。
2. **`GET /users` 无鉴权**：任何人不带 token 就能拿到全部用户列表（原设计如此，未改动）。
3. **`tb_refresh_token` 表已建但未使用**：当前仅单 Access Token，刷新令牌流程尚未实现。
4. **未纳入本次提交的本地文件**：`.trae/`（启动 skill）、`docs/init_all_tables.sql`（建表脚本）。

---

## 七、回滚方式

```powershell
git restore back/app/main.py back/app/api/router.py back/app/api/routes/users.py back/app/api/routes/auth.py back/app/schemas/user.py
```

或整体回到基线提交：

```powershell
git reset --hard 222a942
```

（`git reset --hard` 会丢弃所有未提交改动，执行前请确认。）
