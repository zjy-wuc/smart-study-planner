# Smart Study Planner V3.0 A4.0 源码与数据库检查报告

- 检查时间：2026-11-27
- 检查方式：只读检查（未修改业务代码、未执行数据库迁移、未安装依赖、未启动任何服务）
- 仓库：`d:\project\back`（git 根 `d:\project`），HEAD `3387853`
- 数据库：`ssp_v3_admin_dev`（开发库，只读查询；未输出任何密码/密钥）
- 当前基线：575 collected / 566 passed / 9 skipped / 0 failed（A3 验收后）
- 工作区现状（只读记录）：`app/api/routes/admin.py` 已修改；`app/services/admin/statistics_service.py`、`tests/test_auth_a3_statistics_acceptance.py` 未提交；A3 代码尚未 commit

---

# 第一批：AI Guard 核心源码

## 1.1 关键结论（先给答案）

| 问题 | 结论 |
| --- | --- |
| AI 请求在哪里进行准入检查 | `app/services/knowledge/ai_guard_service.py` 的 `admit_request()` |
| 每日额度与并发限制从哪里读取 | 全部来自静态 `app/config.py` 的 `settings.AI_USER_DAILY_LIMIT` / `AI_GLOBAL_DAILY_LIMIT` / `AI_USER_CONCURRENCY` / `AI_GLOBAL_CONCURRENCY`；**不读 `ai_runtime_config`** |
| `ai_guard_mutex` 在何处加锁 | `ai_guard_repository.lock_admission()`：`SELECT id FROM ai_guard_mutex WHERE id = 1 FOR UPDATE` |
| 事务在哪里开启、提交、回滚 | `admit_request()` 使用调用方传入的 Session，隐式事务；检查+插入完成后 `db.commit()`，任一异常 `db.rollback()`。结算 `_finish_request_record()` 使用独立 `SessionLocal()` 短事务 |
| 六项 AI 功能是否复用同一准入逻辑 | 是。四个笔记 AI 接口 + 练习生成 + 练习批改全部走 `admit_request()`，而后统一由 `metered_ai_stream()` 管理 SSE 生命周期 |
| `ai_runtime_config` 是否已被生产代码读取 | **否**。`app/` 目录全量检索 `ai_runtime_config` 为 0 命中；仅存在于 `Smart_Study_Planner_V3.0_A0_Migration.sql`、A0 报告和 `logs/v3_admin_dev_dump.sql` |

## 1.2 相关文件清单

| 文件 | 说明 |
| --- | --- |
| `app/services/knowledge/ai_guard_service.py` | 准入、流式计量、状态结算 |
| `app/repositories/knowledge/ai_guard_repository.py` | 互斥锁、日额度统计、有效并发统计、请求插入/结算 |
| `app/config.py` | 静态 AI 配置来源 |
| `app/core/clock.py` | 东八区业务日期 `business_today()` |
| `app/api/routes/knowledge_ai.py` | 4 个笔记 AI 入口 + `require_ai_available` 门禁 |
| `app/api/routes/ai_practice.py` | 2 个练习 AI 入口（生成/批改） |
| `app/repositories/knowledge/…` 下 | **不存在** `ai_runtime_config` 的 Repository |

`ai_runtime_config` 的 Repository / Service：**当前不存在**。`app/` 内无任何读写代码，也没有对应 Pydantic Schema。

## 1.3 `app/services/knowledge/ai_guard_service.py`（完整源码）

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

## 1.4 `app/repositories/knowledge/ai_guard_repository.py`（完整源码）

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

## 1.5 租约（lease）现状说明

- 创建：`insert_request()` 写入 `status='RUNNING'` 与 `leased_until = UTC_TIMESTAMP(6) + AI_LEASE_SECONDS`（当前 180 秒）。
- 续约：**不存在续约接口**。整个请求生命周期内不刷新 `leased_until`；靠 `AI_LEASE_SECONDS(180) > AI_MAX_STREAM_SECONDS(120)` 保证正常流不会在租约内失效（`admit_request` 中显式断言）。
- 释放：无显式释放；由 `finish_request()` 在结算时把状态改为最终状态即退出并发统计。
- 失效：`active_counts()` / A3 统计以 `leased_until > UTC_TIMESTAMP(6)` 判断，过期 RUNNING 自动不再计入并发，但**不会被改写状态**；没有任何后台清理任务（`app/jobs/plan_expiration_worker.py` 只处理计划到期，与 AI 无关）。

## 1.6 准入逻辑覆盖的六项 AI 功能

| 入口 | 文件 | operation |
| --- | --- | --- |
| `POST /notes/ai/generate` | [knowledge_ai.py](file:///d:/project/back/app/api/routes/knowledge_ai.py#L76-L109) | `GENERATE` |
| `POST /notes/{note_id}/ai/organize` | [knowledge_ai.py](file:///d:/project/back/app/api/routes/knowledge_ai.py#L112-L147) | `ORGANIZE` |
| `POST /notes/{note_id}/ai/summary` | [knowledge_ai.py](file:///d:/project/back/app/api/routes/knowledge_ai.py#L150-L185) | `SUMMARY` |
| `POST /notes/{note_id}/ai/ask` | [knowledge_ai.py](file:///d:/project/back/app/api/routes/knowledge_ai.py#L193-L240) | `ASK` |
| `POST /ai/practices/generate` | `app/api/routes/ai_practice.py` | `PRACTICE_GENERATE` |
| `POST /ai/practices/submit` | `app/api/routes/ai_practice.py` | `PRACTICE_GRADE`（仅 `needs_ai_grading` 时） |

统一门禁 `require_ai_available()`（`knowledge_ai.py:45-58`，读 `settings.AI_ENABLED` 与 `DEEPSEEK_API_KEY`），`ai_practice.py` 复用同一函数。

---

# 第二批：配置、数据库及基础设施

## 2.1 `app/config.py`（完整源码）

```python
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ==================== 数据库 ====================

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # ==================== JWT ====================

    SECRET_KEY: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)

    # ==================== 登录会话 ====================

    SESSION_IDLE_EXPIRE_DAYS: int = Field(
    default=7,
    gt=0,
)

    SESSION_ABSOLUTE_EXPIRE_DAYS: int = Field(
    default=30,
    gt=0,
)

    # 最后活跃时间写入间隔
    SESSION_ACTIVITY_INTERVAL_SECONDS: int = Field(
    default=300,
    gt=0,
)


    #Refresh Cookie

    REFRESH_COOKIE_NAME: str = "ssp_refresh"
    REFRESH_COOKIE_PATH: str = "/auth"
    REFRESH_COOKIE_SECURE: bool = True

    AUTH_ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    #  邮箱验证码 

    EMAIL_CODE_SECRET: str
    EMAIL_CODE_EXPIRE_MINUTES: int = Field(
        default=5,
        gt=0,
    )

    EMAIL_CODE_COOLDOWN_SECONDS: int = Field(
        default=60,
        gt=0,
    )

    EMAIL_CODE_MAX_ATTEMPTS: int = Field(
        default=5,
        gt=0,
    )

    EMAIL_DAILY_LIMIT: int = Field(
        default=10,
        gt=0,
    )

    EMAIL_IP_DAILY_LIMIT: int = Field(
        default=30,
        gt=0,
    )


    # ==================== 邮件服务 ====================

    MAIL_ENABLED: bool = False

    BREVO_API_KEY: str | None = None
    MAIL_FROM_EMAIL: str | None = None
    MAIL_FROM_NAME: str = "Smart Study Planner"

    MAIL_TIMEOUT_SECONDS: int = Field(default=10, gt=0)#邮件延迟

    EMAIL_GLOBAL_DAILY_LIMIT: int = Field(
        default=80,
        gt=0,
    )

    # ==================== IP 认证限流 ====================

    AUTH_IP_WINDOW_MINUTES: int = Field(#设置 IP 认证限流的统计窗口为 15 分钟
        default=15,
        gt=0,
    )

    PASSWORD_IP_MAX_ATTEMPTS: int = Field(
        default=30,
        gt=0,
    )

    EMAIL_CODE_IP_MAX_ATTEMPTS: int = Field(
        default=30,
        gt=0,
    )

    AUTH_LOCK_TIMEOUT_SECONDS: int = Field(#控制获取认证相关锁时的等待时间，默认 3 秒
        default=3,
        gt=0,
    )



        # ==================== 认证安全 ====================
    PASSWORD_MAX_FAILED_ATTEMPTS: int = Field(
        default=5,
        gt=0,
    )

    PASSWORD_LOCK_MINUTES: int = Field(
        default=15,
        gt=0,
    )

    AUTH_EVENT_RETENTION_DAYS: int = Field(
        default=30,
        gt=0,
    )

    # 头像 

    AVATAR_MAX_BYTES: int = 2 * 1024 * 1024
    AVATAR_MAX_SIZE: int = 512

    #  AI 原有配置 

    AI_ENABLED: bool = False
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-flash"

    AI_MAX_NOTE_CHARS: int = 12000
    AI_MAX_OUTPUT_CHARS: int = 12000
    AI_STREAM_CHUNK_CHARS: int = 240
    AI_MAX_OUTPUT_TOKENS: int = 3500

    AI_USER_DAILY_LIMIT: int = 10
    AI_GLOBAL_DAILY_LIMIT: int = 80

    AI_USER_CONCURRENCY: int = 1
    AI_GLOBAL_CONCURRENCY: int = 2

    AI_MAX_STREAM_SECONDS: int = 120
    AI_LEASE_SECONDS: int = 180

    # 密钥校验 

    @field_validator("SECRET_KEY", "EMAIL_CODE_SECRET")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("密钥长度不能小于32字节")

        return value

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.SECRET_KEY == self.EMAIL_CODE_SECRET:
            raise ValueError("JWT和邮箱验证码不能使用相同密钥")

        return self

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )






    #头像配置
    AVATAR_MAX_BYTES: int = Field(
        default=2 * 1024 * 1024,
        gt=0,
    )

    AVATAR_MAX_SIZE: int = Field(
        default=512,
        gt=0,
    )

    AVATAR_MAX_PIXELS: int = Field(
        default=16_000_000,
        gt=0,
    )

    AVATAR_DIR: Path = BASE_DIR / "storage" / "avatars"



    AUTH_CLEANUP_ENABLED: bool = False


settings = Settings()
```

> 说明：`AVATAR_MAX_BYTES` / `AVATAR_MAX_SIZE` 在类中重复声明（先字面量后 `Field`），后者生效，不影响运行。`DB_PASSWORD` / `SECRET_KEY` / `DEEPSEEK_API_KEY` 等敏感值未读取、未输出。

## 2.2 `app/database.py`（完整源码）

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

## 2.3 应用启动与 lifespan：`app/main.py`（完整源码）

结论：**没有配置 `lifespan`，也没有 `@app.on_event("startup"/"shutdown")`**。应用启动不做任何 Redis / AI 配置加载 / 后台任务初始化。

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.response import error,success

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.services.auth import activity_service

from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

app.include_router(api_router)


# 仅公开经过处理的头像目录
settings.AVATAR_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

app.mount(
    "/media/avatars",
    StaticFiles(
        directory=str(settings.AVATAR_DIR),
        follow_symlink=False,
    ),
    name="avatars",
)



# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
   allow_origins=settings.AUTH_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#中间件
@app.middleware("http")
async def session_activity_middleware(
    request: Request,
    call_next,#将请求传递给后续处理流程的可调用对象
):

    response = await call_next(request)#它表示将当前请求交给后续中间件、认证依赖和业务接口处理，然后等待获得响应对象

    identity = getattr(#用于动态读取对象的属性
        request.state,
        "auth_identity",
        None,
    )

    is_event_stream = response.headers.get(
        "content-type",
        "",
    ).startswith("text/event-stream")#可以匹配带有字符编码等附加参数的响应头

    if (
        identity is not None#	用户已经完成身份认证
        and 200 <= response.status_code < 300
        and not is_event_stream
        and request.headers.get(#前端将此次请求标记为用户活动
            "X-User-Activity"
        ) == "1"
        and activity_service.is_activity_path(
            request.url.path
        )
    ):

        user_id, family_id = identity

        await run_in_threadpool(#线程池
            activity_service.record_activity,
            user_id,
            family_id,
        )

    return response





# 统一处理 HTTP 异常


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):

    detail = exc.detail

    if isinstance(detail, dict):
        message = detail.get("message") or "请求失败"
    else:
        message = str(detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": message,
            "detail": jsonable_encoder(detail),
            "data": None,
        },
        headers=exc.headers,
    )



# 统一处理请求参数验证异常
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):

    errors = [
        {
            "loc": item["loc"],
            "type": item["type"],
            "msg": "Invalid input",
        }
        for item in exc.errors()
    ]

    return error(
        code=422,
        message="Request validation failed",
        data=errors,
    )

# 统一处理未捕获异常
@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request,
    exc: Exception,
):

    return error(
        code=500,
        message="服务器内部错误",
    )
```

## 2.4 后端依赖清单 `requirements.txt`（完整内容）

依赖管理只有 `requirements.txt`；**不存在** `pyproject.toml` / `poetry.lock` / `Pipfile` / `uv.lock`。

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
APScheduler==3.11.3
click==8.5.0
cryptography==50.0.2
dnspython==2.9.2
email-validator==2.4.0
fastapi==0.143.3
h11==0.16.0
httptools==0.9.0
httpx==0.28.1
idna==3.20
mysql-connector-python==26.7.0
opentelemetry-api==1.45.1
Pillow==13.0.0
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

## 2.5 Redis 检查结果

| 检查项 | 结果 |
| --- | --- |
| Redis 服务/进程 | **未安装**。无 `redis-server` / `redis-cli`；6379 端口无监听 |
| Python `redis` 客户端 | **未安装**（`importlib.util.find_spec("redis")` → `False`） |
| `requirements.txt` | 无 `redis` 依赖 |
| 代码中的 Redis 使用 | `app/` 全目录检索 `redis|Redis|REDIS` → 0 命中；仓库内仅 A0 报告文档提到 Redis |
| 连接池 / 配置项 | **均不存在**（无 host/port/db/password 配置，无 `redis.asyncio` 或 `Redis(..., connection_pool=...)`） |

结论：当前代码库对 Redis **零依赖、零接入**，A4 需同时引入依赖、连接配置与服务端。

## 2.6 Windows 开发环境的 WSL / Docker

| 检查项 | 结果 |
| --- | --- |
| WSL | `wsl.exe` 存在但为未安装状态：`wsl -l -v` 与 `wsl --version` 均退出码 1，只输出安装帮助；无任何发行版 |
| Docker | **未安装**：`docker` 命令不存在，无 `docker` / `com.docker.service` 服务 |

结论：本机目前**没有可用的 WSL 发行版，也没有 Docker**，无法通过容器方式启动 Redis。本阶段按要求未安装、未启动任何服务。

## 2.7 四张表完整 DDL（`SHOW CREATE TABLE`，来源库 `ssp_v3_admin_dev`）

### 2.7.1 `ai_runtime_config`

```sql
CREATE TABLE `ai_runtime_config` (
  `id` tinyint unsigned NOT NULL COMMENT '固定为 1（单行配置）',
  `enabled` tinyint NOT NULL DEFAULT '1' COMMENT 'AI 总开关：1 开启，0 关闭',
  `user_daily_limit` int unsigned NOT NULL DEFAULT '10' COMMENT '单用户每日 AI 请求额度',
  `global_daily_limit` int unsigned NOT NULL DEFAULT '80' COMMENT '全站每日 AI 请求额度',
  `updated_at` datetime(6) NOT NULL COMMENT '最后修改时间（UTC，应用显式写入）',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_ai_runtime_config_enabled` CHECK ((`enabled` in (0,1))),
  CONSTRAINT `chk_ai_runtime_config_global_ge_user` CHECK ((`global_daily_limit` >= `user_daily_limit`)),
  CONSTRAINT `chk_ai_runtime_config_positive` CHECK (((`user_daily_limit` > 0) and (`global_daily_limit` > 0))),
  CONSTRAINT `chk_ai_runtime_config_single_row` CHECK ((`id` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI 运行时动态配置（固定单行，id=1）'
```

### 2.7.2 `ai_guard_mutex`

```sql
CREATE TABLE `ai_guard_mutex` (
  `id` tinyint unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
```

### 2.7.3 `ai_requests`

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

### 2.7.4 管理员审计日志 `admin_audit_logs`

```sql
CREATE TABLE `admin_audit_logs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `admin_id` bigint unsigned NOT NULL COMMENT '操作管理员 users.id（不建外键，审计长期保留）',
  `action` varchar(32) NOT NULL COMMENT '操作类型：BAN_USER / UNBAN_USER / REVOKE_SESSIONS / UPDATE_AI_CONFIG',
  `target_type` varchar(32) NOT NULL COMMENT '目标类型：USER / AI_CONFIG',
  `target_id` bigint unsigned NOT NULL COMMENT '目标主键（users.id 或 ai_runtime_config.id）',
  `before_data` json NOT NULL COMMENT '变更前快照（禁止存放密码哈希/Token）',
  `after_data` json NOT NULL COMMENT '变更后快照（禁止存放密码哈希/Token）',
  `reason` varchar(200) NOT NULL COMMENT '操作原因（1~200 字符）',
  `created_at` datetime(6) NOT NULL COMMENT '操作时间（UTC，由后端显式写入）',
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_created` (`created_at`),
  KEY `idx_admin_audit_action_created` (`action`,`created_at`),
  KEY `idx_admin_audit_admin_created` (`admin_id`,`created_at`),
  KEY `idx_admin_audit_target` (`target_type`,`target_id`,`created_at`),
  CONSTRAINT `chk_admin_audit_reason_len` CHECK ((char_length(trim(`reason`)) between 1 and 200))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='管理员操作审计日志（长期保留，不级联删除）'
```

## 2.8 `ai_runtime_config` 现有记录

```text
id=1, enabled=1, user_daily_limit=10, global_daily_limit=80, updated_at=2026-11-26 16:46:31.555236
```

行数核对：`ai_runtime_config` = 1 行，`ai_guard_mutex` = 1 行（id=1，存在），`ai_requests` = 0 行，`admin_audit_logs` = 0 行。

> 注：`updated_at` 为应用显式写入的 UTC 时间（字面值不带时区）。

---

# 第三批：管理后台现有源码

## 3.1 `app/api/routes/admin.py`（完整源码）

```python
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
)

from app.services.admin import statistics_service

from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import require_admin
from app.core.auth_cookie import require_auth_request
from app.response import success

from app.schemas.admin import (
    AdminAction,
    AdminActionRequest,
    AdminUserStatus,
)

from app.services.admin import (
    user_service,
    audit_service,
)


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


UserId = Annotated[
    int,
    Path(gt=0, le=2**64 - 1),
]


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=254),
    status: AdminUserStatus | None = Query(None),
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.list_users(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
        )
    )


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: UserId,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.get_user_detail(
            db,
            user_id,
        )
    )


@router.post(
    "/users/{user_id}/ban",
    dependencies=[Depends(require_auth_request)],
)
def ban_user(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="BAN_USER",
            data=data,
        )
    )


@router.post(
    "/users/{user_id}/unban",
    dependencies=[Depends(require_auth_request)],
)
def unban_user(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="UNBAN_USER",
            data=data,
        )
    )


@router.post(
    "/users/{user_id}/revoke-sessions",
    dependencies=[Depends(require_auth_request)],
)
def revoke_user_sessions(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="REVOKE_SESSIONS",
            data=data,
        )
    )


@router.get("/audit-logs")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: AdminAction | None = Query(None),
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=audit_service.list_audit_logs(
            db,
            page=page,
            page_size=page_size,
            action=action,
        )
    )




@router.get("/dashboard")
def get_dashboard(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=statistics_service.get_dashboard(db)
    )


@router.get("/ai/statistics")
def get_ai_statistics(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=statistics_service.get_ai_statistics(db)
    )
```

## 3.2 `app/services/admin/statistics_service.py`（完整源码）

```python
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today

from app.repositories.admin import statistics_repository


AI_STATUSES = (
    "SUCCESS",
    "ERROR",
    "TIMEOUT",
    "CANCELLED",
    "BLOCKED",
    "STALE",
    "RUNNING",
    "RUNNING_EXPIRED",
    "OTHER",
)

AI_OPERATIONS = (
    "GENERATE",
    "ORGANIZE",
    "SUMMARY",
    "ASK",
    "PRACTICE_GENERATE",
    "PRACTICE_GRADE",
    "OTHER",
)


def get_dashboard(
    db: Session,
) -> dict:

    today = business_today()

    start_date = today - timedelta(days=6)

    start_at = datetime.combine(
        start_date,
        time.min,
    )

    end_exclusive = datetime.combine(
        today + timedelta(days=1),
        time.min,
    )

    # 1. 用户统计

    user_counts = statistics_repository.get_user_counts(
        db,
    )

    new_user_rows = (
        statistics_repository.get_daily_new_users(
            db,
            start_at,
            end_exclusive,
        )
    )

    # 2. 学习打卡统计

    total_checkins = (
        statistics_repository.count_checkins(db)
    )

    learning_rows = (
        statistics_repository.get_daily_learning_activity(
            db,
            start_at,
            end_exclusive,
        )
    )

    # 3. 计划统计

    raw_plan_counts = (
        statistics_repository.get_plan_status_counts(db)
    )

    plan_counts = {
        "DRAFT": raw_plan_counts.get("DRAFT", 0),
        "ACTIVE": raw_plan_counts.get("ACTIVE", 0),
        "ENDED": raw_plan_counts.get("ENDED", 0),
    }

    # 4. 笔记统计

    note_count = statistics_repository.count_notes(db)

    # 5. 今日 AI 用量

    today_ai_requests = (
        statistics_repository.count_ai_requests(
            db,
            today,
        )
    )

    # 6. 将数据库结果转换为日期映射

    new_user_map = {
        str(row["date"]): int(row["new_user_count"])
        for row in new_user_rows
    }

    learning_map = {
        str(row["date"]): row
        for row in learning_rows
    }

    # 7. 补齐连续7天数据

    daily_trend = []

    for offset in range(7):

        current_date = start_date + timedelta(
            days=offset,
        )

        date_key = current_date.isoformat()

        learning = learning_map.get(date_key, {})

        daily_trend.append({
            "date": date_key,
            "new_user_count": new_user_map.get(
                date_key, 0,
            ),
            "active_user_count": int(
                learning.get("active_user_count", 0)
            ),
            "checkin_count": int(
                learning.get("checkin_count", 0)
            ),
        })

    # 最后一项始终为今天

    today_trend = daily_trend[-1]

    # 8. 返回 Dashboard 数据

    return {
        "as_of_date": today.isoformat(),

        "overview": {
            "total_users": int(
                user_counts["total_users"]
            ),
            "enabled_users": int(
                user_counts["enabled_users"]
            ),
            "disabled_users": int(
                user_counts["disabled_users"]
            ),

            "new_users_today": (
                today_trend["new_user_count"]
            ),

            "learning_active_users_today": (
                today_trend["active_user_count"]
            ),

            "total_checkins": total_checkins,

            "today_checkins": (
                today_trend["checkin_count"]
            ),

            "total_plans": sum(
                plan_counts.values()
            ),

            "active_plans": plan_counts["ACTIVE"],

            "total_notes": note_count,

            "today_ai_requests": today_ai_requests,
        },

        "daily_trend": daily_trend,

        "plan_status_distribution": plan_counts,
    }


def get_ai_statistics(
    db: Session,
) -> dict:

    today = business_today()

    start_date = today - timedelta(days=6)

    end_exclusive = today + timedelta(days=1)

    # 1. 近7日 AI 调用趋势

    daily_rows = (
        statistics_repository.get_daily_ai_counts(
            db,
            start_date,
            end_exclusive,
        )
    )

    daily_map = {
        str(row["date"]): int(row["request_count"])
        for row in daily_rows
    }

    daily_trend = []

    for offset in range(7):

        current_date = start_date + timedelta(
            days=offset,
        )

        date_key = current_date.isoformat()

        daily_trend.append({
            "date": date_key,
            "request_count": daily_map.get(
                date_key, 0,
            ),
        })

    today_used = daily_trend[-1]["request_count"]

    # 2. 请求状态及当前有效并发

    ai_state = statistics_repository.get_ai_state(
        db,
        today,
    )

    status_counts = {
        status: 0
        for status in AI_STATUSES
    }

    for status, count in ai_state["status_counts"].items():

        key = (
            status
            if status in status_counts
            else "OTHER"
        )

        status_counts[key] += count

    # 3. AI 功能分布

    raw_operation_counts = (
        statistics_repository.get_ai_operation_counts(
            db,
            today,
        )
    )

    operation_counts = {
        operation: 0
        for operation in AI_OPERATIONS
    }

    for operation, count in raw_operation_counts.items():

        key = (
            operation
            if operation in operation_counts
            else "OTHER"
        )

        operation_counts[key] += count

    # 4. 当前生效的额度
    # A3 阶段 Guard 仍使用静态 settings。
    # A4 接入动态配置后，统一替换这里。

    global_daily_limit = settings.AI_GLOBAL_DAILY_LIMIT

    return {
        "as_of_date": today.isoformat(),

        "overview": {
            "today_used": today_used,

            "today_remaining": max(
                global_daily_limit - today_used,
                0,
            ),

            "today_success": status_counts["SUCCESS"],

            "today_failed": (
                status_counts["ERROR"]
                + status_counts["TIMEOUT"]
            ),

            "today_cancelled": (
                status_counts["CANCELLED"]
            ),

            "current_active": ai_state["active_count"],
        },

        "config": {
            "enabled": settings.AI_ENABLED,

            "user_daily_limit": (
                settings.AI_USER_DAILY_LIMIT
            ),

            "global_daily_limit": global_daily_limit,

            "user_concurrency": (
                settings.AI_USER_CONCURRENCY
            ),

            "global_concurrency": (
                settings.AI_GLOBAL_CONCURRENCY
            ),
        },

        "daily_trend": daily_trend,

        "status_distribution": status_counts,

        "operation_distribution": operation_counts,
    }
```

## 3.3 `app/repositories/admin/statistics_repository.py`（完整源码）

```python
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_counts(db: Session) -> dict:

    row = db.execute(
        text("""
            SELECT
                COUNT(*) AS total_users,
                COUNT(CASE WHEN is_active = 1 THEN 1 END)
                    AS enabled_users,
                COUNT(CASE WHEN is_active = 0 THEN 1 END)
                    AS disabled_users
            FROM users
        """)
    ).mappings().one()

    return dict(row)


def get_daily_new_users(
    db: Session,
    start_at: datetime,
    end_exclusive: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                DATE(created_at) AS date,
                COUNT(*) AS new_user_count
            FROM users
            WHERE created_at >= :start_at
              AND created_at < :end_exclusive
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """),
        {
            "start_at": start_at,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def count_checkins(db: Session) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM study_records AS sr

            JOIN daily_tasks AS dt
                ON dt.id = sr.task_id

            JOIN study_plans AS sp
                ON sp.id = dt.plan_id
               AND sp.user_id = sr.user_id

            WHERE sp.deleted_at IS NULL
        """)
    ).scalar_one()

    return int(count)


def get_daily_learning_activity(
    db: Session,
    start_at: datetime,
    end_exclusive: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                DATE(sr.recorded_at) AS date,
                COUNT(*) AS checkin_count,
                COUNT(DISTINCT sr.user_id)
                    AS active_user_count

            FROM study_records AS sr

            JOIN daily_tasks AS dt
                ON dt.id = sr.task_id

            JOIN study_plans AS sp
                ON sp.id = dt.plan_id
               AND sp.user_id = sr.user_id

            WHERE sp.deleted_at IS NULL
              AND sr.recorded_at >= :start_at
              AND sr.recorded_at < :end_exclusive

            GROUP BY DATE(sr.recorded_at)
            ORDER BY date ASC
        """),
        {
            "start_at": start_at,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def get_plan_status_counts(
    db: Session,
) -> dict:

    rows = db.execute(
        text("""
            SELECT
                status,
                COUNT(*) AS count
            FROM study_plans
            WHERE deleted_at IS NULL
            GROUP BY status
        """)
    ).mappings().all()

    return {
        row["status"]: int(row["count"])
        for row in rows
    }


def count_notes(db: Session) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM knowledge_notes
            WHERE deleted_at IS NULL
        """)
    ).scalar_one()

    return int(count)


def count_ai_requests(
    db: Session,
    request_date: date,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
        """),
        {"request_date": request_date},
    ).scalar_one()

    return int(count)


def get_daily_ai_counts(
    db: Session,
    start_date: date,
    end_exclusive: date,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                request_date AS date,
                COUNT(*) AS request_count
            FROM ai_requests
            WHERE request_date >= :start_date
              AND request_date < :end_exclusive
            GROUP BY request_date
            ORDER BY request_date ASC
        """),
        {
            "start_date": start_date,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def get_ai_state(
    db: Session,
    request_date: date,
) -> dict:

    # 使用同一个数据库 UTC 时间判断租约状态。
    now = db.execute(
        text("SELECT UTC_TIMESTAMP(6)")
    ).scalar_one()

    rows = db.execute(
        text("""
            SELECT
                CASE
                    WHEN status = 'RUNNING'
                     AND leased_until <= :now
                    THEN 'RUNNING_EXPIRED'

                    ELSE status
                END AS status_group,

                COUNT(*) AS count

            FROM ai_requests
            WHERE request_date = :request_date

            GROUP BY status_group
        """),
        {
            "request_date": request_date,
            "now": now,
        },
    ).mappings().all()

    # 有效并发不限制日期：
    # 昨天开始、今天仍在运行的请求也占用并发。
    active_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE status = 'RUNNING'
              AND leased_until > :now
        """),
        {"now": now},
    ).scalar_one()

    return {
        "status_counts": {
            row["status_group"]: int(row["count"])
            for row in rows
        },
        "active_count": int(active_count),
    }


def get_ai_operation_counts(
    db: Session,
    request_date: date,
) -> dict:

    rows = db.execute(
        text("""
            SELECT
                operation,
                COUNT(*) AS count
            FROM ai_requests
            WHERE request_date = :request_date
            GROUP BY operation
        """),
        {
            "request_date": request_date,
        },
    ).mappings().all()

    return {
        row["operation"]: int(row["count"])
        for row in rows
    }
```

## 3.4 `app/repositories/admin/audit_repository.py`（完整源码）

```python
import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_audit_log(
    db: Session,
    *,
    admin_id: int,
    action: str,
    target_type: str,
    target_id: int,
    before_data: dict,
    after_data: dict,
    reason: str,
    now: datetime,
) -> None:
    db.execute(
        text("""
            INSERT INTO admin_audit_logs (
                admin_id,
                action,
                target_type,
                target_id,
                before_data,
                after_data,
                reason,
                created_at
            )
            VALUES (
                :admin_id,
                :action,
                :target_type,
                :target_id,
                :before_data,
                :after_data,
                :reason,
                :now
            )
        """),
        {
            "admin_id": admin_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "before_data": json.dumps(
                before_data, ensure_ascii=False
            ),
            "after_data": json.dumps(
                after_data, ensure_ascii=False
            ),
            "reason": reason,
            "now": now,
        },
    )


def _filter_sql(action: str | None) -> tuple[str, dict]:
    if action is None:
        return "", {}

    return "WHERE action = :action", {"action": action}


def count_logs(
    db: Session,
    *,
    action: str | None,
) -> int:

    where_sql, params = _filter_sql(action)

    result = db.execute(
        text(
            "SELECT COUNT(*) FROM admin_audit_logs "
            f"{where_sql}"
        ),
        params,
    ).scalar_one()

    return int(result)


def list_logs(
    db: Session,
    *,
    action: str | None,
    limit: int,
    offset: int,
) -> list[dict]:

    where_sql, params = _filter_sql(action)

    rows = db.execute(
        text(f"""
            SELECT
                a.id,
                a.admin_id,
                u.username AS admin_username,
                a.action,
                a.target_type,
                a.target_id,
                a.before_data,
                a.after_data,
                a.reason,
                a.created_at
            FROM admin_audit_logs AS a
            LEFT JOIN users AS u
                ON u.id = a.admin_id
            {where_sql}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            **params,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]
```

## 3.5 `app/schemas/admin.py`（完整源码）

```python
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


AdminAction = Literal[
    "BAN_USER",
    "UNBAN_USER",
    "REVOKE_SESSIONS",
    "UPDATE_AI_CONFIG",
]

AdminUserAction = Literal[
    "BAN_USER",
    "UNBAN_USER",
    "REVOKE_SESSIONS",
]

AdminUserStatus = Literal["ACTIVE", "DISABLED"]

AdminTargetType = Literal["USER", "AI_CONFIG"]

AdminReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]


class AdminActionRequest(BaseModel):
    reason: AdminReason
```

> 说明：`AdminAction` 已包含 `UPDATE_AI_CONFIG`、`AdminTargetType` 已包含 `AI_CONFIG`，但**目前没有任何路由/服务写入该 action**；`AdminActionRequest` 只有 `reason`，没有 AI 配置字段。

## 3.6 管理员认证依赖：`app/core/deps.py`（完整源码）

```python
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.core.security import (
    decode_access_token_detailed,
)

from app.database import SessionLocal

from app.services.auth import session_service


from fastapi import Depends, Request, HTTPException

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def authenticate_access(
    token: str | None,
) -> dict:
    """验证 Access Token 和对应登录会话"""

    if not token:
        session_service.reject_auth(
            "INVALID_TOKEN",
            "缺少 Access Token",
        )

    payload, error_code = (
        decode_access_token_detailed(token)
    )

    if payload is None:

        if error_code == "ACCESS_EXPIRED":

            session_service.reject_auth(
                "ACCESS_EXPIRED",
                "Access Token 已过期",
            )

        session_service.reject_auth(
            error_code or "INVALID_TOKEN",
            "Access Token 无效",
        )

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    # 使用独立的短生命周期数据库 Session。
    # 避免认证查询提前开启业务事务。
    with SessionLocal() as db:

        return session_service.get_active_session(
            db,
            user_id=user_id,
            family_id=family_id,
        )


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> dict:

    user = authenticate_access(token)

    # 保存身份，用于请求成功后的活跃时间更新，中间件要用
    request.state.auth_identity = (
        user["id"],
        user["family_id"],
    )

    return user




def require_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """校验当前用户是否具有管理员权限"""

    if user.get("role") != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_REQUIRED",
                "message": "需要管理员权限",
            },
        )

    return user
```

## 3.7 管理端业务事务实现：`app/services/admin/user_service.py`（完整源码，事务范例）

```python
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now

from app.repositories.admin import (
    user_repository as admin_user_repository,
    audit_repository,
)

from app.repositories.auth import (
    user_repository as auth_user_repository,
    session_repository,
)

from app.schemas.admin import (
    AdminUserAction,
    AdminUserStatus,
    AdminActionRequest,
)

from app.services.auth import session_service


def _reject(
    status_code: int,
    code: str,
    message: str,
) -> None:

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def _mask_email(email: str) -> str:

    local, domain = email.rsplit("@", 1)

    return f"{local[:1]}***@{domain}"


def _count_active_sessions(
    db: Session,
    user_id: int,
    now: datetime,
) -> int:

    idle_cutoff = now - timedelta(
        days=settings.SESSION_IDLE_EXPIRE_DAYS,
    )

    return session_repository.count_active_sessions(
        db,
        user_id=user_id,
        now=now,
        idle_cutoff=idle_cutoff,
    )


def _format_user(
    user: dict,
    *,
    mask_email: bool,
) -> dict:

    result = dict(user)

    result["is_active"] = bool(
        result["is_active"]
    )

    if mask_email:
        result["email"] = _mask_email(
            result["email"]
        )

    # 原有用户业务时间采用北京时间
    business_tz = timezone(timedelta(hours=8))

    for field in ("created_at", "updated_at"):
        value = result.get(field)

        if value is not None and value.tzinfo is None:
            result[field] = value.replace(
                tzinfo=business_tz,
            )

    # 邮箱验证时间采用 UTC
    verified_at = result.get("email_verified_at")

    if (
        verified_at is not None
        and verified_at.tzinfo is None
    ):
        result["email_verified_at"] = (
            verified_at.replace(tzinfo=timezone.utc)
        )

    return result


def list_users(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str,
    status: AdminUserStatus | None,
) -> dict:

    keyword = keyword.strip()

    is_active = None

    if status == "ACTIVE":
        is_active = 1

    elif status == "DISABLED":
        is_active = 0

    total = admin_user_repository.count_users(
        db,
        keyword=keyword,
        is_active=is_active,
    )

    users = admin_user_repository.list_users(
        db,
        keyword=keyword,
        is_active=is_active,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return {
        "items": [
            _format_user(
                user,
                mask_email=True,
            )
            for user in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_user_detail(
    db: Session,
    user_id: int,
) -> dict:

    user = admin_user_repository.find_user_detail(
        db,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="用户不存在",
        )

    statistics = (
        admin_user_repository.get_user_statistics(
            db,
            user_id,
        )
    )

    statistics["active_session_count"] = (
        _count_active_sessions(
            db,
            user_id,
            utc_db_now(),
        )
    )

    return {
        **_format_user(
            user,
            mask_email=False,
        ),
        "statistics": statistics,
    }


def change_user_state(
    db: Session,
    *,
    admin: dict,
    user_id: int,
    action: AdminUserAction,
    data: AdminActionRequest,
) -> dict:

    admin_id = admin["id"]
    family_id = admin["family_id"]

    with db.begin():

        # 1. 按固定顺序锁定两名用户
        locked_users = {}

        for uid in sorted({admin_id, user_id}):

            locked_users[uid] = (
                auth_user_repository.find_by_id(
                    db,
                    uid,
                    for_update=True,
                )
            )

        operator = locked_users[admin_id]
        target = locked_users[user_id]

        # 2. 事务内重新校验操作者
        if operator is None:
            _reject(
                401,
                "SESSION_REVOKED",
                "登录身份已失效",
            )

        if not operator["is_active"]:
            _reject(
                403,
                "ACCOUNT_DISABLED",
                "账户已被禁用",
            )

        if operator["role"] != "ADMIN":
            _reject(
                403,
                "ADMIN_REQUIRED",
                "需要管理员权限",
            )

        # 3. 锁定并校验管理员当前会话
        current_session = (
            session_repository.find_session(
                db,
                admin_id,
                family_id,
                for_update=True,
            )
        )

        now = utc_db_now()

        session_service.require_active_session(
            current_session,
            now,
        )

        # 4. 校验目标用户
        if target is None:
            _reject(
                404,
                "USER_NOT_FOUND",
                "用户不存在",
            )

        if target["role"] == "ADMIN":
            _reject(
                403,
                "ADMIN_TARGET_FORBIDDEN",
                "不允许操作管理员账户",
            )

        is_active = bool(target["is_active"])

        # 5. 检查账户状态冲突
        if action == "BAN_USER" and not is_active:
            _reject(
                409,
                "USER_ALREADY_DISABLED",
                "该用户已经被封禁",
            )

        if action == "UNBAN_USER" and is_active:
            _reject(
                409,
                "USER_ALREADY_ACTIVE",
                "该用户当前未被封禁",
            )

        active_session_count = _count_active_sessions(
            db,
            user_id,
            now,
        )

        before_data = {
            "is_active": is_active,
            "active_session_count": active_session_count,
        }

        revoked_session_count = 0
        revoked_token_count = 0

        # 6. 执行账户状态变更
        if action == "BAN_USER":

            admin_user_repository.update_user_active(
                db,
                user_id=user_id,
                is_active=False,
            )

            is_active = False

        elif action == "UNBAN_USER":

            admin_user_repository.update_user_active(
                db,
                user_id=user_id,
                is_active=True,
            )

            is_active = True

        # 7. 封禁及强制下线撤销全部凭证
        if action in (
            "BAN_USER",
            "REVOKE_SESSIONS",
        ):

            (
                revoked_session_count,
                revoked_token_count,
            ) = (
                session_service
                .revoke_user_sessions_with_counts(
                    db,
                    user_id=user_id,
                    now=now,
                    reason="ADMIN",
                    exclude_family_id=None,
                )
            )

            active_session_count = 0

        after_data = {
            "is_active": is_active,
            "active_session_count": active_session_count,
            "revoked_session_count": revoked_session_count,
            "revoked_token_count": revoked_token_count,
        }

        # 8. 无实际变更的强制下线不记录审计
        changed = (
            action != "REVOKE_SESSIONS"
            or revoked_session_count > 0
            or revoked_token_count > 0
        )

        # 9. 审计与账户状态变更同事务
        if changed:

            audit_repository.insert_audit_log(
                db,
                admin_id=admin_id,
                action=action,
                target_type="USER",
                target_id=user_id,
                before_data=before_data,
                after_data=after_data,
                reason=data.reason,
                now=now,
            )

    # 离开 with db.begin() 后已完成提交
    return {
        "user_id": user_id,
        "is_active": is_active,
        "revoked_session_count": revoked_session_count,
        "revoked_token_count": revoked_token_count,
        "changed": changed,
    }
```

## 3.8 `app/services/admin/audit_service.py`（完整源码）

```python
import json
from datetime import timezone

from sqlalchemy.orm import Session

from app.repositories.admin import audit_repository
from app.schemas.admin import AdminAction


def list_audit_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    action: AdminAction | None,
) -> dict:

    total = audit_repository.count_logs(
        db,
        action=action,
    )

    logs = audit_repository.list_logs(
        db,
        action=action,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    for log in logs:

        for field in ("before_data", "after_data"):

            if isinstance(log[field], str):
                log[field] = json.loads(
                    log[field]
                )

        created_at = log["created_at"]

        if created_at.tzinfo is None:

            log["created_at"] = (
                created_at.replace(
                    tzinfo=timezone.utc,
                )
            )

    return {
        "items": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

## 3.9 管理后台重点问题回答

1. **A3 的 AI 统计接口 config 字段从哪里获取？**
   `statistics_service.get_ai_statistics()` 中直接读静态 `settings.AI_ENABLED` / `AI_USER_DAILY_LIMIT` / `AI_GLOBAL_DAILY_LIMIT` / `AI_USER_CONCURRENCY` / `AI_GLOBAL_CONCURRENCY`（`statistics_service.py:285-332`），代码注释已标注“A4 接入动态配置后统一替换这里”。

2. **是否与 AI Guard 使用同一配置来源？**
   是同一份静态 `settings`，因此当前自然一致；但 A4 一旦只改 Guard 不改统计，二者会不一致。

3. **现有审计模块是否支持 AI 配置变更？**
   存储层和类型层已预留：`admin_audit_logs` 的 `action` 注释含 `UPDATE_AI_CONFIG`、`target_type` 含 `AI_CONFIG`；`schemas/admin.py` 的 `AdminAction` 含 `"UPDATE_AI_CONFIG"`。但**没有对应路由、Service、请求 Schema（缺配置字段）与写入调用**，属于“只定义未实现”。

4. **管理员认证依赖与业务 Service 如何管理数据库事务？**
   - `require_admin` 只做 Token/Session 校验，认证查询使用**独立短生命周期 `SessionLocal()`**（`deps.py:55-61`），不占用路由的 `get_db` 会话，也不提前开启业务事务。
   - 业务写操作在 `user_service.change_user_state()` 中用 `with db.begin()` 显式开启事务，按 `sorted({admin_id, user_id})` 固定顺序 `SELECT ... FOR UPDATE` 锁用户，再锁管理员当前会话；事务内复核操作者/会话权限，修改状态、撤销凭证、插入审计在同一事务提交；异常自动回滚。
   - 验证码/Cookie 类写接口额外挂 `Depends(require_auth_request)` 做 CSRF 校验。
   - 只读接口（列表、详情、审计查询、统计）不显式开事务，依赖 Session 隐式只读事务，结束时 `db.close()`。

---

# 第四批：测试情况

## 4.1 与 AI / 审计 / 统计相关的测试文件

| 测试文件 | 覆盖范围 |
| --- | --- |
| `tests/test_ai_a3_structure.py`（11 项） | 笔记 AI 结构：generate/summary/organize 正常流、`NOTE_CHANGED`→STALE、Guard 的 STALE/SUCCESS/TIMEOUT 结算、敏感输入、Prompt 结构 |
| `tests/test_ai_a4_qa.py`（26 项） | 问答 QA：输入/历史长度/历史不被当作系统指令、`done`/`blocked`/`error` 帧、Guard 无 `done` 视为 ERROR、STALE 映射、客户端取消落库 CANCELLED、`admit_request` 写入 operation、准入失败回滚、空笔记 422 |
| `tests/test_ai_a5_generate.py`（11 项） | 练习生成：题目解析/数量/选项/去重/短笔记、答案不泄漏、流式不泄漏 delta、练习票据 24h 过期、篡改票据拒绝 |
| `tests/test_ai_a5_grade.py`（13 项） | 练习批改：跳过答案归一化、未知题目/重复答案拒绝、锁定提交、禁止换答案、越权、部分得分、AI 失败不落库、全部跳过不调用 AI |
| `tests/test_knowledge_ai.py`（10 项） | 笔记总结结构校验、快照读取、凭据拒绝、流式成功/非法输出/blocked、DeepSeek SSE 解析与内容审核识别 |
| `tests/test_auth_a3_statistics_acceptance.py`（19 项） | A3 验收：两接口 ADMIN 权限、空库/连续 7 天趋势、用户/计划/笔记统计、同日多次打卡活跃去重、软删除口径、北京时间自然日边界、所有准入状态计入额度与六类功能、过期 vs 有效 RUNNING 与跨日并发、config 与剩余额度、审计 `admin_username` 分页与 action 筛选 |
| `tests/test_auth_a2_admin_acceptance.py`（约 30 项） | 管理员权限/CSRF、用户列表与详情、封禁/解封/强制下线、无变更不写审计、审计失败整体回滚、并发（封禁 vs 登录、下线 vs 刷新、双管理员同目标、操作者被降权/会话被撤销）、审计日志快照/UTC/筛选/分页/原因校验 |
| `tests/test_auth_a1_3_acceptance.py` | `test_ai_guard_tables_untouched`：认证操作不得触碰 `ai_guard_mutex` |
| `tests/test_auth_a1_1_acceptance.py` | 断言 `settings` 具备 `AI_USER_DAILY_LIMIT` / `AI_GLOBAL_DAILY_LIMIT` / `AI_LEASE_SECONDS` 等配置项 |
| `tests/test_auth_a2_3_avatar_profile_cleanup_acceptance.py` | `test_ai_guard_and_business_untouched`：清理任务不得触碰 AI/knowledge 代码 |

## 4.2 覆盖缺口（重要）

以下方向**没有专项测试**（只能在 A3 统计测试中通过手工插入数据间接验证展示逻辑）：

- 用户每日额度真正触顶 → `AI_USER_DAILY_LIMIT` 429
- 全站每日额度触顶 → `AI_GLOBAL_DAILY_LIMIT` 429
- 用户并发触顶 → `AI_USER_BUSY`
- 全站并发触顶 → `AI_GLOBAL_BUSY`
- 练习生成剩余额度不足 → `AI_PRACTICE_QUOTA_INSUFFICIENT` / `AI_PRACTICE_GLOBAL_QUOTA_INSUFFICIENT`
- 租约过期后重新准入（并发名额回收）
- 跨日额度重置（`request_date` 切换）
- 多实例/多进程并发准入（现有并发测试均针对认证与管理员模块，AI Guard 只有 mock 单元测试）

`test_ai_a4_qa.py` 中 `admit_request` 的测试通过 monkeypatch 替换 `lock_admission` / `daily_counts` / `active_counts` / `insert_request`，不验证真实 MySQL 锁行为。

---

# 最终补充

## 1. 当前 AI Guard 完整请求调用链

```text
HTTP POST（6 个入口之一，需登录）
  → require_ai_available()              # settings.AI_ENABLED + DEEPSEEK_API_KEY，失败 503，不占额度
  → 输入/快照校验（部分入口先 prepare_note_snapshot，finally db.rollback()）
  → admit_request(db, user_id, note_id, operation)
        ├─ 校验 operation 白名单
        ├─ 校验 AI_LEASE_SECONDS > AI_MAX_STREAM_SECONDS
        ├─ lock_admission(db)                   # SELECT ... FOR UPDATE ai_guard_mutex(id=1)
        ├─ daily_counts(today, user_id)         # 全站/用户当日 COUNT
        ├─ [PRACTICE_GENERATE] 预留 2 次额度检查
        ├─ 全站/用户日额度检查 → 429
        ├─ active_counts(user_id)               # RUNNING 且 leased_until > UTC_TIMESTAMP(6)
        ├─ 全站/用户并发检查 → 429
        ├─ insert_request(... status='RUNNING', leased_until=now+180s)
        └─ db.commit()                          # 锁在调用模型前释放
  → stream_response(metered_ai_stream(admission, event_stream))
        ├─ asyncio.timeout(120s)
        ├─ done    → _finish_request_record(SUCCESS) → 转发 done
        ├─ blocked → BLOCKED
        ├─ error   → STALE / ERROR
        ├─ 无终止帧 → ERROR + AI_STREAM_INTERRUPTED
        ├─ 超时    → TIMEOUT + AI_TOTAL_TIMEOUT
        ├─ 取消    → CANCELLED（finally 兜底落库）
        └─ 异常    → ERROR + AI_INTERNAL_ERROR
  → 结算使用独立 SessionLocal 短事务，UPDATE ... WHERE status='RUNNING'
```

## 2. 当前 AI 配置读取链路

```text
.env / 环境变量
  → pydantic-settings Settings（app/config.py，进程启动时实例化单例 settings）
  → settings.AI_ENABLED / AI_USER_DAILY_LIMIT / AI_GLOBAL_DAILY_LIMIT
     / AI_USER_CONCURRENCY / AI_GLOBAL_CONCURRENCY / AI_LEASE_SECONDS / AI_MAX_STREAM_SECONDS
  → 使用点：
       app/api/routes/knowledge_ai.py:48          AI_ENABLED（门禁，ai_practice 复用）
       app/services/knowledge/ai_guard_service.py:84,103  AI_USER_DAILY_LIMIT
       app/services/knowledge/ai_guard_service.py:90,97   AI_GLOBAL_DAILY_LIMIT
       app/services/knowledge/ai_guard_service.py:114,120 AI_USER_CONCURRENCY / AI_GLOBAL_CONCURRENCY
       app/services/admin/statistics_service.py:289,317-331 统计展示用 5 项配置
```

`ai_runtime_config` 表**不在任何链路中**。A4 需要在上述 6 处读取点之间插入统一的动态配置读取层（含缓存/失效策略），并让统计接口与准入使用同一来源。

## 3. 数据库事务与加锁顺序

**AI 准入（关键路径）**

1. 事务：路由依赖 `get_db` 的 Session 隐式事务；`admit_request` 内 `try/except` + `db.commit()` / `db.rollback()`。
2. 加锁顺序：`ai_guard_mutex(id=1)` 单行 `FOR UPDATE` → 两次 `COUNT`（`request_date`、`user_id+request_date`）→ `COUNT` 有效并发 → `INSERT ai_requests`。
3. 全局串行化依赖唯一互斥行；不存在多把锁的交叉等待，因此无经典死锁路径。代价是所有 AI 准入串行，锁持有时间仅限本轮查询+插入。
4. 模型调用期间不持有任何数据库行锁（commit 已先行）。
5. 结算为独立短事务：`UPDATE ai_requests SET status..., finished_at=UTC_TIMESTAMP(6) WHERE request_id=? AND status='RUNNING'`；不获取互斥锁，因此不阻塞准入。重复结算因 `status='RUNNING'` 条件而幂等。

**管理员写操作**

1. `with db.begin()` 显式事务。
2. 锁顺序：`users`（`sorted({admin_id, user_id})` 升序，`FOR UPDATE`）→ 管理员 `user_sessions` 当前 family 行 `FOR UPDATE` → 业务更新 → 审计 `INSERT` → 提交。
3. 审计与业务同事务，审计失败整体回滚（有专项测试覆盖）。

**只读接口**（统计、审计列表、AI 统计）：无显式事务、无加锁；`get_ai_state` 用数据库 `UTC_TIMESTAMP(6)` 保证租约判断与写入时钟一致。

## 4. Redis 环境检查结果（复述）

- 服务端：未安装，6379 未监听。
- Python 客户端：未安装，`requirements` 无 `redis`。
- 代码：`app/` 无任何 Redis 引用，无连接池/配置。
- WSL：未安装（无发行版，`wsl --version` 失败）。
- Docker：未安装（无命令、无服务）。
- 本次未安装、未启动任何服务。

## 5. A4 接入可能涉及的文件清单

| 类型 | 文件 | 预期改动方向 |
| --- | --- | --- |
| 新增 | `app/repositories/admin/ai_config_repository.py`（或 knowledge 下） | `SELECT ... FOR UPDATE` 单行读取、`UPDATE` 配置、与审计同事务 |
| 新增 | `app/services/admin/ai_config_service.py` | 更新配置、校验、审计快照、并发控制 |
| 新增 | `app/schemas/admin.py` 内新增请求模型 | `enabled` / `user_daily_limit` / `global_daily_limit` + `reason` |
| 修改 | `app/api/routes/admin.py` | `GET/PUT /admin/ai/config`（写接口需 `require_auth_request`） |
| 修改 | `app/services/knowledge/ai_guard_service.py` | `admit_request` 改读动态配置（替换 4 处 `settings.AI_*`） |
| 修改 | `app/api/routes/knowledge_ai.py` | `require_ai_available` 改读动态 `enabled` |
| 修改 | `app/services/admin/statistics_service.py` | `config` 字段与 `today_remaining` 改读同一动态配置 |
| 新增 | `app/core/redis.py`（建议） | 连接池、健康检查、优雅关闭 |
| 修改 | `app/main.py` | 增加 `lifespan`：初始化/关闭 Redis 连接池（目前无 lifespan） |
| 修改 | `app/config.py` | 新增 `REDIS_*` 配置项 |
| 修改 | `requirements.txt` | 新增 `redis` 依赖 |
| 新增 | AI 频率限制模块 | 例如 `app/services/knowledge/ai_rate_limit.py`，在 `admit_request` 之前/内执行 |
| 修改 | `app/database.py` | 一般无需改动（除非调整隔离级别） |
| 测试 | `tests/` 新增 A4 专项 | 额度/并发/租约/跨日/多实例/配置变更审计/限流 |
| 文档 | `Smart_Study_Planner_V3.0_A0_Migration.sql` | 表已建，A4 无需再迁移（如无新表） |

## 6. 已发现的风险与需要进一步确认的问题

1. **配置读取点分散**：`settings.AI_*` 在 Guard（4 处）、门禁（1 处）、统计（5 处）共 10 个使用点。若只改 Guard，统计页会展示旧值；建议统一封装 `get_ai_runtime_config(db)` 并在请求内复用。
2. **`ai_runtime_config` 无任何读写代码**：首次接入需处理“行缺失”与缓存失效；表约束 `id=1`、`global_daily_limit >= user_daily_limit`、`>0` 需在 Service 层同步校验，避免直接抛数据库异常。
3. **动态 `enabled` 的生效时延**：若加缓存，关闭 AI 后可能有延迟；若不缓存，每个 AI 请求多一次查询（可接受，但需明确）。同时 `require_ai_available` 目前是同步函数且无 `db` 参数，接入动态配置需调整签名与全部调用点（含 `ai_practice.py`）。
4. **Redis 不可用会否阻断 AI**：需确认策略（fail-open 放行 / fail-closed 429）。当前系统无 Redis，A4 上线前必须有明确降级方案，否则 AI 全挂。
5. **限流与额度的顺序**：Redis 限流应在 `insert_request` 之前执行，否则被限流的请求仍会消耗 MySQL 每日额度（当前“成功准入即扣额度、失败不退”）。
6. **租约无续约、无清理**：长流仅靠 180s 租约；若未来放宽 `AI_MAX_STREAM_SECONDS`，必须同步租约。过期 RUNNING 不会被归档，统计中显示为 `RUNNING_EXPIRED`，会长期累积。
7. **审计未实现**：`UPDATE_AI_CONFIG` / `AI_CONFIG` 仅在类型与表注释中预留；`AdminActionRequest` 不含配置字段，A4 需新增专用 Schema，且审计应与配置更新同事务、并 `FOR UPDATE` 单行以保证并发安全（参考 `change_user_state` 模式）。
8. **统计口径**：`get_dashboard` 的 `today_ai_requests` 与 AI 统计的 `today_used` 均为 `COUNT(*)`（含 BLOCKED 等所有状态），A4 若调整额度读取，需保持该口径不变，否则前端展示会跳变。
9. **管理端 `action` 筛选**：`AdminAction` Literal 已含 `UPDATE_AI_CONFIG`，接入后 `GET /admin/audit-logs?action=UPDATE_AI_CONFIG` 可直接工作，无需改查询层。
10. **多实例**：MySQL 互斥行可跨实例串行准入；但 Redis 限流如使用固定窗口需注意多实例时钟一致（建议使用 Redis 服务端时间或 `INCR`+`EXPIRE` 原子脚本）。现有测试无多进程覆盖，建议 A4 增加。
11. **工作区未提交**：A3 的 `admin.py`、`statistics_service.py`、A3 测试尚未 commit；A4 改动前建议先固化 A3 基线，避免混入同一提交。
12. **`config.py` 重复字段**：`AVATAR_MAX_BYTES` / `AVATAR_MAX_SIZE` 重复定义（后者覆盖），与 A4 无关但修改 `config.py` 时需注意不要误删。
13. **`ai_requests` 无 `operation`/`status` 约束**：白名单仅在应用层校验；`statistics_service` 已用 `OTHER` 兜底，但脏数据无法被数据库拒绝。
14. **待确认**：A4 是否需要“配置变更立即生效”的强一致（跨实例）；Redis 限流粒度（用户/IP/接口/分钟窗口）；限流命中是否要写审计或 `ai_requests`；管理员是否可查看 `ai_runtime_config.updated_at` 与操作人。

---

（本报告仅做检查，未修改任何业务代码、数据库结构或依赖。）