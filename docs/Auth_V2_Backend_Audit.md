# Auth V2.0 后端现状审计

> 审计对象：`d:\project\back`（FastAPI + SQLAlchemy Core text SQL + MySQL 8.4）
> 审计时间：2026-11-24
> 审计方式：只读。仅阅读源码、执行 `SELECT` / `SHOW` / `information_schema` 查询与 `mysqldump --no-data`。
> 未修改任何业务代码，未安装依赖，未执行任何 `CREATE` / `ALTER` / `DELETE` / `UPDATE`，未清理任何数据。
> 敏感信息：`.env` 仅列出变量名，未输出任何真实密钥、数据库密码、Token 或 API Key。

---

## 0. 结论摘要

| 项 | 现状 |
|---|---|
| 认证方式 | JWT 双 Token（HS256），Access 15 分钟、Refresh 7 天 |
| 密码哈希 | PBKDF2-HMAC-SHA256，600,000 次迭代，16 字节随机盐 |
| Refresh Token 存储 | SHA-256 摘要存 `tb_refresh_token`，带 `family_id`（UUID4）与轮换链 `replaced_by` |
| 会话标识 | `family_id` 已等价于「一次登录会话」，但目前没有独立会话表，也没有设备/IP/最后活跃信息 |
| Access Token 即时撤销 | **不支持**。仅校验用户存在与 `is_active`，退出登录不会使未过期 Access Token 失效 |
| 登录限流 | **不存在**。全项目没有登录失败计数、验证码、IP 限制或通用 HTTP 限流中间件 |
| 请求限流 | 仅 AI 业务：`ai_guard_mutex` 行锁 + `ai_requests` 每日额度/并发控制 |
| 邮件能力 | **不存在**。无邮件发送代码、无验证码表、无相关依赖 |
| 头像能力 | `users.avatar_url` 列已存在，但后端无上传/读取接口，前端仅显示昵称首字 |
| 定时任务 | 仅 `plan_expiration_worker`（APScheduler，每 5 分钟检查计划到期） |
| 数据清理 | **不存在**。过期 Refresh Token、AI 请求日志、练习记录均无清理任务 |
| Redis / ORM Models / Alembic | 均未引入 |
| 数据库字符集 | 库默认 `utf8mb4 / utf8mb4_general_ci`；业务表多为 `utf8mb4_0900_ai_ci`，`ai_guard_mutex` 为 `utf8mb4_general_ci`（存在混用） |

---

## 1. 后端完整目录树

排除 `.venv`、`__pycache__`、`.git`、`.pytest_cache`：

```text
back/
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ database.py
│  ├─ response.py
│  ├─ api/
│  │  ├─ router.py
│  │  └─ routes/
│  │     ├─ auth.py
│  │     ├─ users.py
│  │     ├─ system.py
│  │     ├─ plans.py
│  │     ├─ plan_lifecycle.py
│  │     ├─ steps.py
│  │     ├─ schedules.py
│  │     ├─ daily_tasks.py
│  │     ├─ tasks.py
│  │     ├─ rollovers.py
│  │     ├─ active_tasks.py
│  │     ├─ active_steps.py
│  │     ├─ progress.py
│  │     ├─ statistics.py
│  │     ├─ knowledge.py
│  │     ├─ knowledge_ai.py
│  │     ├─ ai_practice.py
│  │     ├─ focus.py
│  │     └─ __init__.py
│  │  └─ __init__.py
│  ├─ core/
│  │  ├─ security.py
│  │  ├─ deps.py
│  │  ├─ clock.py
│  │  ├─ practice_ticket.py
│  │  └─ __init__.py
│  ├─ schemas/
│  │  ├─ auth.py
│  │  ├─ user.py
│  │  ├─ ai_practice.py
│  │  ├─ ai_practice_submit.py
│  │  ├─ knowledge.py
│  │  ├─ knowledge_ai.py
│  │  ├─ plan.py
│  │  ├─ schedule.py
│  │  ├─ step.py
│  │  ├─ task.py
│  │  ├─ active_task.py
│  │  ├─ active_step.py
│  │  ├─ rollover.py
│  │  ├─ statistics.py
│  │  ├─ focus.py
│  │  └─ __init__.py
│  ├─ services/
│  │  ├─ auth/
│  │  │  ├─ auth_service.py
│  │  │  └─ __init__.py
│  │  ├─ focus/
│  │  │  ├─ focus_service.py
│  │  │  └─ focus_statistics_service.py
│  │  ├─ knowledge/
│  │  │  ├─ ai_guard_service.py
│  │  │  ├─ ai_note_service.py
│  │  │  ├─ ai_practice_grading_service.py
│  │  │  ├─ ai_practice_history_service.py
│  │  │  ├─ ai_practice_service.py
│  │  │  ├─ ai_provider.py
│  │  │  ├─ ai_qa_service.py
│  │  │  ├─ ai_service.py
│  │  │  └─ note_service.py
│  │  ├─ plans/
│  │  │  ├─ plan_activation_service.py
│  │  │  ├─ plan_lifecycle_service.py
│  │  │  ├─ plan_rules.py
│  │  │  ├─ plan_service.py
│  │  │  └─ __init__.py
│  │  ├─ progress/
│  │  │  ├─ progress_service.py
│  │  │  └─ __init__.py
│  │  ├─ rollovers/
│  │  │  ├─ rollover_service.py
│  │  │  └─ __init__.py
│  │  ├─ schedules/
│  │  │  ├─ schedule_service.py
│  │  │  └─ __init__.py
│  │  ├─ statistics/
│  │  │  ├─ statistics_service.py
│  │  │  └─ streak_rules.py
│  │  ├─ steps/
│  │  │  ├─ active_step_service.py
│  │  │  ├─ step_service.py
│  │  │  └─ __init__.py
│  │  ├─ tasks/
│  │  │  ├─ active_task_service.py
│  │  │  ├─ daily_task_service.py
│  │  │  ├─ task_service.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ repositories/
│  │  ├─ focus/
│  │  │  ├─ focus_repository.py
│  │  │  └─ focus_statistics_repository.py
│  │  ├─ knowledge/
│  │  │  ├─ ai_guard_repository.py
│  │  │  ├─ note_repository.py
│  │  │  ├─ practice_repository.py
│  │  │  └─ review_repository.py
│  │  ├─ plans/
│  │  │  ├─ plan_lifecycle_repository.py
│  │  │  ├─ plan_repository.py
│  │  │  └─ __init__.py
│  │  ├─ progress/
│  │  │  ├─ progress_repository.py
│  │  │  └─ __init__.py
│  │  ├─ rollovers/
│  │  │  ├─ rollover_repository.py
│  │  │  └─ __init__.py
│  │  ├─ schedules/
│  │  │  ├─ schedule_repository.py
│  │  │  └─ __init__.py
│  │  ├─ statistics/
│  │  │  └─ statistics_repository.py
│  │  ├─ steps/
│  │  │  ├─ active_step_repository.py
│  │  │  ├─ step_repository.py
│  │  │  └─ __init__.py
│  │  └─ tasks/
│  │     ├─ active_task_repository.py
│  │     ├─ daily_task_repository.py
│  │     ├─ task_repository.py
│  │     └─ __init__.py
│  └─ jobs/
│     └─ plan_expiration_worker.py
├─ tests/
│  ├─ test_ai_a3_structure.py
│  ├─ test_ai_a4_qa.py
│  ├─ test_ai_a5_generate.py
│  ├─ test_ai_a5_grade.py
│  ├─ test_knowledge_ai.py
│  ├─ test_lifecycle_regression.py
│  ├─ test_progress_regression.py
│  └─ test_rollover_regression.py
├─ requirements.txt
├─ test_db.py
└─ .env（仅变量名见第 6 节）
```

> 说明：路由层没有 `app/api/routes/repositories` 之类的独立 Auth Repository；认证相关持久化逻辑集中在 `app/services/auth/auth_service.py` 内，直接使用 `text()` SQL。项目整体没有 ORM Models。

---

## 2. 关键源码

### 2.1 应用入口与配置

`app/main.py`：

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.response import error,success

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

app.include_router(api_router)

# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 统一处理 HTTP 异常
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
        detail = exc.detail

        # 保留原始 detail，特别是认证错误中的业务 code
        response = JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": (
                    detail.get("message", "Request failed")
                    if isinstance(detail, dict)
                    else str(detail)
                ),
                "detail": jsonable_encoder(detail),
                "data": None,
            },
        )

        # 保留认证相关响应头
        if exc.headers:
            response.headers.update(exc.headers)

        return response

# 统一处理请求参数验证异常
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return error(
        code=422,
        message="Request validation failed",
        data=exc.errors(),
    )


# 统一处理未捕获异常
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return error(code=500, message="服务器内部错误")
```

`app/config.py`：

```python

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    AI_ENABLED: bool = False
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-flash"

    AI_MAX_NOTE_CHARS: int = 12000
    AI_MAX_OUTPUT_CHARS: int = 12000
    AI_STREAM_CHUNK_CHARS: int = 240
    AI_MAX_OUTPUT_TOKENS: int = 3500

    # 共享额度
    AI_USER_DAILY_LIMIT: int = 10
    AI_GLOBAL_DAILY_LIMIT: int = 80

    # 共享并发
    AI_USER_CONCURRENCY: int = 1
    AI_GLOBAL_CONCURRENCY: int = 2

    # 整条流的最大执行时间与租约有效期
    AI_MAX_STREAM_SECONDS: int = 120
    AI_LEASE_SECONDS: int = 180

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
```

`app/database.py`：

```python

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.config import settings

DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
    query={"charset": "utf8mb4"},
)



engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
#北京时区，保证now是+8
    connect_args={
        "init_command": "SET time_zone = '+08:00'",
    },
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`app/response.py`：

```python
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success(data=None, message="success", code=200):
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "data": jsonable_encoder(data)#转换成json格式
        }
    )


def error(code=400, message="Request failed", data=None):
    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "message": message,
            "data": jsonable_encoder(data)
        }
    )
```

### 2.2 认证核心

`app/core/security.py`：

```python
#hash和jwt的工具函数
#hashcode
import hashlib
import hmac
import secrets
ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000
import uuid

# jwt
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError,ExpiredSignatureError

from app.config import settings
JWT_ALGORITHM = "HS256"

# 密码哈希函数
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    ).hex()
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest}"

# 密码验证函数
def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest = stored_hash.split("$")
        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    if algorithm != ALGORITHM:
        return False
    if not 100000 <= iterations_int <= 2000000:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations_int
    ).hex()
    return hmac.compare_digest(computed, digest)


# 创建JWT令牌


def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    now = datetime.now(timezone.utc)

    payload = data.copy()

    payload.update({
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
        # jti 保证即使同一秒内重复签发，token 也互不相同
        "jti": str(uuid.uuid4()),
    })

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


#access token
def create_access_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        token_type="access",
    )


#refresh token
def create_refresh_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        token_type="refresh",
    )



# 解码令牌

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )
    except InvalidTokenError:
        return None


def decode_access_token(token: str) -> dict | None:
    payload = decode_token(token)

    if payload is None:
        return None

    if payload.get("type") != "access":
        return None

    return payload


def decode_access_token_detailed(token: str) -> tuple[dict | None, str | None]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )

    except ExpiredSignatureError:
        return None, "ACCESS_EXPIRED"

    except InvalidTokenError:
        return None, "INVALID_TOKEN"

    if payload.get("type") != "access":
        return None, "TOKEN_TYPE_INVALID"

    return payload, None


def decode_refresh_token(token: str) -> dict | None:
    payload = decode_token(token)

    if payload is None:
        return None

    if payload.get("type") != "refresh":
        return None

    return payload


#refresh token 摘要
def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

#登录会话id

def create_family_id() -> str:
    return str(uuid.uuid4())
```

`app/core/deps.py`：

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token_detailed
from app.database import get_db


# 从请求头中提取 Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 根据 Token 获取当前用户
def get_current_user(
    #依赖注入
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
#check token
    payload, error_code = decode_access_token_detailed(token)

    if payload is None:
        if error_code == "ACCESS_EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "ACCESS_EXPIRED",
                    "message": "Access token expired",
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": error_code,
                "message": "Invalid access token",
            },
        )

    user_id = payload.get("sub")

    if user_id is None or not str(user_id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN_PAYLOAD",
                "message": "Invalid token payload",
            },
        )

    user_id = int(user_id)

    sql = text("""
    SELECT id, username, nickname, is_active
    FROM users
    WHERE id = :user_id
""")

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()
    #check user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
    "code": "USER_NOT_FOUND",
    "message": "User not found",
    }
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_DISABLED",
                "message": "Account is disabled",
            },
        )

    return dict(user)
```

`app/core/clock.py`：

```python

from datetime import date, datetime, timedelta, timezone


# 业务日期统一按东八区计算，避免服务器使用 UTC 时「今日任务」错位
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))


def business_today() -> date:
    """返回东八区（Asia/Shanghai）的当前日期"""

    return datetime.now(BUSINESS_TIMEZONE).date()
```

`app/schemas/auth.py`：

```python
#登录接口规定

from pydantic import BaseModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

# 刷新 Token 请求体
class RefreshRequest(BaseModel):
    refresh_token: str
```

`app/api/routes/auth.py`：

```python
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import verify_password
from app.services.auth.auth_service import issue_token_pair
from app.response import success

from app.schemas.auth import RefreshRequest
from app.services.auth.auth_service import (
    issue_token_pair,
    rotate_refresh_token,
    revoke_current_session,
    revoke_all_sessions,
)


from app.core.deps import get_current_user

router = APIRouter()
#登录接口,返回令牌和token种类

@router.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    #  查询用户
    sql = text("""
        SELECT id, username, password_hash, nickname, is_active
        FROM users
        WHERE username = :username
    """)

    result = db.execute(
        sql,
        {"username": form_data.username},
    )

    user = result.mappings().first()

    #  验证账号密码
    if user is None or not verify_password(
        form_data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACCOUNT_DISABLED",
                "message": "Account is disabled",
            },
        )   

    # 创建双 Token，并登记 Refresh Token 摘要
    token_pair = issue_token_pair(
        db=db,
        user_id=user["id"],
    )

    # 返回 Token 和用户信息 
    return success(
        data={
            **token_pair,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "nickname": user["nickname"],
            },
        },
        message="登录成功",
        code=200,
    )



# 刷新 Token 接口
@router.post("/auth/refresh")
def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
):
    token_pair = rotate_refresh_token(
        db=db,
        refresh_token=request.refresh_token,
    )

    return success(
        data=token_pair,
        message="Token refreshed",
        code=200,
    )



#退出当前会话
@router.post("/auth/logout")
def logout(
    request: RefreshRequest,
    db: Session = Depends(get_db),
):
    revoke_current_session(
        db=db,
        refresh_token=request.refresh_token,
    )

    return success(
        message="Logged out successfully",
    )



#退出全部会话
@router.post("/auth/logout-all")
def logout_all(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    revoke_all_sessions(
        db=db,
        user_id=current_user["id"],
    )

    return success(
        message="All sessions logged out successfully",
    )
```

`app/services/auth/auth_service.py`：

```python

from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_family_id,
    hash_refresh_token,
    decode_refresh_token,
)
from app.schemas.auth import TokenPair


class TokenData(TypedDict):
    token_pair: dict[str, Any]
    token_hash: str
    expires_at: datetime


def _utc_now() -> datetime:
    """返回 UTC 时间，适配数据库中的无时区 DATETIME"""

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


def _build_token_pair(
    user_id: int,
    family_id: str,
) -> TokenData:
    """
    创建 Access Token 和 Refresh Token。

    本函数不执行数据库操作。
    """

    access_token = create_access_token({
        "sub": str(user_id),
    })

    refresh_token = create_refresh_token({
        "sub": str(user_id),
        "family_id": family_id,
    })

    token_hash = hash_refresh_token(refresh_token)

    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise ValueError(
            "Refresh Token generation failed"
        )

    expires_at = datetime.fromtimestamp(
        payload["exp"],
        tz=timezone.utc,
    ).replace(tzinfo=None)

    token_pair = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=(
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        ),
    )

    return {
        "token_pair": token_pair.model_dump(),
        "token_hash": token_hash,
        "expires_at": expires_at,
    }


def _insert_refresh_token(
    db: Session,
    user_id: int,
    family_id: str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """向数据库保存 Refresh Token 摘要"""

    sql = text("""
        INSERT INTO tb_refresh_token (
            user_id,
            token_hash,
            family_id,
            expires_at
        )
        VALUES (
            :user_id,
            :token_hash,
            :family_id,
            :expires_at
        )
    """)

    db.execute(
        sql,
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "family_id": family_id,
            "expires_at": expires_at,
        },
    )


def issue_token_pair(
    db: Session,
    user_id: int,
) -> dict:
    """新登录：创建 family 并签发 Token Pair"""

    family_id = create_family_id()

    token_data = _build_token_pair(
        user_id=user_id,
        family_id=family_id,
    )

    try:
        _insert_refresh_token(
            db=db,
            user_id=user_id,
            family_id=family_id,
            token_hash=token_data["token_hash"],
            expires_at=token_data["expires_at"],
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return token_data["token_pair"]


def rotate_refresh_token(
    db: Session,
    refresh_token: str,
) -> dict:
    """
    使用旧 Refresh Token 换取新 Token Pair。

    检测到已轮换 Token 再次使用时，
    撤销整个 family。

    重放检测后的撤销必须先提交事务，
    再向客户端返回 401。
    """

    # 1. 验证 JWT
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    raw_user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if raw_user_id is None or not isinstance(
        family_id, str
    ) or not family_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    try:
        user_id = int(raw_user_id)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id",
        )

    token_hash = hash_refresh_token(refresh_token)

    replay_detected = False

    token_pair: dict[str, Any] | None = None

    try:
        # 2. 锁定旧 Refresh Token
        select_sql = text("""
            SELECT
                id,
                user_id,
                family_id,
                expires_at,
                revoked_at,
                replaced_by
            FROM tb_refresh_token
            WHERE token_hash = :token_hash
            FOR UPDATE
        """)

        old_token = db.execute(
            select_sql,
            {"token_hash": token_hash},
        ).mappings().first()

        if old_token is None:
            raise HTTPException(
                status_code=401,
                detail="Refresh token not found",
            )

        # 3. 验证 JWT 与数据库记录是否匹配
        if (
            old_token["user_id"] != user_id
            or old_token["family_id"] != family_id
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token mismatch",
            )

        # 4. 检查用户账号是否有效
        user_sql = text("""
            SELECT is_active
            FROM users
            WHERE id = :user_id
            FOR UPDATE
        """)

        user = db.execute(
            user_sql,
            {"user_id": user_id},
        ).mappings().first()

        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "USER_NOT_FOUND",
                    "message": "User not found",
                },
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ACCOUNT_DISABLED",
                    "message": "Account is disabled",
                },
            )

        # 获取锁之后再读取当前时间
        now = _utc_now()

        # 5. 检查 Token 是否发生重放
        if old_token["replaced_by"] is not None:

            replay_detected = True

            # 撤销整个 family 的有效 Refresh Token
            revoke_sql = text("""
                UPDATE tb_refresh_token
                SET revoked_at = :now
                WHERE user_id = :user_id
                  AND family_id = :family_id
                  AND revoked_at IS NULL
            """)

            db.execute(
                revoke_sql,
                {
                    "now": now,
                    "user_id": user_id,
                    "family_id": family_id,
                },
            )

        # 6. 普通失效检查
        elif (
            old_token["revoked_at"] is not None
            or old_token["expires_at"] <= now
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token already revoked or expired",
            )

        else:
            # 7. 正常轮换：生成新的 Token Pair
            token_data = _build_token_pair(
                user_id=user_id,
                family_id=family_id,
            )

            new_token_hash = token_data["token_hash"]

            # 8. 更新旧 Token
            update_sql = text("""
                UPDATE tb_refresh_token
                SET
                    revoked_at = :now,
                    replaced_by = :new_token_hash
                WHERE id = :id
                  AND revoked_at IS NULL
                  AND replaced_by IS NULL
                  AND expires_at > :now
            """)

            update_result = cast(
                CursorResult[Any],
                db.execute(
                    update_sql,
                    {
                        "now": now,
                        "new_token_hash": new_token_hash,
                        "id": old_token["id"],
                    },
                ),
            )

            if update_result.rowcount != 1:
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token has already been used",
                )

            # 9. 保存新 Refresh Token
            _insert_refresh_token(
                db=db,
                user_id=user_id,
                family_id=family_id,
                token_hash=new_token_hash,
                expires_at=token_data["expires_at"],
            )

            token_pair = token_data["token_pair"]

        # 10. 统一提交事务
        # 重放撤销和正常轮换都在这里提交
        db.commit()

    except Exception:
        db.rollback()
        raise

    # 11. 重放发生时，撤销操作已经提交
    if replay_detected:
        raise HTTPException(
            status_code=401,
            detail=(
                "Refresh token replay detected; "
                "session revoked"
            ),
        )

    if token_pair is None:
        raise RuntimeError(
            "Refresh Token rotation did not produce a token pair"
        )

    return token_pair


def revoke_current_session(
    db: Session,
    refresh_token: str,
) -> None:
    """
    撤销当前 Refresh Token 所属的整个 family。
    """

    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    raw_user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if raw_user_id is None or not isinstance(
        family_id, str
    ) or not family_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    try:
        user_id = int(raw_user_id)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    token_hash = hash_refresh_token(refresh_token)

    try:
        # 1. 锁定并验证当前 Token
        select_sql = text("""
            SELECT user_id, family_id
            FROM tb_refresh_token
            WHERE token_hash = :token_hash
            FOR UPDATE
        """)

        record = db.execute(
            select_sql,
            {"token_hash": token_hash},
        ).mappings().first()

        if (
            record is None
            or record["user_id"] != user_id
            or record["family_id"] != family_id
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token not found",
            )

        now = _utc_now()

        # 2. 撤销当前 family 全部有效 Token
        revoke_sql = text("""
            UPDATE tb_refresh_token
            SET revoked_at = :now
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
        """)

        db.execute(
            revoke_sql,
            {
                "now": now,
                "user_id": user_id,
                "family_id": family_id,
            },
        )

        # 3. 提交事务
        db.commit()

    except Exception:
        db.rollback()
        raise


def revoke_all_sessions(
    db: Session,
    user_id: int,
) -> None:
    """撤销当前用户的所有 Refresh Token"""

    now = _utc_now()

    try:
        sql = text("""
            UPDATE tb_refresh_token
            SET revoked_at = :now
            WHERE user_id = :user_id
              AND revoked_at IS NULL
        """)

        db.execute(
            sql,
            {
                "now": now,
                "user_id": user_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
```

### 2.3 用户模块

`app/schemas/user.py`：

```python
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str


class UserUpdate(BaseModel):
    nickname: str
    
```

`app/api/routes/users.py`：

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.response import success, error
from app.core.deps import get_current_user
from app.schemas.user import UserCreate, UserUpdate

from sqlalchemy.exc import IntegrityError
from app.core.security import hash_password


router = APIRouter()


@router.post("/users", status_code=201)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    stored_hash = hash_password(user.password)

    sql = text("""
        INSERT INTO users
        (username, password_hash, nickname, created_at, updated_at)
        VALUES (:username, :password_hash, :nickname, NOW(), NOW())
    """)

    try:
        result = db.execute(sql, {
            "username": user.username,
            "password_hash": stored_hash,
            "nickname": user.nickname,
        })
        db.commit()

        return success({
            "id": result.lastrowid,
            "username": user.username,
            "nickname": user.nickname,
        }, message="User created", code=201)

    except IntegrityError:
        db.rollback()
        return error(409, "用户名已存在")

    except Exception:
        db.rollback()
        raise


@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
    """)

    result = db.execute(sql)
    users = [dict(row) for row in result.mappings().all()]

    return success(users)


@router.get("/users/me")
def get_me(current_user=Depends(get_current_user)):
    return success(current_user)


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return success(dict(user))


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    user: UserUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("""
        UPDATE users
        SET nickname = :nickname, updated_at = NOW()
        WHERE id = :user_id
    """)

    result = db.execute(sql, {
        "nickname": user.nickname,
        "user_id": user_id,
    })

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="User not found")

    db.commit()
    return success(message="User updated")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("DELETE FROM users WHERE id = :user_id")

    result = db.execute(sql, {"user_id": user_id})

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="User not found")

    db.commit()
    return success(message="User deleted")
```

### 2.4 全局异常处理

全局异常处理全部位于 `app/main.py`，共三层：

1. `StarletteHTTPException` 处理器：保留 `detail`（含认证业务 `code`），统一输出 `{code, message, detail, data}`，并保留 `exc.headers`（因此 `WWW-Authenticate: Bearer` 不会丢失）。
2. `RequestValidationError` 处理器：统一返回 422，`data` 为 Pydantic 错误列表。
3. `Exception` 兜底处理器：统一返回 500 `服务器内部错误`，**不记录日志**，也不回显异常详情。

需要注意的现状：

- `HTTPException(detail="字符串")` 会被包装成 `message` 为该字符串、`detail` 为该字符串，前端 `apiFetch` 已兼容两种形态。
- `users.delete_user` 未捕获 `IntegrityError`；当用户仍被 `study_plans` / `study_records` 引用时（`ON DELETE NO ACTION`），会落到 500 兜底，而不是可读的业务错误。
- 兜底 500 处理器未调用 `logger.exception`，认证类异常排查会缺少服务端日志证据。

### 2.5 现有登录限流 / 请求限流 / AI Guard

`app/services/knowledge/ai_guard_service.py`：

```python

"""A2 AI 公共守卫：共享额度、并发限制、流式请求状态结算。"""

import asyncio
import json
import logging
from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import uuid4

import anyio
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.knowledge import ai_guard_repository
from app.services.knowledge.ai_service import _sse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Admission:
    """通过 MySQL 准入检查的请求；主题生成不绑定笔记 ID。"""

    request_id: str
    user_id: int
    note_id: int | None


def _reject_limit(code: str, message: str) -> None:
    """额度和并发拒绝都返回 HTTP 429，以及可识别的业务错误码。"""
    raise HTTPException(
        status_code=429,
        detail={"code": code, "message": message},
    )


def admit_request(
    db: Session,
    user_id: int,
    note_id: int | None,
    operation: str = "SUMMARY",
) -> Admission:
    """在同一个数据库事务中原子检查额度、并发，并写入 RUNNING。

    多进程通过 ai_guard_mutex 的 FOR UPDATE 串行准入；
    在调用 DeepSeek 之前 COMMIT，避免模型生成期间占用数据库行锁。
    """
    allowed_operations = {
        "SUMMARY",
        "GENERATE",
        "ORGANIZE",
        "ASK",
        "PRACTICE_GENERATE",
        "PRACTICE_GRADE",
    }

    if operation not in allowed_operations:
        raise ValueError("Unsupported AI operation")

    if settings.AI_LEASE_SECONDS <= settings.AI_MAX_STREAM_SECONDS:
        raise RuntimeError("AI lease must exceed stream timeout")

    request_id = str(uuid4())
    today = business_today()

    try:
        ai_guard_repository.lock_admission(db)

        global_daily, user_daily = ai_guard_repository.daily_counts(
            db=db,
            request_date=today,
            user_id=user_id,
        )

        # A5 练习生成至少需要剩余两次请求额度：
        # 一次用于题目生成，一次用于后续简答题批改。
        # 这里只检查，不预留额度。
        if operation == "PRACTICE_GENERATE":
            if user_daily + 2 > settings.AI_USER_DAILY_LIMIT:
                _reject_limit(
                    "AI_PRACTICE_QUOTA_INSUFFICIENT",
                    "至少需要剩余 2 次 AI 调用额度才能生成练习",
                )

            if global_daily + 2 > settings.AI_GLOBAL_DAILY_LIMIT:
                _reject_limit(
                    "AI_PRACTICE_GLOBAL_QUOTA_INSUFFICIENT",
                    "全站剩余 AI 调用额度不足，暂时无法生成练习",
                )


        if global_daily >= settings.AI_GLOBAL_DAILY_LIMIT:
            _reject_limit(
                "AI_GLOBAL_DAILY_LIMIT",
                "今日全站 AI 调用额度已用完",
            )

        if user_daily >= settings.AI_USER_DAILY_LIMIT:
            _reject_limit(
                "AI_USER_DAILY_LIMIT",
                "你今天的 AI 调用额度已用完",
            )

        global_active, user_active = ai_guard_repository.active_counts(
            db=db,
            user_id=user_id,
        )

        if global_active >= settings.AI_GLOBAL_CONCURRENCY:
            _reject_limit(
                "AI_GLOBAL_BUSY",
                "AI 服务繁忙，请稍后重试",
            )

        if user_active >= settings.AI_USER_CONCURRENCY:
            _reject_limit(
                "AI_USER_BUSY",
                "你已有正在生成的 AI 请求",
            )

        # 一旦成功准入，便占用当天一次请求额度；失败不自动退还。
        ai_guard_repository.insert_request(
            db=db,
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
            request_date=today,
            lease_seconds=settings.AI_LEASE_SECONDS,
            operation=operation,
        )

        db.commit()

        return Admission(
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
        )

    except Exception:
        db.rollback()
        raise


def _finish_request_record(
    request_id: str,
    status: str,
    usage: dict | None,
) -> None:
    """独立短事务结算状态；未获取用量时写 NULL 而不是 0。"""

    usage = usage or {}

    def valid_token_count(value: object) -> int | None:
        # bool 是 int 的子类，但 True/False 不是合法 Token 用量。
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return value

        return None

    with SessionLocal() as db:
        try:
            ai_guard_repository.finish_request(
                db=db,
                request_id=request_id,
                status=status,
                prompt_tokens=valid_token_count(
                    usage.get("prompt_tokens")
                ),
                completion_tokens=valid_token_count(
                    usage.get("completion_tokens")
                ),
            )
            db.commit()

        except Exception:
            db.rollback()
            raise


def _event_name(frame: str) -> str:
    """只解析应用内部构造的 SSE 帧，不解析厂商原始响应。"""
    return frame.split("\n", 1)[0].removeprefix("event: ").strip()


def _event_data(frame: str) -> dict:
    for line in frame.splitlines():
        if line.startswith("data: "):
            value = json.loads(line[6:])
            return value if isinstance(value, dict) else {}

    return {}


async def metered_ai_stream(
    admission: Admission,
    event_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """与具体 AI 业务无关的流式生命周期管理器。

    - start/delta/reviewing：直接转发，为临时结果；
    - done：先写 SUCCESS 再发送成功事件；
    - blocked/error：结算对应状态，再发送终止事件；
    - 取消、超时与意外错误：尽力落库，避免长期占用并发。
    """

    final_status = "ERROR"
    usage: dict | None = None
    recorded = False

    async def settle(status: str) -> None:
        nonlocal final_status, recorded

        final_status = status

        # 同步 SQLAlchemy 写入放入工作线程；
        # 成功返回才算结算完成。
        await anyio.to_thread.run_sync(
            _finish_request_record,
            admission.request_id,
            status,
            usage,
        )

        recorded = True

    try:
        async with asyncio.timeout(settings.AI_MAX_STREAM_SECONDS):

            # 业务流必须是 AsyncGenerator，以支持 aclose() 清理连接。
            async with aclosing(event_stream):

                async for frame in event_stream:
                    event = _event_name(frame)

                    if event not in {"done", "blocked", "error"}:
                        yield frame
                        continue

                    payload = _event_data(frame)

                    if isinstance(payload.get("usage"), dict):
                        usage = payload["usage"]

                    if event == "done":
                        # 必须先提交数据库，才发送成功事件。
                        await settle("SUCCESS")
                        yield frame
                        return

                    if event == "blocked":
                        await settle("BLOCKED")
                        yield frame
                        return

                    # 业务流可通过状态元数据声明 STALE。
                    # Guard 不需要认识 NOTE_CHANGED 等业务错误码。
                    error_status = (
                        "STALE"
                        if payload.get("status") == "STALE"
                        else "ERROR"
                    )

                    await settle(error_status)
                    yield frame
                    return

                # 没有终止事件就结束，属于协议不完整。
                # 不允许视为成功。
                await settle("ERROR")

                yield _sse(
                    "error",
                    {
                        "code": "AI_STREAM_INTERRUPTED",
                        "message": "AI 响应提前结束",
                    },
                )

    except TimeoutError:
        # 先把 TIMEOUT 写入数据库，再向客户端报告超时。
        try:
            await settle("TIMEOUT")

        except Exception:
            logger.exception(
                "ai_timeout_settlement_failed request_id=%s",
                admission.request_id,
            )

            yield _sse(
                "error",
                {
                    "code": "AI_INTERNAL_ERROR",
                    "message": "AI 生成失败",
                },
            )

        else:
            yield _sse(
                "error",
                {
                    "code": "AI_TOTAL_TIMEOUT",
                    "message": "本次 AI 生成超时",
                },
            )

    except asyncio.CancelledError:
        final_status = "CANCELLED"
        raise

    except Exception:
        final_status = "ERROR"

        logger.exception(
            "ai_stream_unexpected request_id=%s",
            admission.request_id,
        )

        yield _sse(
            "error",
            {
                "code": "AI_INTERNAL_ERROR",
                "message": "AI 生成失败",
            },
        )

    finally:
        if not recorded:
            try:
                # shield 降低取消信号打断结算的风险；
                # 但不能抵御进程强制终止。
                #，就再尝试把状态写入数据库
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(
                        _finish_request_record,
                        admission.request_id,
                        final_status,
                        usage,
                    )

            except Exception:
                # RUNNING 可能残留。
                # 租约到期后不再计入并发数量。
                logger.exception(
                    "ai_request_finalization_failed request_id=%s",
                    admission.request_id,
                )
```

`app/repositories/knowledge/ai_guard_repository.py`：

```python

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session
##当多个用户同时调用 AI 时，利用 MySQL 统一管理请求数量、并发额度和请求状态，避免超过系统设置的限制。

def lock_admission(db: Session) -> None:
    """
    统一串行化 AI 请求准入。

    所有进程必须先获得这把数据库行锁，
    才能检查共享额度并插入新请求。
    """
    row = db.execute(
        text("""
            SELECT id
            FROM ai_guard_mutex
            WHERE id = 1
            FOR UPDATE
        """)
    ).scalar_one_or_none()
#是在确保数据库中确实存在这条锁记录
    if row is None:
        raise RuntimeError("AI admission mutex is missing")

#检查用户和全局请求数量
def daily_counts(
    db: Session,
    request_date: date,
    user_id: int,
) -> tuple[int, int]:
    global_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
        """),
        {"request_date": request_date},
    ).scalar_one()

    user_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
              AND user_id = :user_id
        """),
        {
            "request_date": request_date,
            "user_id": user_id,
        },
    ).scalar_one()

    return int(global_count), int(user_count)


def active_counts(
    db: Session,
    user_id: int,
) -> tuple[int, int]:
    global_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE status = 'RUNNING'
              AND leased_until > UTC_TIMESTAMP(6)
        """)#租约截止时间大于当前时间，说明请求正在运行
    ).scalar_one()

    user_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE user_id = :user_id
              AND status = 'RUNNING'
              AND leased_until > UTC_TIMESTAMP(6)
        """),
        {"user_id": user_id},
    ).scalar_one()

    return int(global_count), int(user_count)

#登记 AI 请求

def insert_request(
    db: Session,
    request_id: str,
    user_id: int,
    note_id: int | None,
    request_date: date,
    lease_seconds: int,
    operation: str = "SUMMARY",
) -> None:
    db.execute(
        text("""
            INSERT INTO ai_requests (
                request_id,
                user_id,
                note_id,
                operation,
                request_date,
                status,
                leased_until
            )
            VALUES (
                :request_id,
                :user_id,
                :note_id,
                :operation,
                :request_date,
                'RUNNING',
                DATE_ADD(
                    UTC_TIMESTAMP(6),
                    INTERVAL :lease_seconds SECOND
                )
            )
        """),
        {
            "request_id": request_id,
            "user_id": user_id,
            "note_id": note_id,
            "operation": operation,
            "request_date": request_date,
            "lease_seconds": lease_seconds,
        },
    )


def finish_request(
    db: Session,
    request_id: str,
    status: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> None:
    db.execute(
        text("""
            UPDATE ai_requests
            SET status = :status,
                finished_at = UTC_TIMESTAMP(6),
                prompt_tokens = :prompt_tokens,
                completion_tokens = :completion_tokens
            WHERE request_id = :request_id
              AND status = 'RUNNING'
        """),
        {
            "request_id": request_id,
            "status": status,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )
```

现状要点：

- **只有 AI 业务有限流**：`operation` 白名单为 `SUMMARY / GENERATE / ORGANIZE / ASK / PRACTICE_GENERATE / PRACTICE_GRADE`。
- 准入事务使用 `ai_guard_mutex(id=1) FOR UPDATE` 串行化所有进程，然后检查「全站当日总数」「用户当日总数」「全站 RUNNING 租约并发」「用户 RUNNING 租约并发」，通过后写入 `ai_requests` 并立即 `COMMIT`，避免模型生成期间长期持锁。
- 额度扣减语义为「准入即计数，失败不退还」。
- 没有针对 `/auth/login`、`/users` 注册、`/auth/refresh` 的任何限流或失败计数。
- 没有通用 IP 限流、没有请求体大小限制、没有 SlowAPI/中间件级限流。

### 2.6 定时任务 / 后台任务 / 日志 / 数据清理

`app/jobs/plan_expiration_worker.py`：

```python

import logging
import sys
from datetime import timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.plans import plan_lifecycle_repository
from app.services.plans import plan_lifecycle_service


logger = logging.getLogger(__name__)


def run_due_plan_check() -> dict:
    """执行一次计划到期检查"""

    today = business_today()

    # 先读取需要处理的计划 ID
    with SessionLocal() as db:
        plan_ids = (
            plan_lifecycle_repository.find_expired_plan_ids(
                db=db,
                today=today,
                limit=500,
            )
        )

    ended_count = 0
    failed_count = 0

    # 每个计划使用独立事务。
    # 某个计划失败，不影响其他计划。
    for plan_id in plan_ids:
        with SessionLocal() as db:
            try:
                changed = (
                    plan_lifecycle_service.expire_due_plan(
                        db=db,
                        plan_id=plan_id,
                        today=today,
                    )
                )

                if changed:
                    ended_count += 1

            except Exception:
                failed_count += 1

                logger.exception(
                    "计划 %s 自动到期处理失败",
                    plan_id,
                )

    result = {
        "checked_count": len(plan_ids),
        "ended_count": ended_count,
        "failed_count": failed_count,
    }

    logger.info("到期检查结果：%s", result)

    if len(plan_ids) == 500:
        logger.warning(
            "本次达到500条处理上限，剩余计划将在下次检查"
        )

    return result


def main():
    """启动独立的定时任务进程"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # 使用 UTC 调度间隔，
    # 业务日期始终由 business_today() 判断。
    scheduler = BlockingScheduler(
        timezone=timezone.utc,
    )

    scheduler.add_job(
        run_due_plan_check,
        trigger="interval",
        minutes=5,
        id="expire_study_plans",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        replace_existing=True,
    )

    # 启动时立即检查一次。
    # 避免程序重启后遗漏已经到期的计划。
    run_due_plan_check()

    logger.info("计划自动到期 Worker 已启动")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 正在停止")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    if "--once" in sys.argv:
        logging.basicConfig(level=logging.INFO)
        print(run_due_plan_check())
    else:
        main()
```

现状要点：

- 唯一的后台进程是「计划到期 Worker」，APScheduler `BlockingScheduler`，每 5 分钟执行一次，启动时立即执行一次。
- 该 Worker 需要独立启动（`python -m app.jobs.plan_expiration_worker`），不由 FastAPI 进程托管。
- 日志仅使用标准库 `logging`：`ai_guard_service` 记录结算失败，Worker 记录到期处理结果；没有集中日志表、没有审计事件表。
- **没有任何数据清理任务**：过期/已撤销的 Refresh Token、`ai_requests` 历史、AI 临时状态均不会自动清理。
- 没有 Celery、没有 Redis、没有消息队列。
- `requirements.txt` 未声明 `APScheduler`，但虚拟环境已安装 `apscheduler 3.11.3`；在全新环境按 `requirements.txt` 安装会导致 Worker 导入失败。

### 2.7 依赖清单

`requirements.txt`：

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
click==8.5.0
cryptography==50.0.2
fastapi==0.143.3
h11==0.16.0
httptools==0.9.0
httpx==0.28.1
idna==3.20
mysql-connector-python==26.7.0
opentelemetry-api==1.45.1
pydantic==2.14.1
pydantic-settings==2.16.0
pydantic_core==2.50.1
pytest==9.2.0
PyJWT==2.15.1
PyMySQL==1.2.3
python-dotenv==1.2.4
python-multipart==0.0.33
PyYAML==6.0.3
SQLAlchemy==2.1.5
starlette==1.8.0
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.54.0
watchfiles==1.3.0
websockets==17.2
```

补充核对：

- `PyJWT==2.15.1` 用于 JWT 签发/校验。
- `PyMySQL==1.2.3` + `SQLAlchemy==2.1.5` 为数据访问层。
- `python-multipart==0.0.33` 支撑 `OAuth2PasswordRequestForm`。
- `httpx==0.28.1` 已存在，可复用于后续调用邮件服务 HTTP API（但当前未被用于邮件）。
- 缺少 `APScheduler` 声明（见上）。
- 无 `passlib` / `bcrypt` / `argon2`，密码哈希为自实现 PBKDF2。
- 无 `email-validator`；后续若用 `EmailStr` 需要新增依赖（或改用正则校验）。

---


## 3. 数据库审计

数据库：`smart_study_planner`，MySQL `8.4.9`，本次审计全部为只读查询。

### 3.1 数据表与精确行数

| # | 表名 | 精确行数 | 引擎 / 排序规则 | 说明 |
|---|---|---:|---|---|
| 1 | `users` | 47 | InnoDB / utf8mb4_0900_ai_ci | 用户主表 |
| 2 | `tb_refresh_token` | 210 | InnoDB / utf8mb4_0900_ai_ci | Refresh Token 轮换链 |
| 3 | `ai_requests` | 16 | InnoDB / utf8mb4_0900_ai_ci | AI 额度/并发/用量日志 |
| 4 | `ai_guard_mutex` | 1 | InnoDB / utf8mb4_general_ci | AI 准入全局行锁（必须保留 `id=1`） |
| 5 | `study_plans` | 39 | InnoDB / utf8mb4_0900_ai_ci | 学习计划 |
| 6 | `plan_steps` | 91 | InnoDB / utf8mb4_0900_ai_ci | 计划步骤（自引用树） |
| 7 | `daily_tasks` | 280 | InnoDB / utf8mb4_0900_ai_ci | 每日任务 |
| 8 | `schedule_entries` | 85 | InnoDB / utf8mb4_0900_ai_ci | 草稿排期 |
| 9 | `task_rollovers` | 7 | InnoDB / utf8mb4_0900_ai_ci | 任务顺延关系 |
| 10 | `study_records` | 52 | InnoDB / utf8mb4_0900_ai_ci | 学习行为记录 |
| 11 | `focus_sessions` | 14 | InnoDB / utf8mb4_0900_ai_ci | 专注会话 |
| 12 | `knowledge_notes` | 4 | InnoDB / utf8mb4_0900_ai_ci | 知识笔记（含软删除） |
| 13 | `knowledge_review_records` | 5 | InnoDB / utf8mb4_0900_ai_ci | 笔记复习记录 |
| 14 | `practice_records` | 0 | InnoDB / utf8mb4_0900_ai_ci | AI 练习历史 |

补充统计：

- `users`：`email` 非空 0 条，`avatar_url` 非空 0 条，`is_active=1` 47 条。
- `tb_refresh_token`：总 210 条、涉及 45 个用户、114 个 `family_id`、当前有效 2 条、已轮换（`replaced_by` 非空）96 条；最早 `created_at=2026-11-10 16:49:35`，最新 `2026-11-24 21:30:35`。
- 单个 family 最长链 25 条（`4ea4faf4-...`），其次 20、16、5、4 条。
- `users.AUTO_INCREMENT=852` 但仅有 47 行；`tb_refresh_token.AUTO_INCREMENT=261` 但仅 210 行。说明历史上已发生过批量删除，ID 不会复用。

### 3.2 `users` 完整 DDL

```sql
CREATE TABLE `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL COMMENT '登录用户名',
  `password_hash` varchar(255) NOT NULL COMMENT '密码哈希',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱（可选）',
  `nickname` varchar(50) DEFAULT NULL COMMENT '用户昵称',
  `avatar_url` varchar(255) DEFAULT NULL COMMENT '头像地址（可选）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_active` tinyint NOT NULL DEFAULT '1' COMMENT 'Whether the user account is active',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=852 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户表';
```

认证相关要点：

- `email` 已存在且带唯一索引；MySQL 唯一索引允许多个 `NULL`，所以现有 47 个无邮箱用户不冲突。
- `avatar_url` 已存在，但全项目无读写代码。
- 没有 `email_verified_at`、`password_updated_at`、`last_login_at`、`deleted_at` 等字段。
- `is_active` 为 `tinyint`，后端按真值判断。

### 3.3 `tb_refresh_token` 完整 DDL

```sql
CREATE TABLE `tb_refresh_token` (
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
) ENGINE=InnoDB AUTO_INCREMENT=261 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='刷新令牌表';
```

认证相关要点：

- 无 `session_id`、无设备名、无 User-Agent、无 IP、无 `last_used_at`、无 `absolute_expires_at`。
- `family_id` 为 `char(36)`，与 UUID4 文本长度一致。
- 仅 `token_hash` 唯一；同一 family 内允许多代 token 共存，符合轮换链设计。

### 3.4 AI 限流 / 日志表完整 DDL

`ai_requests`（额度、并发、状态、Token 用量）：

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

`ai_guard_mutex`（准入全局互斥行）：

```sql
CREATE TABLE `ai_guard_mutex` (
  `id` tinyint unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
```

注意：

- `ai_requests.user_id` **没有外键**，删除用户不会级联删除其 AI 用量记录，会留下孤儿行。
- `ai_guard_mutex` 必须始终存在 `id=1` 这一行，否则 `lock_admission` 抛 `RuntimeError`，全站 AI 不可用。
- 这两张表属于 AI 业务基础设施，**不应被认证改造复用为通用限流表**，以免破坏 AI Guard 的语义与并发正确性。

### 3.5 所有引用 `users.id` 的外键及删除策略

| 引用表 | 列 | 约束名 | ON DELETE | ON UPDATE |
|---|---|---|---|---|
| `tb_refresh_token` | `user_id` | `fk_refresh_token_user` | CASCADE | NO ACTION |
| `study_plans` | `user_id` | `fk_study_plans_user` | **NO ACTION（RESTRICT）** | NO ACTION |
| `study_records` | `user_id` | `fk_study_records_user` | **NO ACTION（RESTRICT）** | NO ACTION |
| `knowledge_notes` | `user_id` | `fk_notes_user` | CASCADE | NO ACTION |
| `knowledge_review_records` | `user_id` | `fk_review_user` | CASCADE | NO ACTION |
| `practice_records` | `user_id` | `fk_practice_user` | CASCADE | NO ACTION |
| `focus_sessions` | `user_id` | `fk_focus_user` | CASCADE | NO ACTION |

其余业务外键（不直接引用 `users`，但影响清理顺序）：

| 引用表 | 列 | 引用目标 | ON DELETE |
|---|---|---|---|
| `daily_tasks` | `plan_id` | `study_plans.id` | NO ACTION |
| `daily_tasks` | `step_id` | `plan_steps.id` | NO ACTION |
| `plan_steps` | `plan_id` | `study_plans.id` | NO ACTION |
| `plan_steps` | `parent_id` | `plan_steps.id` | NO ACTION |
| `schedule_entries` | `step_id` | `plan_steps.id` | NO ACTION |
| `study_records` | `task_id` | `daily_tasks.id` | NO ACTION |
| `task_rollovers` | `source_task_id` | `daily_tasks.id` | NO ACTION |
| `task_rollovers` | `target_task_id` | `daily_tasks.id` | NO ACTION |
| `focus_sessions` | `plan_id` | `study_plans.id` | SET NULL |
| `focus_sessions` | `task_id` | `daily_tasks.id` | SET NULL |
| `knowledge_notes` | `plan_id` | `study_plans.id` | SET NULL |
| `knowledge_notes` | `step_id` | `plan_steps.id` | SET NULL |
| `knowledge_review_records` | `note_id` | `knowledge_notes.id` | CASCADE |
| `practice_records` | `note_id` | `knowledge_notes.id` | SET NULL |

关键结论：**直接 `DELETE FROM users WHERE id=?` 在有学习计划或学习记录时会失败**（`fk_study_plans_user`、`fk_study_records_user` 为 RESTRICT）。清理必须按依赖顺序显式删除。

### 3.6 认证相关索引与字段类型

`users`：

| 类型 | 名称 | 列 |
|---|---|---|
| PRIMARY | PRIMARY | `id` |
| UNIQUE | `uk_users_username` | `username` |
| UNIQUE | `uk_users_email` | `email` |

`tb_refresh_token`：

| 类型 | 名称 | 列 |
|---|---|---|
| PRIMARY | PRIMARY | `id` |
| UNIQUE | `uk_refresh_token_hash` | `token_hash` |
| INDEX | `idx_refresh_user_family` | `user_id, family_id` |
| INDEX | `idx_refresh_expires_at` | `expires_at` |

类型层面：

- `users.id`、`tb_refresh_token.user_id` 均为 `bigint unsigned`，后续新表必须保持一致，否则外键无法建立。
- `token_hash` / `replaced_by` 为 `char(64)`，对应 SHA-256 十六进制 64 字符。
- `family_id` 为 `char(36)`，对应 UUID 文本。
- 时间字段为无时区 `datetime`；应用连接设置 `SET time_zone='+08:00'`，而 `_utc_now()` 写入的是「UTC 的 naive 时间」。**同一张表里存在两套时间语义**：`created_at` 由 MySQL `CURRENT_TIMESTAMP` 按 +08:00 写入，`expires_at/revoked_at` 由 Python 按 UTC 写入。这会让人工排查时间线时产生 8 小时错觉。

### 3.7 MySQL 实例、字符集、排序规则、时区

| 项 | 值 |
|---|---|
| 版本 | `8.4.9` |
| 服务端字符集 | `utf8mb4` |
| 服务端排序规则 | `utf8mb4_general_ci` |
| 当前库字符集 | `utf8mb4` |
| 当前库排序规则 | `utf8mb4_general_ci` |
| 全局 `time_zone` | `SYSTEM` |
| 会话 `time_zone` | `SYSTEM` |
| 系统时区 | 中国标准时间（UTC+8） |
| `NOW()` / `UTC_TIMESTAMP()` | `2026-11-24 21:45:31` / `2026-11-24 13:45:31` |
| 应用连接 | `SET time_zone = '+08:00'`（`app/database.py`） |

排序规则混用：

- 库默认是 `utf8mb4_general_ci`。
- `users`、`tb_refresh_token`、`ai_requests`、业务表均为 `utf8mb4_0900_ai_ci`。
- `ai_guard_mutex` 为 `utf8mb4_general_ci`。
- 新建认证表建议显式声明 `utf8mb4_0900_ai_ci`，与 `users` 保持一致，避免跨表字符串比较/连接出现排序规则冲突。

### 3.8 现有 Token Family 数据结构与关联方式

```text
users (id)
  └─ tb_refresh_token (user_id, family_id, token_hash, replaced_by, revoked_at, expires_at)
        family_id = 一次登录会话
        token_hash ──replaced_by──> 下一代 token_hash（同 family）
```

- 生成：`create_family_id()` 返回 `str(uuid.uuid4())`，登录时新建 family；刷新时复用同一 `family_id`。
- 关联：同一 `family_id` 下的多行构成轮换链；`replaced_by` 指向下一代的 `token_hash`，形成单向链表。
- 撤销：`revoked_at` 置为 UTC 当前时间；重放检测会撤销整个 family 的所有有效行。
- 现状数据：114 个 family 分布在 45 个用户；最长链 25 代；96 条历史 token 已轮换但仍保留。
- 局限：`family_id` 本身没有独立元数据（创建时间、最后使用时间、设备、IP、撤销原因），无法直接用于「我的登录设备列表」展示；也没有「按 session 查询」的索引（现有组合索引只能按 user+family 查）。

**`family_id` 能否直接作为 Session ID？**

可以，且是成本最低的方案：

- 语义一致：一次登录 = 一个 family = 一个会话。
- 长度/类型稳定：`char(36)` UUID4，全局唯一，无需额外映射。
- 现有轮换与重放撤销已经以 family 为单位，注销当前会话也已经按 family 撤销。

但需要补足：

- 会话列表需要「每会话一行」的元数据，而现有表是「每代 token 一行」，无法直接分页展示 114 个 family 的当前状态。
- 建议新增 `tb_login_session`，主键直接使用 `family_id`，由登录时同事务写入；`tb_refresh_token.family_id` 作为外键或逻辑外键关联。这样无需引入新的 session_id，也不会破坏现有轮换链。
- 若坚持不建会话表，也可通过 `SELECT family_id, MIN(created_at), MAX(created_at) ... GROUP BY family_id` 临时聚合，但无法可靠记录设备/IP/最后活跃时间，也无法在撤销后保留审计信息。

### 3.9 旧用户安全清理建议（仅建议，不执行）

目标：清理旧用户及其关联业务数据，保留表结构、`ai_guard_mutex`、其他用户数据与无关系统数据。

前置原则：

1. 全程在单个事务中执行，先 `SELECT` 导出待删用户清单与行数快照，再删除。
2. 只按明确的 `user_id` 集合删除，禁止无条件 `DELETE`。
3. 不使用 `TRUNCATE`（会重置自增并可能破坏外键语义）。
4. 不删除 `ai_guard_mutex`；不修改任何 DDL。
5. 删除前备份：`mysqldump` 按用户导出相关表，或先写入归档表（如果业务允许新建归档表，则属于 DDL，需另行批准）。

推荐删除顺序（按外键依赖，从叶子到根）：

```text
1. task_rollovers        （通过 daily_tasks.plan_id 关联到目标用户）
2. study_records         （user_id 直接关联；同时阻塞 daily_tasks）
3. focus_sessions        （user_id；对 plan/task 是 SET NULL，可先删）
4. schedule_entries      （通过 plan_steps.plan_id 关联）
5. daily_tasks           （通过 plan_id 关联）
6. plan_steps            （通过 plan_id 关联；自引用 parent_id 需先删子节点或将 parent_id 置 NULL）
7. study_plans           （user_id 直接关联）
8. knowledge_notes       （user_id；会级联 knowledge_review_records，practice_records.note_id 置 NULL）
9. practice_records      （user_id；建议显式删除，避免依赖 note 级联）
10. tb_refresh_token     （user_id；本身 CASCADE，仍建议显式删除以便统计）
11. users                （最后删除）
```

补充说明：

- `plan_steps` 的自引用外键为 `NO ACTION`：安全做法是先 `UPDATE plan_steps SET parent_id = NULL WHERE plan_id IN (...)`，再删除；或按层级从深到浅删除。
- `ai_requests` 无外键，不会阻塞删除；但删除用户后其历史额度记录会变成孤儿。是否保留需产品决策：保留可作为用量审计，删除可减小表体积。若保留，建议至少记录一次「用户已删除」的运维日志。
- 删除 `knowledge_notes` 会把 `practice_records.note_id` 置 NULL，历史练习仍可读（`note_title_snapshot` 保留标题），这与 A5 历史模块的设计一致。
- 删除后应校验：目标用户相关表计数为 0、其他用户计数不变、`ai_guard_mutex` 仍为 1 行、`users` 剩余行数符合预期。
- 若未来引入 `tb_login_session` / `tb_email_verification` / `tb_auth_event`，清理流程需同步补充这三张表的按 `user_id` 删除步骤。

---

## 4. 认证机制逐项审计

| # | 审计项 | 现状 | 源码位置 | 结论 |
|---|---|---|---|---|
| 1 | Access Token payload | `sub`(字符串用户 ID)、`iat`、`exp`、`type="access"`、`jti`(UUID4) | `app/core/security.py::_create_token` / `create_access_token` | 结构完整；无 `family_id`/`session_id`，因此无法按会话撤销 |
| 2 | Refresh Token payload | `sub`、`family_id`、`iat`、`exp`、`type="refresh"`、`jti` | `app/core/security.py::create_refresh_token`、`auth_service._build_token_pair` | 含 `family_id`，可作为会话标识 |
| 3 | `family_id` 生成方式/长度/唯一性 | `uuid4()` 字符串，36 字符，`char(36)`；登录时新建 | `security.py::create_family_id`、`auth_service.issue_token_pair` | 唯一性由 UUID4 保证；无数据库唯一约束，但 `token_hash` 唯一 + 轮换链足以约束 |
| 4 | Refresh Token 哈希算法 | `hashlib.sha256(token).hexdigest()`，无密钥、无 pepper | `security.py::hash_refresh_token` | 仅防明文泄露；若数据库与 token 同时泄露仍可重放。可考虑 HMAC-SHA256(SECRET_KEY) |
| 5 | 密码哈希算法 | PBKDF2-HMAC-SHA256，600,000 迭代，16 字节随机盐，格式 `pbkdf2_sha256$iterations$salt$digest` | `security.py::hash_password` / `verify_password` | 强度可接受；校验允许 10 万–200 万迭代，兼容历史哈希 |
| 6 | Refresh 轮换事务与锁 | `SELECT ... FOR UPDATE` 锁旧 token 行 + `SELECT users ... FOR UPDATE`；条件 `UPDATE` 校验 `rowcount=1`；新增下一代；统一 `commit`/`rollback` | `auth_service.rotate_refresh_token` | 并发安全；同一 token 并发刷新只有一个成功，另一个得到 401 |
| 7 | Refresh 重放检测 | 旧 token `replaced_by IS NOT NULL` 即判定重放，撤销整个 family，先 commit 再返回 401 | `auth_service.rotate_refresh_token` 步骤 5、10、11 | 检测有效；但**不会撤销已签发的 Access Token** |
| 8 | 退出当前会话 | 解析 refresh token → 校验 DB 记录匹配 → 撤销整个 family | `auth_service.revoke_current_session`、`POST /auth/logout` | 仅撤销 refresh；Access Token 仍可用至过期 |
| 9 | 退出所有会话 | 按 `user_id` 撤销所有未撤销 refresh token | `auth_service.revoke_all_sessions`、`POST /auth/logout-all` | 同上，Access Token 不受影响 |
| 10 | `get_current_user` 流程 | 取 Bearer → `decode_access_token_detailed`（区分过期/非法/类型错误）→ 校验 `sub` 为数字 → 回查 `users(id,username,nickname,is_active)` → 不存在 401 / 禁用 403 | `app/core/deps.py` | 每次请求一次数据库查询；无缓存 |
| 11 | 即时撤销未过期 Access Token | **不能**。JWT 无状态，`deps` 只校验用户存在与 `is_active`；没有 token 版本号、黑名单或 session 状态检查 | `deps.py` | 退出/改密/换绑后，旧 Access Token 最长仍可用 15 分钟 |
| 12 | 受保护接口是否统一使用认证依赖 | 67 个路由中 60 个使用 `Depends(get_current_user)`；7 个公开 | 见下方清单 | 业务接口覆盖完整；但 `GET /users` 是匿名可读的敏感接口 |
| 13 | AI 流式接口是否使用同一认证依赖 | 是。`knowledge_ai.py` 4 个 + `ai_practice.py` 2 个 SSE 接口全部依赖 `get_current_user` | `app/api/routes/knowledge_ai.py`、`ai_practice.py` | 认证一致；流式响应本身不额外校验会话状态 |
| 14 | `family_id` 直接作为 Session ID | 可行 | 见 3.8 | 建议新增会话表时直接以 `family_id` 为主键 |

### 4.1 路由保护覆盖明细

公开（无需认证）的 7 个路由：

| 方法 | 路径 | 说明 | 风险 |
|---|---|---|---|
| GET | `/` | 根信息 | 低 |
| GET | `/health` | 健康检查 | 低 |
| POST | `/auth/login` | 登录 | 应加限流 |
| POST | `/auth/refresh` | 刷新 | 应加限流/重放保护（已有重放检测） |
| POST | `/auth/logout` | 退出（凭 refresh token） | 中（可被用于探测 token 有效性） |
| POST | `/users` | 注册 | **无验证码、无限流、无邮箱验证** |
| GET | `/users` | **列出全部用户（id/username/nickname/created_at/updated_at）** | **高：匿名数据泄露** |

其余 60 个路由均使用 `Depends(get_current_user)`，覆盖 plans、steps、tasks、rollovers、active_*、progress、statistics、knowledge、knowledge_ai、ai_practice、focus、users 的其余接口。

### 4.2 现有 Access Token 生命周期与「即时撤销」缺口

```text
登录 → Access(15m) + Refresh(7d)
刷新 → 新 Access(15m) + 新 Refresh(7d)，旧 Refresh 标记 revoked/replaced_by
退出 → 撤销整个 family 的 Refresh
      → 已签发的 Access 仍然有效，直到 exp
禁用 → is_active=0，下一请求被 deps 拦截（403）
删除 → 下一请求 401（USER_NOT_FOUND）
```

要实现 Auth V2.0 的「服务端即时撤销」，最小改动方向：

1. Access Token 增加 `family_id`（或 `sid`）声明。
2. `get_current_user` 除用户状态外，再校验该会话是否有效：
   - 方案 A：每次请求查 `tb_login_session`（或 `tb_refresh_token` 中该 family 是否存在未撤销记录）——实时但增加一次查询。
   - 方案 B：在 `users` 增加 `token_version`，Access 携带版本号，撤销时自增——一次查询用户即可，但只能「全端撤销」，无法精确到单会话。
3. 若采用 HttpOnly Cookie，可在登出时清除 Cookie，但服务端仍需上述机制才能真正即时失效。

### 4.3 认证接口请求/响应契约现状

- 登录：`application/x-www-form-urlencoded`（`OAuth2PasswordRequestForm`，字段 `username`、`password`），返回 `{code,message,data:{access_token,refresh_token,token_type,expires_in,user}}`。
- 刷新/登出：JSON `{refresh_token}`。
- 登出全部：仅需 Bearer。
- 错误：401/403/429 均经全局处理器包装；`WWW-Authenticate` 头在登录失败时保留。
- 当前**没有**：邮箱字段、验证码、注册验证、修改密码、换绑邮箱、头像上传、会话列表、会话单独踢出。

---


## 5. 限流与最少建表分析

### 5.1 现有基础设施可复用性评估

| 现有设施 | 能否复用 | 结论 |
|---|---|---|
| `ai_guard_mutex` + `ai_requests` | **不建议复用** | 语义是「AI 调用额度/并发」，复用会污染 AI Guard；且 `ai_requests.operation` 白名单固定，新增认证 operation 会改变 AI 统计口径。其**设计模式**（行锁 + 同事务检查 + 短事务提交）可以复用 |
| `tb_refresh_token` | 部分复用 | 可判断会话是否仍有效，但没有设备/IP/最后活跃字段，不能直接当会话表使用 |
| `users` | 需扩展 | 已有 `email`、`avatar_url`、`is_active`；缺邮箱验证时间、密码更新时间、登录失败状态 |
| Python `logging` | 仅文件/控制台 | 无持久审计表，无法支撑「关键认证事件」查询与跨进程统计 |
| MySQL 行锁 / 唯一索引 | 可复用 | 无 Redis 条件下，DB 是唯一可靠的跨进程协调点 |
| `httpx` | 可复用 | 已安装，可直接调用邮件服务 HTTP API |

### 5.2 八类限流需求与落点

| 需求 | 建议落点 | 并发正确性方案 |
|---|---|---|
| 邮箱验证码发送间隔 | `tb_email_verification`：查询同一 `email + purpose` 最近一条 `created_at` | 发码前在同一事务内 `SELECT ... FOR UPDATE` 最近一条，或在全局发信锁内检查 |
| 邮箱每日发送次数 | `tb_email_verification`：`COUNT(*) WHERE email=? AND created_at >= 当日 00:00` | 与「发送间隔」检查放在同一临界区 |
| IP 每日发送次数 | `tb_email_verification`：`COUNT(*) WHERE request_ip=? AND created_at >= 当日 00:00` | 同上；`request_ip` 必须来自可信代理后的真实客户端 IP |
| 全局邮件发送额度 | 跨进程临界区 + 当日总数 | 用 MySQL 命名锁 `GET_LOCK('auth_mail_quota', 2)` 包住「计数 + 插入」；或使用一张单行额度表 `FOR UPDATE`。**不要用进程内变量** |
| 验证码错误次数 | `tb_email_verification.attempts` | 原子 `UPDATE ... SET attempts=attempts+1 WHERE id=? AND attempts < 5 AND consumed_at IS NULL`，用 `rowcount` 判定 |
| 密码登录失败限制 | `tb_auth_event`：按 `identifier`(用户名/邮箱) + `ip` + 时间窗计数 | 失败事件先写入（独立短事务），登录前在临界区内计数；或用固定窗口计数 |
| 关键认证事件记录 | `tb_auth_event` | 只追加写；`user_id` 不设外键，保证用户删除后审计仍保留 |
| 多进程并发正确性 | 全部依赖 MySQL 事务/行锁/唯一索引/命名锁 | 禁止任何进程内字典或 `lru_cache` 计数；AI Guard 已验证该模式可行 |

### 5.3 建议的最小数据库改动（仅建议，未执行）

#### （1）扩展 `users`（ALTER，不新建表）

```sql
-- 建议字段（名称可调整）
ALTER TABLE users
  ADD COLUMN email_verified_at datetime NULL COMMENT '邮箱验证时间',
  ADD COLUMN password_updated_at datetime NULL COMMENT '密码最近修改时间';
```

说明：

- `email`、`avatar_url`、`is_active` 已存在，无需重复添加。
- 现有 `uk_users_email` 已满足邮箱唯一性；`email` 保持可空，兼容 47 个历史用户（当前 0 个有邮箱）。
- 若要求「邮箱登录必须已验证」，注册时先写 `email`、`email_verified_at=NULL`，验证成功后更新；登录查询需同时判断 `email_verified_at IS NOT NULL`。
- 不建议把 `email` 改为 `NOT NULL`，否则无法兼容历史数据，也会让「仅用户名登录」用户无法存在。

#### （2）新增 `tb_login_session`（会话表，主键复用 `family_id`）

```sql
CREATE TABLE tb_login_session (
  session_id      char(36)     NOT NULL COMMENT '会话 ID，等于 Refresh Token 的 family_id',
  user_id         bigint unsigned NOT NULL COMMENT '用户 ID',
  created_at      datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at    datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at      datetime     NOT NULL COMMENT '会话绝对过期时间',
  revoked_at      datetime     DEFAULT NULL,
  revoked_reason  varchar(32)  DEFAULT NULL COMMENT 'LOGOUT/LOGOUT_ALL/REPLAY/PASSWORD_CHANGED/ADMIN',
  ip              varchar(45)  DEFAULT NULL,
  user_agent      varchar(255) DEFAULT NULL,
  device_label    varchar(64)  DEFAULT NULL,
  PRIMARY KEY (session_id),
  KEY idx_login_session_user (user_id, revoked_at),
  KEY idx_login_session_expires (expires_at),
  CONSTRAINT fk_login_session_user
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='登录会话（多设备管理）';
```

- `session_id` 直接使用现有 `family_id`，**不需要额外映射**，也不需要改 `tb_refresh_token` 的主键结构。
- 登录时与 Refresh Token 同事务插入；刷新时更新 `last_seen_at`；退出/重放/改密时写 `revoked_at`。
- 会话列表按 `user_id + revoked_at IS NULL + expires_at > now` 查询即可。
- 可选：给 `tb_refresh_token.family_id` 增加指向本表的外键；但历史数据（114 个 family）需要先回填，否则建外键会失败。最小方案是保持逻辑关联，不建物理外键。

#### （3）新增 `tb_email_verification`

```sql
CREATE TABLE tb_email_verification (
  id          bigint unsigned NOT NULL AUTO_INCREMENT,
  email       varchar(100)    NOT NULL,
  purpose     enum('REGISTER','LOGIN','RESET_PASSWORD','CHANGE_EMAIL') NOT NULL,
  code_hash   char(64)        NOT NULL COMMENT '验证码摘要（禁止存明文）',
  expires_at  datetime        NOT NULL,
  attempts    tinyint unsigned NOT NULL DEFAULT 0,
  consumed_at datetime        DEFAULT NULL,
  request_ip  varchar(45)     DEFAULT NULL,
  created_at  datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_email_code_lookup (email, purpose, created_at),
  KEY idx_email_code_ip (request_ip, created_at),
  KEY idx_email_code_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='邮箱验证码';
```

- 验证码只存 SHA-256/HMAC 摘要，成功或过期后写 `consumed_at`。
- 发送间隔、邮箱日限额、IP 日限额均可通过该表索引直接统计，无需额外计数表。
- 建议定期清理过期记录（当前项目没有任何清理任务，需要新增 Worker 或在现有 Worker 中增加清理步骤）。

#### （4）新增 `tb_auth_event`（建议新增）

```sql
CREATE TABLE tb_auth_event (
  id          bigint unsigned NOT NULL AUTO_INCREMENT,
  user_id     bigint unsigned DEFAULT NULL COMMENT '不设外键，用户删除后审计保留',
  identifier  varchar(100)    DEFAULT NULL COMMENT '尝试登录的用户名/邮箱',
  event_type  varchar(32)     NOT NULL COMMENT 'LOGIN_SUCCESS/LOGIN_FAILED/LOGOUT/REFRESH_REPLAY/PASSWORD_CHANGED/EMAIL_CHANGED/CODE_SENT/CODE_FAILED',
  email       varchar(100)    DEFAULT NULL,
  ip          varchar(45)     DEFAULT NULL,
  user_agent  varchar(255)    DEFAULT NULL,
  session_id  char(36)        DEFAULT NULL,
  detail      varchar(255)    DEFAULT NULL,
  created_at  datetime(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_auth_event_type_time (event_type, created_at),
  KEY idx_auth_event_user_time (user_id, created_at),
  KEY idx_auth_event_ip_time (ip, created_at),
  KEY idx_auth_event_identifier_time (identifier, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='认证安全事件';
```

为什么建议新增而不是复用现有表：

- 现有没有任何「安全日志/审计」表；`ai_requests` 只服务 AI，字段语义完全不匹配。
- 仅写文件日志无法支持管理端查询、跨进程失败计数、按 IP/用户追溯。
- 该表是「关键认证事件」和多因素限流的共同落点，属于必要基础设施，而非冗余。

#### （5）明确不动的对象

- 不修改 `ai_guard_mutex`（必须保留 `id=1`）。
- 不修改 `ai_requests` 结构与 `operation` 白名单。
- 不引入 Redis、ORM Models、Alembic（本次约束）。
- 不重建 `tb_refresh_token`；如确需设备信息，优先从 `tb_login_session` 读取，避免破坏现有轮换链。

### 5.4 多进程并发正确性要点

1. **准入检查必须在锁内完成**：`SELECT COUNT` 本身不加锁，两个进程可能同时看到「未超限」。必须先用 `ai_guard_mutex` 式行锁或 `GET_LOCK` 串行化「计数 + 写入」。
2. **验证码错误计数用条件更新**：`UPDATE ... WHERE attempts < N` + `rowcount`，避免读改写竞态。
3. **登录失败计数不要用内存**：多 worker 下每个进程独立，内存计数会失效。
4. **发送间隔判断要防重入**：同一邮箱并发请求发码时，应在锁内检查「最近发送时间」后再插入新记录。
5. **全局邮件额度需要跨进程锁**：建议 `GET_LOCK('auth_mail_quota', 2)`，`finally` 中 `RELEASE_LOCK`；若使用连接池，务必保证 `GET_LOCK` 与 `RELEASE_LOCK` 在同一连接/事务上下文。
6. **已撤销会话的 Access Token 仍需服务端校验**：否则「即时撤销」只对 Refresh 生效。
7. **时间基准统一**：现有 `expires_at/revoked_at` 用 UTC naive，`created_at` 用 +08:00；新表应统一为 UTC 或统一为 +08:00，并在代码中只使用一种，避免限流窗口错位。

---

## 6. 部署环境审计

### 6.1 当前运行方式（本机实测）

| 组件 | 现状 |
|---|---|
| MySQL | `mysqld` 进程方式启动（未注册 Windows 服务），端口 3306，配置文件 `C:\ProgramData\MySQL\MySQL Server 8.4\my.ini` |
| 后端 | `d:\project\back\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`，cwd=`d:\project\back` |
| 前端 | `next dev`，端口 3000，`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` |
| 进程模型 | 后端开发模式单进程 + `--reload`；**未配置生产 worker 数** |
| 静态资源 | Next.js 自带；后端未挂载 `StaticFiles` |

### 6.2 域名 / 同源代理 / HTTPS

- 仓库内**没有** Nginx、Caddy、Traefik、Dockerfile、docker-compose、systemd 配置。
- 前端通过 `NEXT_PUBLIC_API_BASE_URL` 直接访问 `http://127.0.0.1:8000`，属于**跨源直连**，不是同源代理。
- 后端 CORS 仅允许 `http://localhost:3000` 与 `http://127.0.0.1:3000`，`allow_credentials=True`。
- 当前**没有 HTTPS**：后端无 TLS 终止、无证书配置，前端默认 http。
- 生产域名/证书/反向代理：**UNKNOWN**（仓库无证据；需运维提供）。

对 Auth V2.0 的影响：

- HttpOnly + Secure Cookie 必须运行在 HTTPS 下；本地开发可用 `Secure=False` 或 localhost 例外。
- 若未来改为同源代理（例如 `/api` 反代到 8000），需要同步修改 `NEXT_PUBLIC_API_BASE_URL` 与 CORS/Origin 策略，并重新评估 CSRF。

### 6.3 Uvicorn Worker 与可信代理

- 当前启动命令未指定 `--workers`，默认 1 个 worker。
- 未配置 `--proxy-headers` / `--forwarded-allow-ips`。
- 代码中**没有读取** `request.client`、`X-Forwarded-For`、`X-Real-IP`。
- 因此：**当前无法可靠获取客户端 IP**。上线前若走 Nginx/负载均衡，必须：
  1. Uvicorn 增加 `--proxy-headers --forwarded-allow-ips=<代理IP>`；
  2. 或在应用内显式解析可信头；
  3. 且只信任来自已知代理的转发头，防止伪造 IP 绕过限流。
- 多 worker 对现有 JWT 校验无影响；对 Refresh 轮换的 DB 行锁无影响（锁在 MySQL 侧）；但新增的限流必须遵守 5.4 的 DB 协调原则。

### 6.4 头像文件持久化方案

现状：

- `users.avatar_url varchar(255)` 已存在，但无上传接口、无静态目录、无文件校验。
- 前端 `UsersProfile.tsx` 仅用昵称首字符渲染，不读取 `avatar_url`。

可行方案（建议）：

1. 配置 `AVATAR_DIR`（例如 `d:\project\back\storage\avatars`），**放在代码目录之外或纳入持久化卷**，避免重新部署被覆盖。
2. 上传接口校验：扩展名/MIME、文件大小（如 ≤2MB）、图片解码校验、随机文件名（UUID），禁止使用用户原始文件名。
3. 存储 `users.avatar_url` 存相对路径（如 `/media/avatars/<uuid>.webp`），不要存绝对磁盘路径。
4. 读取：FastAPI `StaticFiles(directory=AVATAR_DIR, ...)` 挂载到 `/media/avatars`，或由 Nginx 直接服务；两者都需考虑缓存头与防盗链。
5. 旧头像替换/删除时清理孤儿文件；数据库事务与文件写入无法强一致，建议「先写新文件、更新 DB、再异步删旧文件」。
6. 若未来多实例部署，必须使用共享存储（NAS/对象存储），否则各实例头像不一致。

### 6.5 邮件 HTTP API 出站条件

现状：**没有任何邮件代码或依赖**。Auth V2.0 需新增：

- 出站 HTTPS（通常 443）访问邮件服务商 API；若服务器在受限网络，需要放行域名/配置 `HTTPS_PROXY`。
- 超时、重试、幂等键、失败降级（返回可读错误，不泄露内部细节）。
- 发信密钥只从环境变量读取，禁止入库、禁止日志打印。
- 发送频率与配额必须在服务端强制（见第 5 节），不能只依赖服务商限额。
- 若使用 SMTP 而非 HTTP API，还需放行 465/587；但任务描述为 HTTP API，建议优先 HTTPS。

### 6.6 `.env` 变量名（仅名称，无值）

后端 `d:\project\back\.env` 当前包含：

```text
DB_HOST
DB_PORT
DB_USER
DB_PASSWORD
DB_NAME
SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS
AI_ENABLED
DEEPSEEK_MODEL
DEEPSEEK_API_KEY
```

前端 `d:\project\next-fro\.env.local` 当前包含：

```text
NEXT_PUBLIC_API_BASE_URL
```

> 未输出任何真实密钥、数据库密码、Token、邮件 API Key。Auth V2.0 新增配置建议使用新变量名（如 `MAIL_API_BASE`、`MAIL_API_KEY`、`MAIL_FROM`、`AVATAR_DIR`、`COOKIE_SECURE`、`COOKIE_DOMAIN`），具体值由部署环境注入。

---

## 7. 风险与潜在冲突

### 7.1 高优先级

1. **`GET /users` 匿名可读全部用户**
   - 位置：`app/api/routes/users.py::get_users`
   - 影响：泄露用户名、昵称、注册/更新时间；为撞库提供用户名清单。
   - 建议：删除该接口或加管理员鉴权；至少加 `Depends(get_current_user)` 并限制返回字段。

2. **登录/注册无任何限流**
   - 影响：密码爆破、验证码轰炸、邮件配额耗尽。
   - 建议：按第 5 节落地；在引入邮箱验证码前先加登录失败限制。

3. **Access Token 无法即时撤销**
   - 影响：登出、改密、换绑邮箱、踢设备后，旧 Access Token 仍可用最长 15 分钟。
   - 建议：Access 增加 `family_id`，`get_current_user` 校验会话有效性（或 `token_version`）。

4. **Refresh Token 仅 SHA-256 摘要、无 pepper**
   - 影响：数据库泄露 + 日志/前端泄露同时发生时可直接重放。
   - 建议：改为 `HMAC-SHA256(SECRET_KEY, token)` 或加独立 pepper；需兼容迁移（可双读一段时间）。

### 7.2 中优先级

5. **Refresh Token 存储明文风险转移到了 localStorage**
   - 现状：前端 `lib/auth/token.ts` 把 Access/Refresh 都存 `localStorage`，任意 XSS 可直接窃取 7 天 Refresh Token。
   - 目标：HttpOnly Cookie + SameSite + CSRF 防护；需同步改造前端所有请求封装（见前端审计）。

6. **`tb_refresh_token` 无会话元数据**
   - 影响：无法实现「多设备 Session 管理」的设备名、IP、最后活跃、单独踢出。
   - 建议：新增 `tb_login_session`，`session_id = family_id`。

7. **时间语义混用（UTC naive vs +08:00）**
   - 影响：`expires_at`、`revoked_at` 与 `created_at` 相差 8 小时，限流窗口/审计时间线容易误判。
   - 建议：新表统一 UTC，或统一 +08:00；在代码注释中明确。

8. **无过期数据清理**
   - 现状：210 条 token、96 条已轮换、大量过期；`ai_requests` 也只增不减。
   - 影响：表持续膨胀，索引效率下降。
   - 建议：在 `plan_expiration_worker` 中增加每日清理（或新增独立任务）：删除/归档 `expires_at < now - 30d` 且已撤销的 token、过期验证码、超过保留期的认证事件。

9. **`requirements.txt` 缺少 APScheduler**
   - 影响：全新环境安装后 Worker 无法启动。
   - 建议：补充 `APScheduler==3.11.3`（当前虚拟环境实际版本）。

### 7.3 低优先级 / 实现细节

10. **`users.delete_user` 未处理外键冲突**：有 `study_plans`/`study_records` 时抛 `IntegrityError` → 500。建议返回 409 并说明需先清理业务数据。
11. **`UserUpdate` 只支持 `nickname`**：无法改密码、改邮箱；Auth V2.0 需新增专用接口与 Schema。
12. **`UserCreate` 无邮箱、无验证码、无密码强度校验**：注册只依赖 `username` 唯一索引。
13. **`GET /users/me` 返回 `is_active`**：泄露内部状态，建议按前端需要裁剪。
14. **`users` 表字段顺序**：`email`/`avatar_url` 是历史预留字段，当前 0 使用；改造时无需迁移数据。
15. **字符集/排序规则混用**：库默认 `utf8mb4_general_ci`，业务表 `utf8mb4_0900_ai_ci`，`ai_guard_mutex` 为 `general_ci`。新建表请显式指定 `utf8mb4_0900_ai_ci`。
16. **无 CSRF 防护**：改为 Cookie 后必须补；当前 Bearer 模式天然免疫 CSRF，但也因此把 token 暴露给 JS。
17. **CORS 仅本地来源**：生产域名加入前需更新白名单；`allow_credentials=True` 时不能用 `*`。
18. **AI Guard 的全局互斥行是单点**：`ai_guard_mutex` 缺失会导致所有 AI 请求 500；同样模式用于认证时需保证哨兵行初始化与监控。
19. **邮件发送失败与额度**：建议「发送成功才计入日额度」，或明确「尝试即计数」；需要在实现前定死语义，否则限流口径会漂移。
20. **测试缺口**：现有 `tests/` 无认证相关测试（登录、刷新、重放、撤销均无覆盖）。Auth V2.0 改造前建议先补最小回归测试。

---

## 附录 A：本次只读审计使用的查询（示例）

```sql
SELECT VERSION(), @@character_set_server, @@collation_server,
       @@character_set_database, @@collation_database,
       @@global.time_zone, @@session.time_zone, @@system_time_zone,
       NOW(), UTC_TIMESTAMP();

SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'smart_study_planner';

SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME,
       REFERENCED_COLUMN_NAME, CONSTRAINT_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'smart_study_planner'
  AND REFERENCED_TABLE_NAME IS NOT NULL;

SELECT TABLE_NAME, CONSTRAINT_NAME, UPDATE_RULE, DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'smart_study_planner';

SELECT COUNT(*) AS total_tokens,
       COUNT(DISTINCT user_id) AS users_with_tokens,
       COUNT(DISTINCT family_id) AS families,
       SUM(revoked_at IS NULL AND expires_at > UTC_TIMESTAMP()) AS active_tokens,
       SUM(replaced_by IS NOT NULL) AS rotated_tokens
FROM tb_refresh_token;
```

未执行：任何 `INSERT` / `UPDATE` / `DELETE` / `CREATE` / `ALTER` / `DROP` / `TRUNCATE`。

---

*本报告基于 2026-11-24 的实际源码与只读数据库查询生成；部署域名、HTTPS、反向代理、邮件服务商等仓库外信息标注为 UNKNOWN。*
